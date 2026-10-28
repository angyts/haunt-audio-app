#!/usr/bin/env python3
"""Gui Gui Ghost Gate: ultrasonic + GPIO5 reed + three separate audio tracks."""
import os, json, time, threading, signal, subprocess, tempfile, hmac
from pathlib import Path
from urllib.request import Request, urlopen
from flask import Flask, request, jsonify
from gpiozero import Button

app = Flask(__name__)
TOKEN = os.environ['HAUNT_TOKEN']
ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'room5_scene.json'
AUDIO_DIR = Path.home() / 'haunt-audio'
FILES = {'instruction': AUDIO_DIR/'instruction_gate.mp3', 'ritual': AUDIO_DIR/'ritual_gate.mp3'}
STOP = threading.Event()
LOCK = threading.RLock()
STATUS = {'phase':'disabled','distance_cm':None,'stale':True,'talisman_present':False,
          'talisman_held_seconds':0,'manual_stop':False,'elapsed_seconds':0,'error':None}
PLAYERS = {}
reed = Button(5, pull_up=True, bounce_time=0.05)

def set_status(**kw):
    with LOCK: STATUS.update(kw)

def api(port, path, data=None):
    headers={'X-Haunt-Token':TOKEN}
    if data is not None: headers['Content-Type']='application/json'
    req=Request(f'http://127.0.0.1:{port}{path}',headers=headers,
                data=json.dumps(data).encode() if data is not None else None,
                method='POST' if data is not None else 'GET')
    with urlopen(req, timeout=3) as r: return json.load(r)

def relay(number, on): api(5052,f'/relay/{number}',{'on':bool(on)})

def play(kind, volume, loop=False):
    p=PLAYERS.get(kind)
    if p is not None and p.poll() is None: return
    path=FILES[kind]
    if not path.is_file(): raise RuntimeError(f'Missing {path.name}; upload it first')
    args=['cvlc','--intf','rc','--rc-fake-tty','--no-video',
          '--loop' if loop else '--play-and-exit',str(path)]
    p=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,text=True)
    PLAYERS[kind]=p
    try:
        p.stdin.write(f'volume {round(volume*256/100)}\n');p.stdin.flush()
    except (OSError, ValueError): pass

def stop_audio(kind):
    p=PLAYERS.pop(kind,None)
    if p is None: return
    if p.poll() is None:
        p.terminate()
        try:p.wait(timeout=1.5)
        except subprocess.TimeoutExpired:p.kill();p.wait()
    if p.stdin:
        try:p.stdin.close()
        except OSError:pass

def validate(c):
    fields={'enabled','near_cm','trigger_cm','release_cm','cooldown_seconds',
            'talisman_confirm_seconds','exit_confirm_seconds','ritual_duration_seconds',
            'exit_light_seconds','instruction_volume','ritual_volume',
            'red_blink_cycles','red_blink_on_seconds','red_blink_off_seconds',
            'white_on_at_seconds'}
    if not isinstance(c,dict) or set(c)!=fields:
        raise ValueError('Missing or unknown fields: '+str(sorted(set(c)^fields)))
    if type(c['enabled']) is not bool:raise ValueError('enabled must be boolean')
    ranges={'near_cm':(5,300),'trigger_cm':(5,300),'release_cm':(5,300),
            'cooldown_seconds':(0,300),'talisman_confirm_seconds':(.1,5),
            'exit_confirm_seconds':(.5,15),'ritual_duration_seconds':(5,120),
            'exit_light_seconds':(0,300),'instruction_volume':(0,100),
            'ritual_volume':(0,100),'red_blink_cycles':(1,20),
            'red_blink_on_seconds':(.3,5),'red_blink_off_seconds':(.3,5),
            'white_on_at_seconds':(0,120)}
    for key,(lo,hi) in ranges.items():
        if type(c[key]) not in (int,float) or not lo<=c[key]<=hi:raise ValueError('Invalid '+key)
    if type(c['red_blink_cycles']) is not int:raise ValueError('red_blink_cycles must be integer')
    if not c['near_cm']<=c['trigger_cm']<c['release_cm']:raise ValueError('Require near <= trigger < release')
    if c['white_on_at_seconds']>=c['ritual_duration_seconds']:raise ValueError('White light must turn on during ritual')
    return c

def config():return validate(json.loads(CONFIG.read_text(encoding='utf-8')))

def set_lights(white,red):
    relay(1,white);relay(2,red)

def loop():
    phase='disabled';talisman_since=None;exit_since=None;start=0;last_end=-1e9
    white_done=False;blink_last=None;last_enabled=False
    while not STOP.wait(.12):
        try:
            c=config()
            with LOCK: manual=STATUS['manual_stop']
            enabled=c['enabled'] and not manual
            if not enabled:
                if phase!='disabled':
                    stop_audio('instruction');stop_audio('ritual')
                    # On disarm, keep theatrical lighting predictable. Safety/exit lights are independent.
                    set_lights(False,False)
                phase='disabled';last_enabled=False;talisman_since=None
                set_status(phase='manual stop' if manual else 'disabled',elapsed_seconds=0)
                continue
            sensor=api(5054,'/status')
            d=sensor.get('distance_cm')
            stale=bool(sensor.get('stale') or not sensor.get('enabled') or type(d) not in (int,float))
            present=bool(reed.is_pressed)
            now=time.monotonic()
            if present:
                if talisman_since is None:talisman_since=now
            else:talisman_since=None
            held=now-talisman_since if talisman_since is not None else 0
            set_status(distance_cm=d,stale=stale,talisman_present=present,
                       talisman_held_seconds=round(held,2),error=None)
            if phase=='disabled':
                set_lights(False,True)
                phase='idle';exit_since=None
            if phase=='idle':
                set_status(phase='idle',elapsed_seconds=0)
                if not stale and d<=c['trigger_cm'] and now-last_end>=c['cooldown_seconds']:
                    play('instruction',c['instruction_volume'],loop=True)
                    phase='approach'
            elif phase=='approach':
                set_status(phase='approach')
                if stale:
                    stop_audio('instruction');phase='idle';exit_since=None
                elif held>=c['talisman_confirm_seconds']:
                    stop_audio('instruction')
                    play('ritual',c['ritual_volume'])
                    start=now;phase='ritual';white_done=False;blink_last=None
                elif not stale and d>=c['release_cm']:
                    if exit_since is None:exit_since=now
                    if now-exit_since>=c['exit_confirm_seconds']:
                        stop_audio('instruction');phase='idle';exit_since=None
                else:exit_since=None
            elif phase=='ritual':
                elapsed=now-start
                set_status(phase='ritual',elapsed_seconds=round(elapsed,1))
                if not white_done and elapsed>=c['white_on_at_seconds']:
                    set_lights(True,False);white_done=True
                elif not white_done:
                    period=c['red_blink_on_seconds']+c['red_blink_off_seconds']
                    blink_duration=period*c['red_blink_cycles']
                    on=(elapsed%period)<c['red_blink_on_seconds'] if elapsed<blink_duration else True
                    if on!=blink_last:relay(2,on);blink_last=on
                if elapsed>=c['ritual_duration_seconds']:
                    stop_audio('ritual')
                    set_lights(True,False)
                    phase='exit';start=now;exit_since=None
            elif phase=='exit':
                elapsed=now-start
                set_status(phase='exit',elapsed_seconds=round(elapsed,1))
                # Never reset during the minimum exit light interval; require both removal and distance clearance.
                if elapsed>=c['exit_light_seconds'] and not present and not stale and d>=c['release_cm']:
                    if exit_since is None:exit_since=now
                    if now-exit_since>=c['exit_confirm_seconds']:
                        set_lights(False,True);phase='idle';last_end=now;exit_since=None
                else:exit_since=None
        except Exception as exc:
            set_status(error=f'{type(exc).__name__}: {str(exc)[:140]}')
            print('Room5:',repr(exc),flush=True)
            STOP.wait(.8)
    stop_audio('instruction');stop_audio('ritual')
    try:set_lights(False,False)
    except Exception:pass
    reed.close()

@app.before_request
def auth():
    if not hmac.compare_digest(request.headers.get('X-Haunt-Token',''),TOKEN):
        return jsonify(error='Unauthorized'),401

@app.route('/config',methods=['GET','PUT'])
def configuration():
    if request.method=='GET':return jsonify(config())
    try:
        if request.content_length and request.content_length>65536:return jsonify(error='Too large'),413
        c=validate(request.get_json(force=True))
        with tempfile.NamedTemporaryFile(mode='w',dir=ROOT,delete=False,encoding='utf-8') as f:
            json.dump(c,f,indent=2);f.write('\n');name=f.name
        os.replace(name,CONFIG)
        return jsonify(ok=True)
    except (ValueError,TypeError) as exc:return jsonify(error=str(exc)),400

@app.get('/status')
def status():
    with LOCK:return jsonify(dict(STATUS))

@app.post('/override')
def override():
    value=(request.get_json(silent=True) or {}).get('stop')
    if type(value) is not bool:return jsonify(error='stop must be boolean'),400
    set_status(manual_stop=value)
    return status()

@app.post('/audio/<kind>')
def upload(kind):
    if kind not in FILES:return jsonify(error='Unknown audio slot'),404
    f=request.files.get('file')
    if not f or Path(f.filename).suffix.lower()!='.mp3':return jsonify(error='MP3 required'),400
    if request.content_length and request.content_length>20*1024*1024:return jsonify(error='20 MB max'),413
    AUDIO_DIR.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=AUDIO_DIR,delete=False) as temp:
        size=0
        while True:
            chunk=f.stream.read(65536)
            if not chunk:break
            size+=len(chunk)
            if size>20*1024*1024:
                name=temp.name;temp.close();os.unlink(name)
                return jsonify(error='Too large'),413
            temp.write(chunk)
        name=temp.name
    os.replace(name,FILES[kind]);return jsonify(ok=True)

def shutdown(*_):STOP.set()
signal.signal(signal.SIGTERM,shutdown)
signal.signal(signal.SIGINT,shutdown)
if __name__=='__main__':
    threading.Thread(target=loop,daemon=True).start()
    app.run(host='0.0.0.0',port=5058,threaded=True)
