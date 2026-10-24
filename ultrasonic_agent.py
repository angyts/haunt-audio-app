import os
import time
import threading
from flask import Flask, jsonify, request
from gpiozero import DistanceSensor

app = Flask(__name__)
TOKEN = os.environ['HAUNT_TOKEN']
TRIG = int(os.environ.get('ULTRASONIC_TRIG', '23'))
ECHO = int(os.environ.get('ULTRASONIC_ECHO', '24'))
MAX_DISTANCE = float(os.environ.get('ULTRASONIC_MAX_METRES', '3'))
lock = threading.Lock()
state = {'distance_cm': None, 'threshold_cm': 80, 'enabled': True, 'updated_at': None, 'error': None}

sensor = DistanceSensor(trigger=TRIG, echo=ECHO, max_distance=MAX_DISTANCE, queue_len=5)

def sample():
    while True:
        try:
            cm = round(sensor.distance * 100, 1)
            with lock:
                state.update(distance_cm=cm, updated_at=time.time(), error=None)
        except Exception as exc:
            with lock:
                state['error'] = type(exc).__name__
        time.sleep(0.3)

threading.Thread(target=sample, daemon=True).start()

@app.before_request
def auth():
    if request.headers.get('X-Haunt-Token') != TOKEN:
        return jsonify(error='Unauthorized'), 401

@app.get('/status')
def status():
    with lock:
        result = dict(state)
    result['detected'] = bool(result['enabled'] and result['distance_cm'] is not None and result['distance_cm'] <= result['threshold_cm'])
    result['stale'] = result['updated_at'] is None or time.time() - result['updated_at'] > 3
    result['gpio'] = {'trigger': TRIG, 'echo': ECHO}
    return jsonify(result)

@app.post('/settings')
def settings():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(error='Expected JSON object'), 400
    if any(k not in ('threshold_cm', 'enabled') for k in body):
        return jsonify(error='Unsupported setting'), 400
    if 'threshold_cm' in body:
        try:
            val = float(body['threshold_cm'])
            if not 10 <= val <= min(MAX_DISTANCE * 100, 300):
                raise ValueError()
        except (ValueError, TypeError):
            return jsonify(error='Threshold must be between 10 cm and maximum range'), 400
    with lock:
        if 'threshold_cm' in body:
            state['threshold_cm'] = val
        if 'enabled' in body:
            if not isinstance(body['enabled'], bool):
                return jsonify(error='enabled must be boolean'), 400
            state['enabled'] = body['enabled']
    return status()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5054, threaded=True)
