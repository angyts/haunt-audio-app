# Gui Gui Audio Control v1

A simple LAN-only Flask master dashboard and room audio agents. Each room stores its uploaded audio locally and loops with VLC. One room agent per speaker Pi; the microphone Pi does not need this agent.

## Install on each audio Pi (including haunt-master)

Copy this directory to `/home/haunt/haunt-audio-app` (e.g. with `scp -r`). Then SSH into each Pi:

```bash
sudo apt update
sudo apt install -y vlc python3-venv
cd ~/haunt-audio-app
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
printf 'HAUNT_TOKEN=%s\n' 'REPLACE_WITH_A_LONG_RANDOM_SHARED_SECRET' > haunt.env
chmod 600 haunt.env
sudo cp haunt-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now haunt-agent
sudo systemctl status haunt-agent
```

Use the SAME token on all audio Pis. For a random token, run `openssl rand -hex 24` once and copy it to each Pi's `haunt.env`. Keep the token private.

On `haunt-master` only, also run:

```bash
sudo cp haunt-master.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now haunt-master
```

Open `http://haunt-master.local:5000` on your LAN.

## Important
- Room names resolve via mDNS. If `.local` names fail, replace entries in `ROOMS` in `master.py` with the corresponding Pi LAN IPs.
- The audio agent uses VLC's default audio output. Test with `cvlc --intf dummy --play-and-exit ~/some-test.mp3` and configure the Pi's output device as necessary.
- Uploaded audio is saved in `~/haunt-audio/loop.<extension>` on the room Pi. Upload replaces the previous loop and immediately starts playing it.
- Pause uses POSIX SIGSTOP/SIGCONT to freeze/resume VLC. Stop terminates VLC. A paused loop may not auto-resume after reboot; playback is intentionally not started automatically on boot.
- The master dashboard has no login. Use ONLY on a private, trusted LAN. Do not expose ports 5000 or 5051 to the internet or configure router port forwarding. For stronger protection, add dashboard authentication and network restrictions.
- The room API uses a shared token, but HTTP traffic is unencrypted on the local network. Do not use over an untrusted network.
- VLC on Raspberry Pi OS Lite may require an audio backend/output selection depending on the Pi and speaker connection. This is a prototype and should be tested with each speaker before the event.
