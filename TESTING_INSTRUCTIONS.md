# WiFi Configuration via BLE - Testing Instructions

## Overview
The system has been updated to allow the Raspberry Pi to scan for available WiFi networks and send them to the mobile app. Users can now select from a list of available networks instead of manually entering the SSID.

## Changes Made

### Python Script (config.py)
1. **Added WiFi Network Scanning**:
   - New `scan_networks()` method in WiFiManager class
   - Supports both `nmcli` and `iwlist` for scanning
   - Returns list of networks with SSID, signal strength, and security status

2. **New BLE Characteristic**:
   - Added `WIFI_NETWORKS_CHAR_UUID` (12345678-1234-5678-1234-56789abcdef1)
   - WiFiNetworksCharacteristic provides readable list of available networks as JSON
   - Updated other UUIDs: SSID (def2), PASSWORD (def3), STATUS (def4)

3. **Enhanced Logging**:
   - Network scan logging with count of found networks
   - Signal strength information for each network

### Flutter App
1. **New Network Selection Screen**:
   - Displays list of available WiFi networks
   - Shows signal strength indicators (colored icons)
   - Shows security status (Open/Secured)
   - Sortable by signal strength
   - Pull-to-refresh to rescan networks

2. **Updated WiFi Configuration Screen**:
   - Removed SSID input field
   - Accepts selected SSID from network selection screen
   - Shows selected network in a card
   - Only requires password input

3. **Updated BLE Service**:
   - Added `readNetworks()` method to read available networks
   - Updated UUIDs to match Python script
   - Added JSON parsing for network list

4. **Updated Navigation Flow**:
   - Device List → Network Selection → WiFi Configuration
   - Automatically reads networks after connection

## Testing Steps

### 1. Start the BLE Server on Raspberry Pi

```bash
# SSH into the Raspberry Pi
ssh saipi@sssnl.local

# Run the BLE configuration script
python3 config.py
```

You should see:
```
🎉 BLE WiFi Configuration Server Starting
============================================================
✅ Connected to D-Bus system bus
✅ Using Bluetooth adapter: /org/bluez/hci0
📶 Initializing WiFi Manager...
...
🚀 BLE WiFi Configuration Server is RUNNING
```

### 2. Install the Updated Flutter App

#### Option A: Via USB (Recommended)
```bash
# Connect your Android phone via USB
# Enable USB debugging on your phone
# From your computer:
cd /Users/vishnuguhan/Documents/workspace/pi_ble_config/flutter_app
flutter install
```

#### Option B: Via Wireless ADB
```bash
# Enable wireless debugging on your phone (Settings → Developer Options)
# Connect via ADB:
adb connect <your-phone-ip>:5555

# Then install:
cd /Users/vishnuguhan/Documents/workspace/pi_ble_config/flutter_app
flutter install
```

#### Option C: Copy APK to Phone
```bash
# The APK is located at:
/Users/vishnuguhan/Documents/workspace/pi_ble_config/flutter_app/build/app/outputs/flutter-apk/app-release.apk

# Copy it to your phone and install manually
```

### 3. Test the Complete Flow

1. **Open the App**
   - Grant Bluetooth and Location permissions when prompted

2. **Scan for Devices**
   - You should see "RaspberryPi-WiFi" in the device list
   - Tap on it to connect

3. **View Available Networks**
   - After connection, the app will automatically scan for networks
   - You'll see a list of available WiFi networks
   - Each network shows:
     - Network name (SSID)
     - Signal strength (colored icon: green = strong, orange = medium, red = weak)
     - Security status (Open/Secured)
     - Signal percentage

4. **Select a Network**
   - Tap on any network from the list
   - You'll be taken to the WiFi configuration screen

5. **Configure WiFi**
   - The selected network is displayed at the top
   - Enter the WiFi password (minimum 8 characters)
   - Tap "Send Credentials"

6. **Monitor Status**
   - Check the status card for connection progress
   - Possible statuses:
     - "Ready" - Waiting for credentials
     - "Connecting..." - Attempting to connect
     - "Connected" - Successfully connected to WiFi
     - "Failed" - Connection failed

### 4. Verify on Raspberry Pi

```bash
# SSH into the Pi and check WiFi connection
nmcli connection show --active

# Or check IP address
ip addr show wlan0
```

## Features

### Network Scanning
- **Primary Method**: Uses `nmcli` for network scanning
- **Fallback Method**: Uses `iwlist` if nmcli is not available
- **Sorting**: Networks are sorted by signal strength (strongest first)
- **Deduplication**: Duplicate SSIDs are automatically removed

### UI Enhancements
- **Signal Indicators**: Color-coded WiFi icons
  - Green: Signal ≥ 75%
  - Orange: Signal ≥ 50%
  - Red: Signal < 50%
- **Pull-to-Refresh**: Swipe down to rescan networks
- **Loading States**: Clear indicators during scanning and sending
- **Error Handling**: Informative error messages with retry options

### BLE Characteristics

| Characteristic | UUID | Access | Description |
|---------------|------|--------|-------------|
| Networks | ...def1 | Read | JSON array of available WiFi networks |
| SSID | ...def2 | Write | WiFi network name to connect to |
| Password | ...def3 | Write | WiFi network password |
| Status | ...def4 | Read/Notify | Current connection status |

## Troubleshooting

### No Networks Found
- Ensure WiFi is enabled on the Raspberry Pi
- Check that wlan0 interface is up: `ip link show wlan0`
- Try running scan manually: `nmcli device wifi list`

### Connection Failed
- Verify password is correct (minimum 8 characters)
- Check WiFi is in range
- Ensure network is not hidden (hidden networks not supported yet)

### App Can't Connect to Pi
- Verify Bluetooth is enabled on both devices
- Check Pi's BLE service is running: `sudo systemctl status bluetooth`
- Restart BLE service: `sudo systemctl restart bluetooth`

### Permission Errors
- Ensure all Bluetooth and Location permissions are granted
- On Android 12+, requires precise location permission

## Files Modified

### Python
- `/Users/vishnuguhan/Documents/workspace/pi_ble_config/config.py`
  - Added WiFiManager.scan_networks()
  - Added WiFiManager._parse_iwlist_output()
  - Added WiFiNetworksCharacteristic class
  - Updated UUIDs and characteristic order

### Flutter
- `lib/services/ble_service.dart` - Added readNetworks() method, updated UUIDs
- `lib/screens/network_selection_screen.dart` - New screen for network selection
- `lib/screens/wifi_config_screen.dart` - Updated to accept selectedSsid
- `lib/screens/device_list_screen.dart` - Updated navigation flow

## Next Steps

To further enhance the system, consider:

1. **Hidden Network Support**: Add option to manually enter SSID for hidden networks
2. **Saved Networks**: Show previously connected networks
3. **Advanced Settings**: Add support for static IP, DNS, etc.
4. **Connection History**: Track successful/failed connection attempts
5. **Multiple Networks**: Queue multiple networks to try in order
