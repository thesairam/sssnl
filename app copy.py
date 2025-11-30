import RPi.GPIO as GPIO
# DHT library selection: prefer CircuitPython driver, fall back to legacy Adafruit_DHT, else mock
try:
    import board
    import adafruit_dht as adafruit_circ_dht
    _DHT_LIB = 'circuitpython'
    print('Using adafruit_circuitpython_dht')
except Exception:
    try:
        import Adafruit_DHT
        adafruit_circ_dht = None
        board = None
        _DHT_LIB = 'legacy'
        print('Using legacy Adafruit_DHT')
    except Exception:
        adafruit_circ_dht = None
        board = None
        Adafruit_DHT = None
        _DHT_LIB = 'mock'
        print('No DHT library available; using mock values')
import subprocess
import time
import threading
from flask import Flask, render_template_string, jsonify

# -------------------
# CONFIG
# -------------------
PIR_PIN = 17
DHT_PIN = 4
# DHT type: 'DHT11' or 'DHT11'
DHT_TYPE = 'DHT11'
_dht_sensor_obj = None
if _DHT_LIB == 'circuitpython':
    # construct sensor object for board.Dxx pin
    try:
        board_pin = getattr(board, f'D{DHT_PIN}')
        if DHT_TYPE == 'DHT11':
            _dht_sensor_obj = adafruit_circ_dht.DHT11(board_pin)
        else:
            _dht_sensor_obj = adafruit_circ_dht.DHT11(board_pin)
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

# Shared values
current_temp = "--"
current_hum = "--"
motion_active = False
video_process = None
motion_status_msg = "No motion"

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
# SENSOR THREADS
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
                if _DHT_LIB == 'circuitpython' and _dht_sensor_obj is not None:
                    try:
                        # CircuitPython driver exposes properties
                        temperature = _dht_sensor_obj.temperature
                        humidity = _dht_sensor_obj.humidity
                    except Exception as e:
                        # read problems happen; log and continue
                        print('CircuitPython DHT read error:', e)
                        temperature = None
                        humidity = None
                elif _DHT_LIB == 'legacy' and Adafruit_DHT is not None:
                    try:
                        # legacy driver: read_retry
                        sensor = Adafruit_DHT.DHT22 if DHT_TYPE == 'DHT22' else Adafruit_DHT.DHT11
                        humidity, temperature = Adafruit_DHT.read_retry(sensor, DHT_PIN)
                    except Exception as e:
                        print('Legacy Adafruit_DHT read error:', e)
                        humidity = None
                        temperature = None
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
# DASHBOARD
# -------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Shirdi Sai Samaj Dashboard</title>
<style>
body { margin:0; background:black; color:white; font-family:Arial, sans-serif; overflow:hidden; }
.top-message { width:100%; background:#222; padding:10px; text-align:center; font-size:1.2em; position:fixed; top:0; left:0; }
    .top-message { width:100%; background:#222; padding:10px; text-align:center; font-size:1.2em; position:fixed; top:0; left:0; }
    .top-message .alert { color:#ff4d4d; font-weight:700; font-size:1.4em; }
.weather { position:absolute; top:5px; left:10px; font-size:1em; color:#fff; }
.main { display:flex; height:100vh; padding-top:60px; }
.left { width:50%; background:#000; }
.right { width:50%; display:flex; flex-direction:column; }
.news { flex:1; background:#111; text-align:center; font-size:1.2em; line-height:3em; }
.gallery { flex:1; background:#222; text-align:center; font-size:1.2em; line-height:3em; }
video { width:100%; height:100%; object-fit:cover; }
        /* unified media item sizing */
        :root { --media-aspect: 16/9; }
        .media-item { width:100%; height:100%; object-fit:cover; display:block; border-radius:6px; }
        .thumb { width:160px; height:100px; object-fit:cover; border-radius:6px; }
    /* layout tweaks: left column narrower, right wider */
    /* 2x2 equal grid layout: each quadrant gets equal space */
    .main { display:grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; height: calc(100vh - 60px); padding-top:60px; }
    .cell { overflow:hidden; display:flex; flex-direction:column; align-items:stretch; }
    .cell video, .cell img { width:100%; height:100%; object-fit:cover; display:block; }
    .cell.video { grid-column: 1 / 2; grid-row: 1 / 2; background:#000; }
    .cell.gallery { grid-column: 2 / 3; grid-row: 1 / 2; background:#111; }
    .cell.message { grid-column: 1 / 2; grid-row: 2 / 3; background:#111; display:flex; align-items:center; justify-content:center; padding:8px; }
    .cell.news { grid-column: 2 / 3; grid-row: 2 / 3; background:#222; }
    /* gallery/news grids: larger tiles that fill the quadrant */
    /* responsive grid: min tile size scales with viewport width, with sensible fallbacks */
    .gallery-grid, .news-grid { display:grid; gap:10px; padding:12px; width:100%; grid-template-columns: repeat(auto-fit, minmax(18vw, 1fr)); }
    .grid-item { width:100%; aspect-ratio: 4/3; overflow:hidden; }

    /* ensure tiles aren't too small on tiny screens */
    @media (max-width: 600px) {
        .gallery-grid, .news-grid { grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); }
        .grid-item { aspect-ratio: 4/3; }
    }
    /* increase min tile size on very large screens */
    @media (min-width: 1600px) {
        .gallery-grid, .news-grid { grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
    }
    .grid-item img { width:100%; height:100%; object-fit:cover; display:block; }
        .grid-item img { width:100%; height:100%; object-fit:cover; display:block; }
        .left-bottom img, .msg-img { width:100%; height:100%; object-fit:cover; border-radius:6px; }
</style>
</head>
</head>
<body>
<div class="top-message"><span class="alert">🌼 Please don't forget to turn off Diyas and close the door when leaving 🌼</span></div>
<div class="weather">🌤 Temp: <span id="temp">{{temp}}</span> | 💧 Humidity: <span id="hum">{{hum}}</span><br><small id="motion">🔍 Motion: {{motion_status}}</small><br><small id="dht-time"></small></div>
<div class="main">
    <div class="cell video">
        <video id="main-video" controls muted playsinline>
            <source src="/static/xxx.mp4" type="video/mp4">
        </video>
    </div>
    <div class="cell gallery">
        <h3 style="margin:8px;color:#fff;">🖼️ Gallery</h3>
        {% if gallery_images %}
            <div class="gallery-grid">
            {% for img in gallery_images %}
                <div class="grid-item"><img src="{{img}}" class="media-item"/></div>
            {% endfor %}
            </div>
        {% else %}
            <div style="color:#ddd;padding:8px;">�️ No gallery images found</div>
        {% endif %}
    </div>
    <div class="cell message">
        {% if message_image %}
            <img src="{{message_image}}" class="media-item"/>
        {% else %}
            <div style="color:#ddd;padding:8px;">No message image available</div>
        {% endif %}
    </div>
    <div class="cell news">
        <h3 style="margin:8px;color:#fff;">� News</h3>
        {% if news_images %}
            <div class="news-grid">
            {% for img in news_images %}
                <div class="grid-item"><img src="{{img}}" class="media-item"/></div>
            {% endfor %}
            </div>
        {% else %}
            <div style="color:#ddd;padding:8px;">� No news images found</div>
        {% endif %}
    </div>
</div>
<script>
// Poll server /status to update motion/temp and play/pause the video in-browser
async function fetchStatus(){
    try{
        const resp = await fetch('/status');
        if(!resp.ok) return;
        const data = await resp.json();
        document.getElementById('motion').innerText = '🔍 Motion: ' + data.motion_status;
        document.getElementById('temp').innerText = data.temp;
        document.getElementById('hum').innerText = data.hum;
        const dhtEl = document.getElementById('dht-time');
        if(data.last_dht_time){
            const t = new Date(data.last_dht_time*1000);
            dhtEl.innerText = 'Last DHT success: ' + t.toLocaleTimeString();
        } else {
            dhtEl.innerText = '';
        }

        const vid = document.getElementById('main-video');
        // ensure we only trigger one playback per motion event and let it finish
        if(typeof window.motionTriggered === 'undefined') window.motionTriggered = false;
        if(!vid.hasListenerAttached){
            vid.addEventListener('ended', ()=>{ window.motionTriggered = false; });
            vid.hasListenerAttached = true;
        }
        if(data.motion_active){
            try{
                if(!window.motionTriggered && vid.paused){ vid.play(); window.motionTriggered = true; }
            }catch(e){ }
        } else {
            // do not interrupt playback when motion stops; allow it to finish
        }
    }catch(e){ console.log('status error', e); }
}
setInterval(fetchStatus, 2000);
window.addEventListener('load', fetchStatus);
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(
        HTML_TEMPLATE,
        temp=current_temp,
        hum=current_hum,
        motion_status=motion_status_msg,
        news_images=news_images,
        gallery_images=gallery_images,
        message_image=message_image,
        message_images=message_images,
    )


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

# -------------------
# MAIN
# -------------------
if __name__ == "__main__":
    # start sensor threads
    threading.Thread(target=read_dht_sensor, daemon=True).start()
    threading.Thread(target=motion_detector, daemon=True).start()

    # copy video to Flask static folder
    import os, shutil
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    os.makedirs(static_dir, exist_ok=True)
    shutil.copy(VIDEO_PATH, os.path.join(static_dir, "xxx.mp4"))

    # copy images from sssnl/news and sssnl/gallery into static folders (if they exist)
    base_dir = os.path.dirname(__file__)
    def copy_images(src_rel, dest_subdir):
        """Copy images from one or more candidate source locations into static/<dest_subdir>.
        Returns list of URLs (starting with /static/...) present in the destination.
        Candidate sources tried (in order):
          - base_dir/src_rel (e.g. project/sssnl/news)
          - base_dir/<basename(src_rel)> (e.g. project/news)
          - other matches if present
        Also includes any images already present in the destination.
        """
        dest = os.path.join(static_dir, dest_subdir)
        os.makedirs(dest, exist_ok=True)
        imgs_set = []
        seen = set()

        # build candidate source paths
        candidates = []
        candidates.append(os.path.join(base_dir, src_rel))
        candidates.append(os.path.join(base_dir, os.path.basename(src_rel)))

        # try each candidate and copy images found
        for candidate in candidates:
            if os.path.isdir(candidate):
                for name in sorted(os.listdir(candidate)):
                    if not name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        continue
                    src_path = os.path.join(candidate, name)
                    dest_path = os.path.join(dest, name)
                    try:
                        # copy (overwrite) to destination
                        shutil.copy(src_path, dest_path)
                        url = f"/{os.path.relpath(dest, base_dir)}/{name}"
                        if url not in seen:
                            imgs_set.append(url)
                            seen.add(url)
                    except Exception as e:
                        print(f"Failed copying {src_path} -> {dest_path}: {e}")

        # Also include any images already present in dest (in case user placed them directly)
        if os.path.isdir(dest):
            for name in sorted(os.listdir(dest)):
                if not name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    continue
                url = f"/{os.path.relpath(dest, base_dir)}/{name}"
                if url not in seen:
                    imgs_set.append(url)
                    seen.add(url)

        return imgs_set

    # populate image lists used by the template via module globals
    news_images = copy_images('sssnl/news', 'news')
    gallery_images = copy_images('sssnl/gallery', 'gallery')

    # fetch today's message image from mysai.org and save to static/message/latest.jpg
    def fetch_today_message_image():
        import datetime, urllib.request, os
        try:
            today = datetime.date.today()
            # Build direct image URL like: https://www.mysai.org/month10/22.jpg
            img_url = f"https://www.mysai.org/month{today.month}/{today.day}.jpg"
            # download image
            with urllib.request.urlopen(img_url, timeout=10) as r2:
                if r2.status != 200:
                    print('Failed to download message image', r2.status)
                    return None
                data = r2.read()
                dest_dir = os.path.join(static_dir, 'message')
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(dest_dir, 'latest.jpg')
                with open(dest_path, 'wb') as f:
                    f.write(data)
                return f"/{os.path.relpath(dest_dir, base_dir)}/latest.jpg"
        except Exception as e:
            print('Error fetching message image:', e)
            return None

    try:
        message_image = fetch_today_message_image()
    except Exception as e:
        print('Message fetch failed:', e)
    message_images = copy_images('sssnl/message', 'message')

    print("🚀 Dashboard running on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000)
