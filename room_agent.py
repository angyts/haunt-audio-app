import os, subprocess, threading
from pathlib import Path
from flask import Flask, request, jsonify

app = Flask(__name__)
TOKEN = os.environ['HAUNT_TOKEN']
AUDIO = Path.home() / 'haunt-audio'
AUDIO.mkdir(exist_ok=True)
LOCK = threading.Lock()
PLAYER = None
PAUSED = False
CURRENT = None
VOLUME = 70

def launch_player(path):
    p = subprocess.Popen(['cvlc','--intf','rc','--rc-fake-tty','--no-video','--loop',path], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    set_player_volume(p)
    return p

def set_player_volume(p):
    if p and p.poll() is None and p.stdin:
        try:
            p.stdin.write(f'volume {round(VOLUME*256/100)}\n')
            p.stdin.flush()
        except (BrokenPipeError, OSError):
            pass


@app.before_request
def auth():
    if request.headers.get('X-Haunt-Token') != TOKEN:
        return jsonify(error='Unauthorized'), 401

def stop_player():
    global PLAYER, PAUSED
    if PLAYER and PLAYER.poll() is None:
        PLAYER.terminate()
        try: PLAYER.wait(timeout=3)
        except subprocess.TimeoutExpired: PLAYER.kill(); PLAYER.wait()
    PLAYER = None
    PAUSED = False

def status():
    running = PLAYER is not None and PLAYER.poll() is None
    return {'file': CURRENT, 'state': 'paused' if running and PAUSED else 'playing' if running else 'stopped', 'volume': VOLUME}

@app.get('/status')
def get_status():
    with LOCK: return jsonify(status())

@app.post('/upload')
def upload():
    global CURRENT
    f = request.files.get('file')
    if not f or not f.filename: return jsonify(error='No file'), 400
    suffix = Path(f.filename).suffix.lower()
    if suffix not in ('.mp3','.wav','.ogg','.flac','.m4a'):
        return jsonify(error='Unsupported audio type'), 400
    # No unbounded uploads to SD card
    if request.content_length and request.content_length > 40 * 1024 * 1024:
        return jsonify(error='File too large (40 MB max)'), 413
    with LOCK:
        stop_player()
        path = AUDIO / ('loop' + suffix)
        tmp = AUDIO / ('incoming' + suffix)
        f.save(tmp)
        if tmp.stat().st_size > 40 * 1024 * 1024:
            tmp.unlink(missing_ok=True)
            return jsonify(error='File too large'), 413
        for old in AUDIO.glob('loop.*'): old.unlink()
        tmp.replace(path)
        CURRENT = str(path)
        global PLAYER, PAUSED
        PLAYER = launch_player(CURRENT)
        PAUSED = False
        return jsonify(status())

@app.post('/play')
def play():
    global PLAYER, PAUSED, CURRENT
    with LOCK:
        if not CURRENT:
            files = list(AUDIO.glob('loop.*'))
            if files: CURRENT = str(files[0])
        if not CURRENT: return jsonify(error='Upload a sound first'), 400
        if PLAYER and PLAYER.poll() is None and PAUSED:
            PLAYER.send_signal(__import__('signal').SIGCONT)
            PAUSED = False
        elif not PLAYER or PLAYER.poll() is not None:
            PLAYER = launch_player(CURRENT)
            PAUSED = False
        return jsonify(status())

@app.post('/pause')
def pause():
    global PAUSED
    with LOCK:
        if PLAYER and PLAYER.poll() is None and not PAUSED:
            PLAYER.send_signal(__import__('signal').SIGSTOP)
            PAUSED = True
        return jsonify(status())

@app.post('/volume')
def volume():
    global VOLUME
    data = request.get_json(silent=True) or {}
    value = data.get('volume')
    if type(value) not in (int, float) or not 0 <= value <= 100:
        return jsonify(error='Volume must be 0 to 100'), 400
    with LOCK:
        VOLUME = int(value)
        set_player_volume(PLAYER)
        return jsonify(status())

@app.post('/stop')
def stop():
    with LOCK:
        stop_player()
        return jsonify(status())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5051)
