from unittest.mock import patch
import unittest
import test_notifications as fixtures
from test_notifications import game
import notifications as n

class SubscriptionTests(unittest.TestCase):
    setUp = fixtures.NotificationsTests.setUp
    def multi(self):
        return {"sender": self.request["sender"], "displayName": "The Rathole", "subscriptions": [
            {"id": "one", "recipient": "first@example.com", "team": "VAN", "enabled": True},
            {"id": "two", "recipient": "second@example.com", "team": "VGK", "enabled": True}]}

    def test_independent_recipients_and_teams(self):
        request = self.multi()
        with patch.object(n, "season", return_value=[game()]):
            n.save_settings(request)
        with patch.object(n, "season", return_value=[game(), game(2)]), patch.object(n, "fetch", return_value={}), patch.object(n, "send_email") as send:
            n.check_results()
            n.check_results()
            self.assertEqual(send.call_count, 2)
            self.assertEqual([(c.args[0]["recipient"], c.args[1]) for c in send.call_args_list], [
                ("first@example.com", "Canucks lose 2–3"), ("second@example.com", "Golden Knights win 3–2")])
            send.reset_mock()
            n.test_email("two")
            self.assertEqual(send.call_args.args[0]["recipient"], "second@example.com")

    def test_failed_subscription_does_not_block_others(self):
        with patch.object(n, "season", return_value=[game()]):
            n.save_settings(self.multi())
        def deliver(config, subject, body, before_send):
            if config["recipient"] == "first@example.com":
                raise n.UserError("Rejected recipient")
            before_send()
        with patch.object(n, "season", return_value=[game(2)]), patch.object(n, "fetch", return_value={}), patch.object(n, "send_email", side_effect=deliver) as send:
            with self.assertRaises(n.UserError):
                n.check_results()
            self.assertEqual(send.call_count, 2)
        history = n.history_for(n.settings())["subscriptions"]
        self.assertIn("2", history["two"]["seen"])
        self.assertNotIn("2", history["one"]["seen"])

    def test_edit_one_preserves_other_history_and_remove(self):
        request = self.multi()
        with patch.object(n, "season", return_value=[game()]):
            n.save_settings(request)
        scope = n.settings()["subscriptions"][1]["scope"]
        request["subscriptions"][0]["recipient"] = "new@example.com"
        with patch.object(n, "season", return_value=[game(2)]):
            n.save_settings(request)
        self.assertEqual(n.settings()["subscriptions"][1]["scope"], scope)
        request["subscriptions"].pop(0)
        with patch.object(n, "season") as feed:
            n.save_settings(request)
            feed.assert_not_called()
        self.assertEqual(set(n.history_for(n.settings())["subscriptions"]), {"two"})

    def test_duplicate_recipient_team_rejected(self):
        request = self.multi()
        request["subscriptions"][1].update(recipient="FIRST@example.com", team="VAN")
        with self.assertRaisesRegex(n.UserError, "already"):
            n.save_settings(request)

    def test_migration_preserves_legacy_history(self):
        legacy = self.request | {"scope": "existing"}
        history = {"scope": "existing", "seen": ["1", "2"], "delivery": {"3": "uncertain"}, "lastSent": 42}
        n.atomic_json(n.CONFIG / "notifications.json", legacy)
        n.atomic_json(n.STATE / "notifications.json", history)
        with patch.object(n, "send_email") as send, patch.object(n, "season") as feed:
            n.migrate()
            n.migrate()
            send.assert_not_called()
            feed.assert_not_called()
        self.assertEqual(n.settings()["subscriptions"][0]["scope"], "existing")
        self.assertEqual(n.history_for(n.settings())["subscriptions"]["legacy"], history)
