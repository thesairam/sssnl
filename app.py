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
import sqlite3
from sqlalchemy import create_engine, text, Table, Column, Integer, String, MetaData
from sqlalchemy.engine import Engine
from flask import Flask, render_template_string, jsonify, request, send_from_directory, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash

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
# Secret key for session cookies (set via env in production)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-sssnl')

"""Database configuration: uses SQLAlchemy. Defaults to MariaDB if DB_URI env provided,
else falls back to SQLite file under data/users.db."""
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)
USERS_DB_PATH = os.path.join(DATA_DIR, 'users.db')

DB_URI = os.environ.get('DB_URI') or f"sqlite:///{USERS_DB_PATH}"
_db_engine: Engine = create_engine(DB_URI, pool_pre_ping=True, future=True)

_metadata = MetaData()
users_table = Table(
    'users', _metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('username', String(255), unique=True, nullable=False),
    Column('password_hash', String(255), nullable=False),
    Column('role', String(32), nullable=False, default='user'),
    Column('created_at', Integer, nullable=False),
)

devices_table = Table(
    'devices', _metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('user_id', String(255), nullable=False),
    Column('device_mac', String(255), nullable=False),
    Column('device_name', String(255)),
    Column('configured_at', Integer, nullable=False),
)

def _db_connect():
    return _db_engine.connect()

def init_users_db():
    # Create tables if not exist
    _metadata.create_all(_db_engine)
    # Seed admins
    admin_user = os.environ.get('SSSNL_ADMIN_USER')
    admin_pass = os.environ.get('SSSNL_ADMIN_PASS')
    with _db_engine.begin() as conn:
        if admin_user and admin_pass:
            row = conn.execute(text('SELECT id FROM users WHERE username=:u'), {'u': admin_user.lower().strip()}).fetchone()
            if not row:
                conn.execute(
                    text('INSERT INTO users (username, password_hash, role, created_at) VALUES (:u,:ph,:role,:ts)'),
                    {'u': admin_user.lower().strip(), 'ph': generate_password_hash(admin_pass), 'role': 'admin', 'ts': int(time.time())}
                )
        # ensure default admin 'dbadmin' exists
        row = conn.execute(text('SELECT id FROM users WHERE username=:u'), {'u': 'dbadmin'}).fetchone()
        if not row:
            conn.execute(
                text('INSERT INTO users (username, password_hash, role, created_at) VALUES (:u,:ph,:role,:ts)'),
                {'u': 'dbadmin', 'ph': generate_password_hash('dbadmin'), 'role': 'admin', 'ts': int(time.time())}
            )
@app.route('/api/admin/change_password', methods=['POST'])
def admin_change_password():
    if not require_admin():
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip().lower()
    new_password = data.get('password') or ''
    if not username or not new_password:
        return jsonify({'error': 'username_password_required'}), 400
    with _db_engine.begin() as conn:
        cur = conn.execute(text('SELECT id FROM users WHERE username=:username'), {'username': username}).fetchone()
        if not cur:
            return jsonify({'error': 'not_found'}), 404
        conn.execute(text('UPDATE users SET password_hash=:ph WHERE username=:username'), {'ph': generate_password_hash(new_password), 'username': username})
    return jsonify({'ok': True})

# Register media uploader blueprint for simple CMS (API under /api/media)
try:
    from media_admin import bp as media_uploader_bp
    app.register_blueprint(media_uploader_bp, url_prefix='/api/media')
except Exception as e:
    print('Warning: media_uploader blueprint not registered:', e)

# Paths to Flutter Web builds
MEDIA_WEB_DIR = os.path.join(os.path.dirname(__file__), 'sssnl_media_controls', 'build', 'web_media')
DEV_WEB_DIR = os.path.join(os.path.dirname(__file__), 'sssnl_media_controls', 'build', 'web_dev')
DASHBOARD_WEB_DIR = os.path.join(os.path.dirname(__file__), 'sssnl_app', 'build', 'web_dashboard')

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
    # Redirect root to Flutter Web dashboard for a web-only experience
    return redirect('/dashboard')


# -------------------
# AUTH ENDPOINTS
# -------------------

@app.route('/api/auth/signup', methods=['POST'])
def api_signup():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip().lower()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({'error': 'username_password_required'}), 400
    try:
        with _db_engine.begin() as conn:
            # Check exists
            exists = conn.execute(text('SELECT 1 FROM users WHERE username=:u'), {'u': username}).fetchone()
            if exists:
                return jsonify({'error': 'user_exists'}), 409
            conn.execute(
                text('INSERT INTO users (username, password_hash, role, created_at) VALUES (:u,:ph,:role,:ts)'),
                {'u': username, 'ph': generate_password_hash(password), 'role': 'user', 'ts': int(time.time())}
            )
    except Exception:
        return jsonify({'error': 'db_error'}), 500
    session['user_id'] = username
    session['role'] = 'user'
    return jsonify({'ok': True, 'user': {'username': username, 'role': 'user'}})


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip().lower()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({'error': 'username_password_required'}), 400
    with _db_engine.connect() as conn:
        row = conn.execute(text('SELECT username, password_hash, role FROM users WHERE username=:u'), {'u': username}).fetchone()
    if not row:
        return jsonify({'error': 'not_found'}), 404
    if not check_password_hash(row[1], password):
        return jsonify({'error': 'invalid_credentials'}), 401
    session['user_id'] = row[0]
    session['role'] = row[2]
    return jsonify({'ok': True, 'user': {'username': row[0], 'role': row[2]}})


@app.route('/api/auth/me', methods=['GET'])
def api_me():
    uid = session.get('user_id')
    role = session.get('role')
    if not uid:
        return jsonify({'error': 'unauthenticated'}), 401
    return jsonify({'user': {'username': uid, 'role': role or 'user'}})


@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})


# -------------------
# DEVICE MANAGEMENT API
# -------------------

@app.route('/api/devices', methods=['GET'])
def get_devices():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'unauthenticated'}), 401
    
    with _db_engine.connect() as conn:
        result = conn.execute(
            text('SELECT id, device_mac, device_name, configured_at FROM devices WHERE user_id=:uid ORDER BY configured_at DESC'),
            {'uid': uid}
        )
        devices = []
        for row in result:
            devices.append({
                'id': row[0],
                'device_mac': row[1],
                'device_name': row[2],
                'configured_at': row[3]
            })
    return jsonify({'devices': devices})


@app.route('/api/devices', methods=['POST'])
def add_device():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'unauthenticated'}), 401
    
    data = request.get_json(silent=True) or {}
    device_mac = (data.get('device_mac') or '').strip()
    device_name = (data.get('device_name') or '').strip() or None
    
    if not device_mac:
        return jsonify({'error': 'device_mac_required'}), 400
    
    try:
        with _db_engine.begin() as conn:
            # Check if device already exists for this user
            existing = conn.execute(
                text('SELECT id FROM devices WHERE user_id=:uid AND device_mac=:mac'),
                {'uid': uid, 'mac': device_mac}
            ).fetchone()
            
            if existing:
                return jsonify({'error': 'device_already_exists'}), 409
            
            # Insert new device
            result = conn.execute(
                text('INSERT INTO devices (user_id, device_mac, device_name, configured_at) VALUES (:uid, :mac, :name, :ts)'),
                {'uid': uid, 'mac': device_mac, 'name': device_name, 'ts': int(time.time())}
            )
            device_id = result.lastrowid
            
        return jsonify({'ok': True, 'device_id': device_id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/devices/<int:device_id>', methods=['DELETE'])
def delete_device(device_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'unauthenticated'}), 401
    
    with _db_engine.begin() as conn:
        # Verify device belongs to user
        row = conn.execute(
            text('SELECT id FROM devices WHERE id=:id AND user_id=:uid'),
            {'id': device_id, 'uid': uid}
        ).fetchone()
        
        if not row:
            return jsonify({'error': 'device_not_found'}), 404
        
        conn.execute(
            text('DELETE FROM devices WHERE id=:id'),
            {'id': device_id}
        )
    
    return jsonify({'ok': True})


@app.route('/api/devices/<int:device_id>', methods=['PUT'])
def update_device(device_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'unauthenticated'}), 401
    
    data = request.get_json(silent=True) or {}
    device_name = (data.get('device_name') or '').strip() or None
    
    with _db_engine.begin() as conn:
        # Verify device belongs to user
        row = conn.execute(
            text('SELECT id FROM devices WHERE id=:id AND user_id=:uid'),
            {'id': device_id, 'uid': uid}
        ).fetchone()
        
        if not row:
            return jsonify({'error': 'device_not_found'}), 404
        
        conn.execute(
            text('UPDATE devices SET device_name=:name WHERE id=:id'),
            {'name': device_name, 'id': device_id}
        )
    
    return jsonify({'ok': True})


# -------------------
# USER SELF-MANAGEMENT (requires logged-in user)
# -------------------

@app.route('/api/user/change_password', methods=['POST'])
def user_change_password():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'unauthenticated'}), 401
    data = request.get_json(silent=True) or {}
    old_password = data.get('old_password') or ''
    new_password = data.get('new_password') or ''
    if not new_password:
        return jsonify({'error': 'password_required'}), 400
    with _db_engine.begin() as conn:
        row = conn.execute(text('SELECT password_hash FROM users WHERE username=:u'), {'u': uid}).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        if old_password and not check_password_hash(row[0], old_password):
            return jsonify({'error': 'invalid_old_password'}), 401
        conn.execute(text('UPDATE users SET password_hash=:ph WHERE username=:u'), {'ph': generate_password_hash(new_password), 'u': uid})
    return jsonify({'ok': True})


@app.route('/api/user/change_username', methods=['POST'])
def user_change_username():
    uid = session.get('user_id')
    if not uid:
        return jsonify({'error': 'unauthenticated'}), 401
    data = request.get_json(silent=True) or {}
    new_username = (data.get('new_username') or '').strip().lower()
    password = data.get('password') or ''
    if not new_username:
        return jsonify({'error': 'username_required'}), 400
    with _db_engine.begin() as conn:
        row = conn.execute(text('SELECT password_hash FROM users WHERE username=:u'), {'u': uid}).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        if password and not check_password_hash(row[0], password):
            return jsonify({'error': 'invalid_credentials'}), 401
        exists = conn.execute(text('SELECT 1 FROM users WHERE username=:nu'), {'nu': new_username}).fetchone()
        if exists:
            return jsonify({'error': 'user_exists'}), 409
        conn.execute(text('UPDATE users SET username=:nu WHERE username=:u'), {'nu': new_username, 'u': uid})
    # Move media directory for the user (static/media/<username>)
    base_dir = os.path.dirname(__file__)
    old_dir = os.path.join(base_dir, 'static', 'media', uid)
    new_dir = os.path.join(base_dir, 'static', 'media', new_username)
    try:
        if os.path.isdir(old_dir):
            os.makedirs(os.path.join(base_dir, 'static', 'media'), exist_ok=True)
            if os.path.exists(new_dir):
                # Merge old into new, avoiding overwrite
                for fname in os.listdir(old_dir):
                    src = os.path.join(old_dir, fname)
                    dst = os.path.join(new_dir, fname)
                    if not os.path.exists(dst):
                        shutil.move(src, dst)
                shutil.rmtree(old_dir, ignore_errors=True)
            else:
                shutil.move(old_dir, new_dir)
    except Exception as e:
        # Non-fatal: return warning in response but keep username change
        session['user_id'] = new_username
        return jsonify({'ok': True, 'user': {'username': new_username}, 'media_move_warning': str(e)})
    # Update session
    session['user_id'] = new_username
    return jsonify({'ok': True, 'user': {'username': new_username}})


# -------------------
# ADMIN USER MANAGEMENT (requires admin role)
# -------------------

def require_admin():
    return session.get('role') == 'admin'


@app.route('/api/admin/users', methods=['GET'])
def admin_list_users():
    if not require_admin():
        return jsonify({'error': 'forbidden'}), 403
    with _db_engine.connect() as conn:
        rows = conn.execute(text('SELECT id, username, role, created_at FROM users ORDER BY username')).fetchall()
    users = [
        {'id': r[0], 'username': r[1], 'role': r[2], 'created_at': r[3]}
        for r in rows
    ]
    return jsonify({'users': users})


@app.route('/api/admin/users', methods=['POST'])
def admin_add_user():
    if not require_admin():
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip().lower()
    password = data.get('password') or ''
    role = (data.get('role') or 'user').strip().lower()
    if role not in {'user', 'admin'}:
        role = 'user'
    if not username or not password:
        return jsonify({'error': 'username_password_required'}), 400
    with _db_engine.begin() as conn:
        exists = conn.execute(text('SELECT 1 FROM users WHERE username=:u'), {'u': username}).fetchone()
        if exists:
            return jsonify({'error': 'user_exists'}), 409
        conn.execute(text('INSERT INTO users (username, password_hash, role, created_at) VALUES (:u,:ph,:role,:ts)'),
                     {'u': username, 'ph': generate_password_hash(password), 'role': role, 'ts': int(time.time())})
    return jsonify({'ok': True})


@app.route('/api/admin/users/<username>', methods=['DELETE'])
def admin_delete_user(username):
    if not require_admin():
        return jsonify({'error': 'forbidden'}), 403
    username = (username or '').strip().lower()
    with _db_engine.begin() as conn:
        conn.execute(text('DELETE FROM users WHERE username=:u'), {'u': username})
    return jsonify({'ok': True})


@app.route('/playlist')
def get_playlist():
    # Require logged-in user and serve user-specific media
    username = session.get('user_id')
    if not username:
        return jsonify({'error': 'unauthenticated'}), 401
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    device_mac = request.args.get('device_mac')
    if device_mac:
        safe_mac = os.path.basename(device_mac)
        media_dir = os.path.join(static_dir, 'media', username, safe_mac)
    else:
        media_dir = os.path.join(static_dir, 'media', username)
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
    """Serve the Flutter Web build of the Media Manager (upload/view)."""
    if not os.path.isdir(MEDIA_WEB_DIR):
        return jsonify({
            'error': 'media_web_not_built',
            'message': 'Run "flutter build web" in sssnl_media_controls to generate build/web_media.',
        }), 500

    full_path = os.path.join(MEDIA_WEB_DIR, path)
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        path = 'index.html'
    return send_from_directory(MEDIA_WEB_DIR, path)


@app.route('/dev/')
@app.route('/dev/<path:path>')
def dev_web_app(path="index.html"):
    """Serve the Flutter Web build of the Dev Controls UI (controls only)."""
    if not os.path.isdir(DEV_WEB_DIR):
        return jsonify({
            'error': 'dev_web_not_built',
            'message': 'Run "flutter build web" in sssnl_media_controls to generate build/web_dev.',
        }), 500

    full_path = os.path.join(DEV_WEB_DIR, path)
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        path = 'index.html'
    return send_from_directory(DEV_WEB_DIR, path)

# -------------------
# STARTUP: prepare static folders, images and playlist
# -------------------
if __name__ == "__main__":
    # init users database for auth
    try:
        init_users_db()
    except Exception as e:
        print('Warning: failed to init users DB:', e)
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

    print("🚀 Web server on http://0.0.0.0:5656 — use /dashboard, /media, /dev")
    app.run(host="0.0.0.0", port=5656)