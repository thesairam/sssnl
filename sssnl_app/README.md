# SSSNL App (Web Dashboard)

Flutter Web app that displays media for a specific device. Intended for kiosk mode on Raspberry Pi or any browser.

## Run (Development)
```bash
cd sssnl_app
flutter pub get
flutter run -d chrome --web-hostname=0.0.0.0 --web-port 5173 --dart-define=BACKEND_BASE_URL=http://<backend-host>:5656
```
- Access in browser: http://<this-machine-ip>:5173
- Pass device context via URL: `?device_mac=<mac>` to scope the playlist.

Example:
- http://localhost:5173/?device_mac=dc:a6:32:12:34:56

## Build (Production)
```bash
cd sssnl_app
flutter build web --dart-define=BACKEND_BASE_URL=https://<backend-domain>
```
Serve `build/web` with any static server (Nginx, Caddy) or point the Raspberry Pi kiosk to the hosted URL including `device_mac`.

## Notes
- The app polls the backend `/status` and `/playlist` endpoints and plays the playlist when motion is detected.
- Use the mobile app to upload media to the selected device before testing playback.

## Troubleshooting
- CORS errors: ensure backend `CORS_ORIGINS` includes your dev origin (e.g., http://localhost:5173).
- No media: confirm uploads for the selected device and that the query contains the correct `device_mac`.
