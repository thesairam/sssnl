# SSSNL Raspberry Pi Agent

This agent runs on a Raspberry Pi to:
- Advertise over BLE a provisioning service.
- Receive Wi‑Fi credentials and optional pairing code from the mobile app.
- Connect to Wi‑Fi and register with the backend.
- Maintain a heartbeat and render the web dashboard in kiosk mode.

Components
- ble_peripheral.py: GATT service for provisioning (BLE UUIDs match the mobile app).
- backend_client.py: Register, claim, and heartbeat to backend.
- kiosk.sh: Launch Chromium in kiosk mode to the Flutter web app.
- kiosk.service: systemd unit to auto-start kiosk on boot.
- kiosk.sh: Launch Chromium in kiosk mode to the Flutter web app.
- service files: systemd unit templates.

Quick start
1. Install system packages (use these to avoid wheel build errors):
```bash
sudo apt update
sudo apt install -y \
  bluetooth bluez bluez-tools rfkill \
  python3-pip python3-venv python3-dev \
  python3-gi python3-dbus \
  libglib2.0-dev libdbus-1-dev libbluetooth-dev \
  chromium || sudo apt install -y chromium-browser
```

2. Create a fresh virtualenv, upgrade pip, and use piwheels for ARM wheels:
```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip setuptools wheel
pip config set global.extra-index-url https://www.piwheels.org/simple
pip install --prefer-binary -r requirements.txt
```
3. Set backend URL:
```bash
export BACKEND_BASE_URL="http://:192.168.29.38:5656"
```
4. Run BLE provisioning service:
```bash
sudo -E env PATH="$PATH" PYTHONPATH="$PYTHONPATH" $(which python3) ble_peripheral.py
```
5. Use the mobile app to pair and send Wi‑Fi credentials.
6. The agent will register with backend and send heartbeat periodically.

Why these steps?
- PyGObject/`gi` is installed via apt (`python3-gi`). Do not `pip install PyGObject` on Raspberry Pi — it often fails to build wheels.
- `--prefer-binary` and the piwheels index ensure ARM wheels are used whenever available.
- `python3-dbus` supplies DBus bindings used by BlueZ and avoids fragile pip builds.

Kiosk mode (Chromium fullscreen)
1) Choose a hostname for your desktop serving the web dashboard (so you don’t need an IP). Options:
   - Use mDNS: set desktop hostname to `sssnl-desktop` so it resolves as `sssnl-desktop.local` on the LAN.
     - Ubuntu/Debian: `sudo apt install -y avahi-daemon`
     - macOS: Bonjour is built-in; Windows: install Apple Bonjour or enable mDNS.
   - Or set a DNS reservation on your router.
   - Or add a static entry in `/etc/hosts` on the Pi.

2) Install kiosk files on the Pi:
```bash
sudo mkdir -p /opt/sssnl
sudo cp kiosk.sh /opt/sssnl/
sudo chmod +x /opt/sssnl/kiosk.sh
sudo cp kiosk.service /etc/systemd/system/sssnl-kiosk.service
```

3) Configure the dashboard URL (uses mDNS by default):
```bash
# Edit the Environment line if your hostname/port differs
sudo systemctl edit sssnl-kiosk --full
# Ensure: Environment=DASHBOARD_URL=http://sssnl-desktop.local:5173
```

4) Enable on boot and start now:
```bash
sudo systemctl daemon-reload
sudo systemctl enable sssnl-kiosk
sudo systemctl start sssnl-kiosk
```

If you see a blank page, confirm the desktop dev server is reachable at the chosen hostname and port. The URL will include `?device_mac=<mac>` automatically.

BLE Service
- Service UUID: 0000ffff-0000-1000-8000-00805f9b34fb
- Characteristics:
  - MAC (read): 0000fff2-0000-1000-8000-00805f9b34fb
  - Credentials (write): 0000fff1-0000-1000-8000-00805f9b34fb
    - Payload JSON: {"ssid":"...","password":"...","pairing_code":"..."}

Security notes
- Wi‑Fi credentials are only stored locally on the Pi.
- The backend stores a per-device secret (token) to authenticate heartbeats.
- Pairing requires a pairing code initiated by a signed-in user from the app.

Tips
- To run the dashboard from your desktop without IPs, prefer a .local mDNS name (e.g., `http://sssnl-desktop.local:5173`). The kiosk script defaults to that and appends `?device_mac=<mac>`.
- You can override the dashboard URL by setting `DASHBOARD_URL` in the systemd unit Environment.

Troubleshooting
- ImportError: gi.repository not found → `sudo apt install -y python3-gi`
- No Bluetooth adapter found → enable Bluetooth: `sudo rfkill unblock all` and ensure BlueZ is running: `sudo systemctl status bluetooth`
- `bluetoothctl` permission issues → run the agent with `sudo -E` or add your user to the `bluetooth` group and restart.
