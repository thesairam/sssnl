# SSSNL Media Controls (Mobile)

Flutter app for sign-in/sign-up, device provisioning over Bluetooth (BLE), and media file management scoped per device.

## Features
- Sign in / Sign up against the SSSNL backend.
- Choose Device: select one of your paired devices to scope media.
- Add Device (Setup): BLE-provision Raspberry Pi with Wi‑Fi credentials and pairing code.
- Media Controls: upload, list, and delete media tied to the selected device.

## Prerequisites
- Flutter SDK installed.
- Android device with Bluetooth LE enabled.
- Backend running independently (e.g., http://<backend-host>:5656) with CORS configured.

Android permissions are already configured in:
- android/app/src/main/AndroidManifest.xml (BLUETOOTH_SCAN, BLUETOOTH_CONNECT, ACCESS_FINE_LOCATION)

Note: BLE is not supported on Web builds. Use an Android (or iOS) device for provisioning.

## Run (Development)
```bash
cd sssnl_media_controls
flutter pub get
flutter run -d android --dart-define=BACKEND_BASE_URL=http://<backend-host>:5656
```
- Replace <backend-host> with the IP/hostname of your backend on the local network.

## Provisioning flow
1) Start the Raspberry Pi BLE service (see raspi-agent/README.md).
2) In the app, tap Add Device (Setup), enter Wi‑Fi SSID and password.
3) Scan, select the Pi, and tap Pair.
4) The app will request a pairing code from the backend and send Wi‑Fi + pairing code to the Pi over BLE.
5) The Pi registers with the backend, claims ownership with the pairing code, and starts heartbeating.
6) Use Choose Device and Media Controls to manage media for that device.

## Build (Release)
```bash
flutter build apk --dart-define=BACKEND_BASE_URL=https://<backend-domain>
```

## Troubleshooting
- BLE scan doesn’t show devices: ensure Bluetooth is on; check Pi BLE service is running; some devices require Location enabled for BLE scans.
- Unauthorized errors: sign in or sign up first; backend must allow CORS from your app’s origin.
- Uploads not visible: ensure you’ve selected a device in Choose Device; media lists are scoped per device.
