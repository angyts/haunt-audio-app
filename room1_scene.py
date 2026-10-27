#!/usr/bin/env python3
"""Room 1 scene engine: JSON hot-reload, no automatic servo/relay reset."""
import json,os,signal,subprocess,threading,time
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parent
CONFIG=ROOT/'room1_scene.json'
TOKEN=os.environ['HAUNT_TOKEN']
HEADERS={'X-Haunt-Token':TOKEN}
STOP=threading.Event()
chant=None
worker=None
armed=False
close_fired=False
last_close=-1e10
exit_since=None
was_enabled=False
arm_applied=False

def api(port,path,data=None):
    headers=dict(HEADERS)
    if data is not None: headers['Content-Type']='application/json'
    req=Request('http://127.0.0.1:'+str(port)+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method='POST' if data is not None else 'GET')
    with urlopen(req,timeout=4) as response: return json.load(response)
def load():
    d=json.loads(CONFIG.read_text())
    if not 10<=d['near_cm']<=d['servo_trigger_cm']<d['trigger_cm']<d['release_cm']<=300: raise ValueError('Invalid thresholds')
    return d

def volume(p,level):
    if p and p.poll() is None and p.stdin:
        try: p.stdin.write(f'volume {round(max(0,min(100,level))*256/100)}\n');p.stdin.flush()
        except (OSError,BrokenPipeError): pass

def stop_chant():
    global chant
    if chant:
        if chant.poll() is None:
            chant.terminate()
            try: chant.wait(timeout=2)
            except subprocess.TimeoutExpired: chant.kill();chant.wait()
        chant=None

def start_chant(path):
    global chant
    if chant and chant.poll() is None:return
    if not Path(path).is_file(): print('Missing chant:',path,flush=True);return
    chant=subprocess.Popen(['cvlc','--intf','rc','--rc-fake-tty','--no-video','--loop',path],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True,bufsize=1)

def execute(actions):
    for step in actions:
        if STOP.is_set(): return
        try:
            if 'parallel' in step:
                api(5053,'/group',{'moves':step['parallel']})
            elif 'servo' in step:
                api(5053,f"/servo/{step['servo']}",{'angle':step['angle']})
            elif 'relay' in step:
                api(5052,f"/relay/{step['relay']}",{'on':step['state']=='on'})
            elif step.get('effect')=='blink':
                for _ in range(step['cycles']):
                    if STOP.is_set(): return
                    api(5052,f"/relay/{step['relay']}",{'on':True})
                    if STOP.wait(step['on_seconds']): return
                    api(5052,f"/relay/{step['relay']}",{'on':False})
                    if STOP.wait(step['off_seconds']): return
                api(5052,f"/relay/{step['relay']}",{'on':step.get('final_state','off')=='on'})
            if STOP.wait(step.get('pause',0)):return
        except Exception as exc:
            print('Scene action failed:',repr(exc),flush=True)

def start_actions(actions):
    global worker
    if worker is not None and worker.is_alive():return False
    worker=threading.Thread(target=execute,args=(list(actions),),daemon=True)
    worker.start()
    return True

def main():
    global armed,close_fired,last_close,exit_since,was_enabled,arm_applied
    print('Room 1 scene engine running',flush=True)
    while not STOP.is_set():
        try:
            c=load()
            if not c.get('enabled'):
                stop_chant()
                was_enabled=False;arm_applied=False;armed=False;close_fired=False;exit_since=None
                STOP.wait(.3);continue
            if not was_enabled:
                was_enabled=True;armed=True;close_fired=False;exit_since=None
            if not arm_applied:
                arm_applied=start_actions(c['on_arm'])
                STOP.wait(.3);continue
            s=api(5054,'/status')
            d=s.get('distance_cm')
            if s.get('stale') or not s.get('enabled') or type(d) not in (int,float):
                stop_chant();exit_since=None
                STOP.wait(.3);continue
            if d>=c['release_cm']:
                if exit_since is None:exit_since=time.monotonic()
                if time.monotonic()-exit_since>=1.0 and not armed and (worker is None or not worker.is_alive()):
                    if start_actions(c['on_exit']):
                        armed=True;close_fired=False;stop_chant()
            else: exit_since=None
            if d<=c['trigger_cm']:
                start_chant(c['chant_file'])
                if chant:
                    f=max(0,min(1,(c['trigger_cm']-d)/(c['trigger_cm']-c['near_cm'])))
                    volume(chant,c['chant_min_volume']+f*(c['chant_max_volume']-c['chant_min_volume']))
                if armed and (worker is None or not worker.is_alive()):
                    if start_actions(c['on_approach']):armed=False
                if d<=c['servo_trigger_cm'] and not close_fired and time.monotonic()-last_close>=c['cooldown_seconds']:
                    if start_actions(c['on_close']):close_fired=True;last_close=time.monotonic()
            elif d>=c['release_cm']:
                stop_chant()
            STOP.wait(.25)
        except Exception as exc:
            print('Scene loop error:',repr(exc),flush=True)
            STOP.wait(1)

def shutdown(*_):
    STOP.set();stop_chant()
signal.signal(signal.SIGTERM,shutdown)
signal.signal(signal.SIGINT,shutdown)
if __name__=='__main__':main()
