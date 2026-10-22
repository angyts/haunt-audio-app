import os, time, subprocess, tempfile, urllib.request, array, math, sys, json, threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEVICE=os.environ.get('VOICE_CAPTURE_DEVICE','plughw:2,0')
DEST=os.environ.get('VOICE_RECEIVER_URL','http://haunt-corridor.local:5012/voice')
TOKEN=os.environ.get('VOICE_TOKEN','')
RATE=16000
STATE=Path.home()/'haunt-voice-settings.json'
DEFAULT={'enabled':True,'threshold':850,'duration':2,'pitch':1.3,'gain':2.0,'cooldown':10}
RANGES={'threshold':(200,3000),'duration':(1,5),'pitch':(1,1.8),'gain':(0.5,4),'cooldown':(3,30)}
lock=threading.RLock()
settings=DEFAULT.copy()
status={'activity':'Starting','last_rms':0,'triggers':0}
if not TOKEN: raise SystemExit('VOICE_TOKEN required')
try:
    saved=json.loads(STATE.read_text())
    for k,v in saved.items():
        if k=='enabled' and isinstance(v,bool):settings[k]=v
        elif k in RANGES and isinstance(v,(int,float)) and RANGES[k][0]<=v<=RANGES[k][1]:settings[k]=v
except (OSError,ValueError,TypeError):pass

def save():
    tmp=STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(settings))
    tmp.replace(STATE)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):self.handle_settings()
    def do_POST(self):self.handle_settings()
    def handle_settings(self):
        if self.path!='/settings':return self.reply(404,{'error':'not found'})
        if self.headers.get('X-Voice-Token')!=TOKEN:return self.reply(401,{'error':'unauthorized'})
        with lock:
            if self.command=='POST':
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if size>2048 or size<0:raise ValueError('invalid size')
                    changes=json.loads(self.rfile.read(size))
                    if not isinstance(changes,dict):raise ValueError('invalid payload')
                    for k,v in changes.items():
                        if k=='enabled':
                            if not isinstance(v,bool):raise ValueError('enabled must be boolean')
                        elif k in RANGES:
                            if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not RANGES[k][0]<=v<=RANGES[k][1]:raise ValueError('invalid '+k)
                        else:raise ValueError('unknown setting '+k)
                    settings.update(changes);save()
                except (ValueError,TypeError) as e:return self.reply(400,{'error':str(e)})
            return self.reply(200,{**settings,**status})
    def reply(self,code,payload):
        b=json.dumps(payload).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def log_message(self,*args):pass

threading.Thread(target=lambda:ThreadingHTTPServer(('0.0.0.0',5013),Handler).serve_forever(),daemon=True).start()
print('Voice Lab ready on port 5013',flush=True)
while True:
    with lock: cfg=settings.copy()
    if not cfg['enabled']:
        with lock:status['activity']='Disabled'
        time.sleep(0.5);continue
    with lock:status['activity']='Listening'
    sample=subprocess.run(['arecord','-q','-D',DEVICE,'-t','raw','-f','S16_LE','-r',str(RATE),'-c','1','-d','1'],capture_output=True)
    if sample.returncode:
        print('Capture error:',sample.stderr.decode(errors='replace'),flush=True);time.sleep(2);continue
    samples=array.array('h');samples.frombytes(sample.stdout[:len(sample.stdout)//2*2])
    if sys.byteorder!='little':samples.byteswap()
    rms=math.sqrt(sum(v*v for v in samples)/len(samples)) if samples else 0
    with lock:status['last_rms']=rms
    if rms<cfg['threshold']:continue
    with lock:status['activity']='Recording';status['triggers']+=1
    print('Triggered RMS',round(rms),flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw=os.path.join(tmp,'original.wav');out=os.path.join(tmp,'shifted.wav')
        rec=subprocess.run(['arecord','-q','-D',DEVICE,'-f','S16_LE','-r',str(RATE),'-c','1','-d',str(int(math.ceil(cfg['duration']))),raw],capture_output=True)
        if rec.returncode:
            print('Record error',rec.stderr.decode(errors='replace'),flush=True)
        else:
            pitch=cfg['pitch'];gain=cfg['gain'];speed=1/pitch
            filt=f'asetrate={RATE}*{pitch},aresample={RATE},atempo={speed},acompressor=threshold=0.05:ratio=4:attack=5:release=100,volume={gain},alimiter=limit=0.9'
            fx=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',raw,'-af',filt,'-acodec','pcm_s16le',out],capture_output=True)
            if fx.returncode:print('FFmpeg error',fx.stderr.decode(errors='replace'),flush=True)
            else:
                try:
                    with lock:status['activity']='Sending'
                    data=Path(out).read_bytes()
                    req=urllib.request.Request(DEST,data=data,method='POST',headers={'X-Voice-Token':TOKEN,'Content-Type':'audio/wav'})
                    with urllib.request.urlopen(req,timeout=8) as resp:print('Sent',resp.status,flush=True)
                except Exception as e:print('Send failed',str(e),flush=True)
    with lock:status['activity']='Cooldown'
    time.sleep(cfg['cooldown'])
