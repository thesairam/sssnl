import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/ble_service.dart';
import '../services/device_service.dart';

class WiFiConfigScreen extends StatefulWidget {
  final BleService bleService;
  final String selectedSsid;
  final String? baseUrl;

  const WiFiConfigScreen({
    super.key,
    required this.bleService,
    required this.selectedSsid,
    this.baseUrl,
  });

  @override
  State<WiFiConfigScreen> createState() => _WiFiConfigScreenState();
}

class _WiFiConfigScreenState extends State<WiFiConfigScreen> {
  final _formKey = GlobalKey<FormState>();
  final _passwordController = TextEditingController();

  bool _isConnected = true;
  bool _isSending = false;
  bool _obscurePassword = true;
  String _status = 'Ready';

  @override
  void initState() {
    super.initState();

    // Listen to connection state
    widget.bleService.connectionStream.listen((connected) {
      setState(() => _isConnected = connected);
      if (!connected && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Device disconnected'),
            backgroundColor: Colors.red,
          ),
        );
        Navigator.pop(context);
      }
    });

    // Listen to status updates
    widget.bleService.statusStream.listen((status) {
      setState(() => _status = status);
    });

    // Read initial status
    _readStatus();
  }

  Future<void> _readStatus() async {
    await widget.bleService.readStatus();
  }

  Future<void> _sendCredentials() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() => _isSending = true);

    bool success = await widget.bleService.sendWifiCredentials(
      widget.selectedSsid,
      _passwordController.text.trim(),
    );

    setState(() => _isSending = false);

    if (success) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('WiFi credentials sent successfully!'),
            backgroundColor: Colors.green,
          ),
        );

        // Wait for potential MAC address or status update
        await Future.delayed(const Duration(seconds: 2));

        // Try to read MAC if available (for compatibility with devices that send it)
        final mac = await widget.bleService.readMacAddress();
        if (mac != null && mac.isNotEmpty) {
          final prefs = await SharedPreferences.getInstance();
          await prefs.setString('device_mac', mac);

          // Register device with backend if baseUrl provided
          if (widget.baseUrl != null) {
            try {
              final deviceService = DeviceService(widget.baseUrl!);
              await deviceService.addDevice(mac, widget.selectedSsid);
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
    } else {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Failed to send credentials'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Color _getStatusColor() {
    if (_status.toLowerCase().contains('connected')) {
      return Colors.green;
    } else if (_status.toLowerCase().contains('connecting')) {
      return Colors.orange;
    } else if (_status.toLowerCase().contains('failed')) {
      return Colors.red;
    }
    return Colors.blue;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Configure WiFi'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () {
            Navigator.pop(context);
          },
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: Center(
              child: Row(
                children: [
                  Icon(
                    Icons.circle,
                    size: 12,
                    color: _isConnected ? Colors.green : Colors.red,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    _isConnected ? 'Connected' : 'Disconnected',
                    style: const TextStyle(fontSize: 12),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24.0),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Icon(Icons.wifi, size: 80, color: Colors.blue),
              const SizedBox(height: 24),
              const Text(
                'WiFi Configuration',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              const Text(
                'Enter your WiFi credentials to configure\nthe Raspberry Pi',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 14, color: Colors.grey),
              ),
              const SizedBox(height: 32),

              // Status Card
              Card(
                color: _getStatusColor().withValues(alpha: 0.1),
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Row(
                    children: [
                      Icon(Icons.info_outline, color: _getStatusColor()),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Status',
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            Text(
                              _status,
                              style: TextStyle(
                                fontSize: 16,
                                color: _getStatusColor(),
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.refresh),
                        onPressed: _readStatus,
                        tooltip: 'Refresh Status',
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 24),

              // Selected Network Display
              Card(
                color: Colors.blue.withValues(alpha: 0.1),
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Row(
                    children: [
                      const Icon(Icons.wifi, color: Colors.blue, size: 32),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Selected Network',
                              style: TextStyle(
                                fontSize: 12,
                                color: Colors.grey,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              widget.selectedSsid,
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 24),

              // Password Field
              TextFormField(
                controller: _passwordController,
                obscureText: _obscurePassword,
                decoration: InputDecoration(
                  labelText: 'WiFi Password',
                  hintText: 'Enter password',
                  prefixIcon: const Icon(Icons.lock),
                  suffixIcon: IconButton(
                    icon: Icon(
                      _obscurePassword
                          ? Icons.visibility
                          : Icons.visibility_off,
                    ),
                    onPressed: () {
                      setState(() => _obscurePassword = !_obscurePassword);
                    },
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                validator: (value) {
                  if (value == null || value.trim().isEmpty) {
                    return 'Please enter WiFi password';
                  }
                  if (value.length < 8) {
                    return 'Password must be at least 8 characters';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 32),

              // Send Button
              ElevatedButton(
                onPressed: _isSending || !_isConnected
                    ? null
                    : _sendCredentials,
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: _isSending
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Text(
                        'Configure WiFi',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
              ),
              const SizedBox(height: 16),

              // Disconnect Button
              OutlinedButton(
                onPressed: _isSending
                    ? null
                    : () {
                        widget.bleService.disconnect();
                        Navigator.pop(context);
                      },
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: const Text('Disconnect', style: TextStyle(fontSize: 16)),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _passwordController.dispose();
    super.dispose();
  }
}
