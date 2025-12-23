import os
import time
import json
import requests
from typing import Optional, Tuple

BACKEND_BASE = os.environ.get('BACKEND_BASE_URL', 'http://localhost:5656')
STATE_FILE = os.environ.get('SSSNL_STATE', '/var/lib/sssnl/device_state.json')


def get_mac_address() -> str:
    env_mac = os.environ.get('SSSNL_DEVICE_MAC')
    if env_mac:
        return env_mac
    try:
        with open('/sys/class/net/wlan0/address', 'r') as f:
            mac = f.read().strip()
            if mac:
                return mac
    except Exception:
        pass
    try:
        for name in os.listdir('/sys/class/net'):
            if name in ('lo',):
                continue
            try:
                with open(f'/sys/class/net/{name}/address', 'r') as f:
                    mac = f.read().strip()
                    if mac and mac != '00:00:00:00:00:00':
                        return mac
            except Exception:
                continue
    except Exception:
        pass
    return '00:00:00:00:00:00'


def register_device(mac: str, name: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    try:
        r = requests.post(f"{BACKEND_BASE}/api/devices/register", json={'mac': mac, 'name': name}, timeout=10)
        if r.ok:
            data = r.json()
            return data.get('device_id'), data.get('device_token')
    except Exception:
        pass
    return None, None


def claim_device(device_id: str, device_token: str, pairing_code: str) -> bool:
    try:
        r = requests.post(f"{BACKEND_BASE}/api/devices/{device_id}/claim", json={'device_token': device_token, 'pairing_code': pairing_code}, timeout=10)
        return r.ok
    except Exception:
        return False


def heartbeat(device_id: str, device_token: str) -> bool:
    try:
        r = requests.post(f"{BACKEND_BASE}/api/devices/{device_id}/heartbeat", json={'device_token': device_token}, timeout=10)
        return r.ok
    except Exception:
        return False


def load_state() -> dict:
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)


def ensure_registered(pairing_code: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    state = load_state()
    mac = get_mac_address()
    device_id = state.get('device_id')
    device_token = state.get('device_token')
    if not device_id or not device_token:
        device_id, device_token = register_device(mac)
        if device_id and device_token:
            state['device_id'] = device_id
            state['device_token'] = device_token
            save_state(state)
    if pairing_code and device_id and device_token:
        if claim_device(device_id, device_token, pairing_code):
            state['claimed'] = True
            save_state(state)
    return device_id, device_token


def run_heartbeat_loop():
    state = load_state()
    device_id = state.get('device_id')
    device_token = state.get('device_token')
    if not device_id or not device_token:
        return
    while True:
        heartbeat(device_id, device_token)
        time.sleep(20)


if __name__ == '__main__':
    did, tok = ensure_registered()
    if did and tok:
        print('Registered device:', did)
        run_heartbeat_loop()
    else:
        print('Failed to register device')
