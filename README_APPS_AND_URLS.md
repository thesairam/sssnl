# SSSNL Apps and URLs

This project has **one backend service** and **one or two front‑end UIs**, all sharing the same data under `static/media`.

---

## 1. What runs where

### Backend: Flask (app.py)

- Process: `python app.py` (or `sssnl-backend.service` on the Pi).
- Responsibilities:
  - Reads DHT and PIR sensors on the Raspberry Pi (or uses mock/random values on desktop).
  - Maintains global status: temperature, humidity, motion.
  - Organises all media under `static/media`.
  - Exposes HTTP APIs and simple HTML pages used by the UIs.

This is the **only required long‑running Python process**.

### Front‑end A: Dashboard display

You have two options; both use the same backend APIs:

1. **HTML dashboard in a browser (simple, good for Pi):**
  - Use Chromium/another browser pointed to `http://localhost:5656/`.
  - Can be started at boot in kiosk mode via `sssnl-dashboard.service`.

2. **Flutter dashboard app (desktop and web):**
  - Project: `sssnl_app`
  - Desktop dev: `cd sssnl_app && flutter run -d linux`
  - Web build (served by app.py):
    - URL: `http://localhost:5656/dashboard`
    - Note: Built with base href `/dashboard/` and served from `sssnl_app/build/web_dashboard`.

### Front‑end B: Media & Developer controls (single Flutter app)

One Flutter app (`sssnl_media_controls`) used in multiple ways:

1. **Desktop dev:**
  - `cd sssnl_media_controls && flutter run -d linux`

2. **Web build (served by app.py):**
  - Build once: `flutter build web`
  - URLs:
    - `http://localhost:5656/media` → same app, opens **Media** tab.
    - `http://localhost:5656/dev`   → same app, opens **Developer** tab.
    - Note: Built with base href `/media/` and served from `sssnl_media_controls/build/web_media`.

There is also a minimal HTML page from media_admin.py at:

- `http://localhost:5656/media/manage`

which is backed by the same media APIs, but the recommended UI is the Flutter app (desktop or web).

---

## 2. Main URLs exposed by app.py

Assuming the backend is reachable as `http://localhost:5656`.

### Dashboard & status

- `/`  
  HTML dashboard (video + images playlist, status bar). Used directly by Chromium kiosk.

- `/status`  
  JSON with current readings and motion state, e.g.
  ```json
  {
    "temp": "24.5°C",
    "hum": "55.0%",
    "motion_status": "Motion detected" | "No motion",
    "motion_active": true | false,
    ...
  }
  ```

- `/playlist`  
  JSON playlist built from all files under `static/media`.
  Used by both the HTML dashboard JS and the Flutter dashboard.

- `/dht-debug`  
  Diagnostic endpoint to see which DHT backend is active and force a one‑off read.

### Media management (from media_admin.py, under /api/media)

- `/media/manage`  
  HTML single‑page media manager (upload/list/delete).

- `/api/media/upload` (POST, multipart)  
  Upload files to a target folder (usually `media`), ends up under `static/media`.

- `/api/media/files` (GET)  
  JSON listing of all files in `static/media` with type information.

- `/api/media/delete` (POST JSON)  
  Delete a single file by name from `static/media`.

- `/api/media/fetch` (POST JSON)  
  Download a remote URL directly into the chosen media folder.

- `/api/media/info` (GET)  
  Returns allowed targets and extensions.

### Mock / developer endpoints

Used mainly for desktop testing or via the Flutter dev panel; you can simply ignore them on the Pi if you want only real sensors.

- `/mock-motion` (POST JSON `{ "active": true|false }`)  
  Forces motion on/off. Affects what `/status` reports and what the dashboard sees.

- `/mock-motion/clear` (POST)  
  Clears the override so the real PIR GPIO drives motion again (on the Pi).

- `/mock-dht` (POST JSON `{ "temp": <number>, "hum": <number> }`)  
  Overrides DHT values used by the background reader.

- `/mock-dht/clear` (POST)  
  Clears DHT override (back to real sensor or random mock values).

### Optional: Flutter Web dashboard & dev/media

If you build the web versions:

```bash
cd /home/<user>/sssnl/sssnl_app
flutter build web --base-href /dashboard/ --output build/web_dashboard

cd /home/<user>/sssnl/sssnl_media_controls
flutter build web --base-href /media/ --output build/web_media
```

then app.py will serve them at:

- `/dashboard`  
  Flutter Web dashboard (same logic as the desktop dashboard app).

- `/media` and `/media/*`  
  Flutter Web media/dev app, opening the **Media** tab by default.

- `/dev` and `/dev/*`  
  Same Flutter Web media/dev app, opening the **Developer** tab by default.

---

## 3. Short answers to common questions

- **"How many apps run at boot on the Pi?"**  
  Recommended: **two processes** – the Flask backend (`app.py`) and a Chromium kiosk window pointing to `/`. Both are managed by systemd.

- **"Do I need the Flutter apps on the Pi?"**  
  No. They are mainly for development and can be used on a laptop/desktop. On the Pi, Chromium + the HTML dashboard is simpler and lighter.

-- **"Where do I manage media from?"**  
  Prefer the Flutter media/dev app (desktop, or `/media` on the web). The older `/media/manage` HTML page is still available but not required. All write into `static/media`.

- **"How do I simulate motion/DHT from my laptop?"**  
  Use the Flutter dev panel (desktop or `/dev`) or call the mock endpoints directly with curl/postman.
