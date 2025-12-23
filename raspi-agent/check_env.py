#!/usr/bin/env python3
import os
import subprocess
import sys

RESULTS = []

def ok(msg):
    RESULTS.append((True, msg))

def fail(msg):
    RESULTS.append((False, msg))

def run(cmd):
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode().strip()
        return 0, out
    except subprocess.CalledProcessError as e:
        return e.returncode, e.output.decode(errors='ignore')

# Check Python imports
try:
    import gi
    from gi.repository import GLib
    ok("gi/GLib import OK")
except Exception as e:
    fail(f"gi import FAILED: {e}. Install: sudo apt install -y python3-gi")

try:
    import pydbus
    ok("pydbus import OK")
except Exception as e:
    fail(f"pydbus import FAILED: {e}. Install in venv: pip install pydbus --prefer-binary")

# Check BlueZ and bluetoothctl
rc, out = run('bluetoothctl --version')
if rc == 0:
    ok(f"bluetoothctl present (BlueZ {out})")
else:
    fail("bluetoothctl not available. Install: sudo apt install -y bluez bluez-tools")

# Check bluetooth service status
rc, out = run('systemctl is-active bluetooth')
if rc == 0 and out.strip() == 'active':
    ok("bluetoothd is active")
else:
    fail("bluetoothd not active. Try: sudo systemctl start bluetooth")

# Check adapter visibility via dbus
try:
    from pydbus import SystemBus
    bus = SystemBus()
    mngr = bus.get('org.bluez', '/')
    objects = mngr.GetManagedObjects()
    adapters = [p for p, ifaces in objects.items() if 'org.bluez.Adapter1' in ifaces]
    if adapters:
        ok(f"Bluetooth adapter(s) found: {', '.join(adapters)}")
    else:
        fail("No Bluetooth adapter found via DBus. Ensure rfkill unblocked and adapter connected.")
except Exception as e:
    fail(f"DBus query for adapters failed: {e}")

# Check GATT Manager interface presence
try:
    from pydbus import SystemBus
    bus = SystemBus()
    mngr = bus.get('org.bluez', '/')
    objects = mngr.GetManagedObjects()
    gatt_mgr = [p for p, ifaces in objects.items() if 'org.bluez.GattManager1' in ifaces]
    if gatt_mgr:
        ok(f"GattManager present on: {', '.join(gatt_mgr)}")
    else:
        fail("GattManager1 not found. On Ubuntu, start bluetoothd with --experimental.\n"
             "Example: sudo systemctl stop bluetooth && sudo /usr/lib/bluetooth/bluetoothd -E -d &")
except Exception as e:
    fail(f"DBus query for GATT manager failed: {e}")

print("\nSSSNL Raspberry Pi Agent Preflight:\n")
for good, msg in RESULTS:
    print(("[OK] " if good else "[FAIL] ") + msg)

bad = [m for g, m in RESULTS if not g]
if bad:
    print("\nFix the FAILED checks above. Common steps:")
    print("  sudo apt update && sudo apt install -y python3-gi python3-dbus bluez bluez-tools rfkill")
    print("  rfkill unblock all")
    print("  Recreate venv with system packages: python3 -m venv --system-site-packages .venv")
    print("  source .venv/bin/activate && pip install --prefer-binary -r requirements.txt")
    sys.exit(1)
else:
    print("\nAll checks passed. You can run ble_peripheral.py now.")
    sys.exit(0)
