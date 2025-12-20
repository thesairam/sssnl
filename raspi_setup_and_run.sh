#!/usr/bin/env bash
# SSSNL Raspberry Pi setup + run helper (Web-only)
# - Installs apt dependencies
# - Creates Python venv and installs pip requirements
# - Builds Flutter Web (dashboard + media) if flutter exists
# - Starts Flask backend
# - Does NOT auto-open the web UI; no desktop app builds

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
ARCH="$(uname -m)"  # aarch64 (64-bit Pi) or armv7l (32-bit)
VENV_DIR="$ROOT_DIR/sssnlvenv"
PYBIN="$VENV_DIR/bin/python"
PIPBIN="$VENV_DIR/bin/pip"

log() { echo -e "[raspi] $*"; }
warn() { echo -e "[raspi][WARN] $*" >&2; }
err() { echo -e "[raspi][ERROR] $*" >&2; }

ensure_apt_pkg() {
  local pkg="$1"
  if ! dpkg -s "$pkg" >/dev/null 2>&1; then
    sudo apt-get install -y "$pkg"
  fi
}

choose_chromium_pkg() {
  if apt-cache show chromium-browser >/dev/null 2>&1; then
    echo chromium-browser
  else
    echo chromium
  fi
}

# 0) Arch sanity note
if [[ "$ARCH" != "aarch64" && "$ARCH" != "armv7l" ]]; then
  warn "This script is intended for Raspberry Pi (arm). Detected: $ARCH"
fi

# 1) OS dependencies
log "Updating apt and installing base packages (sudo required)..."
sudo apt-get update -y
ensure_apt_pkg python3
ensure_apt_pkg python3-venv
ensure_apt_pkg python3-pip
ensure_apt_pkg libgpiod2
# Desktop build deps removed (web-only). Keep Chromium optional.
CHROMIUM_PKG="$(choose_chromium_pkg)"
ensure_apt_pkg "$CHROMIUM_PKG"

# 2) Python venv + pip install
if [[ ! -x "$PYBIN" ]]; then
  log "Creating Python venv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
log "Installing Python requirements..."
"$PIPBIN" install --upgrade pip
"$PIPBIN" install -r "$ROOT_DIR/requirements.txt"

deactivate

# 3) Flutter presence check
HAVE_FLUTTER=0
if command -v flutter >/dev/null 2>&1; then
  HAVE_FLUTTER=1
  log "Flutter found: $(flutter --version 2>/dev/null | head -n1)"
  # Enable linux desktop target; ignore if already enabled
  flutter config --enable-linux-desktop || true
else
  warn "flutter not found on PATH; will skip Flutter builds."
  warn "You can still use the web UI via Chromium kiosk + Flask backend."
fi

# 4) Build Flutter Web bundles (if flutter available)
if [[ "$HAVE_FLUTTER" -eq 1 ]]; then
  log "Building Flutter Web bundles (dashboard + media)..."
  pushd "$ROOT_DIR/sssnl_app" >/dev/null
  flutter build web --release --base-href /dashboard/ --output build/web_dashboard || warn "Web dashboard build failed."
  popd >/dev/null

  pushd "$ROOT_DIR/sssnl_media_controls" >/dev/null
  flutter build web --release --base-href /media/ --output build/web_media || warn "Web media build failed."
  popd >/dev/null
fi

# 5) Launch backend only. Do NOT open web.
PIDS=()
cleanup() {
  log "Stopping child processes..."
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" || true
    fi
  done
}
trap cleanup EXIT INT TERM

log "Starting Flask backend..."
source "$VENV_DIR/bin/activate"
"$PYBIN" "$ROOT_DIR/app.py" &
PIDS+=("$!")
deactivate || true

log "All started. Web builds (if built) are served by Flask at:"
log "  http://localhost:5656/dashboard"
log "  http://localhost:5656/media   and http://localhost:5656/dev"
log "Press Ctrl+C to stop."

# Keep script in foreground while children run
while true; do sleep 2; done
