import unittest
from unittest.mock import patch
import test_notifications as fixtures
import notifications as n

class EmailLogTests(unittest.TestCase):
    setUp = fixtures.NotificationsTests.setUp

    def test_retention_and_clear(self):
        with patch.object(n.time, "time", return_value=1000000):
            n.atomic_json(n.STATE / "email-log.json", {"entries": [{"time": 1000000 - n.LOG_RETENTION - 1}, {"time": 999999}]})
            self.assertEqual(n.email_log()["entries"], [{"time": 999999}])
            self.assertEqual(n.email_log(clear=True)["entries"], [])
            self.assertEqual(n.retained_log(), [])

    def test_records_success_without_credentials_or_body(self):
        with patch.object(n, "send_email"):
            n.logged_send(self.request, "Canucks win 4–1", "Private email body", "Test")
        entry = n.email_log()["entries"][0]
        self.assertEqual(entry["status"], "Sent")
        self.assertEqual(entry["kind"], "Test")
        self.assertEqual(entry["recipient"], self.request["recipient"])
        self.assertNotIn("password", entry)
        self.assertNotIn("Private email body", str(entry))
        self.assertEqual((n.STATE / "email-log.json").stat().st_mode & 0o777, 0o600)

    def test_failed_and_uncertain(self):
        with patch.object(n, "send_email", side_effect=n.UserError("Rejected recipient")):
            with self.assertRaises(n.UserError):
                n.logged_send(self.request, "Result", "Body", "Automatic")
        self.assertEqual(n.email_log()["entries"][0]["status"], "Failed")
        def interrupted(config, subject, body, before_send):
            before_send()
            raise OSError("secret raw transport detail")
        with patch.object(n, "send_email", side_effect=interrupted):
            with self.assertRaises(OSError):
                n.logged_send(self.request, "Result", "Body", "Automatic")
        entry = n.email_log()["entries"][0]
        self.assertEqual(entry["status"], "Delivery uncertain")
        self.assertNotIn("secret raw transport detail", entry["detail"])

    def test_log_write_failure_does_not_interrupt_send(self):
        with patch.object(n, "send_email") as send, patch.object(n, "atomic_json", side_effect=OSError("disk full")):
            n.logged_send(self.request, "Result", "Body", "Test")
            send.assert_called_once()
