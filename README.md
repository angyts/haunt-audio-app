Gui Gui Voice Mimic v1
======================
Add voice_receiver.py and voice_sender.py to the existing GitHub repo. No existing Python files are changed.

The sender uses Python standard library and works with Python 3.13.

On corridor: use existing venv with Flask installed. Copy receiver service, set shared VOICE_TOKEN in voice.env, and start.
On mic: use an environment with working audioop and create voice.env with same token. Install ALSA and ffmpeg. Start sender.

These services bind receiver to port 5012 on the local network. Keep on trusted isolated LAN; do not port-forward. Audio clips are temporary and deleted after playback.
