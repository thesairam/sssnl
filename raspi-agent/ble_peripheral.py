#!/usr/bin/env python3
import os
import json
import time
import threading
from typing import Optional, Any, Dict

try:
    from pydbus import SystemBus
    from gi.repository import GLib
except Exception as import_err:
    print("Missing system packages for BLE provisioning. On Raspberry Pi run:")
    print("  sudo apt update && sudo apt install -y python3-gi python3-dbus bluetooth bluez bluez-tools rfkill")
    print("If using a virtualenv, recreate it with system packages so gi/dbus are visible:")
    print("  rm -rf .venv && python3 -m venv --system-site-packages .venv && source .venv/bin/activate")
    print("Run with the venv interpreter explicitly (as root):")
    print("  sudo -E $(pwd)/.venv/bin/python ble_peripheral.py")
    print("If you still see issues, also install: libglib2.0-dev libdbus-1-dev libbluetooth-dev")
    raise

from backend_client import ensure_registered, run_heartbeat_loop

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
HEARTBEAT_THREAD: Optional[threading.Thread] = None


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
    """
    Root object for the GATT application. BlueZ will introspect children under
    this path to discover services and characteristics. We must register each
    DBus object with pydbus including its introspection XML.
    """
    __dbus_xml__ = """
        <node>
            <interface name='org.freedesktop.DBus.ObjectManager'>
                <method name='GetManagedObjects'>
                    <arg type='a{oa{sa{sv}}}' name='objects' direction='out'/>
                </method>
            </interface>
        </node>
        """

    def __init__(self, bus: SystemBus):
        self.bus = bus
        self.path = '/org/sssnl/app'
        self.services = []
        svc = ProvisioningService(self.bus, 0)
        self.add_service(svc)

        # Register service and characteristics on DBus
        self.bus.register_object(svc.get_path(), svc, None)
        for ch in svc.characteristics:
                        self.bus.register_object(ch.get_path(), ch, None)

    def get_path(self) -> str:
        return self.path

    def add_service(self, service: 'ProvisioningService') -> None:
        self.services.append(service)

    def get_services(self):
        return self.services

    # org.freedesktop.DBus.ObjectManager
    def GetManagedObjects(self) -> Dict[str, Dict[str, Dict[str, Any]]]:  # noqa: N802
        """Return hierarchy for BlueZ: paths -> {iface -> props}.
        Includes services and characteristics registered under this app path.
        """
        result: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for svc in self.services:
            result[svc.get_path()] = {
                'org.bluez.GattService1': svc.GetAll('org.bluez.GattService1')
            }
            for ch in svc.characteristics:
                result[ch.get_path()] = {
                    'org.bluez.GattCharacteristic1': ch.GetAll('org.bluez.GattCharacteristic1')
                }
        return result


class ProvisioningService(object):
    """
    org.bluez.GattService1 implementation via pydbus.
    Exposes the provisioning service and two characteristics under it.
    """
    __dbus_xml__ = """
    <node>
      <interface name='org.bluez.GattService1'>
        <property name='UUID' type='s' access='read'/>
        <property name='Primary' type='b' access='read'/>
        <property name='Includes' type='ao' access='read'/>
      </interface>
      <interface name='org.freedesktop.DBus.Properties'>
        <method name='Get'>
          <arg type='s' name='interface' direction='in' />
          <arg type='s' name='prop' direction='in' />
          <arg type='v' name='value' direction='out' />
        </method>
        <method name='GetAll'>
          <arg type='s' name='interface' direction='in'/>
          <arg type='a{sv}' name='props' direction='out'/>
        </method>
        <method name='Set'>
          <arg type='s' name='interface' direction='in'/>
          <arg type='s' name='prop' direction='in'/>
          <arg type='v' name='value' direction='in'/>
        </method>
      </interface>
    </node>
    """

    def __init__(self, bus: SystemBus, index: int):
        self.path = f"/org/sssnl/service{index}"
        self.bus = bus
        self.uuid = SERVICE_UUID
        self.primary = True
        self.includes: list[str] = []
        self.characteristics: list[Characteristic] = []
        self.add_characteristic(CredentialsCharacteristic(bus, 0, self))
        self.add_characteristic(MacCharacteristic(bus, 1, self))

    # org.freedesktop.DBus.Properties
    def Get(self, interface: str, prop: str) -> Any:  # noqa: N802
        return self.GetAll(interface).get(prop)

    def GetAll(self, interface: str) -> Dict[str, Any]:  # noqa: N802
        if interface == 'org.bluez.GattService1':
            return {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Includes': self.includes,
            }
        return {}

    def Set(self, interface: str, prop: str, value: Any) -> None:  # noqa: N802
        # No writable properties
        pass

    def get_path(self) -> str:
        return self.path

    def add_characteristic(self, characteristic: 'Characteristic') -> None:
        self.characteristics.append(characteristic)


class Characteristic(object):
        """
        Base for org.bluez.GattCharacteristic1. Subclasses implement ReadValue/WriteValue.
        """
        __dbus_xml__ = """
        <node>
            <interface name='org.bluez.GattCharacteristic1'>
                <method name='ReadValue'>
                    <arg type='a{sv}' name='options' direction='in'/>
                    <arg type='ay' name='value' direction='out'/>
                </method>
                <method name='WriteValue'>
                    <arg type='ay' name='value' direction='in'/>
                    <arg type='a{sv}' name='options' direction='in'/>
                </method>
                <property name='Service' type='o' access='read'/>
                <property name='UUID' type='s' access='read'/>
                <property name='Flags' type='as' access='read'/>
            </interface>
            <interface name='org.freedesktop.DBus.Properties'>
                <method name='Get'>
                    <arg type='s' name='interface' direction='in' />
                    <arg type='s' name='prop' direction='in' />
                    <arg type='v' name='value' direction='out' />
                </method>
                <method name='GetAll'>
                    <arg type='s' name='interface' direction='in'/>
                    <arg type='a{sv}' name='props' direction='out'/>
                </method>
                <method name='Set'>
                    <arg type='s' name='interface' direction='in'/>
                    <arg type='s' name='prop' direction='in'/>
                    <arg type='v' name='value' direction='in'/>
                </method>
            </interface>
        </node>
        """

        def __init__(self, bus: SystemBus, index: int, uuid: str, flags: list[str], service: ProvisioningService):
                self.path = service.get_path() + f"/char{index}"
                self.bus = bus
                self.uuid = uuid
                self.service = service
                self.flags = flags

        # org.freedesktop.DBus.Properties
        def Get(self, interface: str, prop: str) -> Any:  # noqa: N802
                return self.GetAll(interface).get(prop)

        def GetAll(self, interface: str) -> Dict[str, Any]:  # noqa: N802
                if interface == 'org.bluez.GattCharacteristic1':
                        return {
                                'Service': self.service.get_path(),
                                'UUID': self.uuid,
                                'Flags': self.flags,
                        }
                return {}

        def Set(self, interface: str, prop: str, value: Any) -> None:  # noqa: N802
                # No writable properties
                pass

        def get_path(self) -> str:
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
            if device_id:
                print('Registered device:', device_id)
                # Start heartbeat loop once device is registered
                global HEARTBEAT_THREAD
                if HEARTBEAT_THREAD is None or not HEARTBEAT_THREAD.is_alive():
                    HEARTBEAT_THREAD = threading.Thread(target=run_heartbeat_loop, daemon=True)
                    HEARTBEAT_THREAD.start()
        except Exception as e:
            print('WriteValue error:', e)


class MacCharacteristic(Characteristic):
    def __init__(self, bus, index, service):
        super().__init__(bus, index, MAC_CHAR_UUID, ['read'], service)

    def ReadValue(self, options):  # noqa: N802
        mac = get_mac()
        return list(mac.encode('utf-8'))


def write_wifi(ssid: str, password: str):
    if os.environ.get('SSSNL_DESKTOP_MODE') == '1' or os.environ.get('SSSNL_SKIP_WIFI') == '1':
        print('Desktop mode: skipping Wi-Fi reconfiguration')
        return
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
    env_mac = os.environ.get('SSSNL_DEVICE_MAC')
    if env_mac:
        return env_mac
    # Prefer wlan0, else pick first non-loopback interface
    candidates = []
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
                        candidates.append(mac)
            except Exception:
                continue
        if candidates:
            return candidates[0]
    except Exception:
        pass
    return '00:00:00:00:00:00'


def register_gatt(app: Application):
    bus = SystemBus()
    adapter_path = get_adapter_path()
    # Register the application path where our service/characteristic objects are exported
    gatt_manager = bus.get(BLUEZ_SERVICE_NAME, adapter_path)
    try:
        gatt_manager.RegisterApplication(app.get_path(), {})
        print('GATT application registered')
    except Exception as e:
        print('RegisterApplication error:', e)


def advertise():
    # Advertising via bluetoothctl quick method; ensure LE advertising is enabled and connectable
    cmds = [
        'bluetoothctl --timeout 2 power on',
        'bluetoothctl --timeout 2 agent NoInputNoOutput',
        'bluetoothctl --timeout 2 default-agent',
        'bluetoothctl --timeout 2 set-alias SSSNL-Device',
    ]
    for c in cmds:
        os.system(c)
    # Prefer LE advertising; fallback to legacy advertising on older BlueZ
    rc = os.system('bluetoothctl --timeout 2 advertise yes')
    if rc != 0:
        os.system('bluetoothctl --timeout 2 advertising on')


def main():
    global MAIN_LOOP
    if os.environ.get('SSSNL_SIMULATE') == '1':
        print('Simulation mode: skipping BLE. Registering and starting heartbeat...')
        device_id, device_token = ensure_registered(pairing_code=os.environ.get('SSSNL_PAIRING_CODE'))
        if device_id:
            t = threading.Thread(target=run_heartbeat_loop, daemon=True)
            t.start()
            print('Heartbeat started for', device_id)
            while True:
                time.sleep(60)
        else:
            print('Failed to register in simulation mode')
            return
    bus = SystemBus()
    app = Application(bus)
    register_gatt(app)
    advertise()

    MAIN_LOOP = GLib.MainLoop()
    print('BLE provisioning service running...')
    MAIN_LOOP.run()


if __name__ == '__main__':
    main()
