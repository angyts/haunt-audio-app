#!/bin/sh
set -eu
cd "$HOME/haunt/haunt-audio-app"
APP_DIR=$(pwd)
APP_USER=$(id -un)
test -x .venv/bin/python || { echo 'Missing .venv/bin/python' >&2; exit 1; }
.venv/bin/python -c 'import flask, gpiozero' || { echo 'Missing flask/gpiozero in venv' >&2; exit 1; }
cat > /tmp/haunt-ultrasonic.service <<EOF
[Unit]
Description=Gui Gui ultrasonic distance monitor
After=network.target
[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/haunt.env
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/ultrasonic_agent.py
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
sudo cp /tmp/haunt-ultrasonic.service /etc/systemd/system/haunt-ultrasonic.service
sudo systemctl daemon-reload
sudo systemctl enable --now haunt-ultrasonic
sudo systemctl status haunt-ultrasonic --no-pager -l
