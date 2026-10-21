import json
import os
import signal
import subprocess
import threading
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)
TOKEN = os.environ['HAUNT_TOKEN']
AUDIO = Path.home() / 'haunt-audio'
AUDIO.mkdir(parents=True, exist_ok=True)
STATE_FILE = AUDIO / 'playback_state.json'
LOCK = threading.Lock()
PLAYER = None
PAUSED = False
CURRENT = None
VOLUME = 70
WANTED_STATE = 'stopped'


def save_state():
    """Atomically persist desired playback state; caller holds LOCK when running."""
    data = {'file': CURRENT, 'volume': VOLUME, 'loop': True, 'state': WANTED_STATE}
    tmp = STATE_FILE.with_suffix('.json.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_FILE)


def set_player_volume(p):
    if p and p.poll() is None and p.stdin:
        try:
            p.stdin.write(f'volume {round(VOLUME * 256 / 100)}\n')
            p.stdin.flush()
        except (BrokenPipeError, OSError):
            pass


def launch_player(path):
    p = subprocess.Popen(
        ['cvlc', '--intf', 'rc', '--rc-fake-tty', '--no-video', '--loop', path],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, text=True, bufsize=1,
    )
    set_player_volume(p)
    return p


def stop_player():
    global PLAYER, PAUSED
    if PLAYER and PLAYER.poll() is None:
        if PAUSED:
            PLAYER.send_signal(signal.SIGCONT)
        PLAYER.terminate()
        try:
            PLAYER.wait(timeout=3)
        except subprocess.TimeoutExpired:
            PLAYER.kill()
            PLAYER.wait()
    PLAYER = None
    PAUSED = False


def restore_state():
    global CURRENT, VOLUME, WANTED_STATE, PLAYER, PAUSED
    if not STATE_FILE.exists():
        return
    try:
        data = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        volume = data.get('volume', 70)
        VOLUME = int(volume) if isinstance(volume, (int, float)) and 0 <= volume <= 100 else 70
        candidate = data.get('file')
        # Only play a previously uploaded file inside our audio directory.
        if isinstance(candidate, str):
            p = Path(candidate).resolve()
            if p.parent == AUDIO.resolve() and p.is_file() and p.name.startswith('loop.'):
                CURRENT = str(p)
        desired = data.get('state', 'stopped')
        WANTED_STATE = desired if desired in ('playing', 'paused', 'stopped') else 'stopped'
        if not CURRENT:
            WANTED_STATE = 'stopped'
        if WANTED_STATE in ('playing', 'paused'):
            PLAYER = launch_player(CURRENT)
            if WANTED_STATE == 'paused':
                PLAYER.send_signal(signal.SIGSTOP)
                PAUSED = True
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        app.logger.error('Unable to restore playback state: %s', exc)


@app.before_request
def auth():
    if request.headers.get('X-Haunt-Token') != TOKEN:
        return jsonify(error='Unauthorized'), 401


def status():
    running = PLAYER is not None and PLAYER.poll() is None
    return {
        'file': CURRENT,
        'state': 'paused' if running and PAUSED else 'playing' if running else 'stopped',
        'volume': VOLUME,
    }


@app.get('/status')
def get_status():
    with LOCK:
        return jsonify(status())


@app.post('/upload')
def upload():
    global CURRENT, PLAYER, PAUSED, WANTED_STATE
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify(error='No file'), 400
    suffix = Path(f.filename).suffix.lower()
    if suffix not in ('.mp3', '.wav', '.ogg', '.flac', '.m4a'):
        return jsonify(error='Unsupported audio type'), 400
    if request.content_length and request.content_length > 40 * 1024 * 1024:
        return jsonify(error='File too large (40 MB max)'), 413
    with LOCK:
        tmp = AUDIO / ('incoming' + suffix)
        f.save(tmp)
        if tmp.stat().st_size > 40 * 1024 * 1024:
            tmp.unlink(missing_ok=True)
            return jsonify(error='File too large'), 413
        stop_player()
        path = AUDIO / ('loop' + suffix)
        for old in AUDIO.glob('loop.*'):
            old.unlink()
        tmp.replace(path)
        CURRENT = str(path)
        WANTED_STATE = 'playing'
        save_state()
        PLAYER = launch_player(CURRENT)
        PAUSED = False
        return jsonify(status())


@app.post('/play')
def play():
    global PLAYER, PAUSED, CURRENT, WANTED_STATE
    with LOCK:
        if not CURRENT:
            files = list(AUDIO.glob('loop.*'))
            if files:
                CURRENT = str(files[0])
        if not CURRENT or not Path(CURRENT).is_file():
            return jsonify(error='Upload a sound first'), 400
        if PLAYER and PLAYER.poll() is None and PAUSED:
            PLAYER.send_signal(signal.SIGCONT)
            PAUSED = False
        elif not PLAYER or PLAYER.poll() is not None:
            PLAYER = launch_player(CURRENT)
            PAUSED = False
        WANTED_STATE = 'playing'
        save_state()
        return jsonify(status())


@app.post('/pause')
def pause():
    global PAUSED, WANTED_STATE
    with LOCK:
        if PLAYER and PLAYER.poll() is None and not PAUSED:
            PLAYER.send_signal(signal.SIGSTOP)
            PAUSED = True
            WANTED_STATE = 'paused'
            save_state()
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
        save_state()
        return jsonify(status())


@app.post('/stop')
def stop():
    global WANTED_STATE
    with LOCK:
        WANTED_STATE = 'stopped'
        save_state()
        stop_player()
        return jsonify(status())


restore_state()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5051)
