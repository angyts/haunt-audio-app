GUI GUI ROOM 5 - GHOST GATE

GitHub repository root: upload master.py, room5_scene.py, room5_scene.json,
haunt-room5.service, install-room5.sh. Audio MP3s can be uploaded through
the dashboard; they are included in this ZIP for convenience.

On haunt-master:
  cd ~/haunt/haunt-audio-app
  git pull
  .venv/bin/python -m py_compile master.py
  sudo systemctl restart haunt-master

On haunt-gate:
  cd ~/haunt/haunt-audio-app
  git pull
  sh install-room5.sh

Dashboard: http://haunt-master.local:5000/scenes
  Upload instruction_gate.mp3 to the Room 5 instruction slot.
  Upload ritual_gate.mp3 to the Room 5 ritual slot.
  On the main Gate audio dashboard, upload ambient_gate.mp3 and start looping.
  Confirm ultrasonic data and GPIO5 reed state. Then arm Room 5.

Default testing distances: near=20, trigger=35, release=45 cm.
The scene starts DISABLED.

Sequence: idle red theatrical light; approach starts looping instruction;
0.5s stable reed closure starts ritual; red blink; white on at 6 seconds;
20-second ritual plays in full; white stays on for minimum 30 more seconds;
reset only when talisman removed AND ultrasonic reads >=45cm for 2 seconds.
Stale ultrasonic data will not cause an exit reset. A stuck reed switch
prevents reset; use dashboard Stop to cancel effects.

CRITICAL SAFETY: This system NEVER locks, latches or actuates the exit door.
The exit must remain operable without power, the talisman, or the Pi.
Independent emergency/exit lighting must remain on; have the actor supervise
and help children with the heavy door. Do not connect safety lighting to relays.

GPIO5 physical pin 29, GND physical pin 30, using Pi internal pull-up.
Do not connect external voltage to the GPIO. GPIO5 must not be claimed by
another active process.

The scene service uses port 5058 and the existing HAUNT_TOKEN.
Requires Flask, gpiozero, working cvlc, existing relay/ultrasonic/audio services.
If the room service cannot control the relays, check its logs:
  sudo journalctl -u haunt-room5 -n 60 --no-pager -l
