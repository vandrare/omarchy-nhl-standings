#!/usr/bin/env python3
"""NHL result emails: keyring credentials, persisted settings, and a timer worker."""
from collections import Counter
from contextlib import contextmanager
import datetime as dt
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
import fcntl
import json
import os
from pathlib import Path
import re
import smtplib
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

from nhl import BASE, label, next_game

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "nhl-standings"
STATE = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "nhl-standings"
DEFAULTS = {"sender": "", "displayName": "The Rathole", "recipient": "", "team": "", "enabled": False, "scope": ""}


class UserError(Exception):
    pass


def load_json(path, default):
    if not path.exists():
        return default.copy()
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (OSError, ValueError):
        raise UserError("Could not read saved notification settings or history. No email was sent.")


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
        json.dump(value, file)
        file.write("\n")
        temp = file.name
    try:
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


@contextmanager
def locked():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(STATE / "notifications.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "w") as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        yield


def settings():
    """Normalize legacy settings; migration is committed under the worker lock."""
    config = load_json(CONFIG / "notifications.json", DEFAULTS)
    if "subscriptions" not in config:
        config = {"sender": config.get("sender", ""), "displayName": config.get("displayName", "The Rathole"),
                  "subscriptions": [{"id": "legacy", **{k: config.get(k, DEFAULTS[k]) for k in ("recipient", "team", "enabled", "scope")}}]
                  if config.get("recipient") or config.get("team") else []}
    return config


def history_for(config):
    history = load_json(STATE / "notifications.json", {})
    if "subscriptions" not in history:
        history = {"subscriptions": {"legacy": history} if history else {}}
    return history


def migrate():
    with locked():
        config = settings()
        history = history_for(config)
        for path in (CONFIG / "notifications.json", STATE / "notifications.json"):
            if path.exists() and not path.with_suffix(".pre-multiple.json").exists():
                atomic_json(path.with_suffix(".pre-multiple.json"), load_json(path, {}))
        atomic_json(STATE / "notifications.json", history)
        atomic_json(CONFIG / "notifications.json", config)


def secret(sender, password=None):
    args = ["application", "local.nhl-standings", "account", sender]
    command = ["secret-tool", "lookup", *args] if password is None else [
        "secret-tool", "store", "--label=NHL standings email", *args]
    try:
        result = subprocess.run(command, input=None if password is None else password,
                                text=True, capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        raise UserError("The system keyring is unavailable or locked. Unlock it and try again.")
    if result.returncode:
        if password is None and result.returncode == 1 and not result.stderr.strip():
            return ""
        raise UserError("The system keyring could not be accessed. Unlock it and try again.")
    return result.stdout.strip() if password is None else ""


def public_settings():
    config = settings()
    message = ""
    try:
        has_password = bool(config["sender"] and secret(config["sender"]))
    except UserError as error:
        has_password = False
        message = str(error)
    history = history_for(config)["subscriptions"]
    subscriptions = []
    for sub in config["subscriptions"]:
        state = history.get(sub["id"], {})
        subscriptions.append({k: sub[k] for k in ("id", "recipient", "team", "enabled")} | {
            "lastCheck": state.get("lastCheck", 0), "lastSent": state.get("lastSent", 0),
            "status": state.get("status", "Notifications are off."), "workerError": state.get("error", "")})
    return {"sender": config["sender"], "displayName": config["displayName"], "subscriptions": subscriptions,
            "hasPassword": has_password, "keyringError": message}


def validate(request):
    config = {k: str(request.get(k, DEFAULTS[k])).strip() for k in ("sender", "displayName")}
    def email_valid(email):
        return len(email) <= 254 and re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+", email)
    if config["sender"] and not email_valid(config["sender"]):
        raise UserError("Enter a valid sender email address.")
    if any(c in config["displayName"] for c in "\r\n") or len(config["displayName"]) > 100:
        raise UserError("Enter a sender display name of at most 100 characters.")
    config["displayName"] = config["displayName"] or "The Rathole"
    rows = request.get("subscriptions", [{"id": "legacy", **request}])
    if not isinstance(rows, list):
        raise UserError("Invalid subscription list.")
    config["subscriptions"] = []
    ids, pairs = set(), set()
    for row in rows:
        sub = {k: str(row.get(k, "")).strip() for k in ("id", "recipient", "team")}
        sub["id"] = sub["id"] or uuid.uuid4().hex
        sub["enabled"] = row.get("enabled") is True
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", sub["id"]) or sub["id"] in ids:
            raise UserError("Invalid or duplicate subscription identifier.")
        ids.add(sub["id"])
        if sub["recipient"] and not email_valid(sub["recipient"]):
            raise UserError("Enter a valid recipient email address.")
        if sub["team"] and not re.fullmatch(r"[A-Z]{2,3}", sub["team"]):
            raise UserError("Choose a team from the list.")
        pair = (sub["recipient"].lower(), sub["team"])
        if all(pair) and pair in pairs:
            raise UserError("This recipient already has a subscription for that team.")
        pairs.add(pair)
        if sub["enabled"] and not (config["sender"] and sub["recipient"] and sub["team"]):
            raise UserError("Add a sender, recipient, and team before enabling notifications.")
        config["subscriptions"].append(sub)
    return config


def fetch(endpoint):
    request = urllib.request.Request(BASE + endpoint, headers={"User-Agent": "Omarchy-NHL-Standings/1.1"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)
    except Exception:
        raise UserError("The NHL feed is unavailable. The next scheduled check will retry.")


def season(team):
    data = fetch("club-schedule-season/" + team + "/now")
    if not isinstance(data.get("games"), list):
        raise UserError("The NHL schedule is unavailable. Try again shortly.")
    return data["games"]


def completed(game, team):
    if game.get("gameState") not in ("FINAL", "OFF") or game.get("gameScheduleState") in ("PPD", "CNCL"):
        return False
    home, away = game.get("homeTeam", {}), game.get("awayTeam", {})
    return team in (home.get("abbrev"), away.get("abbrev")) and all(
        isinstance(t.get("score"), int) for t in (home, away))


def save_settings(request):
    config = validate(request)
    password = str(request.get("password", "")).replace(" ", "").strip()
    if password and (len(password) != 16 or not password.isascii() or not password.isalnum()):
        raise UserError("Use Google's 16-character app password, not your normal Gmail password.")
    if password and not config["sender"]:
        raise UserError("Enter the sender email before saving an app password.")
    with locked():
        previous = settings()
        history = history_for(previous)
        old = {sub["id"]: sub for sub in previous["subscriptions"]}
        new_history = {}
        schedules = {}
        if any(sub["enabled"] for sub in config["subscriptions"]):
            if not password and not secret(config["sender"]):
                raise UserError("Save a Gmail app password before enabling notifications.")
        for sub in config["subscriptions"]:
            prior = old.get(sub["id"], {})
            state = history["subscriptions"].get(sub["id"], {}).copy()
            changed = not prior.get("enabled") or previous["sender"] != config["sender"] or any(prior.get(k) != sub[k] for k in ("recipient", "team"))
            sub["scope"] = prior.get("scope", "")
            if sub["enabled"] and changed:
                if sub["team"] not in schedules:
                    schedules[sub["team"]] = season(sub["team"])
                sub["scope"] = uuid.uuid4().hex
                state = {"scope": sub["scope"], "seen": [str(g["id"]) for g in schedules[sub["team"]] if completed(g, sub["team"])],
                         "delivery": {}, "status": "Watching for the next completed game.", "error": ""}
            elif not sub["enabled"]:
                state.update(status="Notifications are off.", error="")
            new_history[sub["id"]] = state
        if password:
            secret(config["sender"], password)
        atomic_json(STATE / "notifications.json", {"subscriptions": new_history})
        atomic_json(CONFIG / "notifications.json", config)
    return {"ok": True, "message": "Settings saved. Each enabled subscription watches for future results.", "settings": public_settings()}


def team_name(team):
    return " ".join(filter(None, [label(team.get("placeName")), label(team.get("commonName"))])) or team.get("abbrev", "Team")


def recap(game, team, landing=None, upcoming=None):
    home = game["homeTeam"]
    away = game["awayTeam"]
    ours, opponent = (home, away) if home["abbrev"] == team else (away, home)
    own_score, opp_score = ours["score"], opponent["score"]
    nickname = label(ours.get("commonName")) or team
    won = own_score > opp_score
    outcome = "win" if won else "lose" if own_score < opp_score else "tie"
    subject = f"{nickname} {outcome} {own_score}\u2013{opp_score}"
    period = game.get("gameOutcome", {}).get("lastPeriodType", "REG")
    extra = {"OT": " in overtime", "SO": " in a shootout"}.get(period, "")
    verb = "beat" if won else "lost to" if own_score < opp_score else "tied"
    summary = f"{team_name(ours)} {verb} {team_name(opponent)} {own_score}\u2013{opp_score}{extra} on {game.get('gameDate', '')}."
    if landing:
        scorers = Counter()
        for entry in landing.get("summary", {}).get("scoring", []):
            if entry.get("periodDescriptor", {}).get("periodType") == "SO":
                continue
            for goal in entry.get("goals", []):
                if label(goal.get("teamAbbrev")) == team:
                    name = " ".join(filter(None, [label(goal.get("firstName")), label(goal.get("lastName"))])) or label(goal.get("name"))
                    if name:
                        scorers[name] += 1
        if scorers:
            summary += "\n\n" + nickname + " scorers: " + ", ".join(name + (f" ({count} goals)" if count > 1 else "") for name, count in scorers.items()) + "."
        h, a = landing.get("homeTeam", {}), landing.get("awayTeam", {})
        own_stats, opp_stats = (h, a) if home["abbrev"] == team else (a, h)
        if all(isinstance(t.get("sog"), int) for t in (own_stats, opp_stats)):
            summary += f"\nShots on goal: {nickname} {own_stats['sog']}, {label(opponent.get('commonName')) or opponent['abbrev']} {opp_stats['sog']}."
    venue = label(game.get("venue"))
    if venue:
        summary += "\nVenue: " + venue + "."
    if upcoming:
        start = dt.datetime.fromisoformat(upcoming["start"]).astimezone()
        when = start.strftime("%a, %b %-d, %Y")
        when += " · " + ("Time TBD" if upcoming["timeTbd"] else start.strftime("%-I:%M %p %Z"))
        summary += "\n\nNext game: " + upcoming["away"] + " at " + upcoming["home"] + "."
        summary += "\n" + when
        if upcoming.get("venue"):
            summary += "\nVenue: " + upcoming["venue"] + "."
    else:
        summary += "\n\nNext game: No upcoming game scheduled."
    summary += "\n\nhttps://www.nhl.com/gamecenter/" + str(game["id"])
    return subject, summary


def game_email(game, team, games):
    """Identical content for manual tests and automatic result emails."""
    try:
        landing = fetch("gamecenter/" + str(game["id"]) + "/landing")
    except UserError:
        landing = None
    return recap(game, team, landing, next_game({"games": games}))


def send_email(config, subject, body, before_send=None):
    password = secret(config["sender"])
    if not password:
        raise UserError("The sender's app password is missing. Add it in Settings.")
    message = EmailMessage()
    message["From"] = formataddr((config["displayName"], config["sender"]))
    message["To"] = config["recipient"]
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="nhl-standings.local")
    message.set_content(body)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20, context=ssl.create_default_context()) as smtp:
            smtp.login(config["sender"], password)
            if before_send:
                before_send()
            smtp.send_message(message, from_addr=config["sender"], to_addrs=[config["recipient"]])
    except smtplib.SMTPAuthenticationError:
        raise UserError("Gmail rejected the sign-in. Check the sender and its app password.")
    except smtplib.SMTPRecipientsRefused:
        raise UserError("Gmail rejected the recipient address. Check it in Settings.")


LOG_RETENTION = 7 * 24 * 60 * 60


def retained_log():
    path = STATE / "email-log.json"
    try:
        entries = load_json(path, {"entries": []}).get("entries", [])
        cutoff = time.time() - LOG_RETENTION
        return [entry for entry in entries if isinstance(entry, dict) and isinstance(entry.get("time"), (int, float)) and entry["time"] >= cutoff]
    except (UserError, TypeError):
        return []


def prune_log():
    entries = retained_log()
    atomic_json(STATE / "email-log.json", {"entries": entries})
    return entries


def email_log(clear=False):
    with locked():
        entries = [] if clear else retained_log()
        atomic_json(STATE / "email-log.json", {"entries": entries})
    return {"ok": True, "entries": sorted(entries, key=lambda entry: entry["time"], reverse=True)}


def logged_send(config, subject, body, kind, before_send=None):
    # Logging must never change delivery or duplicate-prevention behavior.
    transmitted = False
    def sending():
        nonlocal transmitted
        if before_send:
            before_send()
        transmitted = True
    status, detail = "Sent", "Accepted by Gmail."
    try:
        send_email(config, subject, body, sending)
    except Exception as error:
        ambiguous = transmitted and not isinstance(error, (smtplib.SMTPResponseException, UserError))
        status = "Delivery uncertain" if ambiguous else "Failed"
        detail = str(error) if isinstance(error, UserError) else (
            "Connection interrupted; delivery could not be confirmed." if ambiguous else "Email delivery failed.")
        raise
    finally:
        try:
            entries = retained_log()
            entries.append({"time": time.time(), "recipient": config["recipient"], "team": config["team"],
                            "subject": subject, "kind": kind, "status": status, "detail": detail})
            atomic_json(STATE / "email-log.json", {"entries": entries})
        except (OSError, ValueError):
            pass


def test_email(subscription_id="legacy"):
    with locked():
        shared = settings()
        sub = next((s for s in shared["subscriptions"] if s["id"] == subscription_id), None)
        if sub is None:
            raise UserError("Save this subscription before sending a test.")
        config = shared | sub
        if not all(config[k] for k in ("sender", "recipient", "team")):
            raise UserError("Save a sender, recipient, and team before sending a test.")
        games = season(config["team"])
        finals = [game for game in games if completed(game, config["team"])]
        if not finals:
            raise UserError("No completed game is available for the selected team yet.")
        game = max(finals, key=lambda g: g.get("startTimeUTC", g.get("gameDate", "")))
        subject, body = game_email(game, config["team"], games)
        logged_send(config, subject, body, "Test")
    return {"ok": True, "message": "Latest game recap sent to " + config["recipient"] + "."}


def check_subscription(config, state, persist, schedules):
    if not config["scope"] or state.get("scope") != config["scope"]:
        raise UserError("Notification history is unavailable. Turn notifications off, save, and enable again.")
    state["lastCheck"] = time.time()
    state["error"] = ""
    seen = set(state.get("seen", []))
    delivery = state.setdefault("delivery", {})
    count = 0
    uncertain = any(value in ("sending", "uncertain") for value in delivery.values())
    try:
        if config["team"] not in schedules:
            schedules[config["team"]] = season(config["team"])
        games = schedules[config["team"]]
        for game in sorted(games, key=lambda g: g.get("startTimeUTC", "")):
            game_id = str(game["id"])
            if not completed(game, config["team"]) or game_id in seen:
                continue
            if delivery.get(game_id) in ("sending", "uncertain"):
                uncertain = True
                continue
            subject, body = game_email(game, config["team"], games)
            def mark_sending():
                delivery[game_id] = "sending"
                persist()
            try:
                logged_send(config, subject, body, "Automatic", mark_sending)
            except Exception as error:
                if delivery.get(game_id) == "sending":
                    # Explicit SMTP rejection is safe to retry; a dropped connection
                    # after transmission might have delivered, so never resend blindly.
                    if isinstance(error, (smtplib.SMTPResponseException, UserError)):
                        delivery.pop(game_id, None)
                    else:
                        delivery[game_id] = "uncertain"
                raise
            seen.add(game_id)
            delivery.pop(game_id, None)
            state["seen"] = sorted(seen)
            state["lastSent"] = time.time()
            state["lastSubject"] = subject
            persist()
            count += 1
        state["status"] = ("Sent " + str(count) + " game recap(s).") if count else "Watching for the next completed game."
        if uncertain:
            state["error"] = "A previous delivery could not be confirmed. It will not be resent to avoid duplicate emails."
    except Exception as error:
        state["error"] = str(error) if isinstance(error, UserError) else "Email delivery or the NHL feed failed. Check your connection and saved settings."
        state["status"] = "The notification checker needs attention."
        persist()
        raise UserError(state["error"])
    persist()
    return state["status"]


def check_results():
    with locked():
        try:
            prune_log()
        except OSError:
            pass
        config = settings()
        history = history_for(config)
        schedules, errors, statuses = {}, [], []
        for sub in config["subscriptions"]:
            if not sub["enabled"]:
                continue
            state = history["subscriptions"].setdefault(sub["id"], {})
            def persist():
                atomic_json(STATE / "notifications.json", history)
            try:
                statuses.append(check_subscription(config | sub, state, persist, schedules))
            except UserError as error:
                state.update(error=str(error), status="The notification checker needs attention.")
                persist()
                errors.append(str(error))
        if errors:
            raise UserError("One or more subscriptions need attention. " + errors[0])
    return {"ok": True, "message": " ".join(statuses) or "Notifications are off."}


def main():
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "check":
            result = check_results()
        else:
            request = json.loads(sys.stdin.readline())
            action = request.get("action")
            if action == "get":
                result = {"ok": True, "settings": public_settings()}
            elif action == "save":
                result = save_settings(request)
            elif action == "log":
                result = email_log()
            elif action == "clear-log":
                result = email_log(clear=True)
            elif action == "test":
                result = test_email(request.get("subscriptionId", "legacy"))
            else:
                raise UserError("Unknown settings action.")
    except Exception as error:
        result = {"ok": False, "message": str(error) if isinstance(error, UserError) else "The operation failed. Check your connection and try again."}
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
