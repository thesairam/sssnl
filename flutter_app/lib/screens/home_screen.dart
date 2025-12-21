import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:pi_wifi_config/screens/device_list_screen.dart';
import 'package:pi_wifi_config/services/ble_service.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final BleService _bleService = BleService();
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
    _bleService.adapterState.listen((state) {
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

  void _navigateToDeviceList() {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => DeviceListScreen(bleService: _bleService),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Pi WiFi Config'),
        centerTitle: true,
        elevation: 2,
      ),
      body: _isCheckingPermissions
          ? const Center(child: CircularProgressIndicator())
          : Center(
              child: Padding(
                padding: const EdgeInsets.all(24.0),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.router,
                      size: 100,
                      color: Theme.of(context).primaryColor,
                    ),
                    const SizedBox(height: 32),
                    const Text(
                      'Raspberry Pi WiFi\nConfiguration',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'Configure your Raspberry Pi WiFi\nvia Bluetooth',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 16, color: Colors.grey),
                    ),
                    const SizedBox(height: 48),
                    if (!_isBluetoothOn) ...[
                      const Text(
                        'Bluetooth is OFF',
                        style: TextStyle(
                          fontSize: 16,
                          color: Colors.red,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 16),
                      ElevatedButton.icon(
                        onPressed: _turnOnBluetooth,
                        icon: const Icon(Icons.bluetooth),
                        label: const Text('Turn On Bluetooth'),
                        style: ElevatedButton.styleFrom(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 32,
                            vertical: 16,
                          ),
                        ),
                      ),
                    ] else ...[
                      const Text(
                        'Bluetooth is ON',
                        style: TextStyle(
                          fontSize: 16,
                          color: Colors.green,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 16),
                      ElevatedButton.icon(
                        onPressed: _navigateToDeviceList,
                        icon: const Icon(Icons.search),
                        label: const Text('Scan for Devices'),
                        style: ElevatedButton.styleFrom(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 32,
                            vertical: 16,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
    );
  }

  @override
  void dispose() {
    _bleService.dispose();
    super.dispose();
  }
}
