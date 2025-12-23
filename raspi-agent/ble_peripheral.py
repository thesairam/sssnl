#!/usr/bin/env python3
import os
import json
import time
import threading
from typing import Optional

from pydbus import SystemBus
from gi.repository import GLib

from backend_client import ensure_registered

# BLE UUIDs must match the mobile app
SERVICE_UUID = '0000ffff-0000-1000-8000-00805f9b34fb'
CREDS_CHAR_UUID = '0000fff1-0000-1000-8000-00805f9b34fb'
MAC_CHAR_UUID = '0000fff2-0000-1000-8000-00805f9b34fb'

# Minimal BlueZ GATT server using D-Bus (simplified)
# Adapted from BlueZ examples; production should add security and proper flags

BLUEZ_SERVICE_NAME = 'org.bluez'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
ADAPTER_IFACE = 'org.bluez.Adapter1'

MAIN_LOOP: Optional[GLib.MainLoop] = None


def get_adapter_path():
    bus = SystemBus()
    mngr = bus.get(BLUEZ_SERVICE_NAME, '/')
    objects = mngr.GetManagedObjects()
    for path, ifaces in objects.items():
        adapter = ifaces.get(ADAPTER_IFACE)
        if adapter is not None:
            return path
    raise RuntimeError('Bluetooth adapter not found')


class Application(object):
    def __init__(self, bus):
        self.bus = bus
        self.path = '/org/sssnl/app'
        self.services = []
        self.add_service(ProvisioningService(bus, 0))

    def get_path(self):
        return self.path

    def add_service(self, service):
        self.services.append(service)

    def get_services(self):
        return self.services


class ProvisioningService(object):
    def __init__(self, bus, index):
        self.path = f"/org/sssnl/service{index}"
        self.bus = bus
        self.uuid = SERVICE_UUID
        self.primary = True
        self.characteristics = []
        self.add_characteristic(CredentialsCharacteristic(bus, 0, self))
        self.add_characteristic(MacCharacteristic(bus, 1, self))

    def get_properties(self):
        return {
            'org.bluez.GattService1': {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Characteristics': [c.get_path() for c in self.characteristics],
            }
        }

    def get_path(self):
        return self.path

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)


class Characteristic(object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.get_path() + f"/char{index}"
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags

    def get_properties(self):
        return {
            'org.bluez.GattCharacteristic1': {
                'Service': self.service.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
            }
        }

    def get_path(self):
        return self.path


class CredentialsCharacteristic(Characteristic):
    def __init__(self, bus, index, service):
        super().__init__(bus, index, CREDS_CHAR_UUID, ['write'], service)

    def WriteValue(self, value, options):  # noqa: N802 (BlueZ method naming)
        try:
            data = bytes(value).decode('utf-8')
            payload = json.loads(data)
            ssid = (payload.get('ssid') or '').strip()
            password = (payload.get('password') or '')
            pairing_code = (payload.get('pairing_code') or '').strip()
            if not ssid:
                print('No SSID provided')
                return
            # Apply Wi-Fi configuration
            write_wifi(ssid, password)
            # Register with backend and claim if pairing code supplied
            device_id, device_token = ensure_registered(pairing_code=pairing_code or None)
            print('Registered device:', device_id)
        except Exception as e:
            print('WriteValue error:', e)


class MacCharacteristic(Characteristic):
    def __init__(self, bus, index, service):
        super().__init__(bus, index, MAC_CHAR_UUID, ['read'], service)

    def ReadValue(self, options):  # noqa: N802
        mac = get_mac()
        return list(mac.encode('utf-8'))


def write_wifi(ssid: str, password: str):
    # Very simplified approach using wpa_supplicant
    wpa_path = '/etc/wpa_supplicant/wpa_supplicant.conf'
    content = f'country=US\nctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\n\nnetwork={{\n    ssid="{ssid}"\n    psk="{password}"\n}}\n'
    try:
        with open('/tmp/wpa_supplicant.conf', 'w') as f:
            f.write(content)
        os.system('sudo mv /tmp/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant.conf')
        os.system('sudo wpa_cli -i wlan0 reconfigure || sudo systemctl restart wpa_supplicant')
    except Exception as e:
        print('Failed to write Wi-Fi config:', e)


def get_mac() -> str:
    try:
        with open('/sys/class/net/wlan0/address', 'r') as f:
            return f.read().strip()
    except Exception:
        return '00:00:00:00:00:00'


def register_gatt(app):
    bus = SystemBus()
    adapter_path = get_adapter_path()
    service_manager = bus.get(BLUEZ_SERVICE_NAME, adapter_path)
    service_manager.RegisterApplication(app.get_path(), {}, reply_handler=lambda *a: print('GATT app registered'), error_handler=lambda e: print('RegisterApplication error', e))


def advertise():
    # Advertising via bluetoothctl quick method
    os.system('bluetoothctl --timeout 1 power on')
    os.system('bluetoothctl --timeout 1 agent NoInputNoOutput')
    os.system('bluetoothctl --timeout 1 default-agent')
    os.system('bluetoothctl --timeout 1 set-alias SSSNL-Device')
    os.system('bluetoothctl advertising on')


def main():
    global MAIN_LOOP
    bus = SystemBus()
    app = Application(bus)
    register_gatt(app)
    advertise()

    MAIN_LOOP = GLib.MainLoop()
    print('BLE provisioning service running...')
    MAIN_LOOP.run()


if __name__ == '__main__':
    main()
