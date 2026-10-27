#!/bin/sh
set -eu
cd "$HOME/haunt/haunt-audio-app"
sudo cp haunt-room3.service /etc/systemd/system/haunt-room3.service
sudo systemctl daemon-reload
sudo systemctl enable --now haunt-room3.service
sudo systemctl status haunt-room3.service --no-pager -l
