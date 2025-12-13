#!/usr/bin/env python3
"""Convenience launcher to start backend + both Flutter apps.

Usage (from repo root):
  python run_all.py

Assumptions:
- You're in the correct virtualenv so Flask deps are installed.
- `flutter` is on PATH.
- This is for development on Ubuntu / desktop; for Pi deployment,
  consider building Flutter binaries and using systemd instead.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def start_process(name: str, args: list[str], cwd: Path) -> subprocess.Popen:
    print(f"[launcher] Starting {name} in {cwd} -> {' '.join(args)}")
    return subprocess.Popen(args, cwd=str(cwd))


def main() -> None:
    procs: list[tuple[str, subprocess.Popen]] = []

    try:
        # 1) Flask backend (app.py)
        procs.append(
            (
                "backend",
                start_process("backend", [sys.executable, "app.py"], ROOT),
            )
        )

        # 2) Flutter dashboard app (sssnl_app)
        sssnl_app_dir = ROOT / "sssnl_app"
        procs.append(
            (
                "dashboard",
                start_process(
                    "dashboard",
                    ["flutter", "run", "-d", "linux"],
                    sssnl_app_dir,
                ),
            )
        )

        # 3) Flutter media/dev controls app (sssnl_media_controls)
        media_controls_dir = ROOT / "sssnl_media_controls"
        procs.append(
            (
                "media_controls",
                start_process(
                    "media_controls",
                    ["flutter", "run", "-d", "linux"],
                    media_controls_dir,
                ),
            )
        )

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
