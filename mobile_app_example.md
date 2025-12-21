# Mobile App Example Code

This document provides example code for connecting to the Raspberry Pi BLE server from mobile devices.

## Android Example (Kotlin)

### Add Dependencies to build.gradle

```gradle
dependencies {
    implementation 'androidx.core:core-ktx:1.12.0'
    implementation 'no.nordicsemi.android:ble:2.6.1'
    implementation 'org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3'
}
```

### Permissions in AndroidManifest.xml

```xml
<uses-permission android:name="android.permission.BLUETOOTH" />
<uses-permission android:name="android.permission.BLUETOOTH_ADMIN" />
<uses-permission android:name="android.permission.BLUETOOTH_SCAN" />
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
```

### BLE Manager Class

```kotlin
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCharacteristic
import android.content.Context
import android.util.Log
import no.nordicsemi.android.ble.BleManager
import no.nordicsemi.android.ble.data.Data
import java.util.*

class RaspberryPiBleManager(context: Context) : BleManager(context) {

    companion object {
        private const val TAG = "RaspberryPiBleManager"

        // Service and Characteristic UUIDs
        val WIFI_CONFIG_SERVICE_UUID: UUID = UUID.fromString("12345678-1234-5678-1234-56789abcdef0")
        val WIFI_SSID_CHAR_UUID: UUID = UUID.fromString("12345678-1234-5678-1234-56789abcdef1")
        val WIFI_PASSWORD_CHAR_UUID: UUID = UUID.fromString("12345678-1234-5678-1234-56789abcdef2")
        val WIFI_STATUS_CHAR_UUID: UUID = UUID.fromString("12345678-1234-5678-1234-56789abcdef3")
    }

    private var ssidCharacteristic: BluetoothGattCharacteristic? = null
    private var passwordCharacteristic: BluetoothGattCharacteristic? = null
    private var statusCharacteristic: BluetoothGattCharacteristic? = null

    var onStatusUpdate: ((String) -> Unit)? = null

    override fun getGattCallback(): BleManagerGattCallback {
        return RaspberryPiGattCallback()
    }

    private inner class RaspberryPiGattCallback : BleManagerGattCallback() {

        override fun isRequiredServiceSupported(gatt: BluetoothGatt): Boolean {
            val service = gatt.getService(WIFI_CONFIG_SERVICE_UUID)

            if (service != null) {
                ssidCharacteristic = service.getCharacteristic(WIFI_SSID_CHAR_UUID)
                passwordCharacteristic = service.getCharacteristic(WIFI_PASSWORD_CHAR_UUID)
                statusCharacteristic = service.getCharacteristic(WIFI_STATUS_CHAR_UUID)
            }

            return ssidCharacteristic != null &&
                   passwordCharacteristic != null &&
                   statusCharacteristic != null
        }

        override fun onServicesInvalidated() {
            ssidCharacteristic = null
            passwordCharacteristic = null
            statusCharacteristic = null
        }

        override fun initialize() {
            super.initialize()

            // Enable notifications for status
            statusCharacteristic?.let {
                setNotificationCallback(it).with { _, data ->
                    val status = data.getStringValue(0)
                    Log.d(TAG, "Status update: $status")
                    onStatusUpdate?.invoke(status ?: "Unknown")
                }
                enableNotifications(it).enqueue()
            }
        }
    }

    fun sendWiFiCredentials(ssid: String, password: String) {
        ssidCharacteristic?.let { char ->
            writeCharacteristic(char, Data.from(ssid))
                .done {
                    Log.d(TAG, "SSID written successfully")

                    // Now write password
                    passwordCharacteristic?.let { passChar ->
                        writeCharacteristic(passChar, Data.from(password))
                            .done {
                                Log.d(TAG, "Password written successfully")
                            }
                            .fail { _, status ->
                                Log.e(TAG, "Failed to write password: $status")
                            }
                            .enqueue()
                    }
                }
                .fail { _, status ->
                    Log.e(TAG, "Failed to write SSID: $status")
                }
                .enqueue()
        }
    }

    fun readStatus() {
        statusCharacteristic?.let { char ->
            readCharacteristic(char)
                .with { _, data ->
                    val status = data.getStringValue(0)
                    Log.d(TAG, "Status: $status")
                    onStatusUpdate?.invoke(status ?: "Unknown")
                }
                .enqueue()
        }
    }
}
```

### Activity Example

```kotlin
import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import no.nordicsemi.android.ble.livedata.state.ConnectionState

class MainActivity : AppCompatActivity() {

    private lateinit var bleManager: RaspberryPiBleManager
    private val REQUEST_PERMISSIONS = 1

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // Initialize BLE Manager
        bleManager = RaspberryPiBleManager(this)

        // Request permissions
        if (ActivityCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_SCAN)
            != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(
                    Manifest.permission.BLUETOOTH_SCAN,
                    Manifest.permission.BLUETOOTH_CONNECT,
                    Manifest.permission.ACCESS_FINE_LOCATION
                ),
                REQUEST_PERMISSIONS
            )
        }

        val ssidInput = findViewById<EditText>(R.id.ssidInput)
        val passwordInput = findViewById<EditText>(R.id.passwordInput)
        val statusText = findViewById<TextView>(R.id.statusText)
        val connectButton = findViewById<Button>(R.id.connectButton)
        val sendButton = findViewById<Button>(R.id.sendButton)

        // Status update callback
        bleManager.onStatusUpdate = { status ->
            runOnUiThread {
                statusText.text = "Status: $status"
            }
        }

        // Connect to device
        connectButton.setOnClickListener {
            // Replace with your device's MAC address or use scanning
            val deviceAddress = "XX:XX:XX:XX:XX:XX"
            val device = BluetoothAdapter.getDefaultAdapter().getRemoteDevice(deviceAddress)

            bleManager.connect(device)
                .useAutoConnect(false)
                .retry(3, 100)
                .done {
                    Toast.makeText(this, "Connected!", Toast.LENGTH_SHORT).show()
                }
                .fail { _, status ->
                    Toast.makeText(this, "Connection failed: $status", Toast.LENGTH_SHORT).show()
                }
                .enqueue()
        }

        // Send WiFi credentials
        sendButton.setOnClickListener {
            val ssid = ssidInput.text.toString()
            val password = passwordInput.text.toString()

            if (ssid.isNotEmpty() && password.isNotEmpty()) {
                bleManager.sendWiFiCredentials(ssid, password)
                Toast.makeText(this, "Sending credentials...", Toast.LENGTH_SHORT).show()
            } else {
                Toast.makeText(this, "Please enter SSID and password", Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        bleManager.disconnect().enqueue()
    }
}
```

---

## iOS Example (Swift)

### Info.plist Permissions

```xml
<key>NSBluetoothAlwaysUsageDescription</key>
<string>We need Bluetooth to configure your Raspberry Pi WiFi</string>
<key>NSBluetoothPeripheralUsageDescription</key>
<string>We need Bluetooth to configure your Raspberry Pi WiFi</string>
```

### BLE Manager Class

```swift
import CoreBluetooth
import Foundation

class RaspberryPiBLEManager: NSObject {

    // UUIDs
    static let wifiConfigServiceUUID = CBUUID(string: "12345678-1234-5678-1234-56789abcdef0")
    static let wifiSSIDCharUUID = CBUUID(string: "12345678-1234-5678-1234-56789abcdef1")
    static let wifiPasswordCharUUID = CBUUID(string: "12345678-1234-5678-1234-56789abcdef2")
    static let wifiStatusCharUUID = CBUUID(string: "12345678-1234-5678-1234-56789abcdef3")

    private var centralManager: CBCentralManager!
    private var raspberryPi: CBPeripheral?

    private var ssidCharacteristic: CBCharacteristic?
    private var passwordCharacteristic: CBCharacteristic?
    private var statusCharacteristic: CBCharacteristic?

    var onStatusUpdate: ((String) -> Void)?
    var onConnectionStateChanged: ((Bool) -> Void)?

    override init() {
        super.init()
        centralManager = CBCentralManager(delegate: self, queue: nil)
    }

    func startScanning() {
        guard centralManager.state == .poweredOn else {
            print("Bluetooth is not powered on")
            return
        }

        print("Starting scan...")
        centralManager.scanForPeripherals(
            withServices: [RaspberryPiBLEManager.wifiConfigServiceUUID],
            options: nil
        )
    }

    func stopScanning() {
        centralManager.stopScan()
    }

    func disconnect() {
        guard let peripheral = raspberryPi else { return }
        centralManager.cancelPeripheralConnection(peripheral)
    }

    func sendWiFiCredentials(ssid: String, password: String) {
        guard let peripheral = raspberryPi,
              let ssidChar = ssidCharacteristic,
              let passwordChar = passwordCharacteristic else {
            print("Not connected or characteristics not found")
            return
        }

        // Send SSID
        if let ssidData = ssid.data(using: .utf8) {
            peripheral.writeValue(ssidData, for: ssidChar, type: .withResponse)
        }

        // Send Password (with a small delay to ensure SSID is processed first)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            if let passwordData = password.data(using: .utf8) {
                peripheral.writeValue(passwordData, for: passwordChar, type: .withResponse)
            }
        }
    }

    func readStatus() {
        guard let peripheral = raspberryPi,
              let statusChar = statusCharacteristic else { return }
        peripheral.readValue(for: statusChar)
    }
}

// MARK: - CBCentralManagerDelegate
extension RaspberryPiBLEManager: CBCentralManagerDelegate {

    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        switch central.state {
        case .poweredOn:
            print("Bluetooth is powered on")
            startScanning()
        case .poweredOff:
            print("Bluetooth is powered off")
        case .unsupported:
            print("Bluetooth is not supported")
        default:
            break
        }
    }

    func centralManager(_ central: CBCentralManager,
                       didDiscover peripheral: CBPeripheral,
                       advertisementData: [String : Any],
                       rssi RSSI: NSNumber) {
        print("Discovered: \(peripheral.name ?? "Unknown")")

        // Check if this is our Raspberry Pi
        if peripheral.name == "RaspberryPi-WiFi" {
            raspberryPi = peripheral
            raspberryPi?.delegate = self
            centralManager.stopScan()
            centralManager.connect(peripheral, options: nil)
        }
    }

    func centralManager(_ central: CBCentralManager,
                       didConnect peripheral: CBPeripheral) {
        print("Connected to \(peripheral.name ?? "Unknown")")
        onConnectionStateChanged?(true)
        peripheral.discoverServices([RaspberryPiBLEManager.wifiConfigServiceUUID])
    }

    func centralManager(_ central: CBCentralManager,
                       didDisconnectPeripheral peripheral: CBPeripheral,
                       error: Error?) {
        print("Disconnected")
        onConnectionStateChanged?(false)
        raspberryPi = nil
    }
}

// MARK: - CBPeripheralDelegate
extension RaspberryPiBLEManager: CBPeripheralDelegate {

    func peripheral(_ peripheral: CBPeripheral,
                   didDiscoverServices error: Error?) {
        guard let services = peripheral.services else { return }

        for service in services {
            if service.uuid == RaspberryPiBLEManager.wifiConfigServiceUUID {
                peripheral.discoverCharacteristics(nil, for: service)
            }
        }
    }

    func peripheral(_ peripheral: CBPeripheral,
                   didDiscoverCharacteristicsFor service: CBService,
                   error: Error?) {
        guard let characteristics = service.characteristics else { return }

        for characteristic in characteristics {
            switch characteristic.uuid {
            case RaspberryPiBLEManager.wifiSSIDCharUUID:
                ssidCharacteristic = characteristic
                print("Found SSID characteristic")

            case RaspberryPiBLEManager.wifiPasswordCharUUID:
                passwordCharacteristic = characteristic
                print("Found Password characteristic")

            case RaspberryPiBLEManager.wifiStatusCharUUID:
                statusCharacteristic = characteristic
                peripheral.setNotifyValue(true, for: characteristic)
                print("Found Status characteristic")

            default:
                break
            }
        }
    }

    func peripheral(_ peripheral: CBPeripheral,
                   didUpdateValueFor characteristic: CBCharacteristic,
                   error: Error?) {
        if characteristic.uuid == RaspberryPiBLEManager.wifiStatusCharUUID {
            if let data = characteristic.value,
               let status = String(data: data, encoding: .utf8) {
                print("Status: \(status)")
                onStatusUpdate?(status)
            }
        }
    }

    func peripheral(_ peripheral: CBPeripheral,
                   didWriteValueFor characteristic: CBCharacteristic,
                   error: Error?) {
        if let error = error {
            print("Write error: \(error.localizedDescription)")
        } else {
            print("Successfully wrote to \(characteristic.uuid)")
        }
    }
}
```

### SwiftUI View Example

```swift
import SwiftUI

struct ContentView: View {
    @StateObject private var bleManager = RaspberryPiBLEManager()
    @State private var ssid = ""
    @State private var password = ""
    @State private var status = "Disconnected"
    @State private var isConnected = false

    var body: some View {
        VStack(spacing: 20) {
            Text("Raspberry Pi WiFi Config")
                .font(.title)
                .padding()

            Text("Status: \(status)")
                .foregroundColor(isConnected ? .green : .red)

            TextField("WiFi SSID", text: $ssid)
                .textFieldStyle(RoundedBorderTextFieldStyle())
                .padding(.horizontal)

            SecureField("WiFi Password", text: $password)
                .textFieldStyle(RoundedBorderTextFieldStyle())
                .padding(.horizontal)

            Button(action: {
                bleManager.startScanning()
            }) {
                Text("Scan & Connect")
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(10)
            }
            .padding(.horizontal)
            .disabled(isConnected)

            Button(action: {
                bleManager.sendWiFiCredentials(ssid: ssid, password: password)
            }) {
                Text("Send WiFi Credentials")
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(isConnected ? Color.green : Color.gray)
                    .foregroundColor(.white)
                    .cornerRadius(10)
            }
            .padding(.horizontal)
            .disabled(!isConnected || ssid.isEmpty || password.isEmpty)

            Button(action: {
                bleManager.disconnect()
            }) {
                Text("Disconnect")
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.red)
                    .foregroundColor(.white)
                    .cornerRadius(10)
            }
            .padding(.horizontal)
            .disabled(!isConnected)

            Spacer()
        }
        .padding()
        .onAppear {
            bleManager.onStatusUpdate = { newStatus in
                status = newStatus
            }
            bleManager.onConnectionStateChanged = { connected in
                isConnected = connected
                status = connected ? "Connected" : "Disconnected"
            }
        }
    }
}
```

---

## Testing with nRF Connect App

If you don't want to build a custom app yet, use nRF Connect:

1. **Download nRF Connect:**
   - Android: [Play Store](https://play.google.com/store/apps/details?id=no.nordicsemi.android.mcp)
   - iOS: [App Store](https://apps.apple.com/app/nrf-connect/id1054362403)

2. **Steps:**
   - Open nRF Connect
   - Tap "SCAN"
   - Find "RaspberryPi-WiFi"
   - Tap "CONNECT"
   - Expand the service (UUID: 12345678-1234-5678-1234-56789abcdef0)
   - Tap the ↑ arrow on SSID characteristic and write your WiFi name
   - Tap the ↑ arrow on Password characteristic and write your WiFi password
   - Tap the ↓ arrow on Status characteristic to read the connection status

That's it! Your Raspberry Pi should now connect to WiFi.
