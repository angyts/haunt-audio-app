#!/usr/bin/env python3
"""Room 2 automatic scene and restricted JSON/audio API. Runs on haunt-forest."""
import hmac,json,os,signal,subprocess,tempfile,threading,time
from pathlib import Path
from urllib.request import Request,urlopen
from flask import Flask,request,jsonify
app=Flask(__name__)
TOKEN=os.environ['HAUNT_TOKEN']
ROOT=Path(__file__).resolve().parent
CONFIG=ROOT/'room2_scene.json'
AUDIO=Path.home()/'haunt-audio'/'bubbling.mp3'
LOCK=threading.RLock()
STOP=threading.Event()
state={'phase':'disabled','distance_cm':None,'stale':True,'manual_stop':False,'oscillating':False,'error':None}
player=None

def api(port,path,body=None):
    headers={'X-Haunt-Token':TOKEN}
    if body is not None:headers['Content-Type']='application/json'
    req=Request(f'http://127.0.0.1:{port}{path}',headers=headers,data=json.dumps(body).encode() if body is not None else None,method='POST' if body is not None else 'GET')
    with urlopen(req,timeout=3) as r:return json.load(r)

def validate(d):
    if not isinstance(d,dict):raise ValueError('Expected JSON object')
    keys={'enabled','near_cm','trigger_cm','release_cm','cooldown_seconds','bubbling_file','bubbling_volume','on_arm','on_approach','on_close','on_exit'}
    if set(d)!=keys:raise ValueError('Missing/unknown keys: '+str(sorted(set(d)^keys)))
    if type(d['enabled']) is not bool:raise ValueError('enabled must be boolean')
    def num(v,lo,hi):return type(v) in (int,float) and lo<=v<=hi
    if not all(num(d[k],10,300) for k in ('near_cm','trigger_cm','release_cm')) or not d['near_cm']<d['trigger_cm']<d['release_cm']:
        raise ValueError('Require 10 <= near < trigger < release <= 300')
    if not num(d['cooldown_seconds'],0,300) or not num(d['bubbling_volume'],0,100):raise ValueError('Invalid cooldown or volume')
    if d['bubbling_file']!=str(AUDIO):raise ValueError('Invalid bubbling_file path')
    for name in ('on_arm','on_approach','on_close','on_exit'):
        steps=d[name]
        if not isinstance(steps,list) or len(steps)>20:raise ValueError('Invalid '+name)
        for x in steps:
            if not isinstance(x,dict):raise ValueError('Invalid action')
            if 'relay' in x:
                if set(x)!={'relay','state'} or type(x['relay']) is not int or x['relay'] not in (1,2) or x['state'] not in ('on','off'):raise ValueError('Invalid relay action')
            elif x.get('effect')=='oscillate':
                if set(x)!={'servo','effect','min_angle','max_angle','step','step_delay'} or x['servo']!=1 or not num(x['min_angle'],-90,90) or not num(x['max_angle'],-90,90) or x['min_angle']>=x['max_angle'] or not num(x['step'],1,15) or not num(x['step_delay'],.02,.3):raise ValueError('Invalid oscillation action')
            elif x.get('effect')=='stop':
                if set(x)!={'servo','effect'} or x['servo']!=1:raise ValueError('Invalid stop action')
            else:raise ValueError('Unsupported action')
    return d

def load():return validate(json.loads(CONFIG.read_text()))

def execute(actions):
    for x in actions:
        if 'relay' in x:api(5052,f"/relay/{x['relay']}",{'on':x['state']=='on'})
        elif x.get('effect')=='oscillate':
            with LOCK:blocked=state['manual_stop']
            if not blocked:
                api(5053,'/oscillate/start',{'servo':x['servo'],'min_angle':x['min_angle'],'max_angle':x['max_angle'],'step':x['step'],'step_delay':x['step_delay']})
                with LOCK:state['oscillating']=True
        elif x.get('effect')=='stop':
            api(5053,'/oscillate/stop',{})
            with LOCK:state['oscillating']=False

def audio_start(volume):
    global player
    if player and player.poll() is None:return
    if not AUDIO.is_file():return
    player=subprocess.Popen(['cvlc','--intf','rc','--rc-fake-tty','--no-video','--loop',str(AUDIO)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True)
    try:player.stdin.write(f'volume {round(volume*256/100)}\n');player.stdin.flush()
    except OSError:pass

def audio_stop():
    global player
    if player and player.poll() is None:
        player.terminate()
        try:player.wait(timeout=2)
        except subprocess.TimeoutExpired:player.kill();player.wait()
    player=None

def loop():
    armed=False;close=False;exiting=None;last=-1e10;was_enabled=False
    while not STOP.wait(.25):
        try:
            c=load()
            with LOCK:manual=state['manual_stop']
            if not c['enabled'] or manual:
                if was_enabled or manual:
                    audio_stop()
                    api(5053,'/oscillate/stop',{})
                    with LOCK:state['oscillating']=False
                was_enabled=False;armed=False;close=False;exiting=None
                with LOCK:state['phase']='manual stop' if manual else 'disabled'
                continue
            if not was_enabled:
                execute(c['on_arm']);was_enabled=True;armed=True;close=False
            s=api(5054,'/status');d=s.get('distance_cm')
            stale=s.get('stale') or not s.get('enabled') or type(d) not in (int,float)
            with LOCK:state.update(distance_cm=d,stale=bool(stale),error=None)
            if stale:
                # Fail safe: stop continuous motor if sensor is unreliable.
                api(5053,'/oscillate/stop',{});audio_stop()
                with LOCK:state.update(phase='sensor stale',oscillating=False)
                was_enabled=False
                continue
            if d>=c['release_cm']:
                if exiting is None:exiting=time.monotonic()
                if time.monotonic()-exiting>=1.0 and not armed:
                    execute(c['on_exit']);audio_stop();armed=True;close=False
                with LOCK:state['phase']='idle'
            else:exiting=None
            if d<=c['trigger_cm']:
                audio_start(c['bubbling_volume'])
                if armed and time.monotonic()-last>=c['cooldown_seconds']:
                    execute(c['on_approach']);armed=False;last=time.monotonic()
                if d<=c['near_cm'] and not close:
                    execute(c['on_close']);close=True
                with LOCK:state['phase']='close' if close else 'approach'
        except Exception as e:
            with LOCK:state['error']=str(e)[:180]
            print('Room 2 scene:',repr(e),flush=True)
            STOP.wait(1)

@app.before_request
def auth():
    if not hmac.compare_digest(request.headers.get('X-Haunt-Token',''),TOKEN):return jsonify(error='Unauthorized'),401
@app.route('/config',methods=['GET','PUT'])
def config():
    if request.method=='GET':return jsonify(load())
    try:
        if request.content_length and request.content_length>65536:return jsonify(error='Too large'),413
        d=validate(request.get_json(force=True))
        with tempfile.NamedTemporaryFile(mode='w',dir=ROOT,delete=False,encoding='utf-8') as f:
            json.dump(d,f,indent=2);f.write('\n');tmp=f.name
        os.replace(tmp,CONFIG)
        return jsonify(ok=True)
    except (ValueError,TypeError) as e:return jsonify(error=str(e)),400
    except OSError:return jsonify(error='Cannot save JSON; check file permissions'),500
@app.get('/status')
def status():
    with LOCK:return jsonify(dict(state))
@app.post('/override')
def override():
    b=request.get_json(silent=True) or {}
    if type(b.get('stop')) is not bool:return jsonify(error='stop must be boolean'),400
    with LOCK:state['manual_stop']=b['stop']
    if b['stop']:
        try:api(5053,'/oscillate/stop',{})
        except Exception:pass
        audio_stop()
        with LOCK:state['oscillating']=False
    return status()
@app.post('/audio')
def upload():
    f=request.files.get('file')
    if not f or Path(f.filename).suffix.lower()!='.mp3':return jsonify(error='MP3 required'),400
    if request.content_length and request.content_length>20*1024*1024:return jsonify(error='20MB maximum'),413
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
    STOP.set();audio_stop()
    try:api(5053,'/oscillate/stop',{})
    except Exception:pass
signal.signal(signal.SIGTERM,shutdown);signal.signal(signal.SIGINT,shutdown)
if __name__=='__main__':
    threading.Thread(target=loop,daemon=True).start()
    app.run(host='0.0.0.0',port=5055,threaded=True)
