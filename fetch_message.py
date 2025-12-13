#!/usr/bin/env python3
import os
import datetime
import urllib.request
from pathlib import Path


# Resolve static/media relative to this file's directory so it works on
# any username (e.g. /home/<user>/sssnl/static/media).
PROJECT_ROOT = Path(__file__).resolve().parent
STATIC_DIR = PROJECT_ROOT / "static" / "media"


def fetch_today_message_image() -> str | None:
    """Fetch today's image from mysai.org and save to static/media.

    URL pattern assumed: https://www.mysai.org/month{M}/{D}.jpg
    Saves as latest.jpg in the static directory.
    Returns the filesystem path of the saved image (str) or None on failure.
    """
    try:
        today = datetime.date.today()
        img_url = f"https://www.mysai.org/month{today.month}/{today.day}.jpg"

        # Ensure destination exists
        STATIC_DIR.mkdir(parents=True, exist_ok=True)
        dest_path = STATIC_DIR / "latest.jpg"

        # Download image
        with urllib.request.urlopen(img_url, timeout=15) as resp:
            if getattr(resp, "status", 200) != 200:
                print("Failed to download message image:", getattr(resp, "status", "unknown status"))
                return None
            data = resp.read()

        with open(dest_path, "wb") as f:
            f.write(data)

        print("Saved:", str(dest_path))
        return str(dest_path)
    except Exception as e:
        print("Error fetching message image:", e)
        return None


if __name__ == "__main__":
    fetch_today_message_image()

    