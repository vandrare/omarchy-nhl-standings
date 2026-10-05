import json
from pathlib import Path
import smtplib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import notifications as n


def game(game_id=1, ours=2, theirs=3, state="FINAL"):
    return {"id": game_id, "gameState": state, "gameScheduleState": "OK",
            "startTimeUTC": "2026-10-05T01:00:00Z", "gameDate": "2026-10-04",
            "venue": {"default": "Rogers Arena"},
            "homeTeam": {"abbrev": "VAN", "placeName": {"default": "Vancouver"}, "commonName": {"default": "Canucks"}, "score": ours},
            "awayTeam": {"abbrev": "VGK", "placeName": {"default": "Vegas"}, "commonName": {"default": "Golden Knights"}, "score": theirs}}


class NotificationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        self.config_patch = patch.object(n, "CONFIG", folder / "config")
        self.state_patch = patch.object(n, "STATE", folder / "state")
        self.config_patch.start()
        self.state_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.addCleanup(self.state_patch.stop)
        self.secret_patch = patch.object(n, "secret", return_value="test-app-password")
        self.secret_patch.start()
        self.addCleanup(self.secret_patch.stop)
        self.request = {"sender": "sender@gmail.com", "recipient": "recipient@example.com",
                        "displayName": "The Rathole", "team": "VAN", "enabled": True}

    def enable(self):
        with patch.object(n, "season", return_value=[game()]):
            n.save_settings(self.request)

    def test_default_disabled_and_no_network(self):
        with patch.object(n, "season") as fetch, patch.object(n, "send_email") as send:
            n.check_results()
            fetch.assert_not_called()
            send.assert_not_called()

    def test_enabling_skips_historical_results(self):
        self.enable()
        with patch.object(n, "season", return_value=[game()]), patch.object(n, "send_email") as send:
            n.check_results()
            send.assert_not_called()

    def test_send_once_and_persist_history(self):
        self.enable()
        with patch.object(n, "season", return_value=[game(), game(2)]), patch.object(n, "fetch", return_value={}), patch.object(n, "send_email") as send:
            n.check_results()
            n.check_results()
            self.assertEqual(send.call_count, 1)
            self.assertEqual(send.call_args.args[1], "Canucks lose 2–3")
        history = json.loads((n.STATE / "notifications.json").read_text())
        self.assertIn("2", history["subscriptions"]["legacy"]["seen"])

    def test_changed_recipient_resets_baseline(self):
        self.enable()
        old_scope = n.settings()["subscriptions"][0]["scope"]
        request = self.request | {"recipient": "another@example.com"}
        with patch.object(n, "season", return_value=[game(), game(2)]):
            n.save_settings(request)
        self.assertNotEqual(old_scope, n.settings()["subscriptions"][0]["scope"])
        self.assertIn("2", json.loads((n.STATE / "notifications.json").read_text())["subscriptions"]["legacy"]["seen"])

    def test_unchanged_settings_preserve_scope(self):
        self.enable()
        scope = n.settings()["subscriptions"][0]["scope"]
        with patch.object(n, "season") as fetch:
            n.save_settings(self.request | {"displayName": "New name"})
            fetch.assert_not_called()
        self.assertEqual(scope, n.settings()["subscriptions"][0]["scope"])

    def test_ambiguous_delivery_is_not_repeated(self):
        self.enable()
        def interrupted(config, subject, body, before_send):
            before_send()
            raise OSError("Lost connection after transmission")
        with patch.object(n, "season", return_value=[game(2)]), patch.object(n, "fetch", return_value={}), patch.object(n, "send_email", side_effect=interrupted) as send:
            with self.assertRaises(n.UserError):
                n.check_results()
            n.check_results()
            self.assertEqual(send.call_count, 1)

    def test_definite_rejection_can_retry(self):
        self.enable()
        def rejected(config, subject, body, before_send):
            before_send()
            raise smtplib.SMTPDataError(451, b"Temporary failure")
        with patch.object(n, "season", return_value=[game(2)]), patch.object(n, "fetch", return_value={}):
            with patch.object(n, "send_email", side_effect=rejected):
                with self.assertRaises(n.UserError):
                    n.check_results()
            with patch.object(n, "send_email") as send:
                n.check_results()
                self.assertEqual(send.call_count, 1)

    def test_never_email_live_or_postponed_games(self):
        self.enable()
        postponed = game(3)
        postponed["gameScheduleState"] = "PPD"
        with patch.object(n, "season", return_value=[game(2, state="LIVE"), postponed]), patch.object(n, "send_email") as send:
            n.check_results()
            send.assert_not_called()

    def test_password_never_persisted_or_returned(self):
        request = self.request | {"enabled": False, "password": "abcdefghijklmnop"}
        result = n.save_settings(request)
        self.assertNotIn(request["password"], json.dumps(result))
        self.assertNotIn(request["password"], (n.CONFIG / "notifications.json").read_text())
        self.assertEqual((n.CONFIG / "notifications.json").stat().st_mode & 0o777, 0o600)

    def test_reject_header_injection_and_normal_password(self):
        for changes in [{"sender": "bad\r\nBcc: victim@example.com"}, {"displayName": "Name\nBcc:"}, {"password": "ordinary-password"}]:
            with self.assertRaises(n.UserError):
                n.save_settings(self.request | changes)

    def test_no_password_blocks_enable(self):
        with patch.object(n, "secret", return_value=""):
            with self.assertRaises(n.UserError):
                n.save_settings(self.request)

    def test_email_uses_tls_display_name_and_exact_recipient(self):
        with patch.object(n.smtplib, "SMTP_SSL") as transport:
            n.send_email(self.request, "Canucks lose 2–3", "A short recap.")
            self.assertEqual(transport.call_args.args, ("smtp.gmail.com", 465))
            self.assertIn("context", transport.call_args.kwargs)
            client = transport.return_value.__enter__.return_value
            client.login.assert_called_once_with("sender@gmail.com", "test-app-password")
            message = client.send_message.call_args.args[0]
            self.assertEqual(message["From"].addresses[0].display_name, "The Rathole")
            self.assertEqual(client.send_message.call_args.kwargs["to_addrs"], ["recipient@example.com"])
            self.assertEqual(str(message["Subject"]), "Canucks lose 2–3")

    def test_test_email_sends_latest_final_without_changing_history(self):
        self.enable()
        before = (n.STATE / "notifications.json").read_text()
        older = game(1)
        older["startTimeUTC"] = "2026-10-01T01:00:00Z"
        latest = game(2, 4, 1)
        future = game(3, state="FUT")
        future["startTimeUTC"] = "2026-10-10T01:00:00Z"
        with patch.object(n, "season", return_value=[future, latest, older]), patch.object(n, "fetch", return_value={}) as fetch, patch.object(n, "send_email") as send:
            result = n.test_email()
            self.assertTrue(result["ok"])
            self.assertEqual([call.args[0] for call in fetch.call_args_list], ["gamecenter/2/landing", "standings/now"])
            self.assertEqual(send.call_args.args[1], "Canucks win 4–1")
        self.assertEqual(before, (n.STATE / "notifications.json").read_text())

    def test_test_email_works_when_off_with_missing_optional_stats(self):
        n.save_settings(self.request | {"enabled": False})
        with patch.object(n, "season", return_value=[game()]), patch.object(n, "fetch", side_effect=n.UserError("Unavailable")), patch.object(n, "send_email") as send:
            n.test_email()
            self.assertEqual(send.call_args.args[1], "Canucks lose 2–3")
            self.assertIn("Vancouver Canucks lost to Vegas Golden Knights", send.call_args.args[2])

    def test_test_email_requires_team_and_completed_game(self):
        n.save_settings(self.request | {"enabled": False, "team": ""})
        with patch.object(n, "send_email") as send:
            with self.assertRaisesRegex(n.UserError, "team"):
                n.test_email()
            send.assert_not_called()
        n.save_settings(self.request | {"enabled": False})
        with patch.object(n, "season", return_value=[game(state="LIVE")]), patch.object(n, "send_email") as send:
            with self.assertRaisesRegex(n.UserError, "No completed game"):
                n.test_email()
            send.assert_not_called()

    def test_live_and_test_include_identical_next_game_above_link(self):
        self.enable()
        future = game(3, state="FUT")
        future["startTimeUTC"] = "2099-10-10T01:00:00Z"
        future["venue"] = {"default": "Next game arena"}
        older = game()
        older["startTimeUTC"] = "2026-10-01T01:00:00Z"
        games = [older, game(2), future]
        with patch.object(n, "season", return_value=games), patch.object(n, "fetch", return_value={}), patch.object(n, "send_email") as send:
            n.test_email()
            n.check_results()
            self.assertEqual(send.call_count, 2)
            self.assertEqual(send.call_args_list[0].args[1:3], send.call_args_list[1].args[1:3])
            body = send.call_args_list[0].args[2]
            self.assertIn("Next game: Vegas Golden Knights at Vancouver Canucks.", body)
            self.assertIn("2099", body)
            self.assertIn("Venue: Next game arena.", body)
            self.assertLess(body.index("Next game:"), body.index("https://www.nhl.com/gamecenter/"))

    def test_next_game_tbd_and_no_upcoming_game(self):
        upcoming = {"start": "2099-10-10T01:00:00+00:00", "away": "Vancouver Canucks", "home": "Vegas Golden Knights", "timeTbd": True, "venue": ""}
        body = n.recap(game(), "VAN", upcoming=upcoming)[1]
        self.assertIn("Time TBD", body)
        body = n.recap(game(), "VAN")[1]
        self.assertIn("Next game: No upcoming game scheduled.", body)

    def test_corrupt_history_prevents_resending(self):
        self.enable()
        (n.STATE / "notifications.json").write_text("corrupt")
        with patch.object(n, "send_email") as send:
            with self.assertRaises(n.UserError):
                n.check_results()
            send.assert_not_called()

    def test_recap_scorers_shots_overtime_and_win(self):
        landing = {"homeTeam": {"sog": 19}, "awayTeam": {"sog": 28}, "summary": {"scoring": [
            {"periodDescriptor": {"periodType": "REG"}, "goals": [
                {"teamAbbrev": {"default": "VAN"}, "firstName": {"default": "Elias"}, "lastName": {"default": "Pettersson"}},
                {"teamAbbrev": {"default": "VAN"}, "firstName": {"default": "Elias"}, "lastName": {"default": "Pettersson"}}]},
            {"periodDescriptor": {"periodType": "SO"}, "goals": [{"teamAbbrev": {"default": "VAN"}, "name": {"default": "Shootout player"}}]}]}}
        result = game(2, 3, 2)
        result["gameOutcome"] = {"lastPeriodType": "OT"}
        subject, body = n.recap(result, "VAN", landing)
        self.assertEqual(subject, "Canucks win 3–2")
        self.assertIn("in overtime", body)
        self.assertIn("Elias Pettersson (2 goals)", body)
        self.assertIn("Canucks 19", body)
        self.assertNotIn("Shootout player", body)
        subject, body = n.recap(result, "VGK", landing)
        self.assertEqual(subject, "Golden Knights lose 2–3")
        self.assertIn("Golden Knights 28", body)


if __name__ == "__main__":
    unittest.main()
