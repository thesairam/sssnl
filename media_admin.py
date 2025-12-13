from flask import Blueprint, request, jsonify, current_app, url_for
import os
import pathlib
import urllib.request
import shutil
from werkzeug.utils import secure_filename

bp = Blueprint('media_admin', __name__)

# Optional API key configured via environment; if not set, auth is disabled.
API_KEY = os.environ.get('SSSNL_MEDIA_API_KEY')

ALLOWED_TARGETS = {'gallery', 'news', 'message', 'videos', 'media'}
ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4', 'mov', 'm4v', 'avi', 'webm'}


def is_allowed_filename(filename: str) -> bool:
    name = filename.rsplit('/', 1)[-1]
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    return ext in ALLOWED_EXT


def require_api_key(req):
    # If API_KEY isn't set, allow all (trusted local network mode)
    if not API_KEY:
        return True
    key = req.headers.get('X-API-KEY') or req.args.get('api_key')
    if not key and req.method == 'POST':
        data = req.get_json(silent=True) or {}
        key = req.form.get('api_key') or data.get('api_key')
    return key == API_KEY


def static_target_dir(target: str) -> str:
    root = pathlib.Path(current_app.root_path) / 'static'
    dest = root / target
    dest.mkdir(parents=True, exist_ok=True)
    return str(dest)


@bp.route('/upload', methods=['POST'])
def upload_file():
    if not require_api_key(request):
        return jsonify({'error': 'unauthorized'}), 401
    target = request.form.get('target', 'media')
    if target not in ALLOWED_TARGETS:
        return jsonify({'error': 'invalid target folder'}), 400
    files = request.files.getlist('file')
    if not files:
        return jsonify({'error': 'no files provided'}), 400
    saved = []
    dest_dir = static_target_dir(target)
    for f in files:
        filename = secure_filename(f.filename)
        if not filename:
            continue
        if not is_allowed_filename(filename):
            continue
        dest_path = os.path.join(dest_dir, filename)
        base, ext = os.path.splitext(filename)
        i = 1
        while os.path.exists(dest_path):
            filename = f"{base}_{i}{ext}"
            dest_path = os.path.join(dest_dir, filename)
            i += 1
        f.save(dest_path)
        saved.append(url_for('static', filename=f"{target}/{filename}", _external=False))
    if not saved:
        return jsonify({'error': 'no valid files uploaded'}), 400
    return jsonify({'saved': saved}), 201


@bp.route('/files', methods=['GET'])
def list_files():
    root = pathlib.Path(current_app.root_path) / 'static' / 'media'
    files = []
    if root.exists():
        for p in sorted(root.iterdir()):
            if p.is_file():
                name = p.name
                url = url_for('static', filename=f"media/{name}", _external=False)
                lower = name.lower()
                typ = 'image' if lower.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) else 'video'
                files.append({'name': name, 'url': url, 'type': typ})
    return jsonify({'files': files})


@bp.route('/delete', methods=['POST'])
def delete_file():
    if not require_api_key(request):
        return jsonify({'error': 'unauthorized'}), 401
    data = request.get_json(force=True, silent=True) or {}
    filename = secure_filename(data.get('filename') or '')
    if not filename:
        return jsonify({'error': 'filename required'}), 400
    path = pathlib.Path(current_app.root_path) / 'static' / 'media' / filename
    if not path.exists() or not path.is_file():
        return jsonify({'error': 'not found'}), 404
    try:
        path.unlink()
        return jsonify({'deleted': filename})
    except Exception as e:
        return jsonify({'error': 'delete_failed', 'detail': str(e)}), 500


@bp.route('/fetch', methods=['POST'])
def fetch_remote():
    if not require_api_key(request):
        return jsonify({'error': 'unauthorized'}), 401
    data = request.get_json(force=True, silent=True) or {}
    url = data.get('url')
    target = data.get('target', 'media')
    if not url:
        return jsonify({'error': 'url required'}), 400
    if target not in ALLOWED_TARGETS:
        return jsonify({'error': 'invalid target folder'}), 400
    parsed = urllib.request.urlparse(url)
    filename = secure_filename(os.path.basename(parsed.path))
    if not filename or not is_allowed_filename(filename):
        return jsonify({'error': 'invalid or unsupported filename'}), 400
    dest_dir = static_target_dir(target)
    dest_path = os.path.join(dest_dir, filename)
    base, ext = os.path.splitext(filename)
    i = 1
    while os.path.exists(dest_path):
        filename = f"{base}_{i}{ext}"
        dest_path = os.path.join(dest_dir, filename)
        i += 1
    try:
        with urllib.request.urlopen(url, timeout=20) as resp, open(dest_path, 'wb') as out:
            shutil.copyfileobj(resp, out)
    except Exception as e:
        return jsonify({'error': 'download_failed', 'detail': str(e)}), 400
    return jsonify({'saved': [url_for('static', filename=f"{target}/{filename}", _external=False)]}), 201


@bp.route('/info', methods=['GET'])
def info():
    return jsonify({'allowed_targets': sorted(ALLOWED_TARGETS), 'allowed_ext': sorted(ALLOWED_EXT)})


@bp.route('/manage', methods=['GET'])
def manage_ui():
    # Single-page UI for viewing, uploading, and deleting media in one place
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>SSSNL Media Manager</title>"
        "<style>body{font-family:Inter,Arial,sans-serif;margin:0;background:#071025;color:#e6eef8}"
        ".wrap{padding:16px} .row{display:flex;gap:12px;align-items:center;flex-wrap:wrap}"
        ".btn{background:#3b82f6;color:#fff;padding:8px 12px;border:none;border-radius:8px}"
        ".ghost{background:transparent;border:1px solid rgba(255,255,255,.12)}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin-top:16px}"
        ".card{background:#071827;border-radius:10px;overflow:hidden} .box{padding:10px}"
        ".thumb{width:100%;height:120px;object-fit:cover;background:#02101a}"
        ".name{font-size:12px;color:#cbd5e1;word-break:break-all}"
        "input[type=file]{display:none} .tag{font-size:11px;color:#94a3b8;margin-left:8px}"
        "</style></head><body><div class='wrap'>"
        "<div class='row'><h2 style='margin:0'>Media Manager</h2>"
        "<button class='btn ghost' id='refresh'>Refresh</button>"
        "<label class='btn ghost' for='file'>Choose files</label>"
        "<input id='file' type='file' multiple></div>"
        "<div id='list' class='grid'></div>"
        "</div><script>"
        "document.getElementById('refresh').onclick=fetchFiles;"
        "document.getElementById('file').onchange=async(e)=>{const files=[...e.target.files];for(const f of files){const fd=new FormData();fd.append('file',f);fd.append('target','media');await fetch('/api/media/upload',{method:'POST',body:fd});}fetchFiles();};"
        "async function fetchFiles(){const r=await fetch('/api/media/files');if(!r.ok){alert('List failed');return;}"
        "const data=await r.json();const grid=document.getElementById('list');grid.innerHTML='';for(const f of data.files){const c=document.createElement('div');c.className='card';"
        "let el;if(f.type==='image'){el=document.createElement('img');el.src=f.url;el.className='thumb';}else{el=document.createElement('video');el.src=f.url;el.className='thumb';el.controls=true;}c.appendChild(el);"
        "const box=document.createElement('div');box.className='box';const nm=document.createElement('div');nm.className='name';nm.textContent=f.name;box.appendChild(nm);"
        "const del=document.createElement('button');del.className='btn ghost';del.textContent='Delete';del.onclick=async()=>{if(!confirm('Delete '+f.name+'?'))return;const d=await fetch('/api/media/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:f.name})});if(d.ok)fetchFiles();else alert('Delete failed');};"
        "box.appendChild(del);c.appendChild(box);grid.appendChild(c);} }"
        "fetchFiles();</script></body></html>"
    )