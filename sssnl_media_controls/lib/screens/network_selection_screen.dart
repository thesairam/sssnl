import 'package:flutter/material.dart';
import '../services/ble_service.dart';
import 'wifi_config_screen.dart';

class NetworkSelectionScreen extends StatefulWidget {
  final BleService bleService;
  final String? baseUrl;

  const NetworkSelectionScreen({
    super.key,
    required this.bleService,
    this.baseUrl,
  });

  @override
  State<NetworkSelectionScreen> createState() => _NetworkSelectionScreenState();
}

class _NetworkSelectionScreenState extends State<NetworkSelectionScreen> {
  List<Map<String, dynamic>> _networks = [];
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadNetworks();
  }

  Future<void> _loadNetworks() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final networks = await widget.bleService.readNetworks();
      setState(() {
        _networks = networks;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _isLoading = false;
      });
    }
  }

  Widget _buildSignalIcon(String signal) {
    int signalStrength = int.tryParse(signal) ?? 0;
    IconData icon;
    Color color;

    if (signalStrength >= 75) {
      icon = Icons.signal_wifi_4_bar;
      color = Colors.green;
    } else if (signalStrength >= 50) {
      icon = Icons.signal_wifi_4_bar;
      color = Colors.orange;
    } else if (signalStrength >= 25) {
      icon = Icons.signal_wifi_4_bar;
      color = Colors.red;
    } else {
      icon = Icons.signal_wifi_statusbar_4_bar;
      color = Colors.red;
    }

    return Icon(icon, color: color, size: 30);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Select WiFi Network'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _isLoading ? null : _loadNetworks,
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('Scanning for WiFi networks...'),
          ],
        ),
      );
    }

    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, size: 64, color: Colors.red),
            const SizedBox(height: 16),
            Text('Error: $_error'),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _loadNetworks,
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    if (_networks.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.wifi_off, size: 64, color: Colors.grey),
            const SizedBox(height: 16),
            const Text('No WiFi networks found'),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _loadNetworks,
              child: const Text('Scan Again'),
            ),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _loadNetworks,
      child: ListView.builder(
        itemCount: _networks.length,
        itemBuilder: (context, index) {
          final network = _networks[index];
          final ssid = network['ssid'] ?? 'Unknown';
          final signal = network['signal'] ?? '0';
          final security = network['security'] ?? 'Unknown';

          return Card(
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: ListTile(
              leading: _buildSignalIcon(signal),
              title: Text(
                ssid,
                style: const TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                ),
              ),
              subtitle: Text(
                '$security • Signal: $signal%',
                style: TextStyle(color: Colors.grey[400], fontSize: 14),
              ),
              trailing: const Icon(Icons.arrow_forward_ios, size: 16),
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => WiFiConfigScreen(
                      bleService: widget.bleService,
                      selectedSsid: ssid,
                      baseUrl: widget.baseUrl,
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }
}
