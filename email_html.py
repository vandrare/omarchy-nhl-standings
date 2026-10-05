"""Email-safe HTML presentation of the canonical plain-text game recap."""
from html import escape
import re

TABLE_HEADER = "Rank | Team | GP | W | L | OT | PTS"


def render_email_html(subject, body):
    """Keep both MIME alternatives in sync; format the generated division table."""
    parts, paragraph = [], []
    def flush():
        if not paragraph:
            return
        text = "\n".join(paragraph)
        paragraph.clear()
        if re.fullmatch(r"https://www\.nhl\.com/gamecenter/[0-9]+", text):
            parts.append('<p style="margin:18px 0"><a href="' + escape(text, quote=True) + '" style="color:#1559a6">View game on NHL.com</a></p>')
        elif text.endswith(" Division standings"):
            parts.append('<h2 style="font-size:17px;margin:22px 0 10px">' + escape(text) + '</h2>')
        else:
            parts.append('<p style="margin:0 0 16px;line-height:1.6">' + escape(text).replace("\n", "<br>") + '</p>')
    lines = body.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if line == TABLE_HEADER:
            flush()
            parts.append('<table class="standings" width="100%" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;table-layout:fixed;font-size:12px;line-height:1.4"><thead><tr>')
            for column, heading in enumerate(("#", "Team", "GP", "W", "L", "OT", "PTS")):
                width = "40%" if column == 1 else "8%" if column == 0 else "10.4%"
                alignment = "left" if column == 1 else "center"
                parts.append(f'<th scope="col" width="{width}" style="width:{width};padding:8px 3px;text-align:{alignment};background:#e9eef5;color:#20334d;border-bottom:2px solid #c9d4e2">{heading}</th>')
            parts.append('</tr></thead><tbody>')
            index += 1
            row_index = 0
            while index < len(lines):
                cells = [cell.strip() for cell in lines[index].split("|")]
                if len(cells) != 7:
                    break
                selected = cells[1].endswith(" *")
                background = "#e4efff" if selected else "#f5f7fa" if row_index % 2 else "#ffffff"
                weight = "bold" if selected else "normal"
                parts.append(f'<tr style="background:{background};font-weight:{weight}">')
                for column, cell in enumerate(cells):
                    alignment = "left" if column == 1 else "center"
                    tag = "th" if column == 1 else "td"
                    scope = ' scope="row"' if column == 1 else ""
                    wrapping = "overflow-wrap:break-word;word-wrap:break-word" if column == 1 else "white-space:nowrap"
                    parts.append(f'<{tag}{scope} style="padding:9px 3px;text-align:{alignment};font-weight:{weight};border-bottom:1px solid #dce3ec;{wrapping}">{escape(cell)}</{tag}>')
                parts.append('</tr>')
                index += 1
                row_index += 1
            parts.append('</tbody></table><div style="height:12px;line-height:12px">&nbsp;</div>')
            continue
        if line:
            paragraph.append(line)
        else:
            flush()
        index += 1
    flush()
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>@media screen and (max-width:480px){.email-content{padding:16px 10px!important}.standings{font-size:11px!important}.standings th,.standings td{padding:8px 2px!important}}</style>
</head><body style="margin:0;padding:0;background:#f2f4f7;color:#202b3c;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse"><tr><td align="center">
<div class="email-content" style="max-width:640px;margin:0 auto;padding:24px 16px;background:#ffffff;text-align:left">
<h1 style="font-size:22px;line-height:1.3;margin:0 0 20px">''' + escape(subject) + '</h1>' + "\n".join(parts) + '</div></td></tr></table></body></html>'
