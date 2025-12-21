#!/usr/bin/env python3
"""
BLE WiFi Configuration Server for Raspberry Pi

This script creates a BLE peripheral that:
1. Advertises itself as "RaspberryPi-WiFi"
2. Provides a GATT service for receiving WiFi credentials
3. Configures the WiFi connection on the Raspberry Pi

Requirements:
    - sudo apt-get install python3-dbus
    - sudo systemctl enable bluetooth
    - sudo systemctl start bluetooth

Usage:
    sudo python3 config.py
"""

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib
import subprocess
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# BLE Constants
BLUEZ_SERVICE_NAME = 'org.bluez'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'

GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'
GATT_DESC_IFACE = 'org.bluez.GattDescriptor1'

LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
LE_ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1'

# UUIDs - Custom service and characteristics
WIFI_CONFIG_SERVICE_UUID = '12345678-1234-5678-1234-56789abcdef0'
WIFI_NETWORKS_CHAR_UUID = '12345678-1234-5678-1234-56789abcdef1'
WIFI_SSID_CHAR_UUID = '12345678-1234-5678-1234-56789abcdef2'
WIFI_PASSWORD_CHAR_UUID = '12345678-1234-5678-1234-56789abcdef3'
WIFI_STATUS_CHAR_UUID = '12345678-1234-5678-1234-56789abcdef4'


class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'


class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'


class NotPermittedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotPermitted'


class InvalidValueLengthException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.InvalidValueLength'


class FailedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.Failed'


class Advertisement(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/advertisement'

    def __init__(self, bus, index, advertising_type):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = advertising_type
        self.service_uuids = None
        self.manufacturer_data = None
        self.solicit_uuids = None
        self.service_data = None
        self.local_name = 'RaspberryPi-WiFi'
        self.include_tx_power = False
        self.data = None
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        properties = dict()
        properties['Type'] = self.ad_type
        if self.service_uuids is not None:
            properties['ServiceUUIDs'] = dbus.Array(self.service_uuids, signature='s')
        if self.solicit_uuids is not None:
            properties['SolicitUUIDs'] = dbus.Array(self.solicit_uuids, signature='s')
        if self.manufacturer_data is not None:
            properties['ManufacturerData'] = dbus.Dictionary(self.manufacturer_data, signature='qv')
        if self.service_data is not None:
            properties['ServiceData'] = dbus.Dictionary(self.service_data, signature='sv')
        if self.local_name is not None:
            properties['LocalName'] = dbus.String(self.local_name)
        if self.include_tx_power:
            properties['IncludeTxPower'] = dbus.Boolean(self.include_tx_power)
        if self.data is not None:
            properties['Data'] = dbus.Dictionary(self.data, signature='yv')
        return {LE_ADVERTISEMENT_IFACE: properties}

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service_uuid(self, uuid):
        if not self.service_uuids:
            self.service_uuids = []
        self.service_uuids.append(uuid)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        logger.info('GetAll')
        if interface != LE_ADVERTISEMENT_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature='', out_signature='')
    def Release(self):
        logger.info('%s: Released!', self.path)


class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        logger.info('GetManagedObjects')
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            chrcs = service.get_characteristics()
            for chrc in chrcs:
                response[chrc.get_path()] = chrc.get_properties()
                descs = chrc.get_descriptors()
                for desc in descs:
                    response[desc.get_path()] = desc.get_properties()
        return response


class Service(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/service'

    def __init__(self, bus, index, uuid, primary):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Characteristics': dbus.Array(
                    self.get_characteristic_paths(),
                    signature='o')
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    def get_characteristic_paths(self):
        result = []
        for chrc in self.characteristics:
            result.append(chrc.get_path())
        return result

    def get_characteristics(self):
        return self.characteristics

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_SERVICE_IFACE]


class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        self.descriptors = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                'Service': self.service.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
                'Descriptors': dbus.Array(
                    self.get_descriptor_paths(),
                    signature='o')
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_descriptor(self, descriptor):
        self.descriptors.append(descriptor)

    def get_descriptor_paths(self):
        result = []
        for desc in self.descriptors:
            result.append(desc.get_path())
        return result

    def get_descriptors(self):
        return self.descriptors

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        logger.warning('Default ReadValue called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        logger.warning('Default WriteValue called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        logger.warning('Default StartNotify called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        logger.warning('Default StopNotify called, returning error')
        raise NotSupportedException()

    @dbus.service.signal(DBUS_PROP_IFACE, signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass


class Descriptor(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, characteristic):
        self.path = characteristic.path + '/desc' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.chrc = characteristic
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_DESC_IFACE: {
                'Characteristic': self.chrc.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_DESC_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_DESC_IFACE]

    @dbus.service.method(GATT_DESC_IFACE, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        logger.warning('Default ReadValue called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_DESC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        logger.warning('Default WriteValue called, returning error')
        raise NotSupportedException()


class WiFiNetworksCharacteristic(Characteristic):
    def __init__(self, bus, index, service, wifi_manager):
        Characteristic.__init__(
            self, bus, index,
            WIFI_NETWORKS_CHAR_UUID,
            ['read'],
            service)
        self.wifi_manager = wifi_manager
        self.value = []

    def ReadValue(self, options):
        logger.info('='*50)
        logger.info('📡 WiFi Networks Scan Requested')
        logger.info('='*50)
        networks = self.wifi_manager.scan_networks()
        # Send as JSON array
        networks_json = json.dumps(networks)
        logger.info(f'   Found {len(networks)} networks')
        for net in networks[:5]:  # Show first 5
            logger.info(f'   - {net["ssid"]} (Signal: {net["signal"]}%)')
        if len(networks) > 5:
            logger.info(f'   ... and {len(networks) - 5} more')
        logger.info('='*50)
        value = [dbus.Byte(c.encode()) for c in networks_json]
        return value


class WiFiSSIDCharacteristic(Characteristic):
    def __init__(self, bus, index, service, wifi_manager):
        Characteristic.__init__(
            self, bus, index,
            WIFI_SSID_CHAR_UUID,
            ['write'],
            service)
        self.wifi_manager = wifi_manager
        self.value = []

    def WriteValue(self, value, options):
        ssid = ''.join([chr(byte) for byte in value])
        logger.info('='*50)
        logger.info(f'📡 SSID RECEIVED')
        logger.info(f'   SSID: {ssid}')
        logger.info(f'   Length: {len(ssid)} characters')
        logger.info('='*50)
        self.wifi_manager.set_ssid(ssid)
        self.value = value


class WiFiPasswordCharacteristic(Characteristic):
    def __init__(self, bus, index, service, wifi_manager):
        Characteristic.__init__(
            self, bus, index,
            WIFI_PASSWORD_CHAR_UUID,
            ['write'],
            service)
        self.wifi_manager = wifi_manager
        self.value = []

    def WriteValue(self, value, options):
        password = ''.join([chr(byte) for byte in value])
        logger.info('='*50)
        logger.info(f'🔑 PASSWORD RECEIVED')
        logger.info(f'   Password: {"*" * len(password)}')
        logger.info(f'   Length: {len(password)} characters')
        logger.info('='*50)
        self.wifi_manager.set_password(password)
        self.value = value


class WiFiStatusCharacteristic(Characteristic):
    def __init__(self, bus, index, service, wifi_manager):
        Characteristic.__init__(
            self, bus, index,
            WIFI_STATUS_CHAR_UUID,
            ['read', 'notify'],
            service)
        self.wifi_manager = wifi_manager
        self.notifying = False

    def ReadValue(self, options):
        status = self.wifi_manager.get_status()
        logger.info(f'Status read: {status}')
        value = [dbus.Byte(c.encode()) for c in status]
        return value

    def StartNotify(self):
        if self.notifying:
            logger.info('Already notifying, nothing to do')
            return
        self.notifying = True
        logger.info('Notifications enabled')

    def StopNotify(self):
        if not self.notifying:
            logger.info('Not notifying, nothing to do')
            return
        self.notifying = False
        logger.info('Notifications disabled')

    def notify_status(self, status):
        if not self.notifying:
            return
        value = [dbus.Byte(c.encode()) for c in status]
        self.PropertiesChanged(
            GATT_CHRC_IFACE,
            {'Value': value},
            []
        )


class WiFiConfigService(Service):
    def __init__(self, bus, index, wifi_manager):
        Service.__init__(self, bus, index, WIFI_CONFIG_SERVICE_UUID, True)
        self.add_characteristic(WiFiNetworksCharacteristic(bus, 0, self, wifi_manager))
        self.add_characteristic(WiFiSSIDCharacteristic(bus, 1, self, wifi_manager))
        self.add_characteristic(WiFiPasswordCharacteristic(bus, 2, self, wifi_manager))
        self.add_characteristic(WiFiStatusCharacteristic(bus, 3, self, wifi_manager))


class WiFiManager:
    def __init__(self):
        self.ssid = None
        self.password = None
        self.status = "Ready"
        self.available_networks = []

    def scan_networks(self):
        """Scan for available WiFi networks"""
        logger.info('🔍 Scanning for WiFi networks...')
        try:
            # Try using nmcli to scan networks
            scan_cmd = ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'device', 'wifi', 'list']
            result = subprocess.run(scan_cmd, capture_output=True, text=True, timeout=10)

            networks = []
            seen_ssids = set()

            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    parts = line.split(':')
                    if len(parts) >= 3:
                        ssid = parts[0].strip()
                        signal = parts[1].strip()
                        security = parts[2].strip()

                        # Skip empty SSIDs and duplicates
                        if ssid and ssid not in seen_ssids:
                            seen_ssids.add(ssid)
                            networks.append({
                                'ssid': ssid,
                                'signal': signal,
                                'security': 'Open' if not security else 'Secured'
                            })

                # Sort by signal strength
                networks.sort(key=lambda x: int(x['signal']) if x['signal'].isdigit() else 0, reverse=True)
                self.available_networks = networks
                logger.info(f'✅ Found {len(networks)} WiFi networks')
                return networks
            else:
                logger.error(f'Failed to scan networks: {result.stderr}')
                return []

        except FileNotFoundError:
            logger.error('nmcli not found, trying alternative method...')
            # Alternative method using iwlist
            try:
                scan_cmd = ['sudo', 'iwlist', 'wlan0', 'scan']
                result = subprocess.run(scan_cmd, capture_output=True, text=True, timeout=10)
                networks = self._parse_iwlist_output(result.stdout)
                self.available_networks = networks
                return networks
            except Exception as e:
                logger.error(f'Alternative scan failed: {e}')
                return []
        except Exception as e:
            logger.error(f'Network scan error: {e}')
            return []

    def _parse_iwlist_output(self, output):
        """Parse iwlist scan output"""
        networks = []
        current_network = {}

        for line in output.split('\n'):
            line = line.strip()
            if 'ESSID:' in line:
                ssid = line.split('ESSID:')[1].strip('"')
                if ssid:
                    current_network['ssid'] = ssid
            elif 'Quality=' in line:
                # Extract signal quality
                quality = line.split('Quality=')[1].split()[0]
                if '/' in quality:
                    current, maximum = quality.split('/')
                    signal = int((int(current) / int(maximum)) * 100)
                    current_network['signal'] = str(signal)
            elif 'Encryption key:' in line:
                if 'off' in line.lower():
                    current_network['security'] = 'Open'
                else:
                    current_network['security'] = 'Secured'

                if 'ssid' in current_network and current_network not in networks:
                    networks.append(current_network.copy())
                    current_network = {}

        return networks

    def set_ssid(self, ssid):
        logger.info(f'📝 Setting SSID: {ssid}')
        self.ssid = ssid
        if self.password is not None:
            logger.info('✅ Both SSID and Password available, starting WiFi configuration...')
            self.configure_wifi()
        else:
            logger.info('⏳ Waiting for password...')

    def set_password(self, password):
        logger.info(f'🔐 Setting password (length: {len(password)})')
        self.password = password
        if self.ssid is not None:
            logger.info('✅ Both SSID and Password available, starting WiFi configuration...')
            self.configure_wifi()
        else:
            logger.info('⏳ Waiting for SSID...')

    def configure_wifi(self):
        """Configure WiFi connection using nmcli or wpa_supplicant"""
        logger.info('\n' + '='*60)
        logger.info('🚀 STARTING WIFI CONFIGURATION')
        logger.info('='*60)
        logger.info(f'   Target Network: {self.ssid}')
        logger.info(f'   Password Length: {len(self.password)} characters')
        logger.info('='*60)
        self.status = "Connecting..."

        try:
            # Try using nmcli (NetworkManager) - available on most modern Pi OS versions
            logger.info('📶 Attempting connection using NetworkManager (nmcli)...')
            cmd = [
                'nmcli', 'device', 'wifi', 'connect',
                self.ssid,
                'password', self.password
            ]
            logger.info(f'   Command: nmcli device wifi connect {self.ssid} password ********')
            logger.info('   Executing... (timeout: 30 seconds)')

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            logger.info(f'   Return code: {result.returncode}')
            if result.stdout:
                logger.info(f'   stdout: {result.stdout.strip()}')
            if result.stderr:
                logger.info(f'   stderr: {result.stderr.strip()}')

            if result.returncode == 0:
                self.status = "Connected"
                logger.info('\n' + '='*60)
                logger.info('✅ SUCCESS! WiFi Connected')
                logger.info('='*60)
                logger.info(f'   Network: {self.ssid}')
                logger.info(f'   Status: {self.status}')
                logger.info('='*60 + '\n')
            else:
                self.status = f"Failed: {result.stderr}"
                logger.error('\n' + '='*60)
                logger.error('❌ FAILED to connect to WiFi')
                logger.error('='*60)
                logger.error(f'   Network: {self.ssid}')
                logger.error(f'   Error: {result.stderr}')
                logger.error('='*60 + '\n')
            # If nmcli is not available, try wpa_supplicant method
            logger.warning('⚠️  nmcli not found, trying wpa_supplicant method...')
            try:
                self.configure_with_wpa_supplicant()
            except Exception as e:
                self.status = f"Failed: {str(e)}"
                logger.error('='*60)
                logger.error('❌ WPA supplicant configuration FAILED')
                logger.error(f'   Error: {e}')
                logger.error('='*60)

        except subprocess.TimeoutExpired:
            self.status = "Failed: Timeout"
            logger.error('='*60)
            logger.error('⏱️  CONNECTION TIMEOUT')
            logger.error('   The connection attempt took too long (>30s)')
            logger.error('='*60)

        except Exception as e:
            self.status = f"Failed: {str(e)}"
            logger.error('='*60)
            logger.error('❌ UNEXPECTED ERROR')
            logger.error(f'   Error: {e}')
            logger.error(f'   Type: {type(e).__name__}')
            logger.error('='*60)
        """Alternative method using wpa_supplicant configuration"""
        logger.info('📝 Configuring using wpa_supplicant...')
        config = f"""
network={{
    ssid="{self.ssid}"
    psk="{self.password}"
    key_mgmt=WPA-PSK
}}
"""
        logger.info('   Writing configuration to /tmp/wpa_supplicant.conf')
        # Write to wpa_supplicant config
        with open('/tmp/wpa_supplicant.conf', 'w') as f:
            f.write(config)

        logger.info('   Copying to /etc/wpa_supplicant/wpa_supplicant.conf')
        # Copy to the system location (requires sudo)
        subprocess.run(['sudo', 'cp', '/tmp/wpa_supplicant.conf',
                       '/etc/wpa_supplicant/wpa_supplicant.conf'], check=True)

        logger.info('   Reconfiguring wlan0 interface...')
        # Restart the wireless interface
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'], check=True)

        self.status = "Connected"
        logger.info('='*60)
        logger.info('✅ SUCCESS! WiFi configured via wpa_supplicant')
        logger.info('='*60)
        return self.status


def find_adapter(bus):
    """Find the first available Bluetooth adapter"""
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                                DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()

    for o, props in objects.items():
        if GATT_MANAGER_IFACE in props.keys():
            return o

    return None


def register_app_cb():
    logger.info('='*60)
    logger.info('✅ GATT application registered successfully')
    logger.info('='*60)


def register_app_error_cb(error):
    logger.error('='*60)
    logger.error('❌ Failed to register GATT application')
    logger.error(f'   Error: {error}')
    logger.error('='*60)
    mainloop.quit()


def register_ad_cb():
    logger.info('='*60)
    logger.info('✅ BLE Advertisement registered successfully')
    logger.info('   Device is now discoverable as "RaspberryPi-WiFi"')
    logger.info('='*60)


def register_ad_error_cb(error):
    logger.error('='*60)
    logger.error('❌ Failed to register BLE advertisement')
    logger.error(f'   Error: {error}')
    logger.error('='*60)
    mainloop.quit()


def main():
    global mainloop

    logger.info('\n' + '='*60)
    logger.info('🎉 BLE WiFi Configuration Server Starting')
    logger.info('='*60)

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    bus = dbus.SystemBus()
    logger.info('✅ Connected to D-Bus system bus')

    adapter = find_adapter(bus)
    if not adapter:
        logger.error('='*60)
        logger.error('❌ BLE adapter not found')
        logger.error('   Please check if Bluetooth is enabled')
        logger.error('   Run: sudo systemctl status bluetooth')
        logger.error('='*60)
        return

    logger.info(f'✅ Using Bluetooth adapter: {adapter}')

    # Create WiFi manager
    logger.info('📶 Initializing WiFi Manager...')
    wifi_manager = WiFiManager()
    logger.info('✅ WiFi Manager initialized')

    # Create and register GATT application
    logger.info('\n📝 Registering GATT Application...')
    app = Application(bus)
    app.add_service(WiFiConfigService(bus, 0, wifi_manager))
    logger.info(f'   Service UUID: {WIFI_CONFIG_SERVICE_UUID}')
    logger.info(f'   SSID Characteristic: {WIFI_SSID_CHAR_UUID}')
    logger.info(f'   Password Characteristic: {WIFI_PASSWORD_CHAR_UUID}')
    logger.info(f'   Status Characteristic: {WIFI_STATUS_CHAR_UUID}')

    service_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter),
        GATT_MANAGER_IFACE)

    service_manager.RegisterApplication(app.get_path(), {},
                                       reply_handler=register_app_cb,
                                       error_handler=register_app_error_cb)

    # Create and register advertisement
    logger.info('\n📡 Registering BLE Advertisement...')
    ad_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, adapter),
                                LE_ADVERTISING_MANAGER_IFACE)

    advertisement = Advertisement(bus, 0, 'peripheral')
    advertisement.add_service_uuid(WIFI_CONFIG_SERVICE_UUID)
    logger.info(f'   Advertisement Type: peripheral')
    logger.info(f'   Device Name: RaspberryPi-WiFi')
    logger.info(f'   Service UUID: {WIFI_CONFIG_SERVICE_UUID}')

    ad_manager.RegisterAdvertisement(advertisement.get_path(), {},
                                    reply_handler=register_ad_cb,
                                    error_handler=register_ad_error_cb)

    logger.info('\n' + '='*60)
    logger.info('🚀 BLE WiFi Configuration Server is RUNNING')
    logger.info('='*60)
    logger.info('   Device Name: RaspberryPi-WiFi')
    logger.info(f'   Service UUID: {WIFI_CONFIG_SERVICE_UUID}')
    logger.info('   Status: Waiting for connections...')
    logger.info('='*60)
    logger.info('\n📱 Open your mobile app to scan and connect')
    logger.info('   1. Scan for BLE devices')
    logger.info('   2. Connect to "RaspberryPi-WiFi"')
    logger.info('   3. Send WiFi credentials')
    logger.info('\n' + '='*60 + '\n')

    mainloop = GLib.MainLoop()
    try:
        mainloop.run()
    except KeyboardInterrupt:
        logger.info('\n' + '='*60)
        logger.info('🛑 Shutting down BLE server...')
        logger.info('='*60)
        ad_manager.UnregisterAdvertisement(advertisement.get_path())
        logger.info('✅ Advertisement unregistered')
        dbus.service.Object.remove_from_connection(advertisement)
        logger.info('✅ Server stopped gracefully')
        logger.info('='*60 + '\n')


if __name__ == '__main__':
    main()
