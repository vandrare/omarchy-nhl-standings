#!/usr/bin/env python3
"""Small NHL feed adapter with an atomic, persistent 15-minute cache."""
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.request

BASE = "https://api-web.nhle.com/v1/"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "nhl-standings"
TTL = 900


def label(value):
    return value.get("default", "") if isinstance(value, dict) else str(value or "")


def standings(data):
    if not isinstance(data.get("standings"), list) or not data["standings"]:
        raise ValueError("Standings are not available yet")
    rows = []
    for team in data["standings"]:
        code = label(team.get("teamAbbrev"))
        if not re.fullmatch(r"[A-Z]{2,3}", code):
            continue
        rows.append({
            "code": code, "name": label(team.get("teamName")),
            "conference": team.get("conferenceName", ""),
            "rank": team.get("conferenceSequence", 0),
            "division": team.get("divisionName", ""),
            "divisionRank": team.get("divisionSequence", 0),
            "logo": team.get("teamLogo", ""),
            "gp": team.get("gamesPlayed", 0), "w": team.get("wins", 0),
            "l": team.get("losses", 0), "ot": team.get("otLosses", 0),
            "pts": team.get("points", 0),
        })
    if not rows:
        raise ValueError("No team standings returned")
    return {"teams": rows, "date": data["standings"][0].get("date", "")}


def next_game(data, now=None):
    if not isinstance(data.get("games"), list):
        raise ValueError("Schedule is not available")
    now = now or dt.datetime.now(dt.timezone.utc)
    upcoming = []
    for game in data["games"]:
        if game.get("gameState") in ("FINAL", "OFF"):
            continue
        if game.get("gameScheduleState") in ("PPD", "CNCL"):
            continue
        try:
            start = dt.datetime.fromisoformat(game["startTimeUTC"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if start > now:
            upcoming.append((start, game))
    if not upcoming:
        return None
    start, game = min(upcoming, key=lambda item: item[0])
    def team_name(team):
        return " ".join(filter(None, [label(team.get("placeName")), label(team.get("commonName"))])) or team.get("abbrev", "")
    return {
        "away": team_name(game.get("awayTeam", {})),
        "home": team_name(game.get("homeTeam", {})),
        "start": start.isoformat(), "venue": label(game.get("venue")),
        "timeTbd": game.get("gameScheduleState") == "TBD",
        "kind": {1: "Preseason", 2: "Regular season", 3: "Playoffs"}.get(game.get("gameType"), ""),
    }


def cached_fetch(key, endpoint, force=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (key + ".json")
    cached = None
    try:
        cached = json.loads(path.read_text())
        if not isinstance(cached.get("data"), dict) or not isinstance(cached.get("updated"), (int, float)) or not math.isfinite(cached["updated"]):
            cached = None
    except (OSError, ValueError, AttributeError):
        cached = None
    if cached and not force and time.time() - cached["updated"] < TTL:
        return cached["data"], cached["updated"], False
    try:
        request = urllib.request.Request(BASE + endpoint, headers={"User-Agent": "Omarchy-NHL-Standings/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            data = json.load(response)
        # Validate before replacing a good cached response.
        standings(data) if key == "standings" else next_game(data)
        updated = time.time()
        with tempfile.NamedTemporaryFile(mode="w", dir=CACHE, delete=False) as file:
            json.dump({"data": data, "updated": updated}, file)
            temp_path = file.name
        os.replace(temp_path, path)
        return data, updated, False
    except Exception:
        if cached:
            return cached["data"], cached["updated"], True
        raise


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "standings"
    code = sys.argv[2] if mode == "schedule" and len(sys.argv) > 2 else ""
    result = {"team": code}
    try:
        if mode == "standings":
            data, updated, stale = cached_fetch("standings", "standings/now", "--force" in sys.argv)
            result.update(standings(data))
        elif mode == "schedule" and re.fullmatch(r"[A-Z]{2,3}", code):
            data, updated, stale = cached_fetch("schedule-" + code, "club-schedule-season/" + code + "/now")
            result["game"] = next_game(data)
        else:
            raise ValueError("Invalid request")
        result.update(updated=updated, stale=stale)
    except Exception:
        result["error"] = "NHL data is unavailable. Try again shortly."
    print(json.dumps(result))


if __name__ == "__main__":
    main()
