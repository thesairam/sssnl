import 'package:flutter/material.dart';
import 'package:pi_wifi_config/models/ble_device_model.dart';
import 'package:pi_wifi_config/screens/network_selection_screen.dart';
import 'package:pi_wifi_config/services/ble_service.dart';

class DeviceListScreen extends StatefulWidget {
  final BleService bleService;

  const DeviceListScreen({super.key, required this.bleService});

  @override
  State<DeviceListScreen> createState() => _DeviceListScreenState();
}

class _DeviceListScreenState extends State<DeviceListScreen> {
  List<BleDeviceModel> _devices = [];
  bool _isScanning = false;
  bool _isConnecting = false;
  String? _connectingDeviceId;

  @override
  void initState() {
    super.initState();
    _startScan();
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
          // Only show devices with names (or specifically look for RaspberryPi-WiFi)
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
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(
            builder: (context) => NetworkSelectionScreen(
              bleService: widget.bleService,
            ),
          ),
        );
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

  @override
  Widget build(BuildContext context) {
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
              color: Colors.blue.shade50,
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
                          color: Colors.grey.shade400,
                        ),
                        const SizedBox(height: 16),
                        Text(
                          _isScanning
                              ? 'Looking for devices...'
                              : 'No devices found',
                          style: TextStyle(
                            fontSize: 18,
                            color: Colors.grey.shade600,
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
                                  ? Colors.green.shade100
                                  : Colors.blue.shade100,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Icon(
                              device.name.contains('RaspberryPi')
                                  ? Icons.router
                                  : Icons.bluetooth,
                              color: device.name.contains('RaspberryPi')
                                  ? Colors.green.shade700
                                  : Colors.blue.shade700,
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
                              color: Colors.grey.shade600,
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
