"""Independent four-servo agent for theatrical props only."""
import hmac, os, threading, time
from flask import Flask, jsonify, request
from gpiozero import AngularServo

app=Flask(__name__)
TOKEN=os.environ['HAUNT_TOKEN']
PINS={1:18,2:19,3:12,4:13}
LOCK=threading.RLock()
SERVOS={}
ANGLES={i:0 for i in PINS}

@app.before_request
def auth():
    if not hmac.compare_digest(request.headers.get('X-Haunt-Token',''),TOKEN):
        return jsonify(error='Unauthorized'),401

def get_servo(i):
    if i not in SERVOS:
        SERVOS[i]=AngularServo(PINS[i],min_angle=-90,max_angle=90,min_pulse_width=0.001,max_pulse_width=0.002,initial_angle=None)
    return SERVOS[i]

def move(i,angle):
    with LOCK:
        servo=get_servo(i)
        servo.angle=angle
        ANGLES[i]=angle
        # Stop sending PWM after a short movement; prevents holding jitter.
        time.sleep(0.55)
        servo.detach()

@app.get('/status')
def status():
    with LOCK:
        return jsonify(servos={str(i):{'angle':ANGLES[i],'gpio':PINS[i]} for i in PINS})

@app.post('/servo/<int:i>')
def set_angle(i):
    if i not in PINS: return jsonify(error='Invalid servo'),404
    value=(request.get_json(silent=True) or {}).get('angle')
    if type(value) not in (int,float) or not -45<=value<=45:
        return jsonify(error='Angle must be between -45 and 45'),400
    try: move(i,float(value))
    except Exception as e: return jsonify(error=f'Servo error: {type(e).__name__}'),500
    return jsonify(servo=i,angle=ANGLES[i])

@app.post('/centre')
def centre():
    try:
        for i in PINS: move(i,0)
    except Exception as e: return jsonify(error=f'Servo error: {type(e).__name__}'),500
    return status()

if __name__=='__main__':
    try: app.run(host='0.0.0.0',port=5053,threaded=True)
    finally:
        for servo in SERVOS.values(): servo.detach();servo.close()
