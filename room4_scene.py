#!/usr/bin/env python3
"""Room 4 lift controller. GPIO6 belongs to the existing button agent on port 5055."""
import os,json,time,threading,signal,subprocess,tempfile,hmac
from pathlib import Path
from urllib.request import Request,urlopen
from flask import Flask,request,jsonify
app=Flask(__name__); TOKEN=os.environ['HAUNT_TOKEN']; ROOT=Path(__file__).resolve().parent
CFG=ROOT/'room4_scene.json'; AUDIO=Path.home()/'haunt-audio'/'creepy_lift.mp3'
stop=threading.Event(); lock=threading.Lock(); player=None
status={'phase':'disabled','distance_cm':None,'stale':True,'button_count':None,'button_pressed':False,'elapsed_seconds':0,'manual_stop':False,'error':None}
def update(**kw):
 with lock:status.update(kw)
def api(port,path,data=None):
 headers={'X-Haunt-Token':TOKEN};headers.update({'Content-Type':'application/json'} if data is not None else {})
 req=Request(f'http://127.0.0.1:{port}{path}',headers=headers,data=json.dumps(data).encode() if data is not None else None,method='POST' if data is not None else 'GET')
 with urlopen(req,timeout=4) as r:return json.load(r)
def relay(n,on):api(5052,f'/relay/{n}',{'on':bool(on)})
def arrow(angle):api(5053,'/servo/1',{'angle':angle})
def background(action):api(5051,'/'+action,{})
def valid(c):
 required={'enabled','near_cm','trigger_cm','release_cm','cooldown_seconds','button_debounce_ms','sequence_duration_seconds','actor_light_seconds','exit_confirm_seconds','white_off_at_seconds','red_blink_at_seconds','red_blink_on_seconds','red_blink_off_seconds','red_blink_cycles','arrow_at_seconds','arrow_angle','journey_volume'}
 if not isinstance(c,dict) or set(c)!=required:raise ValueError('Missing or unknown fields: '+str(sorted(set(c)^required)))
 if type(c['enabled']) is not bool:raise ValueError('enabled must be boolean')
 for k,lo,hi in [('near_cm',10,300),('trigger_cm',10,300),('release_cm',10,300),('cooldown_seconds',0,300),('button_debounce_ms',20,1000),('sequence_duration_seconds',10,180),('actor_light_seconds',0,300),('exit_confirm_seconds',0.5,20),('white_off_at_seconds',0,180),('red_blink_at_seconds',0,180),('red_blink_on_seconds',0.3,5),('red_blink_off_seconds',0.3,5),('red_blink_cycles',1,20),('arrow_at_seconds',0,180),('arrow_angle',-90,90),('journey_volume',0,100)]:
  if type(c[k]) not in (int,float) or not lo<=c[k]<=hi:raise ValueError('Invalid '+k)
 if type(c['red_blink_cycles']) is not int or not c['near_cm']<=c['trigger_cm']<c['release_cm']:raise ValueError('Invalid count or distance ordering')
 if max(c['white_off_at_seconds'],c['red_blink_at_seconds'],c['arrow_at_seconds'])>=c['sequence_duration_seconds']:raise ValueError('Cues must precede end of journey')
 return c
def config():return valid(json.loads(CFG.read_text()))
def audio_start(volume):
 global player
 if not AUDIO.is_file():raise RuntimeError('Upload creepy_lift.mp3 first')
 player=subprocess.Popen(['cvlc','--intf','rc','--rc-fake-tty','--no-video','--play-and-exit',str(AUDIO)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True)
 try:player.stdin.write(f'volume {round(volume*256/100)}\n');player.stdin.flush()
 except (OSError,ValueError):pass
def audio_stop():
 global player
 if player and player.poll() is None:
  player.terminate()
  try:player.wait(timeout=2)
  except subprocess.TimeoutExpired:player.kill();player.wait()
 player=None
def all_off():
 audio_stop()
 for n in (1,2):
  try:relay(n,False)
  except Exception as e:update(error=str(e)[:120])
 try:arrow(0)
 except Exception as e:update(error=str(e)[:120])
def loop():
 phase='disabled';seen=None;last_end=-1e9;start=0;exit_since=None;paused=False;white_done=False;arrow_done=False;blink_start=None;blink_last=None
 while not stop.wait(.12):
  try:
   c=config()
   with lock:manual=status['manual_stop']
   if not c['enabled'] or manual:
    if phase!='disabled':
     all_off()
     if paused:
      try:background('play')
      except Exception:pass
      paused=False
    phase='disabled';update(phase='manual stop' if manual else 'disabled',elapsed_seconds=0)
    continue
   s=api(5054,'/status');d=s.get('distance_cm');stale=bool(s.get('stale') or not s.get('enabled') or type(d) not in (float,int))
   b=api(5055,'/status');count=b.get('press_count')
   if type(count) is not int:raise ValueError('Bad button counter')
   if seen is None or count<seen:seen=count
   new_press=count>seen;seen=count
   update(distance_cm=d,stale=stale,button_count=count,button_pressed=b.get('pressed'),error=None)
   now=time.monotonic()
   if phase=='disabled':phase='idle';all_off()
   if phase=='idle':
    update(phase='idle',elapsed_seconds=0)
    if not stale and d<=c['trigger_cm']:
     relay(1,True);phase='ready';exit_since=None
   elif phase=='ready':
    update(phase='ready')
    if new_press and now-last_end>=c['cooldown_seconds']:
     if not AUDIO.is_file():raise RuntimeError('Upload creepy_lift.mp3 first')
     try:background('pause');paused=True
     except Exception:paused=False
     audio_start(c['journey_volume']);start=now;phase='journey';white_done=False;arrow_done=False;blink_start=None;blink_last=None
    elif not stale and d>=c['release_cm']:
     if exit_since is None:exit_since=now
     if now-exit_since>=c['exit_confirm_seconds']:
      relay(1,False);phase='idle';exit_since=None
    else:exit_since=None
   elif phase=='journey':
    t=now-start;update(phase='journey',elapsed_seconds=round(t,1))
    if not white_done and t>=c['white_off_at_seconds']:
     relay(1,False);white_done=True
    if t>=c['red_blink_at_seconds'] and blink_start is None:blink_start=now
    if blink_start is not None:
     period=c['red_blink_on_seconds']+c['red_blink_off_seconds']
     bt=now-blink_start
     desired=True if bt>=c['red_blink_cycles']*period else (bt%period)<c['red_blink_on_seconds']
     if desired!=blink_last:relay(2,desired);blink_last=desired
    if not arrow_done and t>=c['arrow_at_seconds']:
     arrow(c['arrow_angle']);arrow_done=True
    if t>=c['sequence_duration_seconds']:
     audio_stop();relay(2,True);phase='actor';start=now
   elif phase=='actor':
    t=now-start;update(phase='actor',elapsed_seconds=round(t,1))
    if t>=c['actor_light_seconds']:phase='wait_exit';exit_since=None
   elif phase=='wait_exit':
    update(phase='wait_exit')
    if not stale and d>=c['release_cm']:
     if exit_since is None:exit_since=now
     if now-exit_since>=c['exit_confirm_seconds']:
      all_off()
      if paused:
       try:background('play')
       except Exception:pass
       paused=False
      phase='idle';last_end=now;exit_since=None
    else:exit_since=None
  except Exception as e:
   update(error=f'{type(e).__name__}: {str(e)[:140]}');print('Room4:',repr(e),flush=True);stop.wait(.8)
 all_off()
 if paused:
  try:background('play')
  except Exception:pass
@app.before_request
def auth():
 if not hmac.compare_digest(request.headers.get('X-Haunt-Token',''),TOKEN):return jsonify(error='Unauthorized'),401
@app.route('/config',methods=['GET','PUT'])
def configuration():
 if request.method=='GET':return jsonify(config())
 try:
  if request.content_length and request.content_length>65536:return jsonify(error='Too large'),413
  data=valid(request.get_json(force=True))
  with tempfile.NamedTemporaryFile(mode='w',dir=ROOT,delete=False,encoding='utf-8') as f:json.dump(data,f,indent=2);f.write('\n');name=f.name
  os.replace(name,CFG);return jsonify(ok=True)
 except (ValueError,TypeError) as e:return jsonify(error=str(e)),400
@app.get('/status')
def get_status():
 with lock:return jsonify(dict(status))
@app.post('/override')
def override():
 v=(request.get_json(silent=True) or {}).get('stop')
 if type(v) is not bool:return jsonify(error='stop must be boolean'),400
 update(manual_stop=v);return get_status()
@app.post('/audio')
def upload():
 f=request.files.get('file')
 if not f or Path(f.filename).suffix.lower()!='.mp3':return jsonify(error='MP3 required'),400
 if request.content_length and request.content_length>20*1024*1024:return jsonify(error='20 MB max'),413
 AUDIO.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile(dir=AUDIO.parent,delete=False) as tmp:
  size=0
  while True:
   part=f.stream.read(65536)
   if not part:break
   size+=len(part)
   if size>20*1024*1024:
    name=tmp.name;tmp.close();os.unlink(name);return jsonify(error='Too large'),413
   tmp.write(part)
  name=tmp.name
 os.replace(name,AUDIO);return jsonify(ok=True)
def shutdown(*_):stop.set()
signal.signal(signal.SIGTERM,shutdown);signal.signal(signal.SIGINT,shutdown)
if __name__=='__main__':
 threading.Thread(target=loop,daemon=True).start();app.run(host='0.0.0.0',port=5057,threaded=True)
