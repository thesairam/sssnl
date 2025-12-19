# SSSNL on Raspberry Pi (Build + Run)

This guide shows how to clone, install, and run the SSSNL stack on a Raspberry Pi. It also includes optional systemd services so everything starts at boot.

Assumptions:
- Repo will be cloned to `/home/<user>/sssnl`.
- Raspberry Pi OS (Bullseye/Bookworm). 64‑bit is recommended.
- Chromium (or another browser) available to display the dashboard.

Replace `<user>` with your actual username (e.g. `pi`, `saipi`).

---

## Quick Start (manual run)

```bash
# 1) Install OS prerequisites
sudo apt update
sudo apt install -y python3 python3-venv python3-pip libgpiod2 \
  chromium-browser # or: chromium

# 2) Clone and enter repo
cd /home/<user>
git clone https://github.com/<your-org-or-user>/sssnl.git
cd sssnl

# 3) Create venv and install deps
python3 -m venv sssnlvenv
source sssnlvenv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4) Run backend
python app.py
# Visit http://localhost:5656/ (or from another device: http://<pi-ip>:5656/)
```

If you see “dashboard running” logs and the page loads, you’re good. Stop with Ctrl+C to continue with the boot services below.

---

## GPIO/DHT Notes

- PIR: uses BCM pin 17 (`PIR_PIN=17`).
- DHT11/DHT22: uses BCM pin 4 (`DHT_PIN=4`). Set `DHT_TYPE` in `app.py` if needed.
- The code prefers the Adafruit CircuitPython DHT driver via Blinka. Ensure `libgpiod2` is installed (done above).
- You don’t need root if your user is in the proper groups. Add once, then reboot:

```bash
sudo usermod -aG gpio,i2c <user>
sudo reboot
```

Use `sudo raspi-config` to enable interfaces if required.

---

## 1. Initial Setup on the Pi

```bash
cd /home/<user>/sssnl

# Create and activate venv
python3 -m venv sssnlvenv
source sssnlvenv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

To test manually:

```bash
python app.py
# Open http://localhost:5656/ in a browser (or http://<pi-ip>:5656/)
```

Stop it (Ctrl+C) before configuring systemd.

---

## 2. Backend Service (Flask `app.py`)

Create `/etc/systemd/system/sssnl-backend.service`:

```ini
[Unit]
Description=SSSNL Flask backend (app.py)
After=network.target

[Service]
Type=simple
User=<user>
WorkingDirectory=/home/<user>/sssnl
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/<user>/sssnl/sssnlvenv/bin/python app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable sssnl-backend.service
sudo systemctl start sssnl-backend.service
```

Check status:

```bash
sudo systemctl status sssnl-backend.service
```

Backend routes:
- `/` – HTML dashboard (autoplay playlist driven by motion/DHT status)
- `/status` – JSON status (temp, humidity, motion)
- `/playlist` – JSON playlist from `static/media`
- `/api/media/*` – media upload/list/delete/fetch (see `media_admin.py`)
- `/mock-*` – mock motion & DHT endpoints for development
- `/dashboard`, `/media`, `/dev` – optional Flutter Web apps (see below)

---

## 3. Fullscreen Dashboard (Chromium kiosk)

Run a browser in kiosk mode pointing at the Flask HTML UI.

Create `/etc/systemd/system/sssnl-dashboard.service`:

```ini
[Unit]
Description=SSSNL Dashboard (Chromium kiosk)
After=graphical.target sssnl-backend.service
Wants=sssnl-backend.service

[Service]
Type=simple
User=<user>
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/<user>/.Xauthority
ExecStart=/usr/bin/chromium-browser --kiosk --incognito http://localhost:5656/
Restart=always

[Install]
WantedBy=graphical.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable sssnl-dashboard.service
sudo systemctl start sssnl-dashboard.service
```

On boot, the Pi will start `sssnl-backend` and open Chromium fullscreen at `http://localhost:5656/`.

> Prefer a pure desktop app? See the Flutter sections below.

---

## 4. Daily `fetch_message` Service + Timer

`fetch_message.py` downloads a daily image into `static/media`.

Create `/etc/systemd/system/sssnl-fetch-message.service`:

```ini
[Unit]
Description=Fetch daily message image for SSSNL
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=<user>
WorkingDirectory=/home/<user>/sssnl
ExecStart=/home/<user>/sssnl/sssnlvenv/bin/python fetch_message.py
```

Create `/etc/systemd/system/sssnl-fetch-message.timer`:

```ini
[Unit]
Description=Run SSSNL fetch_message daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start the timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable sssnl-fetch-message.timer
sudo systemctl start sssnl-fetch-message.timer
```

Manual run for testing:

```bash
sudo systemctl start sssnl-fetch-message.service
sudo systemctl status sssnl-fetch-message.service
```

---

## 5. Optional: Flutter Web UI on the Pi

You can serve the Flutter UIs from Flask as browser apps. Build on the Pi or copy prebuilt assets.

Build commands (on the Pi):

```bash
# Install Flutter SDK (arm64) separately if not already available.
# Once flutter is on PATH:

cd /home/<user>/sssnl/sssnl_app
flutter build web --release --base-href /dashboard/ --output build/web_dashboard

cd /home/<user>/sssnl/sssnl_media_controls
flutter build web --release --base-href /media/ --output build/web_media
```

Then, with the backend running, access:
- Dashboard (Flutter): http://localhost:5656/dashboard
- Media controls: http://localhost:5656/media
- Dev panel: http://localhost:5656/dev

Note: If `flutter` isn’t installed on the Pi, you can build on a dev machine and copy the `build/web_dashboard` and `build/web_media` folders into the same paths on the Pi.

---

## 6. Optional: Flutter Desktop on Raspberry Pi

For most setups, using Chromium kiosk with the Flask HTML UI is simplest. If you want native Flutter desktop apps on Pi (arm64):

```bash
sudo apt install -y clang cmake ninja-build pkg-config libgtk-3-dev liblzma-dev
# Install Flutter for arm64 and enable linux-desktop
flutter config --enable-linux-desktop

# Build release binaries
cd /home/<user>/sssnl/sssnl_app
flutter build linux --release

cd /home/<user>/sssnl/sssnl_media_controls
flutter build linux --release
```

Update the kiosk service to launch the built binary instead of Chromium, or create separate services for each app. On 32‑bit Pi OS, Flutter desktop is not supported; use the Web approach.

---

## 7. Enable Services at Boot and Verify

```bash
sudo systemctl daemon-reload
sudo systemctl enable sssnl-backend.service
sudo systemctl enable sssnl-dashboard.service
sudo systemctl enable sssnl-fetch-message.timer

# Start now (optional)
sudo systemctl start sssnl-backend.service
sudo systemctl start sssnl-dashboard.service
sudo systemctl start sssnl-fetch-message.timer

# Check statuses
sudo systemctl status sssnl-backend.service
sudo systemctl status sssnl-dashboard.service
sudo systemctl status sssnl-fetch-message.timer
```

View backend logs:

```bash
journalctl -u sssnl-backend.service -f
```

---

## Troubleshooting

- No motion or DHT values: verify wiring, run `groups` to confirm your user is in `gpio` and `i2c`, and check `libgpiod2` is installed. Use `/mock-*` endpoints to simulate.
- Flutter Web routes 500: build the web bundles as shown above so `/dashboard`, `/media`, `/dev` can be served.
- Blank Chromium screen: ensure `DISPLAY=:0` is correct for your session and `.Xauthority` path matches the user.
- Port already in use: stop any previous instance or change the port in `app.py`.
