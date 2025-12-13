# SSSNL Raspberry Pi Services

This document describes how to run the SSSNL stack on a Raspberry Pi and configure systemd services so everything starts at boot.

Assumptions:
- Project cloned to `/home/<user>/sssnl`.
- Python 3 and `python3-venv` installed.
- Chromium (or another browser) installed on the Pi desktop.

Replace `<user>` with your actual username (e.g. `pi`, `saipi`).

---

## 1. Initial setup on the Pi

```bash
cd /home/<user>/sssnl

# Create and activate venv
python3 -m venv sssnlvenv
source sssnlvenv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

Enable GPIO/I2C as needed using `raspi-config`.

To test manually:

```bash
# In venv
python app.py
# Open http://localhost:5000/ in a browser
```

Stop it (Ctrl+C) before configuring systemd.

---

## 2. Backend service (Flask app.py)

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

The backend exposes:
- `/`           – HTML dashboard
- `/status`    – JSON status (temp, humidity, motion)
- `/playlist`  – JSON playlist built from `static/media`
- `/media/*`   – media upload/list/delete (from media_admin.py)
- `/mock-*`    – mock motion & DHT endpoints for dev
- `/dev`       – optional Flutter Web dev panel (if built, see below)

---

## 3. Fullscreen dashboard (Chromium kiosk)

Simplest way to show the dashboard is a browser in kiosk mode pointing at the Flask HTML UI.

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
ExecStart=/usr/bin/chromium-browser --kiosk --incognito http://localhost:5000/
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

On boot, the Pi will:
- start `sssnl-backend` (Flask), then
- open Chromium fullscreen at `http://localhost:5000/`.

> If you later prefer the Flutter desktop dashboard instead of Chromium,
> build it with `flutter build linux` in `sssnl_app` and update `ExecStart`
> to point at the resulting binary.

---

## 4. Daily fetch_message service + timer

`fetch_message.py` downloads the daily image into `static/media`.

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

You can run it manually for testing:

```bash
sudo systemctl start sssnl-fetch-message.service
sudo systemctl status sssnl-fetch-message.service
```

---

## 5. Optional: Flutter dev/media panel at /dev

If you want the Flutter media/dev controls UI to run in the browser at `/dev`:

1. On the Pi (or on a dev machine, then copy the build):

```bash
cd /home/<user>/sssnl/sssnl_media_controls
flutter build web
```

This creates `sssnl_media_controls/build/web`.

2. Ensure the backend is running. The route `/dev` in `app.py` will now serve the Flutter Web app:

- Open: `http://<pi-ip>:5000/dev`
- Login with the dummy credentials: `dev` / `dev123`.

From there you can:
- Manage media with the Media tab (upload/list/delete via `/media/*`).
- Trigger mock motion and DHT with the Developer tab (via `/mock-*`).

On the production Pi you can simply avoid using these mock controls so
that real hardware drives the dashboard as intended.
