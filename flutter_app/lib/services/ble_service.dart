import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

class BleService {
  // Service and Characteristic UUIDs
  static const String wifiConfigServiceUuid =
      '12345678-1234-5678-1234-56789abcdef0';
  static const String wifiNetworksCharUuid =
      '12345678-1234-5678-1234-56789abcdef1';
  static const String wifiSsidCharUuid = '12345678-1234-5678-1234-56789abcdef2';
  static const String wifiPasswordCharUuid =
      '12345678-1234-5678-1234-56789abcdef3';
  static const String wifiStatusCharUuid =
      '12345678-1234-5678-1234-56789abcdef4';

  BluetoothDevice? _connectedDevice;
  BluetoothCharacteristic? _networksCharacteristic;
  BluetoothCharacteristic? _ssidCharacteristic;
  BluetoothCharacteristic? _passwordCharacteristic;
  BluetoothCharacteristic? _statusCharacteristic;

  final StreamController<String> _statusController =
      StreamController<String>.broadcast();
  Stream<String> get statusStream => _statusController.stream;

  final StreamController<bool> _connectionController =
      StreamController<bool>.broadcast();
  Stream<bool> get connectionStream => _connectionController.stream;

  bool get isConnected => _connectedDevice != null;

  // Start scanning for BLE devices
  Stream<List<ScanResult>> startScan() {
    FlutterBluePlus.startScan(
      timeout: const Duration(seconds: 15),
      androidUsesFineLocation: true,
    );

    return FlutterBluePlus.scanResults;
  }

  // Stop scanning
  Future<void> stopScan() async {
    await FlutterBluePlus.stopScan();
  }

  // Connect to a device
  Future<bool> connect(BluetoothDevice device) async {
    try {
      await device.connect(timeout: const Duration(seconds: 15));
      _connectedDevice = device;
      _connectionController.add(true);

      // Listen to connection state
      device.connectionState.listen((state) {
        if (state == BluetoothConnectionState.disconnected) {
          _handleDisconnection();
        }
      });

      // Discover services
      await _discoverServices(device);

      return true;
    } catch (e) {
      debugPrint('Connection error: $e');
      _connectionController.add(false);
      return false;
    }
  }

  // Discover services and characteristics
  Future<void> _discoverServices(BluetoothDevice device) async {
    try {
      List<BluetoothService> services = await device.discoverServices();

      for (var service in services) {
        if (service.uuid.toString().toLowerCase() ==
            wifiConfigServiceUuid.toLowerCase()) {
          debugPrint('Found WiFi Config Service');

          for (var characteristic in service.characteristics) {
            String charUuid = characteristic.uuid.toString().toLowerCase();

            if (charUuid == wifiNetworksCharUuid.toLowerCase()) {
              _networksCharacteristic = characteristic;
              debugPrint('Found Networks characteristic');
            } else if (charUuid == wifiSsidCharUuid.toLowerCase()) {
              _ssidCharacteristic = characteristic;
              debugPrint('Found SSID characteristic');
            } else if (charUuid == wifiPasswordCharUuid.toLowerCase()) {
              _passwordCharacteristic = characteristic;
              debugPrint('Found Password characteristic');
            } else if (charUuid == wifiStatusCharUuid.toLowerCase()) {
              _statusCharacteristic = characteristic;
              debugPrint('Found Status characteristic');

              // Enable notifications for status updates
              if (characteristic.properties.notify) {
                await characteristic.setNotifyValue(true);
                characteristic.lastValueStream.listen((value) {
                  if (value.isNotEmpty) {
                    String status = String.fromCharCodes(value);
                    debugPrint('Status update: $status');
                    _statusController.add(status);
                  }
                });
              }
            }
          }
        }
      }
    } catch (e) {
      debugPrint('Service discovery error: $e');
    }
  }

  // Send WiFi credentials
  Future<bool> sendWifiCredentials(String ssid, String password) async {
    if (_ssidCharacteristic == null || _passwordCharacteristic == null) {
      debugPrint('Characteristics not found');
      return false;
    }

    try {
      // Send SSID
      await _ssidCharacteristic!.write(ssid.codeUnits, withoutResponse: false);
      debugPrint('SSID sent successfully');

      // Wait a bit before sending password
      await Future.delayed(const Duration(milliseconds: 500));

      // Send Password
      await _passwordCharacteristic!.write(
        password.codeUnits,
        withoutResponse: false,
      );
      debugPrint('Password sent successfully');

      // Read status after a delay
      await Future.delayed(const Duration(seconds: 1));
      await readStatus();

      return true;
    } catch (e) {
      debugPrint('Error sending credentials: $e');
      return false;
    }
  }

  // Read available WiFi networks
  Future<List<Map<String, dynamic>>> readNetworks() async {
    if (_networksCharacteristic == null) {
      throw Exception('Networks characteristic not found');
    }

    try {
      final value = await _networksCharacteristic!.read();
      if (value.isEmpty) {
        return [];
      }

      final jsonString = String.fromCharCodes(value);
      debugPrint('Received networks: $jsonString');

      // Parse JSON
      final List<dynamic> networksJson =
          (jsonString.isNotEmpty) ? (jsonDecode(jsonString) as List) : [];

      return networksJson
          .map((network) => {
                'ssid': network['ssid'] ?? '',
                'signal': network['signal'] ?? '0',
                'security': network['security'] ?? 'Unknown',
              })
          .toList();
    } catch (e) {
      debugPrint('Error reading networks: $e');
      throw Exception('Failed to read networks: $e');
    }
  }

  // Read WiFi connection status
  Future<String?> readStatus() async {
    if (_statusCharacteristic == null) {
      debugPrint('Status characteristic not found');
      return null;
    }

    try {
      List<int> value = await _statusCharacteristic!.read();
      if (value.isNotEmpty) {
        String status = String.fromCharCodes(value);
        _statusController.add(status);
        return status;
      }
    } catch (e) {
      debugPrint('Error reading status: $e');
    }
    return null;
  }

  // Disconnect from device
  Future<void> disconnect() async {
    if (_connectedDevice != null) {
      await _connectedDevice!.disconnect();
      _handleDisconnection();
    }
  }

  // Handle disconnection
  void _handleDisconnection() {
    _connectedDevice = null;
    _ssidCharacteristic = null;
    _passwordCharacteristic = null;
    _statusCharacteristic = null;
    _connectionController.add(false);
    debugPrint('Disconnected from device');
  }

  // Check if Bluetooth is available
  Future<bool> isBluetoothAvailable() async {
    try {
      return await FlutterBluePlus.isAvailable;
    } catch (e) {
      return false;
    }
  }

  // Check if Bluetooth is on
  Stream<BluetoothAdapterState> get adapterState =>
      FlutterBluePlus.adapterState;

  // Dispose streams
  void dispose() {
    _statusController.close();
    _connectionController.close();
  }
}
