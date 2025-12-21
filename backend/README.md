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
python -m backend.app
```
Backend will listen on `http://localhost:5656`.

## Run backend + MariaDB via Compose (optional)
This brings up MariaDB and the backend together using the compose file in this folder.

Option A — without sudo (recommended):
```bash
cd backend
export HOST_UID=$(id -u)
export HOST_GID=$(id -g)
docker compose up -d
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

## Configuration
- `DB_URI`: SQLAlchemy database URI. Defaults to `sqlite:///backend/data/users.db`.
- `SSSNL_ADMIN_USER`, `SSSNL_ADMIN_PASS`: seeded admin on startup.
- `SSSNL_MEDIA_API_KEY`: optional API key for `/api/media/*` endpoints.

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
