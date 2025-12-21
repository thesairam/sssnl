# Pi WiFi Config - Flutter App

A Flutter mobile application to configure Raspberry Pi WiFi credentials via Bluetooth Low Energy (BLE).

## Features

- 🔍 Scan for nearby BLE devices
- 📡 Connect to Raspberry Pi BLE peripheral
- 📝 Send WiFi SSID and password
- 📊 Real-time connection status updates
- 📱 Works on both Android and iOS

## Prerequisites

- Flutter SDK (3.0.0 or higher)
- Dart SDK
- Android Studio / Xcode (for mobile development)

## Setup

1. **Install Flutter dependencies:**
   ```bash
   cd flutter_app
   flutter pub get
   ```

2. **For Android:**
   - Minimum SDK: 21 (Android 5.0)
   - Target SDK: 33 or higher
   - Bluetooth permissions are automatically requested at runtime

3. **For iOS:**
   - Minimum iOS version: 12.0
   - Bluetooth permissions configured in Info.plist
   - Run on physical device (Bluetooth doesn't work on simulator)

## Running the App

### Android
```bash
flutter run
```

### iOS
```bash
flutter run
# OR for specific device
flutter run -d <device-id>
```

## Building APK/IPA

### Android APK
```bash
flutter build apk --release
# Output: build/app/outputs/flutter-apk/app-release.apk
```

### Android App Bundle (for Play Store)
```bash
flutter build appbundle --release
# Output: build/app/outputs/bundle/release/app-release.aab
```

### iOS
```bash
flutter build ios --release
# Then open in Xcode to archive and export IPA
```

## Project Structure

```
flutter_app/
├── lib/
│   ├── main.dart                    # App entry point
│   ├── models/
│   │   └── ble_device_model.dart    # BLE device data model
│   ├── services/
│   │   └── ble_service.dart         # BLE communication service
│   └── screens/
│       ├── home_screen.dart         # Home screen with BT check
│       ├── device_list_screen.dart  # Device scanning screen
│       └── wifi_config_screen.dart  # WiFi configuration screen
├── android/
│   └── app/src/main/AndroidManifest.xml  # Android permissions
├── ios/
│   └── Runner/Info.plist            # iOS permissions
└── pubspec.yaml                     # Dependencies
```

## How It Works

1. **Home Screen:**
   - Checks Bluetooth availability
   - Requests necessary permissions
   - Prompts to enable Bluetooth if off

2. **Device List Screen:**
   - Scans for BLE devices
   - Filters and displays available devices
   - Prioritizes devices named "RaspberryPi-WiFi"
   - Shows signal strength (RSSI)

3. **WiFi Config Screen:**
   - Displays connection status
   - Input fields for SSID and password
   - Sends credentials to Raspberry Pi
   - Shows real-time status updates
   - Allows disconnection

## BLE Service Details

**Service UUID:** `12345678-1234-5678-1234-56789abcdef0`

**Characteristics:**
- **SSID** (Write): `12345678-1234-5678-1234-56789abcdef1`
- **Password** (Write): `12345678-1234-5678-1234-56789abcdef2`
- **Status** (Read/Notify): `12345678-1234-5678-1234-56789abcdef3`

## Troubleshooting

### Android Issues

**Bluetooth permissions not granted:**
- Go to Settings → Apps → Pi WiFi Config → Permissions
- Enable Location and Bluetooth permissions

**Can't find devices:**
- Ensure Location services are enabled
- Grant location permission (required for BLE scanning on Android)
- Make sure Bluetooth is on

### iOS Issues

**Bluetooth not working:**
- iOS requires a physical device (won't work on simulator)
- Check Settings → Privacy → Bluetooth and enable for the app

**Build errors:**
- Run `flutter clean` then `flutter pub get`
- Update CocoaPods: `cd ios && pod update`

### General Issues

**Connection fails:**
- Ensure Raspberry Pi is running the BLE server
- Move closer to the device (within BLE range ~10m)
- Restart both devices

**Status not updating:**
- Check that notifications are enabled on the characteristic
- Verify the Raspberry Pi script is running correctly

## Testing

1. **Start the Raspberry Pi BLE server:**
   ```bash
   # On Raspberry Pi
   sudo python3 config.py
   ```

2. **Run the Flutter app:**
   ```bash
   flutter run
   ```

3. **Test workflow:**
   - Enable Bluetooth
   - Scan for devices
   - Connect to "RaspberryPi-WiFi"
   - Enter WiFi credentials
   - Send configuration
   - Check status updates

## Dependencies

- **flutter_blue_plus** (^1.31.0): BLE communication
- **permission_handler** (^11.0.1): Runtime permissions

## Future Enhancements

- [ ] Save WiFi credentials for quick access
- [ ] Support multiple Raspberry Pi devices
- [ ] Add WiFi network strength indicator
- [ ] Connection history
- [ ] Dark mode support
- [ ] Localization (multiple languages)

## License

MIT License
