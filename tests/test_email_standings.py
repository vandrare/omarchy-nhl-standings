import unittest
from unittest.mock import patch
import test_notifications as fixtures
from test_notifications import game
import notifications as n

class EmailStandingsTests(unittest.TestCase):
    setUp = fixtures.NotificationsTests.setUp

    def data(self):
        return {"standings": [
            {"teamAbbrev": {"default": "VGK"}, "wins": 12, "points": 25},
            {"teamAbbrev": {"default": "VAN"}, "teamName": {"default": "Vancouver Canucks"},
             "wins": 10, "losses": 5, "otLosses": 2, "gamesPlayed": 17, "points": 22,
             "divisionName": "Pacific", "divisionSequence": 3, "conferenceName": "Western", "conferenceSequence": 6,
             "date": "2026-11-01"}]}

    def test_selected_team_standings_between_recap_and_next_game(self):
        table = self.data()
        # NHL dates are identical across rows in a daily standings response.
        table["standings"][0]["date"] = "2026-11-01"
        with patch.object(n, "fetch", side_effect=lambda endpoint: table if endpoint == "standings/now" else {}):
            subject, body = n.game_email(game(), "VAN", [])
        self.assertEqual(subject, "Canucks lose 2–3")
        self.assertIn("Current standings (as of 2026-11-01):", body)
        self.assertIn("10 wins · 5 losses · 2 overtime losses · 22 points · 17 games played", body)
        self.assertIn("Pacific Division: #3 · Western Conference: #6", body)
        self.assertLess(body.index("Venue: Rogers Arena"), body.index("Current standings"))
        self.assertLess(body.index("Current standings"), body.index("Next game:"))

    def test_standings_failure_still_produces_recap(self):
        def fetch(endpoint):
            if endpoint == "standings/now":
                raise n.UserError("Feed unavailable")
            return {}
        with patch.object(n, "fetch", side_effect=fetch):
            subject, body = n.game_email(game(), "VAN", [])
        self.assertIn("Current standings: Temporarily unavailable.", body)
        self.assertIn("Next game:", body)
        self.assertEqual(subject, "Canucks lose 2–3")

    def test_missing_selected_team_never_shows_another_teams_record(self):
        with patch.object(n, "fetch", return_value={"standings": [{"teamAbbrev": {"default": "VGK"}, "wins": 99}]}):
            _, body = n.game_email(game(), "VAN", [])
        self.assertIn("Current standings: Temporarily unavailable.", body)
        self.assertNotIn("99 wins", body)

    def test_division_table_order_columns_and_placement(self):
        table = self.data()
        table["standings"][0].update(teamName={"default": "Vegas Golden Knights"}, divisionName="Pacific", divisionSequence=1, gamesPlayed=17, wins=12, losses=4, otLosses=1, points=25, date="2026-11-01")
        table["standings"].append({"teamAbbrev": {"default": "COL"}, "teamName": {"default": "Colorado Avalanche"}, "divisionName": "Central", "divisionSequence": 1, "points": 30})
        with patch.object(n, "fetch", side_effect=lambda endpoint: table if endpoint == "standings/now" else {}):
            _, body = n.game_email(game(), "VAN", [])
        self.assertIn("Rank | Team | GP | W | L | OT | PTS", body)
        self.assertIn("1 | Vegas Golden Knights | 17 | 12 | 4 | 1 | 25", body)
        self.assertIn("3 | Vancouver Canucks * | 17 | 10 | 5 | 2 | 22", body)
        self.assertNotIn("Colorado Avalanche", body)
        self.assertLess(body.index("1 | Vegas"), body.index("3 | Vancouver"))
        self.assertLess(body.index("Current standings"), body.index("Pacific Division standings"))
        self.assertLess(body.index("Pacific Division standings"), body.index("Next game:"))

    def test_test_and_automatic_emails_include_same_division_table(self):
        with patch.object(n, "season", return_value=[game()]):
            n.save_settings(self.request)
        latest = game(2)
        table = self.data()
        with patch.object(n, "season", return_value=[latest]), patch.object(n, "fetch", side_effect=lambda endpoint: table if endpoint == "standings/now" else {}), patch.object(n, "send_email") as send:
            n.test_email()
            n.check_results()
        self.assertEqual(send.call_count, 2)
        self.assertEqual(send.call_args_list[0].args[1:3], send.call_args_list[1].args[1:3])
        self.assertIn("Pacific Division standings", send.call_args_list[0].args[2])
