#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define PULSE_PIN 4
#define SDA_PIN 8
#define SCL_PIN 9

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64

Adafruit_SSD1306 display(
  SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1
);

// Based on your measured readings
const int FINGER_ON_LEVEL = 2400;
const int FINGER_OFF_LEVEL = 2300;

const int MIN_BPM = 40;
const int MAX_BPM = 100;

float filtered = 0;
float baseline = 0;
float pulseMin = 0;
float pulseMax = 0;
float threshold = 0;

int bpm = 0;
int fingerScore = 0;

bool fingerPresent = false;
bool aboveThreshold = false;

unsigned long lastSample = 0;
unsigned long lastDisplay = 0;
unsigned long lastBeat = 0;
unsigned long lastValidBeat = 0;
unsigned long rangeStart = 0;

void resetPulse() {
  bpm = 0;
  lastBeat = 0;
  lastValidBeat = 0;
  aboveThreshold = false;
  pulseMin = 0;
  pulseMax = 0;
  threshold = 0;
  baseline = 0;
  filtered = 0;
  rangeStart = millis();
}

void drawDisplay() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);

  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("HEART RATE MONITOR");
  display.drawLine(0, 12, 127, 12, SSD1306_WHITE);

  display.setCursor(0, 18);
  display.print("Finger: ");
  display.println(fingerPresent ? "DETECTED" : "NOT DETECTED");

  display.setTextSize(3);
  display.setCursor(0, 32);
  display.print(bpm);

  display.setTextSize(1);
  display.print(" BPM");

  display.setCursor(0, 56);
  if (!fingerPresent) {
    display.print("Place finger");
  } else if (bpm == 0) {
    display.print("Reading pulse...");
  } else {
    display.print("Pulse detected");
  }

  display.display();
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);

  Wire.begin(SDA_PIN, SCL_PIN);

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED not found; check address and wiring");
    while (true) delay(100);
  }

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(10, 20);
  display.println("Pulse Monitor");
  display.println("Starting...");
  display.display();

  delay(1000);
}

void loop() {
  unsigned long now = millis();

  if (now - lastSample < 10) return;
  lastSample = now;

  int raw = analogRead(PULSE_PIN);

  // Smooth the analog signal
  if (filtered == 0) filtered = raw;
  filtered = 0.80 * filtered + 0.20 * raw;

  // Detect finger placement and removal with hysteresis
  if (!fingerPresent) {
    if (filtered >= FINGER_ON_LEVEL) {
      fingerScore = min(50, fingerScore + 1);
    } else {
      fingerScore = max(0, fingerScore - 1);
    }

    if (fingerScore >= 50) {
      fingerPresent = true;
      fingerScore = 0;
      resetPulse();
      filtered = raw;
      baseline = raw;
      pulseMin = 0;
      pulseMax = 0;
      rangeStart = now;
    }
  } else {
    if (filtered < FINGER_OFF_LEVEL) {
      fingerScore = min(100, fingerScore + 1);
    } else {
      fingerScore = max(0, fingerScore - 1);
    }

    if (fingerScore >= 100) {
      fingerPresent = false;
      fingerScore = 0;
      resetPulse();
    }
  }

  if (fingerPresent) {
    // Remove slow changes caused by contact pressure
    if (baseline == 0) baseline = filtered;
    baseline = 0.995 * baseline + 0.005 * filtered;

    float pulse = filtered - baseline;

    // Learn the recent pulse waveform range
    if (pulse < pulseMin) pulseMin = pulse;
    if (pulse > pulseMax) pulseMax = pulse;

    if (now - rangeStart >= 2500) {
      // Reinitialize range to follow gradual signal changes
      pulseMin = pulse;
      pulseMax = pulse;
      rangeStart = now;
    }

    float amplitude = pulseMax - pulseMin;

    // Require a varying signal before detecting peaks
    if (amplitude > 10) {
      threshold = pulseMin + amplitude * 0.60;

      if (pulse > threshold && !aboveThreshold) {
        aboveThreshold = true;

        if (lastBeat != 0) {
          unsigned long interval = now - lastBeat;

          if (interval >= 600 && interval <= 1500) {
            int candidate = 60000UL / interval;

            if (candidate >= MIN_BPM &&
                candidate <= MAX_BPM) {
              bpm = candidate;
              lastValidBeat = now;
            }
          }
        }

        lastBeat = now;
      }

      if (pulse < pulseMin + amplitude * 0.30) {
        aboveThreshold = false;
      }
    }

    // Remove stale BPM readings
    if (lastValidBeat != 0 &&
        now - lastValidBeat > 10000) {
      bpm = 0;
    }
  }

  if (now - lastDisplay >= 200) {
    lastDisplay = now;

    Serial.print("Raw=");
    Serial.print(raw);
    Serial.print(" Filtered=");
    Serial.print(filtered);
    Serial.print(" Finger=");
    Serial.print(fingerPresent ? "YES" : "NO");
    Serial.print(" BPM=");
    Serial.println(bpm);

    drawDisplay();
  }
}
