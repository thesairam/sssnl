# SSSNL (Web‑Only)

A simple, web‑only dashboard and media manager. The Flask backend reads sensors on Raspberry Pi (PIR + DHT), serves a full‑screen HTML dashboard, and optionally serves two Flutter Web UIs (dashboard and media/dev). Works on Pi and any Linux/desktop browser.

## Quick Start

```bash
# Clone
cd ~
git clone https://github.com/<your-org-or-user>/sssnl.git
cd sssnl

# Python venv + deps
python3 -m venv sssnlvenv
source sssnlvenv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Run backend
python app.py
```

Open:
- Flutter Web dashboard: http://localhost:5656/dashboard
- Media/Dev (Flutter Web): http://localhost:5656/media and http://localhost:5656/dev
- Status API: http://localhost:5656/status
- Playlist API: http://localhost:5656/playlist
- Media manager (HTML): http://localhost:5656/media/manage

## Media Management (APIs)

Endpoints (prefix `/api/media`):
- `/upload` (POST multipart): upload to target (default `media`).
- `/files` (GET): list files under `static/media`.
- `/delete` (POST JSON): delete by filename.
- `/fetch` (POST JSON): download remote URL to target.
- `/info` (GET): report allowed targets and extensions.

Set an API key (recommended):
```bash
export SSSNL_MEDIA_API_KEY='a_long_random_secret'
```

## Optional: Build Flutter Web

If `flutter` is installed, build once and serve from `app.py`:
```bash
cd ./sssnl_app
flutter build web --release --base-href /dashboard/ --output build/web_dashboard

cd ../sssnl_media_controls
flutter build web --release --base-href /media/ --output build/web_media
```

## Raspberry Pi Quick Run

Use the helper script for Pi (web‑only):
```bash
cd ~/sssnl
chmod +x raspi_setup_and_run.sh
./raspi_setup_and_run.sh
```
This installs apt deps, sets up venv, builds Flutter Web (if available), and starts the backend. It does not open a browser.

GPIO/DHT notes:
- PIR on BCM 17, DHT11/22 on BCM 4 (change in `app.py`).
- Ensure `libgpiod2` is installed and your user is in `gpio,i2c` groups.

## Services & Background Run

For kiosk + boot startup (systemd), see README_SERVICES.md.

## Troubleshooting

- Web routes 500 for `/dashboard` or `/media`: build the Flutter Web bundles first.
- No motion/DHT: check wiring, groups, and `libgpiod2`. You can simulate via `/mock-*` endpoints.
- Chromium kiosk blank: ensure `DISPLAY=:0` and `.Xauthority` path for your user.
- Port conflicts: edit the port in `app.py` or stop other processes.
