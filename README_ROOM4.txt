GUI GUI ROOM 4 - GITHUB UPDATE

Upload source files to repository root:
 master.py (dashboard; use on haunt-master)
 room4_scene.py, room4_scene.json
 lift_button_agent.py, haunt-lift-button.service, haunt-room4.service, install-room4.sh

MP3 files are bundled for convenience. Do NOT need to commit MP3s to GitHub:
 - On main dashboard select Lift, upload ambient_lift.mp3; click Play to loop.
 - On Scene Manager Room 4, upload creepy_lift.mp3.

haunt-master:
 cd ~/haunt/haunt-audio-app && git pull
 .venv/bin/python -m py_compile master.py
 sudo systemctl restart haunt-master

haunt-lift:
 cd ~/haunt/haunt-audio-app && git pull
 sh install-room4.sh

Open http://haunt-master.local:5000/scenes and upload the journey MP3.
Start disabled. Arm after testing manual button, sensor, servo and relays.

GPIO6 physical 31 / GND physical 34 is owned by lift_button_agent.py (port 5055).
Scene controller uses port 5057. Other agents: audio 5051, relays 5052,
servo 5053, ultrasonic 5054. All use HAUNT_TOKEN.

Defaults: near 30, trigger 60, release 70 cm; 38.77s journey;
actor_light_seconds=30. White off at 20s, red blinks from 24s,
arrow moves at 27s, red remains on through actor and until confirmed exit.
The actor lighting is NOT turned off after 30s until distance confirms exit.
Manual STOP overrides the full journey and switches theatrical relays off.

CAUTIONS:
 - Audio duration is measured 38.7657s. VLC start latency can shift cues.
 - Existing audio agent loop is paused during the journey, resumed on exit.
 - Room 4 scene is disabled by default. The code is syntax checked but NOT hardware tested.
 - Do not rely on theatrical lights for safe egress or actor visibility.
 - If sensor fails while waiting for exit, red stays ON; manual STOP available.
 - Dashboard edits room4_scene.json on the Pi; git pull may conflict with edits.
 - Keep scene control on trusted LAN; no independent browser authentication.
