import os
import time
import threading
import shutil
import subprocess

# Hardware mocks
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
            return 0
    GPIO = _MockGPIO()

try:
    import board
    import adafruit_dht as adafruit_circ_dht
    _DHT_LIB = 'circuitpython'
except Exception:
    adafruit_circ_dht = None
    board = None
    _DHT_LIB = 'mock'

from flask import Flask, render_template_string, jsonify, request, send_from_directory, redirect, session
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import create_engine, text, Table, Column, Integer, String, MetaData
from sqlalchemy.engine import Engine

PIR_PIN = 17
DHT_PIN = 4
DHT_TYPE = 'DHT11'
_dht_sensor_obj = None
if _DHT_LIB == 'circuitpython':
    try:
        if board is not None:
            board_pin = getattr(board, f'D{DHT_PIN}')
            _dht_sensor_obj = adafruit_circ_dht.DHT11(board_pin) if DHT_TYPE == 'DHT11' else adafruit_circ_dht.DHT22(board_pin)
    except Exception:
        _dht_sensor_obj = None
PIR_ACTIVE_VALUE = 1
PIR_DEBOUNCE_READS = 2

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-sssnl')

# Configure CORS to allow web/mobile dev origins with credentials
_cors_origins = os.environ.get('CORS_ORIGINS', '')
if _cors_origins:
    _allowed_origins = [o.strip() for o in _cors_origins.split(',') if o.strip()]
else:
    _allowed_origins = [
        'http://localhost:5656', 'http://127.0.0.1:5656',
        'http://localhost:3000', 'http://127.0.0.1:3000',
        'http://localhost:5173', 'http://127.0.0.1:5173',
        'http://localhost:8080', 'http://127.0.0.1:8080',
    ]
CORS(app, origins=_allowed_origins, supports_credentials=True)

# Paths relative to project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
STATIC_DIR = os.path.join(PROJECT_ROOT, 'static')
MEDIA_WEB_DIR = os.path.join(PROJECT_ROOT, 'sssnl_media_controls', 'build', 'web_media')
DEV_WEB_DIR = os.path.join(PROJECT_ROOT, 'sssnl_media_controls', 'build', 'web_dev')
DASHBOARD_WEB_DIR = os.path.join(PROJECT_ROOT, 'sssnl_app', 'build', 'web_dashboard')

# DB setup
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

# Devices table: identity, ownership, pairing state
devices_table = Table(
    'devices', _metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('device_id', String(64), unique=True, nullable=False),
    Column('mac', String(64), unique=True, nullable=False),
    Column('name', String(255), nullable=True),
    Column('owner_username', String(255), nullable=True),
    Column('status', String(32), nullable=False, default='provisioning'),
    Column('last_seen', Integer, nullable=True),
    Column('device_secret_hash', String(255), nullable=True),
    Column('pairing_code', String(32), nullable=True),
    Column('pairing_user', String(255), nullable=True),
    Column('pairing_expires', Integer, nullable=True),
)

def _gen_device_id() -> str:
    import secrets, string
    base = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10))
    return f"dev-{base}"

def _gen_pairing_code() -> str:
    import secrets
    return f"{secrets.randbelow(900000)+100000}"

def _db_connect():
    return _db_engine.connect()

# Register media blueprint (supports running as module or script)
try:
    from .media_admin import bp as media_uploader_bp
    app.register_blueprint(media_uploader_bp, url_prefix='/api/media')
except Exception:
    try:
        from media_admin import bp as media_uploader_bp  # fallback when running app.py directly
        app.register_blueprint(media_uploader_bp, url_prefix='/api/media')
    except Exception as e:
        print('Warning: media_uploader blueprint not registered:', e)

current_temp = "--"
current_hum = "--"
motion_active = False
motion_status_msg = "No motion"
last_dht_time = None
last_dht_success = False
last_motion_raw = None
last_motion_change = None
mock_motion_override = None
mock_dht_override = None

dht_lock = threading.Lock()

# Sensor threads

def read_dht_sensor():
    global current_temp, current_hum, motion_status_msg
    global last_dht_time, last_dht_success
    while True:
        humidity = None
        temperature = None
        try:
            with dht_lock:
                if mock_dht_override is not None:
                    temperature = mock_dht_override.get('temp')
                    humidity = mock_dht_override.get('hum')
                elif _DHT_LIB == 'circuitpython' and _dht_sensor_obj is not None:
                    try:
                        temperature = _dht_sensor_obj.temperature
                        humidity = _dht_sensor_obj.humidity
                    except Exception:
                        temperature = None
                        humidity = None
                else:
                    import random
                    temperature = 20.0 + random.random() * 6.0
                    humidity = 40.0 + random.random() * 20.0
        except Exception:
            humidity, temperature = None, None
        if humidity is not None and temperature is not None:
            current_temp = f"{temperature:.1f}°C"
            current_hum = f"{humidity:.1f}%"
            last_dht_time = time.time()
            last_dht_success = True
        else:
            last_dht_success = False
        motion_status_msg = "Motion detected" if motion_active else "No motion"
        time.sleep(10)


def motion_detector():
    global motion_active, motion_status_msg, last_motion_raw, last_motion_change
    consecutive = 0
    last_state = None
    while True:
        raw = GPIO.input(PIR_PIN)
        last_motion_raw = raw
        is_motion = (raw == PIR_ACTIVE_VALUE)
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
                motion_active = True
                motion_status_msg = "Motion detected"
                last_motion_change = time.time()
            elif not is_motion and motion_active:
                motion_active = False
                motion_status_msg = "No motion"
                last_motion_change = time.time()
        time.sleep(0.5)

# Dashboard HTML same as original
HTML_TEMPLATE = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Shirdi Sai Samaj - Autoplay</title><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{height:100%;margin:0;background:black;color:white;font-family:Inter,Arial,sans-serif}.container{position:relative;width:100%;height:100vh;overflow:hidden;background:black;display:flex;align-items:center;justify-content:center}#media-wrapper{position:relative;width:100%;height:100%;background:black}#pl-video,#pl-image{position:absolute;top:0;left:0;width:100%;height:100%;display:none;background:black}#pl-video{object-fit:cover}#pl-image{object-fit:contain}#status-bar{position:fixed;top:12px;left:12px;z-index:60;background:rgba(0,0,0,.50);color:#fff;padding:10px 16px;border-radius:10px;font-size:1.35em;line-height:1.2;box-shadow:0 4px 16px rgba(0,0,0,.65)}.top-msg{position:fixed;top:12px;right:12px;z-index:60;color:#ff6b6b;font-weight:700;font-size:2.4em;background:rgba(0,0,0,.40);padding:16px 24px;border-radius:14px;box-shadow:0 4px 18px rgba(0,0,0,.55)}#pl-video,#pl-image{position:absolute;top:100px;left:0;width:100%;height:calc(100% - 100px);display:none;background:black}.hidden{display:none !important}.center-msg{position:absolute;color:#ddd;font-size:1.2em;text-align:center;left:50%;top:50%;transform:translate(-50%,-50%)}@media (max-width:600px){#status-bar{font-size:1.05em;padding:8px 12px}.top-msg{font-size:1.8em;padding:12px 16px}#pl-video,#pl-image{top:90px;height:calc(100% - 90px)}}</style></head><body><div id="status-bar">Temp: <span id="temp">{{temp}}</span> | Humidity: <span id="hum">{{hum}}</span> | Motion: <span id="motion_txt">{{motion_status}}</span></div><div class="top-msg">🌼 Don't forget to turn off Diyas & close doors 🌼</div><div class="container"><div id="media-wrapper"><video id="pl-video" playsinline muted preload="auto"></video><img id="pl-image" alt="media"/><div id="idle-msg" class="center-msg">Awaiting motion...</div></div></div><script>let playlist=[];const IMAGE_DISPLAY_MS=6000;let playing=false;let motionTriggered=false;function showIdle(yes){const idle=document.getElementById('idle-msg');const vid=document.getElementById('pl-video');const img=document.getElementById('pl-image');if(yes){vid.style.display='none';vid.pause();img.style.display='none';idle.style.display='block'}else{idle.style.display='none'}}function showVideo(){document.getElementById('pl-image').style.display='none';const v=document.getElementById('pl-video');v.style.display='block'}function showImage(){document.getElementById('pl-video').style.display='none';const i=document.getElementById('pl-image');i.style.display='block'}function wait(ms){return new Promise(r=>setTimeout(r,ms))}function waitVideoEnd(videoEl){return new Promise((resolve)=>{let settled=false;function cleanup(){videoEl.removeEventListener('ended',onEnd);videoEl.removeEventListener('error',onError);videoEl.removeEventListener('loadedmetadata',onLoaded);if(timeout)clearTimeout(timeout)}function onEnd(){if(settled)return;settled=true;cleanup();resolve()}function onError(e){if(settled)return;settled=true;cleanup();resolve()}function onLoaded(){setupTimeout()}let timeout=null;function setupTimeout(){if(timeout){clearTimeout(timeout);timeout=null}try{const dur=Number(videoEl.duration)||0;if(dur>0&&isFinite(dur)){timeout=setTimeout(()=>{if(settled)return;settled=true;cleanup();resolve()},(dur*1000)+2500)}}catch(e){}}videoEl.addEventListener('ended',onEnd);videoEl.addEventListener('error',onError);videoEl.addEventListener('loadedmetadata',onLoaded);timeout=setTimeout(()=>{if(settled)return;settled=true;cleanup();resolve()},45000);if(videoEl.ended){onEnd()}})}async function playPlaylistOnce(){if(playing)return;playing=true;motionTriggered=true;showIdle(false);const vid=document.getElementById('pl-video');const img=document.getElementById('pl-image');try{const r=await fetch('/playlist',{cache:'no-store'});if(r.ok){const data=await r.json();playlist=Array.isArray(data.playlist)?data.playlist:[]}else{playlist=[]}}catch(e){playlist=[]}for(const item of playlist){if(item.type==='video'){try{showVideo();vid.muted=true;vid.src=item.src;vid.currentTime=0;try{await vid.play()}catch(e){}await waitVideoEnd(vid)}catch(e){}finally{try{vid.pause();vid.removeAttribute('src');vid.load()}catch(e){}}}else{showImage();img.src=item.src;const ms=item.duration_ms||IMAGE_DISPLAY_MS;await wait(ms)}}playing=false;motionTriggered=false;showIdle(true)}let lastMotionActive=false;async function fetchStatus(){try{const resp=await fetch('/status');if(!resp.ok)return;const data=await resp.json();document.getElementById('temp').innerText=data.temp;document.getElementById('hum').innerText=data.hum;document.getElementById('motion_txt').innerText=data.motion_status;if(data.motion_active&&!motionTriggered&&!playing){playPlaylistOnce()}}catch(e){}}window.addEventListener('load',()=>{showIdle(true);fetchStatus();setInterval(fetchStatus,1500)});</script></body></html>"""

@app.route("/")
def index():
    return jsonify({
        'ok': True,
        'service': 'sssnl-backend',
        'endpoints': {
            'health': '/healthz',
            'status': '/status',
            'status_api': '/api/status',
            'playlist': '/playlist',
            'playlist_api': '/api/playlist',
            'auth': '/api/auth/*',
            'media': '/api/media/*',
        }
    })

@app.route('/healthz')
def healthz():
    return jsonify({'ok': True})

# DB init and seeding

def init_users_db():
    _metadata.create_all(_db_engine)
    admin_user = os.environ.get('SSSNL_ADMIN_USER')
    admin_pass = os.environ.get('SSSNL_ADMIN_PASS')
    with _db_engine.begin() as conn:
        if admin_user and admin_pass:
            row = conn.execute(text('SELECT id FROM users WHERE username=:u'), {'u': admin_user.lower().strip()}).fetchone()
            if not row:
                conn.execute(text('INSERT INTO users (username, password_hash, role, created_at) VALUES (:u,:ph,:role,:ts)'),
                             {'u': admin_user.lower().strip(), 'ph': generate_password_hash(admin_pass), 'role': 'admin', 'ts': int(time.time())})
        row = conn.execute(text('SELECT id FROM users WHERE username=:u'), {'u': 'dbadmin'}).fetchone()
        if not row:
            conn.execute(text('INSERT INTO users (username, password_hash, role, created_at) VALUES (:u,:ph,:role,:ts)'),
                         {'u': 'dbadmin', 'ph': generate_password_hash('dbadmin'), 'role': 'admin', 'ts': int(time.time())})

# Auth endpoints
@app.route('/api/auth/signup', methods=['POST'])
def api_signup():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip().lower()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({'error': 'username_password_required'}), 400
    try:
        with _db_engine.begin() as conn:
            exists = conn.execute(text('SELECT 1 FROM users WHERE username=:u'), {'u': username}).fetchone()
            if exists:
                return jsonify({'error': 'user_exists'}), 409
            conn.execute(text('INSERT INTO users (username, password_hash, role, created_at) VALUES (:u,:ph,:role,:ts)'),
                         {'u': username, 'ph': generate_password_hash(password), 'role': 'user', 'ts': int(time.time())})
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
    base_dir = PROJECT_ROOT
    old_dir = os.path.join(base_dir, 'static', 'media', uid)
    new_dir = os.path.join(base_dir, 'static', 'media', new_username)
    try:
        if os.path.isdir(old_dir):
            os.makedirs(os.path.join(base_dir, 'static', 'media'), exist_ok=True)
            if os.path.exists(new_dir):
                for fname in os.listdir(old_dir):
                    src = os.path.join(old_dir, fname)
                    dst = os.path.join(new_dir, fname)
                    if not os.path.exists(dst):
                        shutil.move(src, dst)
                shutil.rmtree(old_dir, ignore_errors=True)
            else:
                shutil.move(old_dir, new_dir)
    except Exception as e:
        session['user_id'] = new_username
        return jsonify({'ok': True, 'user': {'username': new_username}, 'media_move_warning': str(e)})
    session['user_id'] = new_username
    return jsonify({'ok': True, 'user': {'username': new_username}})

# Admin

def require_admin():
    return session.get('role') == 'admin'

@app.route('/api/admin/users', methods=['GET'])
def admin_list_users():
    if not require_admin():
        return jsonify({'error': 'forbidden'}), 403
    with _db_engine.connect() as conn:
        rows = conn.execute(text('SELECT id, username, role, created_at FROM users ORDER BY username')).fetchall()
    users = [{'id': r[0], 'username': r[1], 'role': r[2], 'created_at': r[3]} for r in rows]
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

# Device APIs

def _require_auth_user() -> str | None:
    return session.get('user_id')

def _require_device_auth(device_id: str, secret: str) -> bool:
    try:
        with _db_engine.connect() as conn:
            row = conn.execute(text('SELECT device_secret_hash FROM devices WHERE device_id=:d'), {'d': device_id}).fetchone()
            if not row or not row[0]:
                return False
            return check_password_hash(row[0], secret)
    except Exception:
        return False

@app.route('/api/devices/register', methods=['POST'])
def device_register():
    data = request.get_json(silent=True) or {}
    mac = (data.get('mac') or '').strip().lower()
    name = (data.get('name') or '').strip()
    if not mac:
        return jsonify({'error': 'mac_required'}), 400
    device_id = _gen_device_id()
    import secrets
    device_secret = secrets.token_hex(16)
    try:
        with _db_engine.begin() as conn:
            existed = conn.execute(text('SELECT device_id FROM devices WHERE mac=:m'), {'m': mac}).fetchone()
            if existed:
                conn.execute(text('UPDATE devices SET device_secret_hash=:h, status=:st, last_seen=NULL WHERE mac=:m'),
                             {'h': generate_password_hash(device_secret), 'st': 'provisioning', 'm': mac})
                device_id = existed[0]
            else:
                conn.execute(text('INSERT INTO devices (device_id, mac, name, status, device_secret_hash) VALUES (:d,:m,:n,:st,:h)'),
                             {'d': device_id, 'm': mac, 'n': name or None, 'st': 'provisioning', 'h': generate_password_hash(device_secret)})
    except Exception:
        return jsonify({'error': 'db_error'}), 500
    return jsonify({'ok': True, 'device_id': device_id, 'device_token': device_secret})

@app.route('/api/devices/<device_id>/pair', methods=['POST'])
def device_pair(device_id: str):
    user = _require_auth_user()
    if not user:
        return jsonify({'error': 'unauthenticated'}), 401
    data = request.get_json(silent=True) or {}
    code = (data.get('pairing_code') or '').strip() or _gen_pairing_code()
    ttl_sec = int(data.get('ttl_sec') or 300)
    expires = int(time.time()) + max(60, min(ttl_sec, 900))
    with _db_engine.begin() as conn:
        cur = conn.execute(text('SELECT id FROM devices WHERE device_id=:d'), {'d': device_id}).fetchone()
        if not cur:
            return jsonify({'error': 'not_found'}), 404
        conn.execute(text('UPDATE devices SET pairing_code=:pc, pairing_user=:pu, pairing_expires=:pe WHERE device_id=:d'),
                     {'pc': code, 'pu': user, 'pe': expires, 'd': device_id})
    return jsonify({'ok': True, 'pairing_code': code, 'expires': expires})

@app.route('/api/devices/pair_by_mac', methods=['POST'])
def device_pair_by_mac():
    user = _require_auth_user()
    if not user:
        return jsonify({'error': 'unauthenticated'}), 401
    data = request.get_json(silent=True) or {}
    mac = (data.get('mac') or '').strip().lower()
    if not mac:
        return jsonify({'error': 'mac_required'}), 400
    code = (data.get('pairing_code') or '').strip() or _gen_pairing_code()
    ttl_sec = int(data.get('ttl_sec') or 300)
    expires = int(time.time()) + max(60, min(ttl_sec, 900))
    with _db_engine.begin() as conn:
        cur = conn.execute(text('SELECT device_id FROM devices WHERE mac=:m'), {'m': mac}).fetchone()
        if not cur:
            return jsonify({'error': 'not_found'}), 404
        conn.execute(text('UPDATE devices SET pairing_code=:pc, pairing_user=:pu, pairing_expires=:pe WHERE mac=:m'),
                     {'pc': code, 'pu': user, 'pe': expires, 'm': mac})
    return jsonify({'ok': True, 'pairing_code': code, 'expires': expires})

@app.route('/api/devices/<device_id>/claim', methods=['POST'])
def device_claim(device_id: str):
    data = request.get_json(silent=True) or {}
    device_token = (data.get('device_token') or '').strip()
    pairing_code = (data.get('pairing_code') or '').strip()
    if not device_token or not pairing_code:
        return jsonify({'error': 'token_and_code_required'}), 400
    now = int(time.time())
    with _db_engine.begin() as conn:
        row = conn.execute(text('SELECT pairing_code, pairing_user, pairing_expires FROM devices WHERE device_id=:d'), {'d': device_id}).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        pc, pu, pe = row
        if not pc or not pu or not pe or pe < now or pc != pairing_code:
            return jsonify({'error': 'pairing_invalid'}), 400
        tok = conn.execute(text('SELECT device_secret_hash FROM devices WHERE device_id=:d'), {'d': device_id}).fetchone()
        if not tok or not tok[0] or not check_password_hash(tok[0], device_token):
            return jsonify({'error': 'invalid_token'}), 401
        conn.execute(text('UPDATE devices SET owner_username=:u, status=:st, pairing_code=NULL, pairing_user=NULL, pairing_expires=NULL WHERE device_id=:d'),
                     {'u': pu, 'st': 'online', 'd': device_id})
    return jsonify({'ok': True})

@app.route('/api/devices/<device_id>/heartbeat', methods=['POST'])
def device_heartbeat(device_id: str):
    data = request.get_json(silent=True) or {}
    device_token = (data.get('device_token') or '').strip()
    if not device_token:
        return jsonify({'error': 'token_required'}), 400
    if not _require_device_auth(device_id, device_token):
        return jsonify({'error': 'invalid_token'}), 401
    with _db_engine.begin() as conn:
        conn.execute(text('UPDATE devices SET last_seen=:ts, status=:st WHERE device_id=:d'), {'ts': int(time.time()), 'st': 'online', 'd': device_id})
    return jsonify({'ok': True})

@app.route('/api/devices', methods=['GET'])
def list_my_devices():
    user = _require_auth_user()
    if not user:
        return jsonify({'error': 'unauthenticated'}), 401
    with _db_engine.connect() as conn:
        rows = conn.execute(text('SELECT device_id, mac, name, status, last_seen FROM devices WHERE owner_username=:u ORDER BY name, mac'), {'u': user}).fetchall()
    devices = [{'device_id': r[0], 'mac': r[1], 'name': r[2], 'status': r[3], 'last_seen': r[4]} for r in rows]
    return jsonify({'devices': devices})

@app.route('/api/devices/<device_id>/rename', methods=['POST'])
def rename_device(device_id: str):
    user = _require_auth_user()
    if not user:
        return jsonify({'error': 'unauthenticated'}), 401
    data = request.get_json(silent=True) or {}
    new_name = (data.get('name') or '').strip()
    if not new_name:
        return jsonify({'error': 'name_required'}), 400
    with _db_engine.begin() as conn:
        cur = conn.execute(text('SELECT owner_username FROM devices WHERE device_id=:d'), {'d': device_id}).fetchone()
        if not cur:
            return jsonify({'error': 'not_found'}), 404
        if cur[0] != user:
            return jsonify({'error': 'forbidden'}), 403
        conn.execute(text('UPDATE devices SET name=:n WHERE device_id=:d'), {'n': new_name, 'd': device_id})
    return jsonify({'ok': True})

# Media playlist/status
@app.route('/playlist')
def get_playlist():
    username = session.get('user_id')
    if not username:
        return jsonify({'error': 'unauthenticated'}), 401
    device_mac = request.args.get('device_mac')
    if device_mac:
        safe_mac = os.path.basename(device_mac)
        media_dir = os.path.join(STATIC_DIR, 'media', username, safe_mac)
    else:
        media_dir = os.path.join(STATIC_DIR, 'media', username)
    image_exts = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
    video_exts = ('.mp4', '.mov', '.m4v', '.avi', '.webm')
    items = []
    try:
        if os.path.isdir(media_dir):
            for fname in sorted(os.listdir(media_dir)):
                if fname.lower().endswith(video_exts):
                    path = os.path.join(media_dir, fname)
                    items.append({'type': 'video', 'src': f"/{os.path.relpath(path, PROJECT_ROOT)}"})
            for fname in sorted(os.listdir(media_dir)):
                if fname.lower().endswith(image_exts):
                    path = os.path.join(media_dir, fname)
                    items.append({'type': 'image', 'src': f"/{os.path.relpath(path, PROJECT_ROOT)}", 'duration_ms': 6000})
    except Exception as e:
        return jsonify({'playlist': [], 'error': str(e)}), 200
    return jsonify({'playlist': items})

@app.route('/api/playlist')
def get_playlist_api():
    return get_playlist()

@app.route('/api/public/playlist_by_mac')
def public_playlist_by_mac():
    mac = (request.args.get('mac') or '').strip().lower()
    if not mac:
        return jsonify({'playlist': []})
    owner = None
    try:
        with _db_engine.connect() as conn:
            row = conn.execute(text('SELECT owner_username FROM devices WHERE mac=:m'), {'m': mac}).fetchone()
            if row and row[0]:
                owner = row[0]
    except Exception:
        owner = None
    if not owner:
        return jsonify({'playlist': []})
    # Build from static/media/<owner>/<mac>
    media_dir = os.path.join(STATIC_DIR, 'media', owner, os.path.basename(mac))
    image_exts = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
    video_exts = ('.mp4', '.mov', '.m4v', '.avi', '.webm')
    items = []
    try:
        if os.path.isdir(media_dir):
            for fname in sorted(os.listdir(media_dir)):
                if fname.lower().endswith(video_exts):
                    path = os.path.join(media_dir, fname)
                    items.append({'type': 'video', 'src': f"/{os.path.relpath(path, PROJECT_ROOT)}"})
            for fname in sorted(os.listdir(media_dir)):
                if fname.lower().endswith(image_exts):
                    path = os.path.join(media_dir, fname)
                    items.append({'type': 'image', 'src': f"/{os.path.relpath(path, PROJECT_ROOT)}", 'duration_ms': 6000})
    except Exception as e:
        return jsonify({'playlist': [], 'error': str(e)}), 200
    return jsonify({'playlist': items})

@app.route('/status')
def status():
    return jsonify({'temp': current_temp, 'hum': current_hum, 'motion_status': motion_status_msg, 'motion_active': motion_active, 'last_dht_time': last_dht_time, 'last_dht_success': last_dht_success, 'last_motion_raw': last_motion_raw, 'last_motion_change': last_motion_change})

@app.route('/api/status')
def status_api():
    return status()

# Diagnostics/mocks
@app.route('/dht-debug')
def dht_debug():
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
        else:
            read['temp'] = 21.5
            read['hum'] = 55.0
    except Exception as e:
        read['error'] = str(e)
    return jsonify({'backend': backend, 'read': read, 'last_dht_time': last_dht_time, 'last_dht_success': last_dht_success})

@app.route('/mock-motion', methods=['POST'])
def mock_motion():
    global mock_motion_override, motion_active, motion_status_msg, last_motion_change
    data = request.get_json(silent=True) or {}
    val = data.get('active')
    if val is None:
        qp = request.args.get('active')
        if qp is not None:
            val = qp
    if isinstance(val, str):
        val = val.strip().lower() in {"1", "true", "on", "yes"}
    elif isinstance(val, (int, float)):
        val = bool(val)
    active = bool(val)
    mock_motion_override = active
    motion_active = active
    motion_status_msg = "Motion detected" if active else "No motion"
    last_motion_change = time.time()
    return jsonify({'ok': True, 'motion_active': motion_active, 'override': True})

@app.route('/mock-motion/clear', methods=['POST'])
def clear_mock_motion():
    global mock_motion_override
    mock_motion_override = None
    return jsonify({'ok': True, 'override': False, 'motion_active': motion_active})

@app.route('/mock-dht', methods=['POST'])
def mock_dht():
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
    global mock_dht_override
    mock_dht_override = None
    return jsonify({'ok': True, 'override': False})

# Flutter web assets
@app.route('/dashboard/')
@app.route('/dashboard/<path:path>')
def dashboard_web_app(path="index.html"):
    if not os.path.isdir(DASHBOARD_WEB_DIR):
        return jsonify({'error': 'dashboard_web_not_built', 'message': 'Run "flutter build web" in sssnl_app first.'}), 500
    full_path = os.path.join(DASHBOARD_WEB_DIR, path)
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        path = 'index.html'
    return send_from_directory(DASHBOARD_WEB_DIR, path)

@app.route('/media/')
@app.route('/media/<path:path>')
def media_web_app(path="index.html"):
    if not os.path.isdir(MEDIA_WEB_DIR):
        return jsonify({'error': 'media_web_not_built', 'message': 'Run "flutter build web" in sssnl_media_controls to generate build/web_media.'}), 500
    full_path = os.path.join(MEDIA_WEB_DIR, path)
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        path = 'index.html'
    return send_from_directory(MEDIA_WEB_DIR, path)

@app.route('/dev/')
@app.route('/dev/<path:path>')
def dev_web_app(path="index.html"):
    if not os.path.isdir(DEV_WEB_DIR):
        return jsonify({'error': 'dev_web_not_built', 'message': 'Run "flutter build web" in sssnl_media_controls to generate build/web_dev.'}), 500
    full_path = os.path.join(DEV_WEB_DIR, path)
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        path = 'index.html'
    return send_from_directory(DEV_WEB_DIR, path)

if __name__ == '__main__':
    try:
        init_users_db()
    except Exception as e:
        print('Warning: failed to init users DB:', e)
    threading.Thread(target=read_dht_sensor, daemon=True).start()
    threading.Thread(target=motion_detector, daemon=True).start()

    # Prepare static/media folder at project root
    os.makedirs(STATIC_DIR, exist_ok=True)
    media_dir = os.path.join(STATIC_DIR, 'media')
    os.makedirs(media_dir, exist_ok=True)

    base_dir = PROJECT_ROOT
    candidate_dirs = [
        os.path.join(base_dir, 'videos'),
        os.path.join(base_dir, 'sssnl', 'gallery'),
        os.path.join(base_dir, 'sssnl', 'news'),
        os.path.join(base_dir, 'sssnl', 'message'),
        os.path.join(base_dir, 'gallery'),
        os.path.join(base_dir, 'news'),
        os.path.join(base_dir, 'message'),
        os.path.join(STATIC_DIR, 'gallery'),
        os.path.join(STATIC_DIR, 'news'),
        os.path.join(STATIC_DIR, 'message'),
        os.path.join(STATIC_DIR, 'videos'),
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

    for d in candidate_dirs:
        move_media_from(d)

    print("🚀 Backend running on http://0.0.0.0:5656")
    app.run(host='0.0.0.0', port=5656)
