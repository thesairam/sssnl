#!/usr/bin/env bash
set -euo pipefail

# SSSNL Raspberry Pi Agent setup script
# Installs system packages, creates venv with system site packages, and installs pip deps.

if [[ ${EUID} -ne 0 ]]; then
  echo "Please run as root: sudo $0"
  exit 1
fi

apt update
apt install -y \
  bluetooth bluez bluez-tools rfkill \
  python3-pip python3-venv python3-dev \
  python3-gi python3-dbus \
  libglib2.0-dev libdbus-1-dev libbluetooth-dev \
  chromium || apt install -y chromium-browser || true

# Create venv with system site packages so gi/dbus are visible
cd "$(dirname "$0")"
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install -U pip setuptools wheel
pip config set global.extra-index-url https://www.piwheels.org/simple || true
python3 -m pip install --prefer-binary -r requirements.txt

# Preflight
./check_env.py || true

echo "\nSetup complete. Run with:"
echo "  sudo -E $(pwd)/.venv/bin/python ble_peripheral.py"
