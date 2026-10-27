#!/bin/sh
set -eu
cd "$(dirname "$0")"
APP="$(pwd)"
USER_NAME="$(id -un)"
[ -x "$APP/.venv/bin/python" ] || { echo 'Missing .venv'; exit 1; }
[ -f "$APP/haunt.env" ] || { echo 'Missing haunt.env'; exit 1; }
[ -f "$APP/room1_scene.json" ] || { echo 'Missing room1_scene.json'; exit 1; }
cat > /tmp/haunt-room1.service <<SERVICE
[Unit]
Description=Gui Gui Room 1 scene controller
After=network-online.target haunt-agent.service haunt-servo.service haunt-ultrasonic.service
Wants=network-online.target
[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$APP
EnvironmentFile=$APP/haunt.env
ExecStart=$APP/.venv/bin/python $APP/room1_scene.py
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
SERVICE
sudo cp /tmp/haunt-room1.service /etc/systemd/system/haunt-room1.service
sudo systemctl daemon-reload
sudo systemctl enable --now haunt-room1
sudo systemctl status haunt-room1 --no-pager -l
