import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:permission_handler/permission_handler.dart';
import '../services/ble_service.dart';
import '../services/device_service.dart';
import '../models/ble_device_model.dart';
import 'network_selection_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

class DeviceListScreen extends StatefulWidget {
  final BleService bleService;
  final String? baseUrl;

  const DeviceListScreen({super.key, required this.bleService, this.baseUrl});

  @override
  State<DeviceListScreen> createState() => _DeviceListScreenState();
}

class _DeviceListScreenState extends State<DeviceListScreen> {
  final List<BleDeviceModel> _devices = [];
  bool _isScanning = false;
  bool _isConnecting = false;
  String? _connectingDeviceId;
  bool _isBluetoothOn = false;
  bool _isCheckingPermissions = true;

  @override
  void initState() {
    super.initState();
    _checkPermissionsAndBluetooth();
  }

  Future<void> _checkPermissionsAndBluetooth() async {
    setState(() => _isCheckingPermissions = true);

    // Request permissions
    if (Platform.isAndroid) {
      await _requestAndroidPermissions();
    } else if (Platform.isIOS) {
      await Permission.bluetooth.request();
    }

    // Check Bluetooth state
    widget.bleService.adapterState.listen((state) {
      if (mounted) {
        setState(() {
          _isBluetoothOn = state == BluetoothAdapterState.on;
        });
      }
    });

    // Initial check
    final state = await FlutterBluePlus.adapterState.first;
    if (mounted) {
      setState(() {
        _isBluetoothOn = state == BluetoothAdapterState.on;
        _isCheckingPermissions = false;
      });

      if (_isBluetoothOn) {
        _startScan();
      }
    }
  }

  Future<void> _requestAndroidPermissions() async {
    Map<Permission, PermissionStatus> statuses = await [
      Permission.bluetoothScan,
      Permission.bluetoothConnect,
      Permission.location,
    ].request();

    if (statuses.values.any((status) => status.isDenied)) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Bluetooth permissions are required'),
            duration: Duration(seconds: 3),
          ),
        );
      }
    }
  }

  Future<void> _turnOnBluetooth() async {
    if (Platform.isAndroid) {
      try {
        await FlutterBluePlus.turnOn();
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Please enable Bluetooth manually in settings'),
              duration: Duration(seconds: 3),
            ),
          );
        }
      }
    } else {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Please enable Bluetooth in Settings'),
            duration: Duration(seconds: 3),
          ),
        );
      }
    }
  }

  void _startScan() {
    setState(() {
      _isScanning = true;
      _devices.clear();
    });

    widget.bleService.startScan().listen((results) {
      setState(() {
        // Filter and update device list
        for (var result in results) {
          // Only show devices with names
          if (result.device.platformName.isNotEmpty) {
            final deviceModel = BleDeviceModel.fromScanResult(result);

            // Remove duplicates
            _devices.removeWhere((d) => d.id == deviceModel.id);
            _devices.add(deviceModel);
          }
        }

        // Sort by RSSI (signal strength)
        _devices.sort((a, b) => b.rssi.compareTo(a.rssi));
      });
    });

    // Stop scanning after timeout
    Future.delayed(const Duration(seconds: 15), () {
      if (mounted) {
        widget.bleService.stopScan();
        setState(() => _isScanning = false);
      }
    });
  }

  Future<void> _connectToDevice(BleDeviceModel deviceModel) async {
    setState(() {
      _isConnecting = true;
      _connectingDeviceId = deviceModel.id;
    });

    await widget.bleService.stopScan();

    bool connected = await widget.bleService.connect(deviceModel.device);

    setState(() {
      _isConnecting = false;
      _connectingDeviceId = null;
    });

    if (connected) {
      if (mounted) {
        // Check if legacy mode or modern mode
        if (widget.bleService.isLegacyMode) {
          // Legacy mode: directly send credentials and get MAC
          _showLegacyCredentialsDialog();
        } else {
          // Modern mode: show network selection
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (context) => NetworkSelectionScreen(
                bleService: widget.bleService,
                baseUrl: widget.baseUrl,
              ),
            ),
          );
        }
      }
    } else {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Failed to connect to device'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  void _showLegacyCredentialsDialog() {
    final ssidCtrl = TextEditingController();
    final passCtrl = TextEditingController();

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        title: const Text('WiFi Credentials'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: ssidCtrl,
              decoration: const InputDecoration(labelText: 'WiFi SSID'),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: passCtrl,
              decoration: const InputDecoration(labelText: 'WiFi Password'),
              obscureText: true,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              widget.bleService.disconnect();
              Navigator.of(ctx).pop();
            },
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () async {
              Navigator.of(ctx).pop();
              await _sendLegacyCredentials(ssidCtrl.text, passCtrl.text);
            },
            child: const Text('Send'),
          ),
        ],
      ),
    );
  }

  Future<void> _sendLegacyCredentials(String ssid, String password) async {
    try {
      bool success = await widget.bleService.sendWifiCredentials(
        ssid,
        password,
      );
      if (success) {
        // Wait a bit then read MAC
        await Future.delayed(const Duration(milliseconds: 500));
        final mac = await widget.bleService.readMacAddress();

        if (mac != null && mac.isNotEmpty) {
          final prefs = await SharedPreferences.getInstance();
          await prefs.setString('device_mac', mac);

          // Register device with backend if baseUrl provided
          if (widget.baseUrl != null) {
            try {
              final deviceService = DeviceService(widget.baseUrl!);
              await deviceService.addDevice(mac, ssid);
            } catch (e) {
              // Non-fatal: device paired locally but not registered
              debugPrint('Failed to register device: $e');
            }
          }

          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('Device paired! MAC: $mac'),
                backgroundColor: Colors.green,
              ),
            );
          }
        }
      }
      await widget.bleService.disconnect();
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isCheckingPermissions) {
      return Scaffold(
        appBar: AppBar(title: const Text('Device Pairing')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    if (!_isBluetoothOn) {
      return Scaffold(
        appBar: AppBar(title: const Text('Device Pairing')),
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.bluetooth_disabled, size: 64, color: Colors.red),
              const SizedBox(height: 16),
              const Text('Bluetooth is OFF', style: TextStyle(fontSize: 18)),
              const SizedBox(height: 16),
              ElevatedButton.icon(
                onPressed: _turnOnBluetooth,
                icon: const Icon(Icons.bluetooth),
                label: const Text('Turn On Bluetooth'),
              ),
            ],
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Available Devices'),
        actions: [
          if (!_isScanning)
            IconButton(icon: const Icon(Icons.refresh), onPressed: _startScan),
        ],
      ),
      body: Column(
        children: [
          if (_isScanning)
            Container(
              padding: const EdgeInsets.all(16),
              color: Colors.blue.shade900,
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                  SizedBox(width: 16),
                  Text(
                    'Scanning for devices...',
                    style: TextStyle(fontSize: 16),
                  ),
                ],
              ),
            ),
          Expanded(
            child: _devices.isEmpty
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.bluetooth_searching,
                          size: 64,
                          color: Colors.grey.shade600,
                        ),
                        const SizedBox(height: 16),
                        Text(
                          _isScanning
                              ? 'Looking for devices...'
                              : 'No devices found',
                          style: TextStyle(
                            fontSize: 18,
                            color: Colors.grey.shade400,
                          ),
                        ),
                        if (!_isScanning) ...[
                          const SizedBox(height: 16),
                          ElevatedButton.icon(
                            onPressed: _startScan,
                            icon: const Icon(Icons.refresh),
                            label: const Text('Scan Again'),
                          ),
                        ],
                      ],
                    ),
                  )
                : ListView.builder(
                    itemCount: _devices.length,
                    padding: const EdgeInsets.all(8),
                    itemBuilder: (context, index) {
                      final device = _devices[index];
                      final isConnecting = _connectingDeviceId == device.id;

                      return Card(
                        margin: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        child: ListTile(
                          leading: Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: device.name.contains('RaspberryPi')
                                  ? Colors.green.shade900
                                  : Colors.blue.shade900,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Icon(
                              device.name.contains('RaspberryPi')
                                  ? Icons.router
                                  : Icons.bluetooth,
                              color: device.name.contains('RaspberryPi')
                                  ? Colors.green.shade300
                                  : Colors.blue.shade300,
                            ),
                          ),
                          title: Text(
                            device.name,
                            style: const TextStyle(fontWeight: FontWeight.bold),
                          ),
                          subtitle: Text(
                            'Signal: ${device.rssi} dBm\n${device.id}',
                            style: TextStyle(
                              fontSize: 12,
                              color: Colors.grey.shade500,
                            ),
                          ),
                          trailing: isConnecting
                              ? const SizedBox(
                                  width: 24,
                                  height: 24,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : const Icon(Icons.arrow_forward_ios, size: 16),
                          onTap: isConnecting || _isConnecting
                              ? null
                              : () => _connectToDevice(device),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  @override
  void dispose() {
    widget.bleService.stopScan();
    super.dispose();
  }
}
