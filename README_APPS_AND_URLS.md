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

You have two ways to show the dashboard:

1. **HTML dashboard in a browser (recommended for Pi):**
   - Use Chromium/another browser pointed to `http://localhost:5000/`.
   - Can be started at boot in kiosk mode via `sssnl-dashboard.service`.

2. **Flutter desktop dashboard app (development / optional on Pi):**
   - Project: `sssnl_app`
   - Run on desktop: `cd sssnl_app && flutter run -d linux`
   - Calls the backend JSON APIs (`/status`, `/playlist`) and plays the media.

### Front‑end B: Media & Developer controls

Again, two ways to use the same backend APIs:

1. **Browser UI from media_admin.py**
   - URL: `http://<host>:5000/media/manage`
   - Simple HTML page for upload/list/delete using `/media/*` endpoints.

2. **Flutter media/dev controls app**
   - Project: `sssnl_media_controls`
   - Linux app (dev): `cd sssnl_media_controls && flutter run -d linux`
   - Optional web build served at `/dev` (see below).

Both talk to the same Flask endpoints; no extra backend.

---

## 2. Main URLs exposed by app.py

Assuming the backend is running on `http://<host>:5000`.

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

### Media management (from media_admin.py)

- `/media/manage`  
  HTML single‑page media manager (upload/list/delete).

- `/media/upload` (POST, multipart)  
  Upload files to a target folder (usually `media`), ends up under `static/media`.

- `/media/files` (GET)  
  JSON listing of all files in `static/media` with type information.

- `/media/delete` (POST JSON)  
  Delete a single file by name from `static/media`.

- `/media/fetch` (POST JSON)  
  Download a remote URL directly into the chosen media folder.

- `/media/info` (GET)  
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

### Optional: Flutter Web dev/media panel

If you build the web version of `sssnl_media_controls`:

```bash
cd /home/<user>/sssnl/sssnl_media_controls
flutter build web
```

then app.py will serve it at:

- `/dev` and `/dev/*`  
  Flutter Web app with:
  - **Media** tab (upload/list/delete via `/media/*`).
  - **Developer** tab (buttons that call `/mock-motion*` and `/mock-dht*`).

---

## 3. Short answers to common questions

- **"How many apps run at boot on the Pi?"**  
  Recommended: **two processes** – the Flask backend (`app.py`) and a Chromium kiosk window pointing to `/`. Both are managed by systemd.

- **"Do I need the Flutter apps on the Pi?"**  
  No. They are mainly for development and can be used on a laptop/desktop. On the Pi, Chromium + the HTML dashboard is simpler and lighter.

- **"Where do I manage media from?"**  
  Either from `/media/manage` in a browser, or from the Flutter media/dev app (desktop or `/dev` web build). Both write into `static/media`.

- **"How do I simulate motion/DHT from my laptop?"**  
  Use the Flutter dev panel (desktop or `/dev`) or call the mock endpoints directly with curl/postman.
