#!/bin/sh
set -eu
cd "$HOME/haunt/haunt-audio-app"
sudo cp haunt-room2.service /etc/systemd/system/haunt-room2.service
sudo systemctl daemon-reload
sudo systemctl enable --now haunt-room2.service
sudo systemctl restart haunt-servo.service
sudo systemctl status haunt-room2.service --no-pager -l
