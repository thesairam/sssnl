#!/usr/bin/env bash
set -euo pipefail

# SSSNL Kiosk launcher for Raspberry Pi
# - Launches Chromium in fullscreen kiosk mode pointing to the Flutter Web dashboard
# - Appends ?device_mac= to the dashboard URL so the backend can scope media
#
# Configuration via env vars:
#   DASHBOARD_URL  (e.g., http://sssnl-desktop.local:5173)
#   BACKEND_BASE_URL (optional, used only by the web app if it needs a fixed backend)

DEVICE_MAC="$(cat /sys/class/net/wlan0/address 2>/dev/null || echo 00:00:00:00:00:00)"
DASHBOARD_URL="${DASHBOARD_URL:-http://sssnl-desktop.local:5173}"

# Normalize URL (strip trailing slash) and append device_mac
BASE_NO_SLASH="${DASHBOARD_URL%/}"
FINAL_URL="${BASE_NO_SLASH}/?device_mac=${DEVICE_MAC}"

echo "[kiosk] Using URL: ${FINAL_URL}"

# Optional: prevent screen blanking if running under X
if command -v xset >/dev/null 2>&1; then
  xset s off || true
  xset s noblank || true
  xset -dpms || true
fi

# Prefer chromium-browser; fallback to chromium
CHROME_BIN="$(command -v chromium-browser || true)"
if [[ -z "${CHROME_BIN}" ]]; then
  CHROME_BIN="$(command -v chromium || true)"
fi
if [[ -z "${CHROME_BIN}" ]]; then
  echo "chromium not found; install chromium-browser" >&2
  exit 1
fi

exec "${CHROME_BIN}" \
  --noerrdialogs \
  --disable-infobars \
  --kiosk \
  --incognito \
  --autoplay-policy=no-user-gesture-required \
  "${FINAL_URL}"
