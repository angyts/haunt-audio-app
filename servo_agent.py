#!/usr/bin/env python3
"""Four-servo API; commands detach after movement and remember last requested angle."""
import hmac,os,threading,time
from flask import Flask,jsonify,request
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
        SERVOS[i]=AngularServo(PINS[i],min_angle=-90,max_angle=90,min_pulse_width=.001,max_pulse_width=.002,initial_angle=None)
    return SERVOS[i]
def valid(i,a):
    return type(i) is int and i in PINS and type(a) in (int,float) and -90<=a<=90
def move_group(moves):
    with LOCK:
        active=[]
        try:
            for i,angle in moves:
                servo=get_servo(i)
                servo.angle=float(angle)
                ANGLES[i]=float(angle)
                active.append(servo)
            time.sleep(.55)
        finally:
            for servo in active: servo.detach()
OSC_STOP=threading.Event()
OSC_THREAD=None
OSC_INFO={'running':False,'servo':None}
def stop_oscillation():
    global OSC_THREAD
    OSC_STOP.set()
    t=OSC_THREAD
    if t and t.is_alive(): t.join(timeout=2)
    OSC_THREAD=None
    OSC_INFO.update(running=False,servo=None)
def oscillate_loop(i,low,high,step,delay):
    try:
        # Each movement is a real servo command; GPIOZero PWM remains active while sweeping.
        with LOCK:
            s=get_servo(i)
            current=float(ANGLES[i])
            while not OSC_STOP.is_set():
                for target in (high,low):
                    while abs(current-target)>0.001 and not OSC_STOP.is_set():
                        delta=min(step,abs(target-current))
                        current+=delta if target>current else -delta
                        s.angle=current
                        ANGLES[i]=round(current,2)
                        if OSC_STOP.wait(delay):break
            s.detach()
    except Exception as exc:
        app.logger.error('Oscillation failed: %r',exc)
    finally:
        try: get_servo(i).detach()
        except Exception: pass
        OSC_INFO.update(running=False,servo=None)
@app.post('/oscillate/start')
def oscillate_start():
    global OSC_THREAD
    b=request.get_json(silent=True) or {}
    i=b.get('servo');low=b.get('min_angle');high=b.get('max_angle')
    step=b.get('step',3);delay=b.get('step_delay',0.04)
    if not valid(i,low) or not valid(i,high) or low>=high or type(step) not in (int,float) or not 1<=step<=15 or type(delay) not in (int,float) or not .02<=delay<=.3:
        return jsonify(error='Invalid oscillation settings'),400
    stop_oscillation()
    OSC_STOP.clear();OSC_INFO.update(running=True,servo=i)
    OSC_THREAD=threading.Thread(target=oscillate_loop,args=(i,low,high,step,delay),daemon=True)
    OSC_THREAD.start()
    return jsonify(ok=True,oscillation=dict(OSC_INFO))
@app.post('/oscillate/stop')
def oscillate_stop():
    stop_oscillation()
    return jsonify(ok=True,oscillation=dict(OSC_INFO))
@app.get('/status')
def status():
    with LOCK: return jsonify(servos={str(i):{'angle':ANGLES[i],'gpio':PINS[i]} for i in PINS},oscillation=dict(OSC_INFO))
@app.post('/servo/<int:i>')
def set_angle(i):
    angle=(request.get_json(silent=True) or {}).get('angle')
    if not valid(i,angle): return jsonify(error='Invalid servo or angle (must be -90..90)'),400
    stop_oscillation()
    try: move_group([(i,angle)])
    except Exception as e: return jsonify(error='Servo error: '+type(e).__name__),500
    return jsonify(servo=i,angle=ANGLES[i])
@app.post('/group')
def group():
    body=request.get_json(silent=True) or {}
    moves=body.get('moves')
    if not isinstance(moves,list) or not 1<=len(moves)<=4: return jsonify(error='Expected 1..4 moves'),400
    parsed=[]
    for m in moves:
        if not isinstance(m,dict) or not valid(m.get('servo'),m.get('angle')): return jsonify(error='Invalid move'),400
        parsed.append((m['servo'],m['angle']))
    if len({i for i,a in parsed})!=len(parsed): return jsonify(error='Duplicate servo'),400
    stop_oscillation()
    try: move_group(parsed)
    except Exception as e: return jsonify(error='Servo error: '+type(e).__name__),500
    return status()
@app.post('/centre')
def centre():
    stop_oscillation()
    try: move_group([(i,0) for i in PINS])
    except Exception as e: return jsonify(error='Servo error: '+type(e).__name__),500
    return status()
if __name__=='__main__':
    try: app.run(host='0.0.0.0',port=5053,threaded=True)
    finally:
        for servo in SERVOS.values(): servo.detach();servo.close()
