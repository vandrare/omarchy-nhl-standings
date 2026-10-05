# NHL Standings for Omarchy

NHL conference and division standings, upcoming games, and optional Gmail
result notifications with multiple recipient/team subscriptions.

## Install

Requires Omarchy with the Quickshell shell and `omarchy plugin add` command,
plus Python 3.10 or newer. Older Omarchy bars do not support this plugin.

```bash
omarchy plugin add https://github.com/vandrare/omarchy-nhl-standings.git --enable
```

The plugin ID is `local.nhl-standings`. Omarchy validates the manifest and
installs it in `~/.config/omarchy/plugins/local.nhl-standings/`. Choose a bar
section when prompted; the default is left. Standings need no account or API key.

### Optional background email notifications

Install the keyring tool if it is missing, then set up the user timer:

```bash
omarchy pkg add libsecret
bash ~/.config/omarchy/plugins/local.nhl-standings/setup-email.sh
```

The setup script installs a systemd **user** service and timer; no root access is
needed for timer setup. Emails are initially off. Configure the sender, Google
app password, and recipient/team subscriptions in Settings, then enable the
desired subscriptions and save. An unlocked Secret Service keyring is required.
The test button can send recaps without the timer.

### Update

```bash
omarchy plugin update local.nhl-standings
```

After updates that change email timer setup, rerun `setup-email.sh`.

### Remove

Stop the optional email timer before removing the plugin:

```bash
systemctl --user disable --now nhl-standings-email.timer
omarchy plugin remove local.nhl-standings
```

Settings, delivery history, and the saved keyring password remain local. Removing
the widget alone does not stop the independently installed email timer.

## Usage

Click **NHL** in the bar to open conference standings. Western is selected
each time the panel opens; choose Eastern to switch. Each conference shows its
two divisions side by side, ordered by division rank. Click a team for its
next scheduled game, including opponent, date, time in the computer's local
timezone, and venue. Preseason games are included when they are next.

Standings refresh every 15 minutes. Click the refresh button or middle-click
the bar widget for a forced refresh. Cached data stays available offline and
is labeled accordingly. A team without a future scheduled game displays
"No upcoming game scheduled." Postponed and cancelled games are excluded.

Keyboard: L opens the email log, Escape closes, left/right changes conference, up/down selects a
row, Enter shows the next game, R refreshes, S opens Settings, Tab switches bar panels.

Requires Python 3 and the Omarchy Quickshell shell. Data comes from
`https://api-web.nhle.com/v1/standings/now` and
`https://api-web.nhle.com/v1/club-schedule-season/{TEAM}/now`. No API key,
database, or additional Python packages are needed. These NHL-hosted feeds
are not a version-guaranteed developer API.

Cache: `${XDG_CACHE_HOME:-~/.cache}/nhl-standings/`.

## Game result emails

Click the **gear icon** to open Settings. Add your Gmail sender address, sender display
name (defaults to **The Rathole**), recipient, team, and a Google app password.
App passwords require two-step verification:
https://support.google.com/mail/answer/185833
Use https://myaccount.google.com/apppasswords to create one. Enter it directly
in the masked Settings field. The normal Google account password is not used.

Save settings, then click **Send test email** to send the selected team's
latest completed-game recap using the same subject and summary as automatic
notifications. Both include the selected team’s current wins, losses, overtime losses, points,
games played, and division/conference positions between the recap and next game.
The standings date is shown because NHL standings may take time to update after
a final result; an unavailable feed is labeled without blocking the email.
Both include the next scheduled matchup, local date and time,
and venue immediately above the NHL game link. This works while notifications are off and does not change
automatic delivery history. Test emails are sent only when this button is
clicked. Enable notifications and save to
begin watching for future completed games. Existing final games are skipped
when enabling, changing team, sender, or recipient. Wins and losses include
the final score in the subject, with scorers and shot totals in a short plain
text recap when those stats are available. Preseason and playoffs are included.

The password is stored with `secret-tool` in the system keyring; it is never
written to the plugin settings, passed on the command line, or returned to
the UI. The keyring must be available and unlocked. Leave the password field
blank to retain a saved password for the same sender.

`nhl-standings-email.timer` checks every five minutes while the user session
is running, even when this panel is closed. The checker resumes when signing
in again. It records sent games to avoid duplicates. A delivery interrupted
after transmission is flagged as uncertain and not automatically resent.
Delivery errors and last-check times appear in Settings; use **Refresh status**.
Saving with notifications off immediately stops future result emails.

Settings: `${XDG_CONFIG_HOME:-~/.config}/nhl-standings/notifications.json`.
Delivery history: `${XDG_STATE_HOME:-~/.local/state}/nhl-standings/notifications.json`.
Both files are private to the user (mode 600); the credential stays in the keyring.

Disable the bar widget with `omarchy plugin disable local.nhl-standings`.
To stop emails as well, disable notifications in Settings or run
`systemctl --user disable --now nhl-standings-email.timer`.

Tests: `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v`.

Multiple recipients
-------------------
Settings → Add recipient / team creates another subscription. Each row has its
own recipient, team, on/off switch, test button, and delivery status. The same
address can follow several teams using separate rows. Duplicate address/team
pairs are rejected. Save settings before testing; new rows start switched off.
All rows share the sender, display name, and app password stored in the keyring.
Tests and live emails use the same latest-game recap and next-game information.

Existing single-recipient settings and delivery history are migrated without
resending previous results. Private pre-migration backups are beside the settings
and state files, named notifications.pre-multiple.json. Editing one row preserves
the histories of the other rows, and failures are reported per subscription.

Email log
---------
The ≡ button between Settings and Refresh opens the email log (keyboard: L).
It records new test and automatic email attempts with time, recipient, team,
subject, and Sent / Failed / Delivery uncertain status. Sent means Gmail accepted
it, not confirmed inbox delivery. Entries are kept locally for seven days and
pruned on scheduled checks, writes, and viewing. Refresh log reloads the list;
Clear log removes displayed history without changing delivery deduplication.
No passwords or full email bodies are logged. Older emails cannot be reconstructed.
The private file is ~/.local/state/nhl-standings/email-log.json.

## License

MIT. This is a community plugin and is not affiliated with the NHL or Omarchy.
