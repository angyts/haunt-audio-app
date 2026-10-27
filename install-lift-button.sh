#!/bin/sh
set -eu
cd "$HOME/haunt/haunt-audio-app"
sudo cp haunt-lift-button.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now haunt-lift-button.service
sudo systemctl status haunt-lift-button.service --no-pager -l
