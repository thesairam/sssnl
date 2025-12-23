# Services & Background Run (Web‑Only)

This guide explains how to run SSSNL as services so it starts at boot and runs in the background. It focuses on Raspberry Pi (recommended) but applies to other Linux systems with minor changes.

## What runs
- Flask backend (`backend.app`) – serves the HTML dashboard and APIs.
- Browser in kiosk mode (Chromium) – points to `http://localhost:5656/dashboard`.
- Optional timer – runs `fetch_message.py` daily to download images into `static/media`.

### Database (MariaDB)
This backend can use MariaDB instead of SQLite. A ready-to-use `docker-compose.yml` is provided.

Quick start:
```bash
cd /home/<user>/sssnl
docker compose up -d mariadb

# optional Adminer UI for browsing the DB
docker compose up -d adminer
```

Environment for the backend:
```bash
export DB_URI="mysql+pymysql://dbadmin:dbadmin@localhost:3306/sssnl"
# optional admin seed (overrides default)
export SSSNL_ADMIN_USER=dbadmin
export SSSNL_ADMIN_PASS=dbadmin
```
If `DB_URI` is not set, the app falls back to a local SQLite file at `data/users.db`.

## Raspberry Pi Setup

Prereqs:
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip libgpiod2 \
  chromium-browser  # or: chromium
```

Create venv and install deps:
```bash
cd /home/<user>/sssnl
python3 -m venv sssnlvenv
source sssnlvenv/bin/activate
pip install -r requirements.txt
```

## Backend service (`sssnl-backend.service`)
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
ExecStart=/home/<user>/sssnl/sssnlvenv/bin/python -m backend.app
Restart=on-failure
Environment=DB_URI=mysql+pymysql://dbadmin:dbadmin@localhost:3306/sssnl
Environment=SSSNL_ADMIN_USER=dbadmin
Environment=SSSNL_ADMIN_PASS=dbadmin

[Install]
WantedBy=multi-user.target
```
Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable sssnl-backend.service
sudo systemctl start sssnl-backend.service
sudo systemctl status sssnl-backend.service
```

## Chromium kiosk (`sssnl-dashboard.service`)
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
ExecStart=/usr/bin/chromium-browser --kiosk --incognito http://localhost:5656/dashboard
Restart=always

[Install]
WantedBy=graphical.target
```
Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable sssnl-dashboard.service
sudo systemctl start sssnl-dashboard.service
sudo systemctl status sssnl-dashboard.service
```

## Daily fetch timer (`sssnl-fetch-message.timer`)
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
Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable sssnl-fetch-message.timer
sudo systemctl start sssnl-fetch-message.timer
sudo systemctl status sssnl-fetch-message.timer
```

## Logs & tips
- Backend logs: `journalctl -u sssnl-backend.service -f`
- If kiosk does not appear: confirm X is running and `DISPLAY=:0` is correct; ensure `.Xauthority` path belongs to `<user>`.
- To stop services: `sudo systemctl stop <service-name>`

## Shortcut: Pi helper script
You can also use the web‑only helper script to set up and run quickly without services:
```bash
cd /home/<user>/sssnl
chmod +x raspi_setup_and_run.sh
./raspi_setup_and_run.sh
```
This installs deps, builds Flutter Web (if `flutter` is available), and starts the backend; it does not open a browser.
