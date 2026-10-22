import os, time, subprocess, tempfile, urllib.request, array, math, sys

DEVICE = os.environ.get('VOICE_CAPTURE_DEVICE', 'plughw:2,0')
DEST = os.environ.get('VOICE_RECEIVER_URL', 'http://haunt-corridor.local:5012/voice')
TOKEN = os.environ.get('VOICE_TOKEN', '')
THRESHOLD = int(os.environ.get('VOICE_THRESHOLD', '850'))
COOLDOWN = float(os.environ.get('VOICE_COOLDOWN', '10'))
RATE = 16000

if not TOKEN:
    raise SystemExit('VOICE_TOKEN is required')

print('Listening; threshold:', THRESHOLD, flush=True)
while True:
    # A short sound-level sample, with no recording retained.
    sample = subprocess.run(['arecord', '-q', '-D', DEVICE, '-t', 'raw', '-f', 'S16_LE', '-r', str(RATE), '-c', '1', '-d', '1'], capture_output=True)
    if sample.returncode != 0:
        print('Capture error:', sample.stderr.decode(errors='replace'), flush=True)
        time.sleep(2)
        continue
    samples = array.array('h')
    samples.frombytes(sample.stdout[:len(sample.stdout) // 2 * 2])
    if sys.byteorder != 'little': samples.byteswap()
    rms = math.sqrt(sum(v * v for v in samples) / len(samples)) if samples else 0
    if rms < THRESHOLD:
        continue
    print('Triggered, RMS:', rms, flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        original = os.path.join(tmp, 'original.wav')
        shifted = os.path.join(tmp, 'shifted.wav')
        rec = subprocess.run(['arecord', '-q', '-D', DEVICE, '-f', 'S16_LE', '-r', str(RATE), '-c', '1', '-d', '2', original], capture_output=True)
        if rec.returncode != 0:
            print('Record error:', rec.stderr.decode(errors='replace'), flush=True)
            time.sleep(COOLDOWN)
            continue
        fx = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', original, '-af', 'asetrate=16000*1.4,aresample=16000', '-acodec', 'pcm_s16le', shifted], capture_output=True)
        if fx.returncode == 0:
            try:
                with open(shifted, 'rb') as f: data = f.read()
                req = urllib.request.Request(DEST, data=data, method='POST', headers={'X-Voice-Token': TOKEN, 'Content-Type': 'audio/wav'})
                with urllib.request.urlopen(req, timeout=8) as res:
                    print('Sent:', res.status, flush=True)
            except Exception as e:
                print('Send failed:', e, flush=True)
        else:
            print('FFmpeg failed:', fx.stderr.decode(errors='replace'), flush=True)
    time.sleep(COOLDOWN)
