import time
import Adafruit_DHT

# Configure sensor and pin (BCM numbering)
DHT_SENSOR = Adafruit_DHT.DHT22
DHT_PIN = 22  # you're using GPIO22 (BCM)

def main():
    print("Starting DHT22 reader on GPIO22. Press Ctrl+C to stop.")
    try:
        while True:
            hum, temp = Adafruit_DHT.read_retry(DHT_SENSOR, DHT_PIN, retries=3, delay_seconds=2)
            ts = time.strftime('%Y-%m-%d %H:%M:%S')
            if hum is not None and temp is not None:
                print(f"{ts}  Temp: {temp:.1f}°C  Humidity: {hum:.1f}%")
            else:
                print(f"{ts}  Failed to get reading. Retrying...")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopped by user.")

if __name__ == "__main__":
    main()