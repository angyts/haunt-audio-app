"""Two-channel relay API. Private trusted LAN only; use external GPIO-safe driver."""
import os
from flask import Flask, jsonify, request
from gpiozero import OutputDevice

app = Flask(__name__)
TOKEN = os.environ['HAUNT_TOKEN']
PINS = {1: int(os.getenv('RELAY_1_GPIO', '17')), 2: int(os.getenv('RELAY_2_GPIO', '27'))}
RELAYS = {n: OutputDevice(pin, active_high=False, initial_value=False) for n, pin in PINS.items()}

def authorized():
    import hmac
    return hmac.compare_digest(request.headers.get('X-Haunt-Token', ''), TOKEN)

@app.before_request
def auth():
    if not authorized(): return jsonify(error='Unauthorized'), 401

@app.get('/status')
def status():
    return jsonify(relays={str(n): {'on': r.is_active, 'gpio': PINS[n]} for n,r in RELAYS.items()})

@app.post('/relay/<int:channel>')
def switch(channel):
    if channel not in RELAYS: return jsonify(error='Invalid relay channel'), 404
    data = request.get_json(silent=True) or {}
    if type(data.get('on')) is not bool: return jsonify(error='on must be true or false'), 400
    if data['on']: RELAYS[channel].on()
    else: RELAYS[channel].off()
    return jsonify(channel=channel, on=RELAYS[channel].is_active)

if __name__ == '__main__':
    try: app.run(host='0.0.0.0', port=5052, debug=False, threaded=True)
    finally:
        for relay in RELAYS.values(): relay.off(); relay.close()
