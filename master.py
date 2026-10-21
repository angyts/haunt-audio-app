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
HTML = '''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gui Gui Audio Control</title><style>body{font:16px system-ui;background:#101522;color:#e9eef9;max-width:900px;margin:25px auto;padding:12px}h1{color:#b9a8ff}.room{background:#20283a;padding:18px;border-radius:14px;margin:12px 0}button,input{margin:5px;padding:10px;border-radius:7px}button{cursor:pointer}.state{font-weight:bold;color:#a9e7c2}small{color:#b7c4d7}</style></head><body><h1>👻 Gui Gui Audio Control</h1><p>Upload a loop to a room, then play / pause / stop.</p><div id="rooms"></div><script>
const names = {{names|tojson}};
const root=document.getElementById('rooms');
for(const name of names){const div=document.createElement('div');div.className='room';div.innerHTML=`<h2>${name}</h2><p class="state" id="s-${name}">Checking...</p><input id="f-${name}" type="file" accept="audio/*"><button onclick="upload('${name}')">Upload</button><p><button onclick="cmd('${name}','play')">▶ Play / Resume</button><button onclick="cmd('${name}','pause')">⏸ Pause</button><button onclick="cmd('${name}','stop')">■ Stop</button></p><label>Volume <span id="v-${name}">70</span>% <input type="range" min="0" max="100" value="70" id="vol-${name}" oninput="document.getElementById('v-${name}').textContent=this.value" onchange="setVolume('${name}',this.value)"></label><br><small id="m-${name}"></small>`;root.appendChild(div)}
async function refresh(name){try{const r=await fetch(`/api/${name}/status`);const d=await r.json();document.getElementById(`s-${name}`).textContent=r.ok?`${d.state} — ${d.file||'No file'}`:`Offline / ${d.error||r.status}`;if(r.ok && Number.isFinite(d.volume)){const slider=document.getElementById(`vol-${name}`);if(document.activeElement!==slider){slider.value=d.volume;document.getElementById(`v-${name}`).textContent=d.volume}}}catch(e){document.getElementById(`s-${name}`).textContent='Offline'}}
async function setVolume(name,value){const r=await fetch(`/api/${name}/volume`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({volume:Number(value)})});const d=await r.json();document.getElementById(`m-${name}`).textContent=d.error||'';refresh(name)}
async function cmd(name,action){const r=await fetch(`/api/${name}/${action}`,{method:'POST'});const d=await r.json();document.getElementById(`m-${name}`).textContent=d.error||'';refresh(name)}
async function upload(name){const file=document.getElementById(`f-${name}`).files[0];if(!file)return alert('Choose a file');const fd=new FormData();fd.append('file',file);const r=await fetch(`/api/${name}/upload`,{method:'POST',body:fd});const d=await r.json();document.getElementById(`m-${name}`).textContent=r.ok?'Uploaded and playing on loop':d.error;refresh(name)}
for(const name of names)refresh(name);setInterval(()=>{for(const name of names)refresh(name)},5000);
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

if __name__ == '__main__': app.run(host='0.0.0.0',port=5000)
