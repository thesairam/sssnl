# SSSNL (Web‑Only)

A simple dashboard and media manager. The Flask backend reads sensors on Raspberry Pi (PIR + DHT), serves a full‑screen HTML dashboard, and optionally serves two Flutter Web UIs (dashboard and media/dev). Works on Pi and any Linux/desktop browser. A Raspberry Pi BLE agent is available to provision devices (Wi‑Fi + pairing) from a mobile app.

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

# Run backend (choose one):
# - From repo root:
python -m backend.app
# - Or from inside the backend folder:
#   cd backend && python -m app
```

Open:
- Flutter Web dashboard: http://localhost:5656/dashboard
- Media/Dev (Flutter Web): http://localhost:5656/media and http://localhost:5656/dev
- Status API: http://localhost:5656/status
- Playlist API: http://localhost:5656/playlist
- Media manager (HTML): http://localhost:5656/media/manage
 
Auth defaults:
- Admin username: `dbadmin`
- Admin password: `dbadmin`
You can override seeding via `SSSNL_ADMIN_USER` and `SSSNL_ADMIN_PASS`.

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

If `flutter` is installed, build once and serve via `backend.app`:
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
- PIR on BCM 17, DHT11/22 on BCM 4 (change in `backend/app.py`).
- Ensure `libgpiod2` is installed and your user is in `gpio,i2c` groups.

## Services & Background Run

For kiosk + boot startup (systemd), see README_SERVICES.md.

## Device Provisioning via BLE (Pi + Mobile)
- The Raspberry Pi agent exposes a BLE GATT service to read the MAC and write Wi‑Fi credentials + pairing code.
- Mobile app filters to LE, connectable devices advertising the provisioning UUID and auto‑sends credentials after pairing.
- See setup and troubleshooting in [raspi-agent/README.md](raspi-agent/README.md).

Mobile dev run:
```bash
# Media controls app (Android/iOS):
cd sssnl_media_controls
flutter run -d <device-id> --dart-define=BACKEND_BASE_URL=http://<backend-host>:5656

# Dashboard web app:
cd ../sssnl_app
flutter run -d chrome --web-hostname=0.0.0.0 --web-port 5173 --dart-define=BACKEND_BASE_URL=http://<backend-host>:5656
```

## Troubleshooting

- Web routes 500 for `/dashboard` or `/media`: build the Flutter Web bundles first.
- No motion/DHT: check wiring, groups, and `libgpiod2`. You can simulate via `/mock-*` endpoints.
- Chromium kiosk blank: ensure `DISPLAY=:0` and `.Xauthority` path for your user.
- Port conflicts: edit the port in `backend/app.py` or stop other processes.
- BLE provisioning not discoverable: ensure Pi agent is running, Bluetooth enabled, and BlueZ supports LE advertising; see `raspi-agent/check_env.py`.
