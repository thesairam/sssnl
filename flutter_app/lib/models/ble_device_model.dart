import 'package:flutter_blue_plus/flutter_blue_plus.dart';

class BleDeviceModel {
  final BluetoothDevice device;
  final String name;
  final String id;
  final int rssi;

  BleDeviceModel({
    required this.device,
    required this.name,
    required this.id,
    required this.rssi,
  });

  factory BleDeviceModel.fromScanResult(ScanResult result) {
    return BleDeviceModel(
      device: result.device,
      name: result.device.platformName.isNotEmpty
          ? result.device.platformName
          : 'Unknown Device',
      id: result.device.remoteId.toString(),
      rssi: result.rssi,
    );
  }
}
