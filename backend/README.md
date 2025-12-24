# SSSNL Backend

A clean, standalone backend packaged in `backend/` that serves APIs and Flutter web assets.

## Run with local Python
```bash
cd backend
source ../sssnlvenv/bin/activate
pip install -r requirements.txt
export DB_URI="mysql+pymysql://dbadmin:dbadmin@localhost:3306/sssnl"
export SSSNL_ADMIN_USER=dbadmin
export SSSNL_ADMIN_PASS=dbadmin
# Allow frontends on other ports (optional, comma-separated)
export CORS_ORIGINS="http://localhost:5656,http://localhost:3000,http://localhost:5173"
# Run from inside this folder:
python -m app


bash -lc "set -e
cd /home/gayathri/projects/sssnl/backend
export HOST_UID=$(id -u)
export HOST_GID=$(id -g)
sudo --preserve-env=HOST_UID,HOST_GID env HOST_UID=$HOST_UID HOST_GID=$HOST_GID docker compose down -v --remove-orphans || true
sudo --preserve-env=HOST_UID,HOST_GID env HOST_UID=$HOST_UID HOST_GID=$HOST_GID docker compose pull || true
sudo --preserve-env=HOST_UID,HOST_GID env HOST_UID=$HOST_UID HOST_GID=$HOST_GID docker compose up -d
sudo docker compose ps
"


# Alternatively, from the repository root use:
# python -m backend.app
```
Backend will listen on `http://localhost:5656`.

## Independent App Launches

These apps run separately and use `BACKEND_BASE_URL` to talk to the backend:

- Dashboard (Flutter dev server):
	```bash
	cd ../sssnl_app
	flutter pub get
	flutter run -d chrome --web-hostname=0.0.0.0 --web-port 5173 --dart-define=BACKEND_BASE_URL=http://localhost:5656
	```

- Media Controls (Flutter mobile):
	```bash
	cd ../sssnl_media_controls
	flutter pub get
	flutter run -d android --dart-define=BACKEND_BASE_URL=http://localhost:5656
	# or: flutter run -d ios --dart-define=BACKEND_BASE_URL=http://localhost:5656
	```

Ensure `CORS_ORIGINS` includes your dev origin (e.g., `http://localhost:5173`).

## Auth Defaults
- Admin username: `dbadmin`
- Admin password: `dbadmin`
These are seeded on first start (or overridden via `SSSNL_ADMIN_USER` / `SSSNL_ADMIN_PASS`).

Notes for clients:
- CORS is enabled with credentials; web/mobile must send and persist cookies.
- Mobile app should run with `--dart-define=BACKEND_BASE_URL=http://<backend-host>:5656`.


## Run backend + MariaDB via Compose (optional)
This brings up MariaDB and the backend together using the compose file in this folder.

Option A — without sudo (recommended):
```bash
cd backend
export HOST_UID=$(id -u)
export HOST_GID=$(id -g)
sudo docker compose up -d
```

Option B — with sudo (when your user can't access Docker yet):
```bash
cd backend
sudo --preserve-env=HOST_UID,HOST_GID env HOST_UID=$(id -u) HOST_GID=$(id -g) docker compose up -d
```

Verify and view logs:
```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f mariadb
```

If running compose with `sudo`, preserve UID/GID mapping so mounted files are writable by your user:
```bash
export HOST_UID=$(id -u)
export HOST_GID=$(id -g)
sudo --preserve-env=HOST_UID,HOST_GID env HOST_UID=$HOST_UID HOST_GID=$HOST_GID docker compose up -d
```

Stop everything:
```bash
docker compose down
```

This mounts the project at `/workspace` inside the backend container so `static/` and your web builds are served directly.

Troubleshooting:
- ModuleNotFoundError: `backend.app` – ensure you’re on the latest compose file and re-run:
	```bash
	cd backend
	docker compose down
	docker compose pull
	docker compose up -d
	```
- Permission denied on docker socket or UID read-only:
	- Without sudo: ensure your user can access docker (recommended):
		```bash
		sudo usermod -aG docker "$USER"
		newgrp docker
		cd backend
		export HOST_UID=$(id -u)
		export HOST_GID=$(id -g)
		docker compose up -d
		```
	- With sudo (preserve env for user mapping):
		```bash
		cd backend
		sudo --preserve-env=HOST_UID,HOST_GID env HOST_UID=$(id -u) HOST_GID=$(id -g) docker compose up -d
		```
- Port 3306 in use – stop other MariaDB/MySQL instances or change the mapped port.
- Check logs:
	```bash
	cd backend
	docker compose ps
	docker compose logs -f backend
	docker compose logs -f mariadb
	```

## API docs
See [docs/api.md](docs/api.md) for endpoint reference used by frontend developers.

Key device endpoints (new):
- `POST /api/devices/register` – from device: body `{mac, name?}` -> returns `{device_id, device_token}`
- `POST /api/devices/<device_id>/heartbeat` – from device with `{device_token}`
- `POST /api/devices/<device_id>/claim` – from device (after user initiated pairing) with `{device_token, pairing_code}`
- `POST /api/devices/pair_by_mac` – from signed-in user: `{mac}` -> returns `{pairing_code, expires}`
- `GET /api/devices` – from signed-in user: list owned devices
- `POST /api/devices/<device_id>/rename` – rename owned device

## Configuration
- `DB_URI`: SQLAlchemy database URI. Defaults to `sqlite:///backend/data/users.db`.
- `SSSNL_ADMIN_USER`, `SSSNL_ADMIN_PASS`: seeded admin on startup.
- `SSSNL_MEDIA_API_KEY`: optional API key for `/api/media/*` endpoints.
- `CORS_ORIGINS`: comma-separated list of allowed origins for web/mobile apps.

## Mobile & Provisioning
- Android/iOS app can pair to the Pi via BLE and send Wi‑Fi credentials automatically after pairing.
- BLE service UUID: `0000ffff-0000-1000-8000-00805f9b34fb`.
- See provisioning flow and Pi agent setup in [raspi-agent/README.md](../raspi-agent/README.md).

Troubleshooting
- Permission denied on Docker socket:
	- Add your user to the `docker` group and re-run without sudo:
		```bash
		sudo usermod -aG docker "$USER"
		newgrp docker
		```
	- Or use the sudo command shown above that preserves `HOST_UID`/`HOST_GID`.
- ModuleNotFoundError `backend.app`:
	- Ensure you run compose from the `backend/` folder and you’re on the latest file:
		```bash
		cd backend
		docker compose down
		docker compose pull
		docker compose up -d
		```
- Wheels download loops / slow first start: the backend container creates a local venv at `/workspace/.venv` and installs `backend/requirements.txt` on first boot; subsequent starts are faster.
