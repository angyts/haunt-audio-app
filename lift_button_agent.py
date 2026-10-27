"""Single owner for lift GPIO6. Future scene controller should poll /status, not claim GPIO6 again."""
import os
import time
import threading
from flask import Flask, jsonify, request
from gpiozero import Button

app = Flask(__name__)
TOKEN = os.environ['HAUNT_TOKEN']
button = Button(6, pull_up=True, bounce_time=0.05)
lock = threading.Lock()
state = {'press_count': 0, 'last_pressed_at': None, 'pressed_since': None}

def pressed():
    with lock:
        state['press_count'] += 1
        state['last_pressed_at'] = time.time()
        state['pressed_since'] = state['last_pressed_at']

def released():
    with lock:
        state['pressed_since'] = None

button.when_pressed = pressed
button.when_released = released
if button.is_pressed:
    pressed()

@app.before_request
def authenticate():
    if request.headers.get('X-Haunt-Token') != TOKEN:
        return jsonify(error='Unauthorized'), 401

@app.get('/status')
def status():
    with lock:
        s = dict(state)
    active = button.is_pressed
    held = max(0.0, time.time() - s['pressed_since']) if active and s['pressed_since'] else 0.0
    return jsonify(pressed=active, stuck=held >= 10.0,
                   held_seconds=round(held, 2), press_count=s['press_count'],
                   last_pressed_at=s['last_pressed_at'], gpio=6)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5055, threaded=True)
