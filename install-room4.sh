#!/bin/sh
set -eu
cd "$HOME/haunt/haunt-audio-app"
.venv/bin/python -m py_compile room4_scene.py
sudo cp haunt-lift-button.service /etc/systemd/system/haunt-lift-button.service
sudo cp haunt-room4.service /etc/systemd/system/haunt-room4.service
sudo systemctl daemon-reload
sudo systemctl enable --now haunt-lift-button.service
sudo systemctl enable --now haunt-room4.service
sudo systemctl status haunt-room4.service --no-pager -l
