# ...existing code...
try:
    import RPi.GPIO as GPIO
    _HAS_GPIO = True
except Exception:
    _HAS_GPIO = False

    class _MockGPIO:
        BCM = 0
        IN = 0

        def setmode(self, *args, **kwargs):
            pass

        def setup(self, *args, **kwargs):
            pass

        def input(self, *args, **kwargs):
            # no real PIR on desktop; default low (no motion)
            return 0

    GPIO = _MockGPIO()
    print('RPi.GPIO not available; using mock GPIO (no real motion input)')

# DHT library selection: prefer CircuitPython driver, else mock
try:
    import board
    import adafruit_dht as adafruit_circ_dht
    _DHT_LIB = 'circuitpython'
    print('Using adafruit_circuitpython_dht')
except Exception:
    adafruit_circ_dht = None
    board = None
    _DHT_LIB = 'mock'
    print('No CircuitPython DHT library available; using mock values')
import subprocess
import time
import threading
import os, shutil
from flask import Flask, render_template_string, jsonify, request, send_from_directory

# -------------------
# CONFIG
# -------------------
PIR_PIN = 17
DHT_PIN = 4
# DHT type: 'DHT11' or 'DHT22'
DHT_TYPE = 'DHT11'
_dht_sensor_obj = None
if _DHT_LIB == 'circuitpython':
    # construct sensor object for board.Dxx pin
    try:
        board_pin = getattr(board, f'D{DHT_PIN}')
        if DHT_TYPE == 'DHT11':
            _dht_sensor_obj = adafruit_circ_dht.DHT11(board_pin)
        else:
            _dht_sensor_obj = adafruit_circ_dht.DHT22(board_pin)
    except Exception as e:
        print('Failed to initialize CircuitPython DHT sensor:', e)
        _dht_sensor_obj = None
VIDEO_PATH = "/home/saipi/Projects/sssnl/videos/xxx.mp4"
# If your PIR outputs 1 for motion, keep PIR_ACTIVE_VALUE = 1.
# If it outputs 0 for motion, set PIR_ACTIVE_VALUE = 0
PIR_ACTIVE_VALUE = 1
# number of consecutive reads required to flip motion state (simple debounce)
PIR_DEBOUNCE_READS = 2

# -------------------
# GPIO SETUP
# -------------------
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)

# -------------------
# FLASK APP
# -------------------
app = Flask(__name__)

# Register media uploader blueprint for simple CMS (API under /api/media)
try:
    from media_admin import bp as media_uploader_bp
    app.register_blueprint(media_uploader_bp, url_prefix='/api/media')
except Exception as e:
    print('Warning: media_uploader blueprint not registered:', e)

# Optional path to Flutter Web build of the media/dev controls app.
DEV_WEB_DIR = os.path.join(os.path.dirname(__file__), 'sssnl_media_controls', 'build', 'web')
DASHBOARD_WEB_DIR = os.path.join(os.path.dirname(__file__), 'sssnl_app', 'build', 'web')

# Shared values
current_temp = "--"
current_hum = "--"
motion_active = False
video_process = None
motion_status_msg = "No motion"

# Optional overrides used for desktop/mock testing; when not None,
# the motion detector / DHT reader will use these instead of hardware.
mock_motion_override = None  # type: ignore[assignment]
mock_dht_override = None     # type: ignore[assignment]

# diagnostic timestamps/status
last_dht_time = None
last_dht_success = False
last_motion_raw = None
last_motion_change = None

# image lists for template
news_images = []
gallery_images = []
message_image = None
message_images = []

# lock to prevent concurrent DHT access
dht_lock = threading.Lock()

# -------------------
# SENSOR THREADS (unchanged logic)
# -------------------
def read_dht_sensor():
    global current_temp, current_hum
    global motion_status_msg
    global last_dht_time, last_dht_success
    # read_retry sometimes fails on some Pi setups; add extra handling and a short timeout
    while True:
        humidity = None
        temperature = None
        try:
            # protect hardware access with a lock to avoid concurrent access from endpoints
            with dht_lock:
                if mock_dht_override is not None:
                    # explicit override for testing (desktop / dev tools)
                    temperature = mock_dht_override.get('temp')
                    humidity = mock_dht_override.get('hum')
                elif _DHT_LIB == 'circuitpython' and _dht_sensor_obj is not None:
                    try:
                        # CircuitPython driver exposes properties
                        temperature = _dht_sensor_obj.temperature
                        humidity = _dht_sensor_obj.humidity
                    except Exception as e:
                        # read problems happen; log and continue
                        print('CircuitPython DHT read error:', e)
                        temperature = None
                        humidity = None
                else:
                    # mock values for testing when no library is available
                    import random
                    temperature = 20.0 + random.random() * 6.0
                    humidity = 40.0 + random.random() * 20.0
        except Exception as e:
            print('Unexpected DHT error:', e)
            humidity, temperature = None, None

        if humidity is not None and temperature is not None:
            # update values
            current_temp = f"{temperature:.1f}°C"
            current_hum = f"{humidity:.1f}%"
            last_dht_time = time.time()
            last_dht_success = True
        else:
            # show blank but keep previous values if available; use placeholders
            current_temp = current_temp if current_temp != "--" else "--"
            current_hum = current_hum if current_hum != "--" else "--"
            last_dht_success = False

        # also update motion status message so the page can display quickly
        if motion_active:
            motion_status_msg = "Motion detected"
        else:
            motion_status_msg = "No motion"

        time.sleep(10)

def motion_detector():
    global motion_active, video_process, motion_status_msg
    global last_motion_raw, last_motion_change
    # simple debounce: require consecutive consistent reads
    consecutive = 0
    last_state = None
    while True:
        raw = GPIO.input(PIR_PIN)
        last_motion_raw = raw
        # interpret according to PIR_ACTIVE_VALUE
        is_motion = (raw == PIR_ACTIVE_VALUE)

        # If a mock override is set (e.g., from /mock-motion endpoint),
        # ignore the hardware reading and use the override value instead.
        if mock_motion_override is not None:
            is_motion = bool(mock_motion_override)

        if last_state is None:
            last_state = is_motion
            consecutive = 1
        else:
            if is_motion == last_state:
                consecutive += 1
            else:
                consecutive = 1
                last_state = is_motion

        if consecutive >= PIR_DEBOUNCE_READS:
            if is_motion and not motion_active:
                print("🚶 Motion detected (debounced)")
                motion_active = True
                motion_status_msg = "Motion detected"
                last_motion_change = time.time()
                # do not spawn VLC fullscreen anymore; browser will play the video
            elif not is_motion and motion_active:
                print("🛑 Motion stopped (debounced)")
                motion_active = False
                motion_status_msg = "No motion"
                last_motion_change = time.time()

        time.sleep(0.5)

# -------------------
# DASHBOARD - single autoplay playlist view
# -------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Shirdi Sai Samaj - Autoplay</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
html,body { height:100%; margin:0; background:black; color:white; font-family:Inter, Arial, sans-serif; }
.container { position:relative; width:100%; height:100vh; overflow:hidden; background:black; display:flex; align-items:center; justify-content:center; }
#media-wrapper { position:relative; width:100%; height:100%; background:black; }
/* Make media cover the whole area while preserving aspect ratio. Using absolute positioning
    avoids layout shifts and ensures full-bleed visuals on different resolutions. */
#pl-video, #pl-image { position:absolute; top:0; left:0; width:100%; height:100%; display:none; background:black; }
#pl-video { object-fit: cover; }
#pl-image { object-fit: contain; }
#status-bar { position:fixed; top:12px; left:12px; z-index:60; background:rgba(0,0,0,0.50); color:#fff; padding:10px 16px; border-radius:10px; font-size:1.35em; line-height:1.2; box-shadow:0 4px 16px rgba(0,0,0,0.65); }
.top-msg { position:fixed; top:12px; right:12px; z-index:60; color:#ff6b6b; font-weight:700; font-size:2.4em; background:rgba(0,0,0,0.40); padding:16px 24px; border-radius:14px; box-shadow:0 4px 18px rgba(0,0,0,0.55); }
#pl-video, #pl-image { position:absolute; top:100px; left:0; width:100%; height:calc(100% - 100px); display:none; background:black; }
.hidden { display:none !important; }
.center-msg { position:absolute; color:#ddd; font-size:1.2em; text-align:center; left:50%; top:50%; transform:translate(-50%,-50%); }
/* Small screens: slightly reduce status font */
@media (max-width:600px){ #status-bar{font-size:1.05em;padding:8px 12px} .top-msg{font-size:1.8em;padding:12px 16px} #pl-video,#pl-image{top:90px;height:calc(100% - 90px)} }
</style>
</head>
<body>
<div id="status-bar">Temp: <span id="temp">{{temp}}</span> | Humidity: <span id="hum">{{hum}}</span> | Motion: <span id="motion_txt">{{motion_status}}</span></div>
<div class="top-msg">🌼 Don't forget to turn off Diyas & close doors 🌼</div>

<div class="container">
    <div id="media-wrapper">
    <video id="pl-video" playsinline muted preload="auto"></video>
        <img id="pl-image" alt="media"/>
        <div id="idle-msg" class="center-msg">Awaiting motion...</div>
    </div>
</div>

<script>
/* Playlist will be fetched on-demand from the server */
let playlist = [];
const IMAGE_DISPLAY_MS = 6000; // default image display duration
let playing = false;
let motionTriggered = false;

function showIdle(yes){
    const idle = document.getElementById('idle-msg');
    const vid = document.getElementById('pl-video');
    const img = document.getElementById('pl-image');
    if(yes){
        vid.style.display = 'none';
        vid.pause();
        img.style.display = 'none';
        idle.style.display = 'block';
    } else {
        idle.style.display = 'none';
    }
}
function showVideo(){
    document.getElementById('pl-image').style.display = 'none';
    const v = document.getElementById('pl-video'); v.style.display = 'block';
}
function showImage(){
    document.getElementById('pl-video').style.display = 'none';
    const i = document.getElementById('pl-image'); i.style.display = 'block';
}
function wait(ms){ return new Promise(r=>setTimeout(r, ms)); }
function waitVideoEnd(videoEl){
    // Wait for the video to end, but don't hang forever — use duration as a fallback timeout.
    return new Promise((resolve) => {
        let settled = false;
        function cleanup(){ videoEl.removeEventListener('ended', onEnd); videoEl.removeEventListener('error', onError); videoEl.removeEventListener('loadedmetadata', onLoaded); if(timeout) clearTimeout(timeout); }
        function onEnd(){ if(settled) return; settled = true; cleanup(); resolve(); }
        function onError(e){ if(settled) return; settled = true; cleanup(); resolve(); }
        function onLoaded(){ // metadata loaded, we can set a duration-based timeout if needed
            setupTimeout();
        }

        let timeout = null;
        function setupTimeout(){
            if(timeout) { clearTimeout(timeout); timeout = null; }
            try{
                const dur = Number(videoEl.duration) || 0;
                if(dur > 0 && isFinite(dur)){
                    // add small buffer
                    timeout = setTimeout(()=>{ if(settled) return; settled = true; cleanup(); resolve(); }, (dur*1000) + 2500);
                }
            }catch(e){ /* ignore */ }
        }

        videoEl.addEventListener('ended', onEnd);
        videoEl.addEventListener('error', onError);
        videoEl.addEventListener('loadedmetadata', onLoaded);

        // start with a safe maximum timeout in case metadata never arrives
        timeout = setTimeout(()=>{ if(settled) return; settled = true; cleanup(); resolve(); }, 45000);

        // if video already ended
        if(videoEl.ended){ onEnd(); }
    });
}

async function playPlaylistOnce(){
    if(playing) return;
    playing = true;
    motionTriggered = true;
    showIdle(false);
    const vid = document.getElementById('pl-video');
    const img = document.getElementById('pl-image');

        // Always load the freshest playlist from server so new uploads are included
        try{
            const r = await fetch('/playlist', {cache: 'no-store'});
            if(r.ok){
                const data = await r.json();
                playlist = Array.isArray(data.playlist) ? data.playlist : [];
            } else {
                playlist = [];
            }
        }catch(e){ playlist = []; }

        for(const item of playlist){
            if(item.type === 'video'){
                try{
                    showVideo();
                    // ensure we can autoplay by keeping muted during autoplay (browsers allow muted autoplay)
                    vid.muted = true;
                    vid.src = item.src;
                    vid.currentTime = 0;
                    // try to play; if autoplay policy prevents playback, the waitVideoEnd() has a timeout fallback
                    try{ await vid.play(); }catch(e){ console.log('autoplay prevented or play failed, will wait for duration fallback', e); }
                    await waitVideoEnd(vid);
                } catch(e){
                    console.log('video play error', e);
                } finally {
                    // cleanup src to free resource
                    try{ vid.pause(); vid.removeAttribute('src'); vid.load(); }catch(e){}
                }
            } else {
                showImage();
                img.src = item.src;
                const ms = item.duration_ms || IMAGE_DISPLAY_MS;
                await wait(ms);
            }
        }

    // finished playlist
    playing = false;
    motionTriggered = false;
    showIdle(true);
}

// Poll status from server to know motion / DHT updates
let lastMotionActive = false;
async function fetchStatus(){
    try{
        const resp = await fetch('/status');
        if(!resp.ok) return;
        const data = await resp.json();
        document.getElementById('temp').innerText = data.temp;
        document.getElementById('hum').innerText = data.hum;
        document.getElementById('motion_txt').innerText = data.motion_status;

        // Trigger playback on motion rising edge only if not currently playing
        if(data.motion_active && !motionTriggered && !playing){
            // Start playback and let it finish (do not restart mid-play)
            playPlaylistOnce();
        }
        // If no motion and not playing => idle screen stays visible (blank)
        // If playing, do not interrupt
    }catch(e){
        console.log('status error', e);
    }
}

window.addEventListener('load', ()=>{
    showIdle(true);
    fetchStatus();
    setInterval(fetchStatus, 1500);
});
</script>
</body>
</html>
"""

@app.route("/")
def index():
    # supply playlist to template
    return render_template_string(
        HTML_TEMPLATE,
        temp=current_temp,
        hum=current_hum,
        motion_status=motion_status_msg,
        # playlist now fetched client-side from /playlist
    )


@app.route('/playlist')
def get_playlist():
    # Build fresh playlist every time from static/media
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    media_dir = os.path.join(static_dir, 'media')
    base_dir = os.path.dirname(__file__)
    image_exts = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
    video_exts = ('.mp4', '.mov', '.m4v', '.avi', '.webm')
    items = []
    try:
        if os.path.isdir(media_dir):
            for fname in sorted(os.listdir(media_dir)):
                if fname.lower().endswith(video_exts):
                    path = os.path.join(media_dir, fname)
                    items.append({'type': 'video', 'src': f"/{os.path.relpath(path, base_dir)}"})
            for fname in sorted(os.listdir(media_dir)):
                if fname.lower().endswith(image_exts):
                    path = os.path.join(media_dir, fname)
                    items.append({'type': 'image', 'src': f"/{os.path.relpath(path, base_dir)}", 'duration_ms': 6000})
    except Exception as e:
        return jsonify({'playlist': [], 'error': str(e)}), 200
    return jsonify({'playlist': items})

@app.route('/status')
def status():
    # Return JSON status for JS polling
    return jsonify({
        'temp': current_temp,
        'hum': current_hum,
        'motion_status': motion_status_msg,
        'motion_active': motion_active,
        'last_dht_time': last_dht_time,
        'last_dht_success': last_dht_success,
        'last_motion_raw': last_motion_raw,
        'last_motion_change': last_motion_change,
    })


@app.route('/dht-debug')
def dht_debug():
    """Return which DHT backend is active and attempt a single immediate read."""
    backend = _DHT_LIB
    read = {'temp': None, 'hum': None, 'error': None}
    try:
        if _DHT_LIB == 'circuitpython' and _dht_sensor_obj is not None:
            try:
                with dht_lock:
                    read['temp'] = _dht_sensor_obj.temperature
                    read['hum'] = _dht_sensor_obj.humidity
            except Exception as e:
                read['error'] = str(e)
        elif _DHT_LIB == 'legacy' and Adafruit_DHT is not None:
            try:
                sensor = Adafruit_DHT.DHT11 if DHT_TYPE == 'DHT11' else Adafruit_DHT.DHT11
                h, t = Adafruit_DHT.read_retry(sensor, DHT_PIN, retries=2, delay_seconds=1)
                read['temp'] = t
                read['hum'] = h
            except Exception as e:
                read['error'] = str(e)
        else:
            read['temp'] = 21.5
            read['hum'] = 55.0
    except Exception as e:
        read['error'] = str(e)

    return jsonify({'backend': backend, 'read': read, 'last_dht_time': last_dht_time, 'last_dht_success': last_dht_success})


@app.route('/mock-motion', methods=['POST'])
def mock_motion():
    """Force motion on/off for testing on desktop.

    Usage examples:
      curl -X POST localhost:5656/mock-motion -H 'Content-Type: application/json' -d '{"active": true}'
      curl -X POST localhost:5656/mock-motion -H 'Content-Type: application/json' -d '{"active": false}'
    """
    global mock_motion_override, motion_active, motion_status_msg, last_motion_change

    data = request.get_json(silent=True) or {}
    val = data.get('active')
    if val is None:
        # allow query param ?active=true as a fallback
        qp = request.args.get('active')
        if qp is not None:
            val = qp

    # Normalize to boolean
    if isinstance(val, str):
        val = val.strip().lower() in {"1", "true", "on", "yes"}
    elif isinstance(val, (int, float)):
        val = bool(val)

    active = bool(val)
    mock_motion_override = active
    motion_active = active
    motion_status_msg = "Motion detected" if active else "No motion"
    last_motion_change = time.time()

    return jsonify({
        'ok': True,
        'motion_active': motion_active,
        'override': True,
    })


@app.route('/mock-motion/clear', methods=['POST'])
def clear_mock_motion():
    """Clear the motion override so PIR GPIO drives motion again."""
    global mock_motion_override
    mock_motion_override = None
    return jsonify({
        'ok': True,
        'override': False,
        'motion_active': motion_active,
    })


@app.route('/mock-dht', methods=['POST'])
def mock_dht():
    """Override DHT readings for desktop/dev testing.

    JSON body: {"temp": 25.0, "hum": 60.0}
    """
    global mock_dht_override, current_temp, current_hum, last_dht_time, last_dht_success

    data = request.get_json(silent=True) or {}
    temp = data.get('temp')
    hum = data.get('hum')

    try:
        temp_val = float(temp) if temp is not None else None
        hum_val = float(hum) if hum is not None else None
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'invalid temp/hum'}), 400

    mock_dht_override = {'temp': temp_val, 'hum': hum_val}
    if temp_val is not None and hum_val is not None:
        current_temp = f"{temp_val:.1f}°C"
        current_hum = f"{hum_val:.1f}%"
        last_dht_time = time.time()
        last_dht_success = True

    return jsonify({'ok': True, 'override': True, 'temp': temp_val, 'hum': hum_val})


@app.route('/mock-dht/clear', methods=['POST'])
def clear_mock_dht():
    """Clear DHT override so real/random readings are used again."""
    global mock_dht_override
    mock_dht_override = None
    return jsonify({'ok': True, 'override': False})


@app.route('/dashboard/')
@app.route('/dashboard/<path:path>')
def dashboard_web_app(path="index.html"):
    """Serve the Flutter Web build of the dashboard app.

    Build first with:
      cd sssnl_app && flutter build web
    """
    if not os.path.isdir(DASHBOARD_WEB_DIR):
        return jsonify({
            'error': 'dashboard_web_not_built',
            'message': 'Run "flutter build web" in sssnl_app first.',
        }), 500

    full_path = os.path.join(DASHBOARD_WEB_DIR, path)
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        path = 'index.html'
    return send_from_directory(DASHBOARD_WEB_DIR, path)


@app.route('/media/')
@app.route('/media/<path:path>')
def media_web_app(path="index.html"):
    """Serve the Flutter Web build of the media/dev controls app for media/dev UI.

    Build first with:
      cd sssnl_media_controls && flutter build web
    """
    # If the web build is missing, return a helpful JSON error.
    if not os.path.isdir(DEV_WEB_DIR):
        return jsonify({
            'error': 'dev_web_not_built',
            'message': 'Run "flutter build web" in sssnl_media_controls first.',
        }), 500

    # Fallback to index.html for unknown paths (SPA-style routing).
    full_path = os.path.join(DEV_WEB_DIR, path)
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        path = 'index.html'
    return send_from_directory(DEV_WEB_DIR, path)


@app.route('/dev/')
@app.route('/dev/<path:path>')
def dev_web_app(path="index.html"):
    """Alias /dev to the same Flutter Web media/dev controls app.

    /media will open the Media tab, /dev will open the Developer tab.
    """
    return media_web_app(path)

# -------------------
# STARTUP: prepare static folders, images and playlist
# -------------------
if __name__ == "__main__":
    # start sensor threads
    threading.Thread(target=read_dht_sensor, daemon=True).start()
    threading.Thread(target=motion_detector, daemon=True).start()

    # unify all media into a single static/media folder (move files from other source folders)
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    os.makedirs(static_dir, exist_ok=True)

    media_dir = os.path.join(static_dir, 'media')
    os.makedirs(media_dir, exist_ok=True)

    # Candidate source directories to move files from (project-root relative)
    base_dir = os.path.dirname(__file__)
    candidate_dirs = [
        os.path.join(base_dir, 'videos'),
        os.path.join(base_dir, 'sssnl', 'gallery'),
        os.path.join(base_dir, 'sssnl', 'news'),
        os.path.join(base_dir, 'sssnl', 'message'),
        os.path.join(base_dir, 'gallery'),
        os.path.join(base_dir, 'news'),
        os.path.join(base_dir, 'message'),
    ]

    # Also include any files already in static subfolders
    candidate_dirs += [
        os.path.join(static_dir, 'gallery'),
        os.path.join(static_dir, 'news'),
        os.path.join(static_dir, 'message'),
        os.path.join(static_dir, 'videos'),
    ]

    image_exts = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
    video_exts = ('.mp4', '.mov', '.m4v', '.avi', '.webm')

    def move_media_from(src_dir):
        if not os.path.isdir(src_dir):
            return
        for name in sorted(os.listdir(src_dir)):
            lower = name.lower()
            if not lower.endswith(image_exts + video_exts):
                continue
            src_path = os.path.join(src_dir, name)
            # compute destination and avoid overwriting
            dest_name = name
            base, ext = os.path.splitext(dest_name)
            counter = 1
            dest_path = os.path.join(media_dir, dest_name)
            while os.path.exists(dest_path):
                dest_name = f"{base}_{counter}{ext}"
                dest_path = os.path.join(media_dir, dest_name)
                counter += 1
            try:
                shutil.move(src_path, dest_path)
                print(f"Moved {src_path} -> {dest_path}")
            except Exception as e:
                print(f"Failed to move {src_path} -> {dest_path}: {e}")

    # Move files from candidates
    for d in candidate_dirs:
        move_media_from(d)

    # Also move the default video if present at VIDEO_PATH into media
    try:
        if os.path.isfile(VIDEO_PATH):
            name = os.path.basename(VIDEO_PATH)
            dest = os.path.join(media_dir, name)
            if not os.path.exists(dest):
                try:
                    shutil.move(VIDEO_PATH, dest)
                    print(f"Moved default video {VIDEO_PATH} -> {dest}")
                except Exception as e:
                    print('Warning: could not move default video:', e)
    except Exception as e:
        print('Warning checking VIDEO_PATH:', e)

    # Client will fetch playlist via /playlist; no need to build here

    print("🚀 Dashboard running on http://0.0.0.0:5656 (single-playlist mode)")
    app.run(host="0.0.0.0", port=5656)