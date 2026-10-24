import os, requests
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 40 * 1024 * 1024
TOKEN = os.environ['HAUNT_TOKEN']
ROOMS = {
    'master': 'haunt-master.local',
    'forest': 'haunt-forest.local',
    'corridor': 'haunt-corridor.local',
    'lift': 'haunt-lift.local',
    'gate': 'haunt-gate.local',
}
HTML = '''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gui Gui Audio Control</title><style>body{font:16px system-ui;background:#101522;color:#e9eef9;max-width:900px;margin:25px auto;padding:12px}h1{color:#b9a8ff}.room{background:#20283a;padding:18px;border-radius:14px;margin:12px 0}button,input{margin:5px;padding:10px;border-radius:7px}button{cursor:pointer}.state{font-weight:bold;color:#a9e7c2}small{color:#b7c4d7}</style></head><body><h1>👻 Gui Gui Audio Control</h1><p>Upload a loop to a room, then play / pause / stop.</p><div id="rooms"></div><section class="room"><h2>🎙 Gui Gui Voice Lab</h2><p class="state" id="mic-status">Checking microphone...</p><div id="mic-controls"></div><button onclick="micSave()">Apply settings</button><button onclick="micToggle(true)">Enable</button><button onclick="micToggle(false)">Disable</button><p><small id="mic-msg"></small></p></section><script>
const names = {{names|tojson}};
const root=document.getElementById('rooms');
for(const name of names){const div=document.createElement('div');div.className='room';div.innerHTML=`<h2>${name}</h2><p class="state" id="s-${name}">Checking...</p><input id="f-${name}" type="file" accept="audio/*"><button onclick="upload('${name}')">Upload</button><p><button onclick="cmd('${name}','play')">▶ Play / Resume</button><button onclick="cmd('${name}','pause')">⏸ Pause</button><button onclick="cmd('${name}','stop')">■ Stop</button></p><label>Volume <span id="v-${name}">70</span>% <input type="range" min="0" max="100" value="70" id="vol-${name}" oninput="document.getElementById('v-${name}').textContent=this.value" onchange="setVolume('${name}',this.value)"></label><br><div class="relay-controls"><h3>💡 Lighting / Relays</h3><p id="rs-${name}">Checking relays...</p><button onclick="relaySet('${name}',1,true)">Relay 1 ON</button><button onclick="relaySet('${name}',1,false)">OFF</button><br><button onclick="relaySet('${name}',2,true)">Relay 2 ON</button><button onclick="relaySet('${name}',2,false)">OFF</button></div><div class="servo-controls"><h3>🦾 Servo Motors</h3><p id="ss-${name}">Checking servos...</p><div id="sv-${name}"></div><button onclick="servoCentre('${name}')">Centre all</button></div><div class="ultrasonic-controls"><h3>📡 Distance Sensor</h3><p id="us-${name}">Checking sensor...</p><label>Trigger distance: <b id="ut-${name}">80</b> cm <input type="range" min="10" max="300" step="5" value="80" id="ud-${name}" oninput="document.getElementById('ut-${name}').textContent=this.value" onchange="ultraSet('${name}',{threshold_cm:Number(this.value)})"></label><p><button onclick="ultraSet('${name}',{enabled:true})">Enable</button><button onclick="ultraSet('${name}',{enabled:false})">Disable</button></p><small>Monitoring only: no automatic relay or servo actions.</small></div><small id="m-${name}"></small>`;root.appendChild(div)}
async function refresh(name){try{const r=await fetch(`/api/${name}/status`);const d=await r.json();document.getElementById(`s-${name}`).textContent=r.ok?`${d.state} — ${d.file||'No file'}`:`Offline / ${d.error||r.status}`;if(r.ok && Number.isFinite(d.volume)){const slider=document.getElementById(`vol-${name}`);if(document.activeElement!==slider){slider.value=d.volume;document.getElementById(`v-${name}`).textContent=d.volume}}}catch(e){document.getElementById(`s-${name}`).textContent='Offline'}}
async function setVolume(name,value){const r=await fetch(`/api/${name}/volume`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({volume:Number(value)})});const d=await r.json();document.getElementById(`m-${name}`).textContent=d.error||'';refresh(name)}
async function cmd(name,action){const r=await fetch(`/api/${name}/${action}`,{method:'POST'});const d=await r.json();document.getElementById(`m-${name}`).textContent=d.error||'';refresh(name)}
async function upload(name){const file=document.getElementById(`f-${name}`).files[0];if(!file)return alert('Choose a file');const fd=new FormData();fd.append('file',file);const r=await fetch(`/api/${name}/upload`,{method:'POST',body:fd});const d=await r.json();document.getElementById(`m-${name}`).textContent=r.ok?'Uploaded and playing on loop':d.error;refresh(name)}
for(const name of names)refresh(name);setInterval(()=>{for(const name of names)refresh(name)},5000);
async function relayRefresh(name){try{const r=await fetch(`/api/${name}/relays`);const d=await r.json();const e=document.getElementById(`rs-${name}`);e.textContent=r.ok?`Relay 1: ${d.relays['1'].on?'ON':'OFF'} | Relay 2: ${d.relays['2'].on?'ON':'OFF'}`:`Relay controller offline (${d.error||r.status})`;}catch(e){document.getElementById(`rs-${name}`).textContent='Relay controller offline'}}
async function relaySet(name,channel,on){try{const r=await fetch(`/api/${name}/relay/${channel}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({on})});const d=await r.json();if(!r.ok)throw Error(d.error||r.status);await relayRefresh(name)}catch(e){document.getElementById(`rs-${name}`).textContent='Error: '+e.message}}
for(const name of names)relayRefresh(name);setInterval(()=>{for(const name of names)relayRefresh(name)},5000);


const servoPins=[18,19,12,13];
for(const name of names){const area=document.getElementById(`sv-${name}`);for(let i=1;i<=4;i++){const row=document.createElement('p');row.innerHTML=`<label>Servo ${i} (GPIO${servoPins[i-1]}): <b id="sa-${name}-${i}">0</b>° <input type="range" min="-45" max="45" step="5" value="0" id="servo-${name}-${i}" oninput="document.getElementById('sa-${name}-${i}').textContent=this.value" onchange="servoSet('${name}',${i},this.value)"></label> <button onclick="servoSet('${name}',${i},0)">Centre</button>`;area.appendChild(row)}}
async function servoRefresh(name){try{const r=await fetch(`/api/${name}/servos`);const d=await r.json();if(!r.ok)throw Error(d.error||r.status);document.getElementById(`ss-${name}`).textContent='Servo controller online';for(let i=1;i<=4;i++){const slider=document.getElementById(`servo-${name}-${i}`);if(document.activeElement!==slider){slider.value=d.servos[String(i)].angle;document.getElementById(`sa-${name}-${i}`).textContent=slider.value}}}catch(e){document.getElementById(`ss-${name}`).textContent='Servo controller offline: '+e.message}}
async function servoSet(name,channel,angle){try{const r=await fetch(`/api/${name}/servo/${channel}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({angle:Number(angle)})});const d=await r.json();if(!r.ok)throw Error(d.error||r.status);document.getElementById(`ss-${name}`).textContent='Servo '+channel+' moved to '+d.angle+'°';await servoRefresh(name)}catch(e){document.getElementById(`ss-${name}`).textContent='Error: '+e.message}}
async function servoCentre(name){try{const r=await fetch(`/api/${name}/servos/centre`,{method:'POST'});const d=await r.json();if(!r.ok)throw Error(d.error||r.status);await servoRefresh(name)}catch(e){document.getElementById(`ss-${name}`).textContent='Error: '+e.message}}
for(const name of names)servoRefresh(name);setInterval(()=>{for(const name of names)servoRefresh(name)},5000);

async function ultraRefresh(name){try{const r=await fetch(`/api/${name}/ultrasonic`);const d=await r.json();if(!r.ok)throw Error(d.error||r.status);const el=document.getElementById(`us-${name}`);el.textContent=d.stale?'Sensor data stale':d.error?`Sensor error: ${d.error}`:`${d.distance_cm===null?'—':d.distance_cm} cm · ${d.enabled?(d.detected?'WITHIN RANGE':'Clear'):'Disabled'}`;const slider=document.getElementById(`ud-${name}`);if(document.activeElement!==slider){slider.value=d.threshold_cm;document.getElementById(`ut-${name}`).textContent=d.threshold_cm}}catch(e){document.getElementById(`us-${name}`).textContent='Sensor offline: '+e.message}}
async function ultraSet(name,settings){try{const r=await fetch(`/api/${name}/ultrasonic`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(settings)});const d=await r.json();if(!r.ok)throw Error(d.error||r.status);await ultraRefresh(name)}catch(e){document.getElementById(`us-${name}`).textContent='Error: '+e.message}}
for(const name of names)ultraRefresh(name);setInterval(()=>{for(const name of names)ultraRefresh(name)},1000);

const micDefs=[['threshold','Trigger threshold',200,3000,50,''],['duration','Record seconds',1,5,0.5,' s'],['pitch','Pitch multiplier',1,1.8,0.05,'×'],['gain','Amplification',0.5,4,0.25,'×'],['cooldown','Cooldown',3,30,1,' s']];
const mc=document.getElementById('mic-controls');
for(const [k,label,min,max,step,suffix] of micDefs){const el=document.createElement('p');el.innerHTML=`<label>${label}: <b id="mic-v-${k}">-</b>${suffix} <input id="mic-${k}" type="range" min="${min}" max="${max}" step="${step}" oninput="document.getElementById('mic-v-${k}').textContent=this.value"></label>`;mc.appendChild(el)}
async function micRequest(method,body){const r=await fetch('/api/mic/settings',{method,headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});const d=await r.json();if(!r.ok)throw Error(d.error||r.status);return d}
async function micRefresh(update=true){try{const d=await micRequest('GET');document.getElementById('mic-status').textContent=`${d.enabled?'Enabled':'Disabled'} · ${d.activity||'Idle'} · Last RMS: ${Math.round(d.last_rms||0)} · Triggers: ${d.triggers||0}`;if(update)for(const [k] of micDefs){const e=document.getElementById('mic-'+k);if(document.activeElement!==e){e.value=d[k];document.getElementById('mic-v-'+k).textContent=d[k]}}}catch(e){document.getElementById('mic-status').textContent='Microphone offline: '+e.message}}
async function micSave(){try{const b={};for(const [k] of micDefs)b[k]=Number(document.getElementById('mic-'+k).value);await micRequest('POST',b);document.getElementById('mic-msg').textContent='Settings saved';micRefresh()}catch(e){document.getElementById('mic-msg').textContent=e.message}}
async function micToggle(on){try{await micRequest('POST',{enabled:on});micRefresh()}catch(e){document.getElementById('mic-msg').textContent=e.message}}
micRefresh();setInterval(()=>micRefresh(false),3000);
</script></body></html>'''

@app.get('/')
def index(): return render_template_string(HTML, names=list(ROOMS))

@app.route('/api/<room>/<action>', methods=['GET','POST'])
def proxy(room,action):
    if room not in ROOMS or action not in ('status','upload','play','pause','stop','volume'):
        return jsonify(error='Unknown room or action'),404
    if action == 'status' and request.method != 'GET': return jsonify(error='Method not allowed'),405
    if action != 'status' and request.method != 'POST': return jsonify(error='Method not allowed'),405
    url=f'http://{ROOMS[room]}:5051/{action}'
    try:
        kwargs={'headers':{'X-Haunt-Token':TOKEN},'timeout':30 if action=='upload' else 3}
        if action=='upload':
            f=request.files.get('file')
            if not f: return jsonify(error='Choose an audio file'),400
            kwargs['files']={'file':(f.filename,f.stream,f.mimetype)}
        if action=='volume': kwargs['json']=request.get_json(silent=True) or {}
        response=requests.request(request.method,url,**kwargs)
        return (response.content,response.status_code,{'Content-Type':'application/json'})
    except requests.RequestException as e:
        return jsonify(error=f'Room unavailable: {e.__class__.__name__}'),503


@app.route('/api/<room>/relays', methods=['GET'])
@app.route('/api/<room>/relay/<int:channel>', methods=['POST'])
def relay_proxy(room, channel=None):
    if room not in ROOMS: return jsonify(error='Unknown room'),404
    if channel is not None and channel not in (1,2): return jsonify(error='Invalid channel'),404
    path='/status' if channel is None else f'/relay/{channel}'
    try:
        r=requests.request(request.method,f'http://{ROOMS[room]}:5052{path}',
            headers={'X-Haunt-Token':TOKEN},
            json=request.get_json(silent=True) if channel is not None else None,timeout=3)
        return (r.content,r.status_code,{'Content-Type':'application/json'})
    except requests.RequestException as exc:
        return jsonify(error='Relay controller unreachable: '+type(exc).__name__),503

@app.route('/api/<room>/servos', methods=['GET'])
@app.route('/api/<room>/servo/<int:channel>', methods=['POST'])
@app.route('/api/<room>/servos/centre', methods=['POST'])
def servo_proxy(room,channel=None):
    if room not in ROOMS: return jsonify(error='Unknown room'),404
    if channel is not None and channel not in (1,2,3,4): return jsonify(error='Invalid servo'),404
    path='/status' if request.method=='GET' else ('/centre' if channel is None else f'/servo/{channel}')
    try:
        r=requests.request(request.method,f'http://{ROOMS[room]}:5053{path}',headers={'X-Haunt-Token':TOKEN},json=request.get_json(silent=True) if channel is not None else None,timeout=5)
        return (r.content,r.status_code,{'Content-Type':'application/json'})
    except requests.RequestException as exc:
        return jsonify(error='Servo controller unreachable: '+type(exc).__name__),503

@app.route('/api/<room>/ultrasonic', methods=['GET','POST'])
def ultrasonic_proxy(room):
    if room not in ROOMS: return jsonify(error='Unknown room'),404
    path = '/status' if request.method == 'GET' else '/settings'
    try:
        r=requests.request(request.method, f'http://{ROOMS[room]}:5054{path}',
            headers={'X-Haunt-Token':TOKEN},
            json=(request.get_json(silent=True) or {}) if request.method == 'POST' else None,
            timeout=3)
        return (r.content,r.status_code,{'Content-Type':'application/json'})
    except requests.RequestException as exc:
        return jsonify(error='Ultrasonic controller unreachable: '+type(exc).__name__),503

@app.route('/api/mic/settings',methods=['GET','POST'])
def mic_settings():
    token=os.environ.get('VOICE_TOKEN','')
    if not token: return jsonify(error='Set VOICE_TOKEN in master haunt.env'),503
    try:
        r=requests.request(request.method,'http://haunt-mic.local:5013/settings',headers={'X-Voice-Token':token},json=(request.get_json(silent=True) or {}) if request.method=='POST' else None,timeout=4)
        return (r.content,r.status_code,{'Content-Type':'application/json'})
    except requests.RequestException as exc:
        return jsonify(error='Microphone unreachable: '+type(exc).__name__),503

if __name__ == '__main__': app.run(host='0.0.0.0',port=5000)
