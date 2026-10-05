import unittest
from unittest.mock import patch
import test_notifications as fixtures
import notifications as n
from email_html import render_email_html

BODY = '''Game summary.

Current standings: 22 points.

Pacific Division standings
Rank | Team | GP | W | L | OT | PTS
1 | Vegas Golden Knights | 17 | 12 | 4 | 1 | 25
3 | Vancouver Canucks * | 17 | 10 | 5 | 2 | 22
* Selected team.

Next game: Vancouver at Vegas.

https://www.nhl.com/gamecenter/123'''

class HtmlEmailTests(unittest.TestCase):
    setUp = fixtures.NotificationsTests.setUp

    def test_multipart_preserves_plain_text_and_prefers_html(self):
        with patch.object(n.smtplib, "SMTP_SSL") as transport:
            n.send_email(self.request, "Canucks result", BODY)
        message = transport.return_value.__enter__.return_value.send_message.call_args.args[0]
        self.assertEqual(message.get_content_type(), "multipart/alternative")
        self.assertEqual([part.get_content_type() for part in message.iter_parts()], ["text/plain", "text/html"])
        self.assertEqual(message.get_body(preferencelist=("plain",)).get_content(), BODY + "\n")
        self.assertEqual(message.get_body().get_content_type(), "text/html")

    def test_table_content_order_and_responsive_styles(self):
        html = render_email_html("Canucks result", BODY)
        self.assertIn('scope="col"', html)
        self.assertIn('scope="row"', html)
        self.assertIn('width="100%"', html)
        self.assertIn('max-width:640px', html)
        self.assertIn('max-width:480px', html)
        self.assertIn('overflow-wrap:break-word', html)
        self.assertIn('background:#e4efff', html)
        self.assertIn('Vancouver Canucks *', html)
        self.assertNotIn("Rank | Team", html)
        self.assertLess(html.index("Current standings"), html.index('class="standings"'))
        self.assertLess(html.index('class="standings"'), html.index("Next game:"))
        self.assertIn('href="https://www.nhl.com/gamecenter/123"', html)

    def test_external_text_is_escaped(self):
        html = render_email_html('<script>bad</script>', BODY.replace('Vancouver Canucks', '<img src=x onerror=bad> & Team'))
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img ', html)
        self.assertIn('&lt;img src=x onerror=bad&gt; &amp; Team', html)

    def test_no_standings_still_renders(self):
        html = render_email_html('Result', 'Current standings: Temporarily unavailable.\n\nNext game: No upcoming game scheduled.')
        self.assertNotIn('class="standings"', html)
        self.assertIn('Temporarily unavailable.', html)
