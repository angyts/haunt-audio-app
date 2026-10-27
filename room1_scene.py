#!/usr/bin/env python3
"""Room 1: distance-based chant overlay and sequential servo cues.
Edit room1_scene.json; changes are loaded automatically. Set enabled=true to arm.
"""
import json, os, signal, subprocess, threading, time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'room1_scene.json'
TOKEN = os.environ['HAUNT_TOKEN']
HEADERS = {'X-Haunt-Token': TOKEN}
BASE = 'http://127.0.0.1:'
STOP = threading.Event()
chant = None
sequence = None
last_trigger = -1e10
armed = True

def api(port, path, data=None):
    headers = dict(HEADERS)
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(BASE + str(port) + path,
                  data=json.dumps(data).encode() if data is not None else None,
                  headers=headers, method='POST' if data is not None else 'GET')
    with urlopen(req, timeout=2) as response:
        return json.load(response)

def config():
    d = json.loads(CONFIG.read_text())
    if not 20 <= float(d['near_cm']) < float(d['trigger_cm']) < float(d['release_cm']) <= 300:
        raise ValueError('Invalid distance thresholds')
    for step in d['servo_sequence']:
        if int(step['servo']) not in (1, 2, 3, 4) or not -45 <= float(step['angle']) <= 45:
            raise ValueError('Invalid servo setting')
    return d

def volume(proc, level):
    if proc and proc.poll() is None and proc.stdin:
        try:
            proc.stdin.write(f'volume {round(max(0,min(100,level))*256/100)}\n')
            proc.stdin.flush()
        except (OSError, BrokenPipeError):
            pass

def stop_chant():
    global chant
    if chant:
        if chant.poll() is None:
            chant.terminate()
            try: chant.wait(timeout=2)
            except subprocess.TimeoutExpired: chant.kill(); chant.wait()
        chant = None

def start_chant(path):
    global chant
    if chant and chant.poll() is None:
        return
    if not Path(path).is_file():
        print('Chant file missing:', path, flush=True)
        return
    chant = subprocess.Popen(['cvlc', '--intf', 'rc', '--rc-fake-tty', '--no-video', '--loop', path],
                             stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, text=True, bufsize=1)

def run_sequence(steps):
    for step in steps:
        if STOP.is_set(): break
        i = int(step['servo'])
        try:
            api(5053, f'/servo/{i}', {'angle': float(step['angle'])})
            if STOP.wait(max(0, float(step.get('hold', 1)))): break
            api(5053, f'/servo/{i}', {'angle': 0})
            if STOP.wait(max(0, float(step.get('pause', .8)))): break
        except Exception as exc:
            print('Servo cue error:', exc, flush=True)

def main():
    global last_trigger, armed, sequence
    print('Room 1 scene controller started; edit JSON to configure', flush=True)
    while not STOP.is_set():
        try:
            c = config()
            if not c.get('enabled', False):
                stop_chant()
                armed = True
                STOP.wait(.5)
                continue
            s = api(5054, '/status')
            d = s.get('distance_cm')
            if s.get('stale') or not s.get('enabled') or not isinstance(d, (int,float)):
                stop_chant()
                STOP.wait(.5)
                continue
            if d >= c['release_cm']:
                armed = True
                stop_chant()
            elif d <= c['trigger_cm']:
                start_chant(c['chant_file'])
                if chant:
                    frac = max(0, min(1, (c['trigger_cm']-d)/(c['trigger_cm']-c['near_cm'])))
                    volume(chant, c['chant_min_volume'] + frac*(c['chant_max_volume']-c['chant_min_volume']))
                if armed and time.monotonic()-last_trigger >= c['cooldown_seconds'] and (sequence is None or not sequence.is_alive()):
                    armed = False
                    last_trigger = time.monotonic()
                    sequence = threading.Thread(target=run_sequence, args=(list(c['servo_sequence']),), daemon=True)
                    sequence.start()
            else:
                stop_chant()
            STOP.wait(.4)
        except Exception as exc:
            print('Scene loop:', type(exc).__name__, str(exc), flush=True)
            stop_chant()
            STOP.wait(2)
    stop_chant()

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    main()
