#!/usr/bin/env bash
# Optional setup: install the background email checker for the current user.
set -euo pipefail

plugin_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
for dependency in python3 secret-tool systemctl; do
  command -v "$dependency" >/dev/null || {
    echo "Missing dependency: $dependency. On Omarchy, install Python and libsecret with: omarchy pkg add python libsecret" >&2
    exit 1
  }
done

unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p -- "$unit_dir"
# Generate the ExecStart from this checkout's actual path; do not assume where
# the user's home or plugin directory lives. Escape systemd specifiers/quotes.
python3 - "$plugin_dir" "$unit_dir" <<'PY'
from pathlib import Path
import os
import sys
plugin, units = map(Path, sys.argv[1:])
def quoted(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
service = (plugin / 'systemd/nhl-standings-email.service').read_text()
service = '\n'.join('ExecStart=' + quoted(sys.executable) + ' ' + quoted(plugin / 'notifications.py') + ' check'
                    if line.startswith('ExecStart=') else line for line in service.splitlines()) + '\n'
# Pass the same XDG locations to the worker as this installation session.
for key in ('XDG_CONFIG_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME'):
    if key in os.environ:
        service += 'Environment=' + quoted(key + '=' + os.environ[key]) + '\n'
# Environment belongs to [Service], before any later section.
(units / 'nhl-standings-email.service').write_text(service)
(units / 'nhl-standings-email.timer').write_text((plugin / 'systemd/nhl-standings-email.timer').read_text())
PY
systemctl --user daemon-reload
systemctl --user enable --now nhl-standings-email.timer
printf '%s\n' 'Email checks installed. Add subscriptions and a Gmail app password in the NHL Settings panel.'
