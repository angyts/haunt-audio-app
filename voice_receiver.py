import os, subprocess, tempfile, threading
from flask import Flask, request, jsonify

app = Flask(__name__)
TOKEN = os.environ.get('VOICE_TOKEN', '')
DEVICE = os.environ.get('VOICE_PLAYBACK_DEVICE', 'plughw:0,0')
MAX_BYTES = 400000
lock = threading.Lock()

def play_and_delete(path):
    try:
        subprocess.run(['aplay', '-q', '-D', DEVICE, path], timeout=15, check=True)
    finally:
        os.unlink(path)
        lock.release()

@app.post('/voice')
def voice():
    if not TOKEN or request.headers.get('X-Voice-Token') != TOKEN:
        return jsonify(error='unauthorized'), 401
    if not lock.acquire(blocking=False):
        return jsonify(error='busy'), 429
    path = None
    try:
        data = request.get_data(cache=False)
        if not data or len(data) > MAX_BYTES or request.content_length and request.content_length > MAX_BYTES:
            lock.release()
            return jsonify(error='invalid size'), 413
        with tempfile.NamedTemporaryFile(prefix='guigui-', suffix='.wav', delete=False) as f:
            path = f.name
            f.write(data)
        threading.Thread(target=play_and_delete, args=(path,), daemon=True).start()
        return jsonify(ok=True), 202
    except Exception:
        if path and os.path.exists(path): os.unlink(path)
        lock.release()
        raise

@app.get('/health')
def health():
    return jsonify(ok=True, busy=lock.locked())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5012, threaded=True)
