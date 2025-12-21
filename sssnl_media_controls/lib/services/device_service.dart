import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/device_model.dart';

class DeviceService {
  final String baseUrl;

  DeviceService(this.baseUrl);

  Future<List<DeviceModel>> getDevices() async {
    final resp = await http
        .get(Uri.parse('$baseUrl/api/devices'))
        .timeout(const Duration(seconds: 10));

    if (resp.statusCode == 200) {
      final data = json.decode(resp.body) as Map<String, dynamic>;
      final list = data['devices'] as List<dynamic>;
      return list
          .map((d) => DeviceModel.fromJson(d as Map<String, dynamic>))
          .toList();
    } else if (resp.statusCode == 401) {
      throw Exception('Unauthenticated');
    } else {
      throw Exception('Failed to load devices: ${resp.statusCode}');
    }
  }

  Future<void> addDevice(String deviceMac, String? deviceName) async {
    final resp = await http
        .post(
          Uri.parse('$baseUrl/api/devices'),
          headers: {'Content-Type': 'application/json'},
          body: json.encode({
            'device_mac': deviceMac,
            if (deviceName != null && deviceName.isNotEmpty)
              'device_name': deviceName,
          }),
        )
        .timeout(const Duration(seconds: 10));

    if (resp.statusCode != 200) {
      throw Exception('Failed to add device: ${resp.statusCode}');
    }
  }

  Future<void> deleteDevice(int deviceId) async {
    final resp = await http
        .delete(Uri.parse('$baseUrl/api/devices/$deviceId'))
        .timeout(const Duration(seconds: 10));

    if (resp.statusCode != 200) {
      throw Exception('Failed to delete device: ${resp.statusCode}');
    }
  }

  Future<void> updateDevice(int deviceId, String deviceName) async {
    final resp = await http
        .put(
          Uri.parse('$baseUrl/api/devices/$deviceId'),
          headers: {'Content-Type': 'application/json'},
          body: json.encode({'device_name': deviceName}),
        )
        .timeout(const Duration(seconds: 10));

    if (resp.statusCode != 200) {
      throw Exception('Failed to update device: ${resp.statusCode}');
    }
  }
}
