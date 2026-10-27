#!/usr/bin/env python3
"""Gui Gui Room 3: distance-triggered laughter and sequential shadow servos."""
import hmac, json, os, signal, subprocess, tempfile, threading, time
from pathlib import Path
from urllib.request import Request, urlopen
from flask import Flask, jsonify, request

app = Flask(__name__)
TOKEN = os.environ['HAUNT_TOKEN']
ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'room3_scene.json'
AUDIO = Path.home() / 'haunt-audio' / 'laughter.mp3'
STOP = threading.Event()
CANCEL = threading.Event()
LOCK = threading.RLock()
state = {'phase':'disabled','distance_cm':None,'stale':True,'manual_stop':False,'sequence_running':False,'error':None}
player = None
worker = None

def api(port, path, body=None):
    headers = {'X-Haunt-Token': TOKEN}
    if body is not None: headers['Content-Type'] = 'application/json'
    req = Request(f'http://127.0.0.1:{port}{path}', headers=headers,
                  data=json.dumps(body).encode() if body is not None else None,
                  method='POST' if body is not None else 'GET')
    with urlopen(req, timeout=3) as response: return json.load(response)

def number(v, lo, hi):
    return type(v) in (int,float) and lo <= v <= hi

def validate(d):
    if not isinstance(d,dict): raise ValueError('JSON object required')
    keys = {'enabled','near_cm','trigger_cm','release_cm','cooldown_seconds','laughter_volume','servo_trigger_cm','on_arm','on_close','on_exit'}
    if set(d) != keys: raise ValueError('Missing or unknown fields: '+str(sorted(set(d)^keys)))
    if type(d['enabled']) is not bool: raise ValueError('enabled must be boolean')
    if not all(number(d[k],10,300) for k in ('near_cm','trigger_cm','release_cm','servo_trigger_cm')): raise ValueError('Invalid distances')
    if not d['near_cm'] <= d['servo_trigger_cm'] <= d['trigger_cm'] < d['release_cm']: raise ValueError('Require near <= servo_trigger <= trigger < release')
    if not number(d['cooldown_seconds'],0,300) or not number(d['laughter_volume'],0,100): raise ValueError('Invalid cooldown or volume')
    for field in ('on_arm','on_close','on_exit'):
        steps=d[field]
        if not isinstance(steps,list) or len(steps)>20: raise ValueError('Invalid '+field)
        for a in steps:
            if not isinstance(a,dict): raise ValueError('Action must be object')
            if 'relay' in a:
                if set(a) not in ({'relay','state'},{'relay','state','pause'}): raise ValueError('Invalid relay action')
                if type(a['relay']) is not int or a['relay'] not in (1,2) or a['state'] not in ('on','off'): raise ValueError('Invalid relay or state')
            elif 'servo' in a:
                if set(a) not in ({'servo','angle'},{'servo','angle','pause'}): raise ValueError('Invalid servo action')
                if type(a['servo']) is not int or a['servo'] not in (1,2) or not number(a['angle'],-90,90): raise ValueError('Invalid servo action')
            else: raise ValueError('Unknown action')
            if not number(a.get('pause',0),0,20): raise ValueError('Invalid pause')
    return d

def load(): return validate(json.loads(CONFIG.read_text(encoding='utf-8')))

def audio_start(volume):
    global player
    if player and player.poll() is None: return
    if not AUDIO.is_file(): return
    player=subprocess.Popen(['cvlc','--intf','rc','--rc-fake-tty','--no-video','--loop',str(AUDIO)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True)
    try:
        player.stdin.write(f'volume {round(volume*256/100)}\n'); player.stdin.flush()
    except (OSError,ValueError): pass

def audio_stop():
    global player
    if player and player.poll() is None:
        player.terminate()
        try: player.wait(timeout=2)
        except subprocess.TimeoutExpired: player.kill(); player.wait()
    player=None

def perform(steps):
    try:
        for a in steps:
            if CANCEL.is_set() or STOP.is_set(): break
            if 'relay' in a:
                api(5052,f"/relay/{a['relay']}",{'on':a['state']=='on'})
            else:
                api(5053,f"/servo/{a['servo']}",{'angle':a['angle']})
            if CANCEL.wait(a.get('pause',0)): break
    except Exception as exc:
        with LOCK: state['error']='Servo sequence: '+str(exc)[:130]
    finally:
        with LOCK: state['sequence_running']=False

def begin(steps):
    global worker
    with LOCK:
        if state['sequence_running']: return
        CANCEL.clear();state['sequence_running']=True
    worker=threading.Thread(target=perform,args=(list(steps),),daemon=True)
    worker.start()

def cancel():
    CANCEL.set()  # A currently executing servo API request can finish before cancellation.

def loop():
    armed=True;near_fired=False;exit_since=None;last=-1e9;was_enabled=False
    while not STOP.wait(.25):
        try:
            c=load()
            with LOCK: manual=state['manual_stop']
            if not c['enabled'] or manual:
                if was_enabled:
                    cancel();audio_stop()
                was_enabled=False;armed=True;near_fired=False;exit_since=None
                with LOCK: state['phase']='manual stop' if manual else 'disabled'
                continue
            if not was_enabled:
                was_enabled=True;armed=True;near_fired=False;exit_since=None
                begin(c['on_arm'])
            s=api(5054,'/status');d=s.get('distance_cm')
            stale=bool(s.get('stale') or not s.get('enabled') or type(d) not in (int,float))
            with LOCK: state.update(distance_cm=d,stale=stale,error=None)
            if stale:
                audio_stop();cancel()
                with LOCK: state['phase']='sensor stale'
                # Do not trigger again until a clear reading at release distance.
                armed=False;near_fired=True
                continue
            if d >= c['release_cm']:
                if exit_since is None: exit_since=time.monotonic()
                if time.monotonic()-exit_since>=1.0 and not armed:
                    cancel();audio_stop()
                    # Wait briefly for an in-flight command before starting reset.
                    if worker and worker.is_alive(): worker.join(timeout=3)
                    begin(c['on_exit'])
                    armed=True;near_fired=False
                with LOCK: state['phase']='idle'
                continue
            exit_since=None
            if d <= c['trigger_cm']:
                audio_start(c['laughter_volume'])
                if d <= c['servo_trigger_cm'] and armed and not near_fired and time.monotonic()-last>=c['cooldown_seconds']:
                    begin(c['on_close']);near_fired=True;armed=False;last=time.monotonic()
                with LOCK: state['phase']='scare' if near_fired else 'laughing'
        except Exception as exc:
            with LOCK: state['error']=str(exc)[:180]
            print('Room 3 scene:',repr(exc),flush=True)
            STOP.wait(1)

@app.before_request
def auth():
    if not hmac.compare_digest(request.headers.get('X-Haunt-Token',''),TOKEN):return jsonify(error='Unauthorized'),401

@app.route('/config',methods=['GET','PUT'])
def config():
    if request.method=='GET': return jsonify(load())
    try:
        if request.content_length and request.content_length>65536:return jsonify(error='Too large'),413
        d=validate(request.get_json(force=True))
        with tempfile.NamedTemporaryFile(mode='w',dir=ROOT,delete=False,encoding='utf-8') as f:
            json.dump(d,f,indent=2);f.write('\n');name=f.name
        os.replace(name,CONFIG)
        return jsonify(ok=True)
    except (ValueError,TypeError) as exc:return jsonify(error=str(exc)),400
    except OSError:return jsonify(error='Cannot save configuration'),500

@app.get('/status')
def status():
    with LOCK:return jsonify(dict(state))

@app.post('/override')
def override():
    b=request.get_json(silent=True) or {}
    if type(b.get('stop')) is not bool:return jsonify(error='stop must be boolean'),400
    with LOCK:state['manual_stop']=b['stop']
    if b['stop']:cancel();audio_stop()
    return status()

@app.post('/audio')
def upload():
    f=request.files.get('file')
    if not f or Path(f.filename).suffix.lower()!='.mp3':return jsonify(error='MP3 required'),400
    if request.content_length and request.content_length>20*1024*1024:return jsonify(error='20MB max'),413
    AUDIO.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=AUDIO.parent,delete=False) as tmp:
        size=0
        while True:
            chunk=f.stream.read(65536)
            if not chunk:break
            size+=len(chunk)
            if size>20*1024*1024:
                name=tmp.name;tmp.close();os.unlink(name);return jsonify(error='Too large'),413
            tmp.write(chunk)
        name=tmp.name
    audio_stop();os.replace(name,AUDIO)
    return jsonify(ok=True)

def shutdown(*_):
    STOP.set();cancel();audio_stop()
signal.signal(signal.SIGTERM,shutdown)
signal.signal(signal.SIGINT,shutdown)
if __name__=='__main__':
    threading.Thread(target=loop,daemon=True).start()
    app.run(host='0.0.0.0',port=5056,threaded=True)
