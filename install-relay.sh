#!/bin/sh
set -eu
cd "$HOME/haunt/haunt-audio-app"
APP_DIR=$(pwd)
APP_USER=$(id -un)
.venv/bin/python -m pip install gpiozero lgpio
cat > /tmp/haunt-relay.service <<EOF
[Unit]
Description=Gui Gui two-channel relay agent
After=network.target
[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/haunt.env
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/relay_agent.py
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
sudo cp /tmp/haunt-relay.service /etc/systemd/system/haunt-relay.service
sudo systemctl daemon-reload
sudo systemctl enable --now haunt-relay
sudo systemctl status haunt-relay --no-pager -l
