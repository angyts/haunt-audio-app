#!/bin/sh
set -eu
cd "$HOME/haunt/haunt-audio-app"
APP_DIR=$(pwd)
APP_USER=$(id -un)
if ! test -x .venv/bin/python; then echo 'Missing .venv/bin/python; create venv first' >&2; exit 1; fi
if ! .venv/bin/python -c 'import flask, gpiozero' >/dev/null 2>&1; then
 echo 'Missing flask or gpiozero in venv. Do not delete existing venv. Check imports first.' >&2
 exit 1
fi
cat > /tmp/haunt-servo.service <<EOF
[Unit]
Description=Gui Gui four-servo agent
After=network.target
[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/haunt.env
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/servo_agent.py
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
sudo cp /tmp/haunt-servo.service /etc/systemd/system/haunt-servo.service
sudo systemctl daemon-reload
sudo systemctl enable --now haunt-servo
sudo systemctl status haunt-servo --no-pager -l
