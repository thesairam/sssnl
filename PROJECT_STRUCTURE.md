# SSSNL Project Structure

This document describes the organized directory structure of the SSSNL project.

## Directory Structure

```
sssnl/
├── backend/              # Backend Flask application (MAIN SERVER)
│   ├── app.py           # Main Flask server with SQLAlchemy
│   ├── media_admin.py   # Media management module
│   ├── requirements.txt # Backend-specific dependencies
│   ├── docker-compose.yml
│   └── docs/
│
├── sensors/             # Sensor-related modules
│   └── dht.py          # DHT sensor reader
│
├── utils/               # Utility modules
│   └── fetch_message.py # Message/image fetcher
│
├── scripts/             # Standalone scripts
│   └── run_all.py      # Convenience launcher for dev
│
├── pi_ble_cfg/          # Raspberry Pi BLE configuration
│   └── config.py
│
├── flutter_app/         # Original Flutter app
├── sssnl_app/           # Dashboard Flutter app
├── sssnl_media_controls/# Media controls Flutter app
│
├── data/                # Data directory (databases, etc.)
├── static/              # Static web assets
├── requirements.txt     # Root-level dependencies
└── docker-compose.yml   # Docker composition
```

## Module Organization

### Backend (`backend/`)
**Purpose**: All Flask backend server code
- Main API server (`app.py`)
- Authentication & user management
- Device management APIs
- Media management (`media_admin.py`)
- Sensor monitoring
- Database management (SQLAlchemy with SQLite/MariaDB support)

**Running the backend**:
```bash
# From project root
cd backend
python app.py

# Or using docker-compose
docker-compose up
```

### Sensors (`sensors/`)
**Purpose**: Sensor interface modules
- DHT temperature/humidity sensor (`dht.py`)
- Future: Other sensor integrations

### Utils (`utils/`)
**Purpose**: Utility functions and helpers
- Message/image fetching (`fetch_message.py`)
- Future: Other utility functions

### Scripts (`scripts/`)
**Purpose**: Development and deployment scripts
- `run_all.py` - Development launcher (builds Flutter web + starts backend)

**Running dev environment**:
```bash
# From project root
python scripts/run_all.py
```

### Flutter Applications
- `flutter_app/` - Original device configuration app
- `sssnl_app/` - Dashboard web/mobile app
- `sssnl_media_controls/` - Media controls app with device management

### Configuration
- `pi_ble_cfg/` - Raspberry Pi BLE configuration module

## Key Changes from Previous Structure

1. **Removed**: `app.py` and `app copy.py` from root directory
2. **Backend Code**: All backend code now exclusively in `backend/` directory
3. **Organized Modules**: Separated concerns into `sensors/`, `utils/`, `scripts/`
4. **Clear Separation**: Backend, utilities, sensors, and scripts are in separate directories

## Development Workflow

### Local Development (with SQLite)
```bash
# Install dependencies
pip install -r requirements.txt
pip install -r backend/requirements.txt

# Run backend
python backend/app.py

# Or run everything (backend + Flutter web builds)
python scripts/run_all.py
```

### Production Deployment (with MariaDB)
```bash
# Set database URI
export DB_URI="mysql+pymysql://user:pass@localhost/sssnl"

# Run backend
python backend/app.py

# Or use docker-compose
cd backend
docker-compose up -d
```

## API Endpoints

See `backend/docs/api.md` for complete API documentation.

Main endpoints:
- `/api/auth/*` - Authentication
- `/api/devices/*` - Device management
- `/api/user/*` - User management
- `/api/admin/*` - Admin functions
- `/dashboard/` - Dashboard web app
- `/media/` - Media controls web app

## Environment Variables

- `DB_URI` - Database connection string (defaults to SQLite)
- `FLASK_SECRET_KEY` - Session secret key
- `SSSNL_ADMIN_USER` - Default admin username
- `SSSNL_ADMIN_PASS` - Default admin password
- `FLUTTER_BIN` - Flutter executable path (for `run_all.py`)
