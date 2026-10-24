#!/bin/sh
set -eu

# Run as the account that owns ~/haunt/haunt-audio-app, not with sudo.
if [ "$(id -u)" -eq 0 ]; then
  echo 'Run this script as the Pi user, without sudo.' >&2
  exit 1
fi

APP_DIR="$HOME/haunt/haunt-audio-app"
APP_USER="$(id -un)"
PYTHON="$APP_DIR/.venv/bin/python"
ENV_FILE="$APP_DIR/haunt.env"
AGENT="$APP_DIR/room_agent.py"
SERVICE='/etc/systemd/system/haunt-agent.service'

for item in "$APP_DIR" "$PYTHON" "$ENV_FILE" "$AGENT"; do
  if [ ! -e "$item" ]; then
    echo "Missing required path: $item" >&2
    echo 'Restore the project, Python environment, and haunt.env before installing.' >&2
    exit 1
  fi
done

if ! "$PYTHON" -c 'import flask, requests' >/dev/null 2>&1; then
  echo 'Python dependencies missing in .venv; run .venv/bin/pip install -r requirements.txt first.' >&2
  exit 1
fi

TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT HUP INT TERM
cat > "$TMP_FILE" <<UNIT
[Unit]
Description=Gui Gui Room Audio Agent
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$PYTHON $AGENT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

sudo install -m 644 "$TMP_FILE" "$SERVICE"
sudo systemctl daemon-reload
sudo systemctl enable haunt-agent.service
sudo systemctl reset-failed haunt-agent.service
sudo systemctl restart haunt-agent.service
sudo systemctl status haunt-agent.service --no-pager -l
