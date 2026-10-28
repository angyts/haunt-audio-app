#!/bin/sh
set -eu
cd "$HOME/haunt/haunt-audio-app"
.venv/bin/python -m py_compile room5_scene.py master.py
sudo cp haunt-room5.service /etc/systemd/system/haunt-room5.service
sudo systemctl daemon-reload
sudo systemctl enable --now haunt-room5.service
sudo systemctl status haunt-room5.service --no-pager -l
