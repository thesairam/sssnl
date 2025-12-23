import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

// BLE only on mobile platforms; guard imports for web.
// flutter_blue_plus does not support web; show instructions instead.
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

const String _kBackendBaseUrlEnv = String.fromEnvironment('BACKEND_BASE_URL', defaultValue: '');
final String kBackendBaseUrl = _kBackendBaseUrlEnv.isNotEmpty ? _kBackendBaseUrlEnv : Uri.base.origin;

// Local cookie-aware client for settings page requests.
class _CookieStore {
  static const _cookieKey = 'session_cookie';
  static String? _cookie;
  static Future<String?> get() async {
    if (_cookie != null) return _cookie;
    final prefs = await SharedPreferences.getInstance();
    _cookie = prefs.getString(_cookieKey);
    return _cookie;
  }
  static Future<void> set(String? cookie) async {
    _cookie = cookie;
    final prefs = await SharedPreferences.getInstance();
    if (cookie == null || cookie.isEmpty) {
      await prefs.remove(_cookieKey);
    } else {
      await prefs.setString(_cookieKey, cookie);
    }
  }
}

class _CookieClient extends http.BaseClient {
  final http.Client _inner = http.Client();
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final cookie = await _CookieStore.get();
    if (cookie != null && cookie.isNotEmpty) {
      request.headers.putIfAbsent('Cookie', () => cookie);
    }
    final resp = await _inner.send(request);
    try {
      final setCookie = resp.headers['set-cookie'];
      if (setCookie != null && setCookie.isNotEmpty) {
        final match = RegExp(r'(?:^|,)[^s]*session=([^;]+)').firstMatch(setCookie);
        if (match != null) {
          final value = match.group(1);
          if (value != null && value.isNotEmpty) {
            await _CookieStore.set('session=$value');
          }
        }
      }
    } catch (_) {}
    return resp;
  }
}

final http.Client _api = _CookieClient();

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final _oldPassCtrl = TextEditingController();
  final _newPassCtrl = TextEditingController();
  final _newUsernameCtrl = TextEditingController();
  final _verifyPassCtrl = TextEditingController();
  String? _msg;
  String? _deviceMac;

  @override
  void initState() {
    super.initState();
    _loadPrefs();
  }

  Future<void> _loadPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _deviceMac = prefs.getString('device_mac');
    });
  }

  Future<void> _changePassword() async {
    setState(() { _msg = null; });
    try {
      final resp = await _api.post(
        Uri.parse('$kBackendBaseUrl/api/user/change_password'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'old_password': _oldPassCtrl.text, 'new_password': _newPassCtrl.text}),
      ).timeout(const Duration(seconds: 10));
      setState(() { _msg = resp.statusCode == 200 ? 'Password updated.' : 'Update failed (${resp.statusCode})'; });
      if (resp.statusCode == 200) {
        _oldPassCtrl.clear();
        _newPassCtrl.clear();
      }
    } catch (e) {
      setState(() { _msg = 'Update error: $e'; });
    }
  }

  Future<void> _changeUsername() async {
    setState(() { _msg = null; });
    try {
      final resp = await _api.post(
        Uri.parse('$kBackendBaseUrl/api/user/change_username'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'new_username': _newUsernameCtrl.text.trim().toLowerCase(), 'password': _verifyPassCtrl.text}),
      ).timeout(const Duration(seconds: 10));
      if (resp.statusCode == 200) {
        setState(() { _msg = 'Username updated.'; });
        _newUsernameCtrl.clear();
        _verifyPassCtrl.clear();
      } else if (resp.statusCode == 409) {
        setState(() { _msg = 'Username already exists.'; });
      } else {
        setState(() { _msg = 'Update failed (${resp.statusCode})'; });
      }
    } catch (e) {
      setState(() { _msg = 'Update error: $e'; });
    }
  }

  void _openPairing() async {
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const DevicePairingPage()));
    _loadPrefs();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Card(
              color: const Color(0xFF020617),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text('Account', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 8),
                    Row(children: [
                      Expanded(child: TextField(controller: _oldPassCtrl, decoration: const InputDecoration(labelText: 'Current Password'), obscureText: true)),
                      const SizedBox(width: 8),
                      Expanded(child: TextField(controller: _newPassCtrl, decoration: const InputDecoration(labelText: 'New Password'), obscureText: true)),
                      const SizedBox(width: 8),
                      ElevatedButton(onPressed: _changePassword, child: const Text('Change Password')),
                    ]),
                    const SizedBox(height: 8),
                    Row(children: [
                      Expanded(child: TextField(controller: _newUsernameCtrl, decoration: const InputDecoration(labelText: 'New Username'))),
                      const SizedBox(width: 8),
                      Expanded(child: TextField(controller: _verifyPassCtrl, decoration: const InputDecoration(labelText: 'Password (verify)'), obscureText: true)),
                      const SizedBox(width: 8),
                      ElevatedButton(onPressed: _changeUsername, child: const Text('Change Username')),
                    ]),
                    if (_msg != null) ...[
                      const SizedBox(height: 8),
                      Text(_msg!, style: const TextStyle(fontSize: 12, color: Colors.white70)),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            Card(
              color: const Color(0xFF020617),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text('Device', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 8),
                    Row(children: [
                      Expanded(child: Text('Current device MAC: ${_deviceMac ?? 'Not paired'}')),
                      const SizedBox(width: 8),
                      ElevatedButton.icon(onPressed: _openPairing, icon: const Icon(Icons.bluetooth), label: const Text('Add / Pair Device')),
                    ]),
                    const SizedBox(height: 8),
                    const Text('Uploads and media listing will be scoped to the paired device folder.'),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class DevicePairingPage extends StatefulWidget {
  const DevicePairingPage({super.key});

  @override
  State<DevicePairingPage> createState() => _DevicePairingPageState();
}

class _DevicePairingPageState extends State<DevicePairingPage> {
  bool _scanning = false;
  List<ScanResult> _devices = const [];
  String? _status;
  final _ssidCtrl = TextEditingController();
  final _wifiPassCtrl = TextEditingController();

  // UUIDs expected from Raspberry Pi BLE peripheral
  // Implement these on Pi side
  static const String serviceUuid = '0000ffff-0000-1000-8000-00805f9b34fb';
  static const String credsCharUuid = '0000fff1-0000-1000-8000-00805f9b34fb';
  static const String macCharUuid = '0000fff2-0000-1000-8000-00805f9b34fb';

  Future<void> _scan() async {
    if (kIsWeb) {
      setState(() { _status = 'Bluetooth pairing is not supported on Web. Use Android/iOS app.'; });
      return;
    }
    setState(() { _scanning = true; _status = null; });
    try {
      await FlutterBluePlus.startScan(timeout: const Duration(seconds: 6));
      final subs = FlutterBluePlus.scanResults.listen((results) {
        setState(() { _devices = results; });
      });
      await Future.delayed(const Duration(seconds: 6));
      await FlutterBluePlus.stopScan();
      await subs.cancel();
      setState(() { _scanning = false; });
    } catch (e) {
      setState(() { _status = 'Scan error: $e'; _scanning = false; });
    }
  }

  Future<void> _pair(ScanResult result) async {
    if (kIsWeb) return;
    setState(() { _status = 'Connecting…'; });
    final device = result.device;
    try {
      await device.connect(timeout: const Duration(seconds: 10));
      final services = await device.discoverServices();
      BluetoothService? svc;
      for (final s in services) {
        if (s.uuid.toString().toLowerCase() == serviceUuid) {
          svc = s; break;
        }
      }
      if (svc == null) {
        setState(() { _status = 'Provisioning service not found.'; });
        await device.disconnect();
        return;
      }
      BluetoothCharacteristic? creds;
      BluetoothCharacteristic? mac;
      for (final c in svc.characteristics) {
        final id = c.uuid.toString().toLowerCase();
        if (id == credsCharUuid) creds = c;
        if (id == macCharUuid) mac = c;
      }
      if (creds == null || mac == null) {
        setState(() { _status = 'Provisioning service/characteristics not found.'; });
        await device.disconnect();
        return;
      }

      // Read MAC address first
      final macBytes = await mac.read();
      final macStr = utf8.decode(macBytes);

      // Get pairing code from backend (bind by MAC)
      String pairingCode = '';
      try {
        final resp = await _api.post(
          Uri.parse('$kBackendBaseUrl/api/devices/pair_by_mac'),
          headers: {'Content-Type': 'application/json'},
          body: json.encode({'mac': macStr, 'ttl_sec': 300}),
        ).timeout(const Duration(seconds: 10));
        if (resp.statusCode == 200) {
          final data = json.decode(resp.body) as Map<String, dynamic>;
          pairingCode = (data['pairing_code'] as String?) ?? '';
        }
      } catch (_) {}

      // Send Wi-Fi credentials and pairing code as JSON
      final payload = json.encode({'ssid': _ssidCtrl.text.trim(), 'password': _wifiPassCtrl.text, 'pairing_code': pairingCode});
      await creds.write(utf8.encode(payload), withoutResponse: false);

      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('device_mac', macStr);

      setState(() { _status = 'Paired device MAC: $macStr'; });
      await device.disconnect();
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      setState(() { _status = 'Pairing error: $e'; });
      try { await device.disconnect(); } catch (_) {}
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Device Pairing')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Enter Wi-Fi credentials to provision the Raspberry Pi via BLE:'),
            const SizedBox(height: 8),
            TextField(controller: _ssidCtrl, decoration: const InputDecoration(labelText: 'Wi-Fi SSID')),
            const SizedBox(height: 8),
            TextField(controller: _wifiPassCtrl, decoration: const InputDecoration(labelText: 'Wi-Fi Password'), obscureText: true),
            const SizedBox(height: 12),
            Row(children: [
              ElevatedButton.icon(onPressed: _scanning ? null : _scan, icon: const Icon(Icons.search), label: const Text('Scan Devices')),
              const SizedBox(width: 8),
              if (_scanning) const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
            ]),
            const SizedBox(height: 12),
            Expanded(
              child: ListView.builder(
                itemCount: _devices.length,
                itemBuilder: (ctx, i) {
                  final r = _devices[i];
                  return ListTile(
                    leading: const Icon(Icons.devices),
                    title: Text(r.device.platformName.isNotEmpty ? r.device.platformName : r.device.remoteId.str),
                    subtitle: Text('RSSI: ${r.rssi}'),
                    trailing: ElevatedButton(onPressed: () => _pair(r), child: const Text('Pair')),
                  );
                },
              ),
            ),
            if (_status != null) ...[
              const SizedBox(height: 8),
              Text(_status!, style: const TextStyle(fontSize: 12, color: Colors.white70)),
            ]
          ],
        ),
      ),
    );
  }
}
