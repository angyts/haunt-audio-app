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

  
Gui Gui Voice Mimic v1
======================
Add voice_receiver.py and voice_sender.py to the existing GitHub repo. No existing Python files are changed.

The sender uses Python standard library and works with Python 3.13.

On corridor: use existing venv with Flask installed. Copy receiver service, set shared VOICE_TOKEN in voice.env, and start.
On mic: use an environment with working audioop and create voice.env with same token. Install ALSA and ffmpeg. Start sender.

These services bind receiver to port 5012 on the local network. Keep on trusted isolated LAN; do not port-forward. Audio clips are temporary and deleted after playback.

# Gui Gui Relay v4

Add `master.py`, `relay_agent.py`, `install-relay.sh` to the existing GitHub project. Do not replace room_agent.py, voice_sender.py or voice_receiver.py. The master.py is based on Voice Lab v2.

**Electrical prerequisite:** Earlier IN1 measured 4.4V. Do not connect Pi GPIO directly to an unverified 5V-biased relay input. Use a verified 3.3V-safe transistor/open-collector driver or level interface. Power off all supplies before changing wiring. Test without lighting loads first. Keep exit/emergency lighting independent. Relays are active LOW, GPIO17 and GPIO27, and start OFF. These are software commands, not a safety interlock.

For each of the five speaker Pis (`haunt-master`, `haunt-forest`, `haunt-corridor`, `haunt-lift`, `haunt-gate`):

```sh
cd ~/haunt/haunt-audio-app
git pull
sh install-relay.sh
```

The script uses each Pi's actual username and directory. `haunt.env` must contain the existing shared `HAUNT_TOKEN`. The relay agent listens on port 5052 on the local network. Keep the Wi-Fi private and do not forward ports 5000, 5051, 5052 or the voice services to the internet.

On `haunt-master` restart the dashboard after pulling:

```sh
sudo systemctl restart haunt-master
```

Check locally:

```sh
systemctl status haunt-relay --no-pager
```

Dashboard at http://haunt-master.local:5000 groups sound and two relay buttons per room. `haunt-mic` has no relays. The GPIO backend may need adjustment for your Raspberry Pi OS version; if pip cannot install `lgpio`, send the exact error instead of forcing the installation. Restarting a relay service resets both channels OFF by design.

# Gui Gui Servo v5

This is an add-on to the working v4 dashboard. Replace **master.py only on haunt-master**, and add **servo_agent.py** and **install-servo.sh** to the GitHub repo. Do not replace room_agent.py, relay_agent.py, voice_sender.py or any existing .env files.

GPIO (BCM): Servo1=18, Servo2=19, Servo3=12, Servo4=13. Relay GPIO17/27 unchanged. Servos use separately protected external 5V power and shared signal ground, never Pi GPIO for motor power. Disconnect all power when wiring. Do not use for doors, emergency lighting, or safety mechanisms. Keep network private and do not expose ports publicly.

The servo agent uses the existing HAUNT_TOKEN in haunt.env, port 5053, and gpiozero already available in the Pi's venv. No pip installation or rebuilding lgpio is attempted. Start with haunt-gate only; deploy to other room Pis after successful test. The four sliders allow -45 to +45 degrees, and the servo signal detaches after 0.55s to reduce jitter. Detached servos do not hold their position; do not attach load-bearing props. The dashboard displays the last commanded angle, not measured shaft position. Restart does not move servos until commanded.

Deployment:
1. Commit files to GitHub.
2. On haunt-gate: `cd ~/haunt/haunt-audio-app && git pull && sh install-servo.sh`.
3. On haunt-master: `cd ~/haunt/haunt-audio-app && git pull && sudo systemctl restart haunt-master`.
4. Open `http://haunt-master.local:5000`; use Gate servo sliders.
5. Later run `sh install-servo.sh` on haunt-master, haunt-forest, haunt-corridor, haunt-lift if servos are physically installed there.

Troubleshoot: `journalctl -u haunt-servo -n 50 --no-pager -l`. The agent's Python must be able to import flask and gpiozero; if not, check existing venv packages. If GPIO pin busy, stop test_servo.py before starting service. Servo jitter can be caused by software PWM; hardware-timed PWM is a future enhancement.
