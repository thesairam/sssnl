class DeviceModel {
  final int id;
  final String deviceMac;
  final String deviceName;
  final int configuredAt;

  DeviceModel({
    required this.id,
    required this.deviceMac,
    required this.deviceName,
    required this.configuredAt,
  });

  factory DeviceModel.fromJson(Map<String, dynamic> json) => DeviceModel(
        id: json['id'] as int,
        deviceMac: json['device_mac'] as String,
        deviceName: json['device_name'] as String,
        configuredAt: json['configured_at'] as int,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'device_mac': deviceMac,
        'device_name': deviceName,
        'configured_at': configuredAt,
      };
}
