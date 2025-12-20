#!/usr/bin/env python3
"""Convenience launcher to start backend and prepare Flutter Web bundles.

Usage (from repo root):
  python run_all.py

Assumptions:
- You're in the correct virtualenv so Flask deps are installed.
- `flutter` is on PATH if you want to (re)build web bundles; otherwise
    prebuilt assets under sssnl_app/build/web_dashboard and
    sssnl_media_controls/build/web_media will be served.
-
This is oriented for development; for Pi deployment, use systemd to
start `app.py` and point a browser (Chromium kiosk or any device) at
`http://<pi-ip>:5656/` for the HTML dashboard, or at `/dashboard`, `/media`.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent


def ensure_flutter_web_build(app_dir: Path, label: str, flutter_bin: str) -> None:
    """Build Flutter web for the given app with correct base href if missing.

    Dashboard needs base href `/dashboard/`; media/dev needs `/media/`.
    Output to distinct folders to avoid clashes.
    """
    out_dir = app_dir / "build" / ("web_dashboard" if label == "dashboard" else "web_media")
    web_index = out_dir / "index.html"
    if web_index.exists():
        return
    print(f"[launcher] Web build for {label} not found; running '{flutter_bin} build web' with base href...")
    try:
        base = "/dashboard/" if label == "dashboard" else "/media/"
        subprocess.run([
            flutter_bin, "build", "web",
            "--base-href", base,
            "--release",
            "--output", str(out_dir)
        ], cwd=str(app_dir), check=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[launcher] Warning: flutter build web failed for {label}: {exc}")

def start_process(name: str, args: list[str], cwd: Path) -> subprocess.Popen:
    print(f"[launcher] Starting {name} in {cwd} -> {' '.join(args)}")
    return subprocess.Popen(args, cwd=str(cwd))
def find_flutter_bin() -> str:
    """Locate the flutter executable reliably across setups.

    Order:
    0. FLUTTER_BIN env override
    1. PATH: use "flutter" if available
    2. $FLUTTER_HOME/bin/flutter if set
    3. ~/flutter/bin/flutter if present
    4. snap: /snap/bin/flutter
    """
    # 0. Explicit override
    override = os.environ.get("FLUTTER_BIN")
    if override:
        cand = Path(override)
        if cand.exists():
            return str(cand)
        else:
            print(f"[launcher] FLUTTER_BIN override set but not found: {override}")
    # 1. PATH
    from shutil import which
    exe = which("flutter")
    if exe:
        return exe
    # 2. FLUTTER_HOME
    fh = os.environ.get("FLUTTER_HOME")
    if fh:
        cand = Path(fh) / "bin" / "flutter"
        if cand.exists():
            return str(cand)
    # 3. ~/flutter/bin/flutter
    home = Path.home()
    cand = home / "flutter" / "bin" / "flutter"
    if cand.exists():
        return str(cand)
    # 4. snap
    cand = Path("/snap/bin/flutter")
    if cand.exists():
        return str(cand)
    # Fallback to plain name; will fail with a clear message
    return "flutter"


# Desktop Flutter apps are no longer launched by this helper.


def main() -> None:
    procs: list[tuple[str, subprocess.Popen]] = []

    try:
        # Detect flutter and ensure web builds exist so /dashboard, /media, /dev work by default.
        flutter_bin = find_flutter_bin()
        sssnl_app_dir = ROOT / "sssnl_app"
        media_controls_dir = ROOT / "sssnl_media_controls"
        if Path(flutter_bin).name == "flutter" and not Path(flutter_bin).exists():
            print("[launcher] Flutter not found. Skipping web builds. Serving prebuilt web if available.")
        else:
            # Build web bundles with correct base-hrefs when flutter is available
            ensure_flutter_web_build(sssnl_app_dir, "dashboard", flutter_bin)
            ensure_flutter_web_build(media_controls_dir, "media_controls", flutter_bin)

        # 1) Flask backend (app.py)
        procs.append(
            (
                "backend",
                start_process("backend", [sys.executable, "app.py"], ROOT),
            )
        )

        # Give the backend a moment to bind to port 5656 (optional wait for ready)
        time.sleep(2)

        # 2) No desktop app launch — use web routes at /dashboard, /media, /dev
        print("[launcher] Web routes: http://localhost:5656/dashboard, /media, /dev.")

        print("[launcher] All processes started. Press Ctrl+C to stop everything.")

        # Monitor children; if any exits, stop the rest.
        while True:
            time.sleep(2)
            for name, proc in list(procs):
                code = proc.poll()
                if code is not None:
                    print(f"[launcher] {name} exited with code {code}; stopping others.")
                    return

    except KeyboardInterrupt:
        print("\n[launcher] KeyboardInterrupt received, stopping all processes...")

    finally:
        for name, proc in procs:
            if proc.poll() is None:
                print(f"[launcher] Terminating {name}...")
                proc.terminate()
        # Give processes a moment to exit cleanly
        time.sleep(3)
        for name, proc in procs:
            if proc.poll() is None:
                print(f"[launcher] Killing {name}...")
                proc.kill()


if __name__ == "__main__":
    main()
