/*
  Thyroid screening prototype - ESP32-C3 Super Mini firmware

  Hold the button  -> records voice (INMP441) and streams it to Flask
  Release          -> audio is finished, then 30 s of sensor measurement
                      (pulse sensor + DS18B20), summary is sent to Flask.

  WHY THE AUDIO HAD GAPS BEFORE
  The old code uploaded 1024-sample (64 ms) chunks, one HTTP request each.
  A request takes longer than 64 ms, so the queue filled up, the capture task
  stopped calling i2s_read(), the I2S buffer overflowed and samples were lost
  at EVERY chunk boundary.

  HOW THIS VERSION AVOIDS IT
  - The capture task only reads the microphone and writes to a 64 KB ring
    buffer (2 s of audio). It never waits for the network.
  - A separate upload task sends big 0.5 s chunks, with retries.
  - WiFi power-save is OFF (it adds up to 100 ms delay to every packet).
  - Any audio that still cannot be stored is counted and reported to Flask,
    so you can see in the server log if a recording is damaged.

  PINS (unchanged)
    BUTTON GPIO1 (to GND)   BPM sensor GPIO0 (ADC1)   DS18B20 GPIO10 (+4.7k pull-up to 3V3)
    OLED SDA GPIO8, SCL GPIO9
    INMP441: SCK GPIO4, WS GPIO5, SD GPIO3, L/R -> GND, VDD -> 3V3
*/

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_wifi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <driver/i2s.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/stream_buffer.h>
#include <math.h>

// =====================================================
// 1. NETWORK & FLASK SERVER SETTINGS
// =====================================================

const char* WIFI_SSID     = "Hanuman ";
const char* WIFI_PASSWORD = "ak12344321kr";

// Constant Flask server URL
const char* SERVER = "https://thyroid-monitoring.vercel.app";

const char* DEVICE_ID  = "esp32-c3";
const char* SUBJECT_ID = "subject_001";

// true  = hold the button to record, release to stop
// false = press once to start, press again to stop
#define HOLD_TO_RECORD true

// =====================================================
// 2. PINS
// =====================================================

#define BUTTON_PIN 1
#define BPM_PIN 0

#define OLED_SDA 8
#define OLED_SCL 9
#define OLED_ADDRESS 0x3C

#define DS18B20_PIN 10

#define I2S_BCLK 4
#define I2S_WS   5
#define I2S_DIN  3

// =====================================================
// 3. AUDIO SETTINGS
// =====================================================

#define SAMPLE_RATE 16000
#define AUDIO_MAX_SECONDS 30
#define AUDIO_MAX_SAMPLES ((uint32_t)SAMPLE_RATE * AUDIO_MAX_SECONDS)
#define AUDIO_MIN_SECONDS 2                 // shorter recordings are rejected
#define AUDIO_MIN_SAMPLES ((uint32_t)SAMPLE_RATE * AUDIO_MIN_SECONDS)

// The microphone needs ~85 ms to wake up and the DC filter needs a moment to
// settle. Everything in the first 400 ms (and any old data left in the I2S
// buffer from before the button press) is thrown away.
#define STARTUP_DISCARD_MS 400

#define I2S_READ_SAMPLES 256                // samples per i2s_read()
#define I2S_DMA_COUNT 16                    // 16 x 384 samples = 384 ms of hardware buffer
#define I2S_DMA_LEN 384

#define RING_BYTES 65536                    // 2 seconds of audio
#define UPLOAD_CHUNK_BYTES 16384            // 8192 samples = 0.512 s per HTTP request
#define UPLOAD_RETRIES 3

// =====================================================
// 4. PULSE SENSOR SETTINGS
// =====================================================

#define BPM_SAMPLE_MS 5                     // 200 samples per second
#define BPM_MIN 40
#define BPM_MAX 200
#define BEAT_MIN_INTERVAL_MS 300            // 200 BPM
#define BEAT_MAX_INTERVAL_MS 1500           // 40 BPM
// Smallest pulse wave (in ADC counts, 0..4095) that counts as a finger on the sensor.
// If BPM stays "--" with a finger on it, lower this; if it shows noise without a finger, raise it.
#define PULSE_MIN_AMPLITUDE 40.0f

#define MEASURE_SECONDS 30

// =====================================================
// 5. GLOBALS
// =====================================================

Adafruit_SSD1306 display(128, 64, &Wire, -1);

OneWire oneWire(DS18B20_PIN);
DallasTemperature tempSensor(&oneWire);
DeviceAddress tempAddress;
bool tempPresent = false;

StreamBufferHandle_t ring = nullptr;
TaskHandle_t captureTaskHandle = nullptr;
TaskHandle_t uploadTaskHandle = nullptr;

volatile bool stopRequested = false;
volatile bool captureFinished = false;
volatile bool uploadFinished = false;
volatile bool audioFailed = false;
volatile bool audioTooShort = false;

volatile uint32_t capturedSamples = 0;      // samples that reached the ring buffer or were counted as dropped
volatile uint32_t droppedSamples = 0;       // samples lost because the ring buffer was full
volatile uint32_t captureWallMs = 0;        // real time the capture lasted
volatile uint32_t chunkIndex = 0;

String recordingId;

enum AppState { IDLE, RECORDING, MEASURING };
AppState appState = IDLE;

unsigned long recordingStarted = 0;
unsigned long measurementStarted = 0;
unsigned long lastDisplay = 0;
unsigned long lastBpmSecond = 0;

// ----- pulse sensor state -----
float bpm = 0;
float bpmTotal = 0;
int bpmReadings = 0;

float bpLow = 0, bpBase = 0, envMax = 0, envMin = 0;
bool pulseHigh = false;
unsigned long lastBeat = 0;
unsigned long lastBpmSample = 0;
unsigned long beatIntervals[5];
int beatCount = 0, beatIndex = 0;

// ----- temperature state -----
float temperatureC = NAN;
float maximumTemperatureC = NAN;
float tempSumAll = 0, tempSumLate = 0;
int tempCountAll = 0, tempCountLate = 0;
bool tempPending = false;
unsigned long tempRequestedAt = 0;

// ----- button -----
bool lastButtonReading = HIGH;
bool stableButtonState = HIGH;
unsigned long debounceStarted = 0;

// ----- final screening summary & phone sync state -----
float finalAverageBPM = 0;
float finalAverageTemp = NAN;
bool lastSyncSuccessful = false;
bool hasCompletedScreening = false;

// =====================================================
// 6. OLED
// =====================================================

void showMessage(const String& a, const String& b = "", const String& c = "") {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(a);
  if (b.length()) display.println(b);
  if (c.length()) display.println(c);
  display.display();
}

void showFinalSensorDisplay(float avgBpm, float avgTemp, bool phoneSynced) {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);

  // Line 0: Header status
  display.setCursor(0, 0);
  if (phoneSynced) {
    display.println(">> PHONE SYNCED OK <<");
  } else {
    display.println(">> UPLOAD FAILED <<");
  }
  display.drawLine(0, 9, 127, 9, SSD1306_WHITE);

  // Line 1: Final BPM
  display.setCursor(0, 13);
  display.print("Final BPM : ");
  if (avgBpm > 0) {
    display.print((int)round(avgBpm));
    display.println(" BPM");
  } else {
    display.println("--");
  }

  // Line 2: Final Temperature
  display.setCursor(0, 24);
  display.print("Final Temp: ");
  if (isfinite(avgTemp) && avgTemp > 0) {
    display.print(avgTemp, 2);
    display.println(" C");
  } else {
    display.println("--");
  }

  // Line 3: Phone App Confirmation
  display.setCursor(0, 36);
  if (phoneSynced) {
    display.println("Sent -> Phone App");
  } else {
    display.println("Check Flask Server");
  }

  // Line 4: Next Action Guide
  display.setCursor(0, 48);
  display.println(HOLD_TO_RECORD ? "Hold: New Voice Test" : "Press: New Test");

  display.display();
}

void refreshDisplay() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  // If a screening just completed and we are idle, show final results and sync status
  if (hasCompletedScreening && appState == IDLE) {
    display.setCursor(0, 0);
    display.println(lastSyncSuccessful ? "Phone: Data Synced OK" : "Phone: Sync Pending");
    display.drawLine(0, 9, 127, 9, SSD1306_WHITE);

    display.setCursor(0, 13);
    display.print("Avg BPM : ");
    if (finalAverageBPM > 0) {
      display.print((int)round(finalAverageBPM));
      display.println(" BPM");
    } else {
      display.println("--");
    }

    display.setCursor(0, 24);
    display.print("Avg Temp: ");
    if (isfinite(finalAverageTemp) && finalAverageTemp > 0) {
      display.print(finalAverageTemp, 2);
      display.println(" C");
    } else {
      display.println("--");
    }

    display.setCursor(0, 36);
    display.println(lastSyncSuccessful ? "Phone Dashboard Ready" : "Check Flask / WiFi");

    display.setCursor(0, 48);
    display.println(HOLD_TO_RECORD ? "Hold: New Voice Test" : "Press: New Test");

    display.display();
    return;
  }

  display.setCursor(0, 0);
  display.println("Thyroid Prototype");

  display.print("BPM: ");
  if (bpm > 0) display.println(bpm, 1);
  else display.println("--");

  display.print("Temp: ");
  if (isfinite(temperatureC)) {
    display.print(temperatureC, 2);
    display.println(" C");
  } else {
    display.println("--");
  }

  display.print("Max: ");
  if (isfinite(maximumTemperatureC)) {
    display.print(maximumTemperatureC, 2);
    display.println(" C");
  } else {
    display.println("--");
  }

  if (appState == RECORDING) {
    int remaining = AUDIO_MAX_SECONDS - (int)((millis() - recordingStarted) / 1000);
    if (remaining < 0) remaining = 0;
    display.println("Recording audio");
    display.print("Seconds left: ");
    display.println(remaining);
  } else if (appState == MEASURING) {
    int remaining = MEASURE_SECONDS - (int)((millis() - measurementStarted) / 1000);
    if (remaining < 0) remaining = 0;
    display.println("Measuring sensors");
    display.print("Seconds left: ");
    display.println(remaining);
  } else {
    display.println(HOLD_TO_RECORD ? "Hold to record voice" : "Press to record voice");
    display.println(WiFi.status() == WL_CONNECTED ? "WiFi: Connected" : "WiFi: Connecting...");
    display.print("Flask: ");
    display.println(WiFi.status() == WL_CONNECTED ? "Online" : "Offline");
  }

  display.display();
}

// =====================================================
// 7. WIFI
// =====================================================

bool connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return true;

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  esp_wifi_set_max_tx_power(WIFI_POWER_8_5dBm);   // needed on many C3 Super Mini boards
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.printf("Connecting to WiFi '%s'", WIFI_SSID);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    Serial.print(".");
    delay(300);
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    WiFi.setSleep(false);   // modem power-save adds latency to every packet
    Serial.print("WiFi connected, ESP32 IP: ");
    Serial.println(WiFi.localIP());
    return true;
  }

  Serial.printf("WiFi failed, status=%d\n", WiFi.status());
  return false;
}

// =====================================================
// 8. HTTP HELPERS
// =====================================================

bool postJson(const String& url, const String& json) {
  if (!connectWiFi()) return false;

  HTTPClient http;
  http.setConnectTimeout(8000);
  http.setTimeout(15000);

  bool beginOk = false;
  WiFiClientSecure secureClient;
  if (url.startsWith("https://")) {
    secureClient.setInsecure();
    beginOk = http.begin(secureClient, url);
  } else {
    beginOk = http.begin(url);
  }

  if (!beginOk) {
    Serial.println("HTTP begin failed");
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  int code = http.POST(json);

  Serial.printf("POST %s -> HTTP %d\n", url.c_str(), code);
  if (code > 0) Serial.println(http.getString());
  else Serial.println(HTTPClient::errorToString(code));

  http.end();
  return code >= 200 && code < 300;
}

bool startServerRecording() {
  char id[24];
  snprintf(id, sizeof(id), "esp32_%08x", (unsigned)esp_random());
  recordingId = String(id);
  chunkIndex = 0;

  String body = "{\"recording_id\":\"" + recordingId +
                "\",\"subject_id\":\"" + String(SUBJECT_ID) + "\"}";

  Serial.println("Starting server audio session: " + body);
  return postJson(String(SERVER) + "/api/audio/start", body);
}

void cancelServerRecording() {
  postJson(String(SERVER) + "/api/audio/cancel/" + recordingId, "{}");
}

bool finishServerRecording() {
  char body[200];
  snprintf(body, sizeof(body),
           "{\"subject_id\":\"%s\",\"dropped_samples\":%u,\"captured_ms\":%u,\"wall_ms\":%u}",
           SUBJECT_ID,
           (unsigned)droppedSamples,
           (unsigned)((uint64_t)capturedSamples * 1000ULL / SAMPLE_RATE),
           (unsigned)captureWallMs);
  return postJson(String(SERVER) + "/api/audio/finish/" + recordingId, String(body));
}

// Sends one block of PCM. Retries when the answer did not arrive.
// The server ignores a chunk it already has, so a retry is always safe.
bool uploadChunk(const uint8_t* data, size_t bytes) {
  String url = String(SERVER) + "/api/audio/chunk/" + recordingId + "/" + String((unsigned)chunkIndex);

  for (int attempt = 1; attempt <= UPLOAD_RETRIES; attempt++) {
    int code = -1;
    String reply;

    if (connectWiFi()) {
      HTTPClient http;
      http.setConnectTimeout(5000);
      http.setTimeout(12000);

      bool beginOk = false;
      WiFiClientSecure secureClient;
      if (url.startsWith("https://")) {
        secureClient.setInsecure();
        beginOk = http.begin(secureClient, url);
      } else {
        beginOk = http.begin(url);
      }

      if (beginOk) {
        http.addHeader("Content-Type", "application/octet-stream");
        http.addHeader("X-Dropped-Samples", String((unsigned long)droppedSamples));
        code = http.POST((uint8_t*)data, bytes);
        if (code > 0) reply = http.getString();
        else reply = HTTPClient::errorToString(code);
        http.end();
      }
    }

    if (code >= 200 && code < 300) {
      Serial.printf("Chunk %u: %u bytes OK (ring %u/%u, dropped %u)\n",
                    (unsigned)chunkIndex, (unsigned)bytes,
                    (unsigned)(ring ? RING_BYTES - xStreamBufferSpacesAvailable(ring) : 0),
                    (unsigned)RING_BYTES, (unsigned)droppedSamples);
      chunkIndex++;
      return true;
    }

    Serial.printf("Chunk %u attempt %d failed: HTTP %d %s\n",
                  (unsigned)chunkIndex, attempt, code, reply.c_str());

    // 4xx = the server refused the data; sending it again will not help.
    if (code >= 400 && code < 500 && code != 408) return false;

    vTaskDelay(pdMS_TO_TICKS(200 * attempt));
  }
  return false;
}

// =====================================================
// 9. MICROPHONE
// =====================================================

bool setupMicrophone() {
  i2s_config_t config = {};
  config.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  config.sample_rate = SAMPLE_RATE;
  config.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  config.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;      // INMP441 L/R pin -> GND
  config.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  config.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  config.dma_buf_count = I2S_DMA_COUNT;
  config.dma_buf_len = I2S_DMA_LEN;
  config.use_apll = false;
  config.tx_desc_auto_clear = false;
  config.fixed_mclk = 0;

  esp_err_t result = i2s_driver_install(I2S_NUM_0, &config, 0, nullptr);
  if (result != ESP_OK) {
    Serial.printf("I2S driver error: %d\n", result);
    return false;
  }

  i2s_pin_config_t pins = {};
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = I2S_BCLK;
  pins.ws_io_num = I2S_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = I2S_DIN;

  result = i2s_set_pin(I2S_NUM_0, &pins);
  if (result != ESP_OK) {
    Serial.printf("I2S pin error: %d\n", result);
    i2s_driver_uninstall(I2S_NUM_0);
    return false;
  }

  return true;
}

// =====================================================
// 10. AUDIO CAPTURE TASK
//     Reads the microphone and writes to the ring buffer.
//     It NEVER waits for the network.
// =====================================================

void captureAudioTask(void* parameter) {
  int32_t* input = (int32_t*)malloc(I2S_READ_SAMPLES * sizeof(int32_t));
  int16_t* output = (int16_t*)malloc(I2S_READ_SAMPLES * sizeof(int16_t));

  if (input == nullptr || output == nullptr) {
    Serial.println("ERROR: capture buffer allocation failed");
    if (input) free(input);
    if (output) free(output);
    audioFailed = true;
    captureFinished = true;
    vTaskDelete(nullptr);
    return;
  }

  const unsigned long taskStart = millis();
  unsigned long keptStart = 0;
  uint32_t kept = 0;

  // DC blocker: y[n] = x[n] - x[n-1] + 0.995 * y[n-1]   (high-pass, about 13 Hz)
  // Removes the constant offset that otherwise causes clicks and a huge 0-50 Hz component.
  int32_t prevX = 0;
  int32_t prevY = 0;

  while (!stopRequested && kept < AUDIO_MAX_SAMPLES) {
    size_t bytesRead = 0;
    esp_err_t result = i2s_read(I2S_NUM_0, input, I2S_READ_SAMPLES * sizeof(int32_t),
                                &bytesRead, pdMS_TO_TICKS(100));

    if (result != ESP_OK || bytesRead == 0) {
      vTaskDelay(1);
      continue;
    }

    size_t count = bytesRead / sizeof(int32_t);
    bool settled = (millis() - taskStart) >= STARTUP_DISCARD_MS;
    size_t n = 0;

    for (size_t i = 0; i < count; i++) {
      int32_t x = input[i] >> 8;                                   // 24-bit signed sample
      int64_t acc = (int64_t)(x - prevX) + (((int64_t)prevY * 32604) >> 15);
      prevX = x;
      prevY = (int32_t)acc;

      if (settled && (kept + n) < AUDIO_MAX_SAMPLES) {
        int32_t s = (int32_t)(acc >> 8);                           // back to 16-bit range
        if (s > 32767) s = 32767;
        if (s < -32768) s = -32768;
        output[n++] = (int16_t)s;
      }
    }

    if (n == 0) continue;

    if (keptStart == 0) keptStart = millis() - (n * 1000UL / SAMPLE_RATE);

    size_t bytes = n * sizeof(int16_t);
    if (xStreamBufferSpacesAvailable(ring) >= bytes) {
      xStreamBufferSend(ring, output, bytes, 0);                   // 0 = never wait
    } else {
      droppedSamples += n;                                         // upload is too slow: count the loss
    }

    kept += n;
    capturedSamples = kept;
  }

  captureWallMs = keptStart ? (uint32_t)(millis() - keptStart) : 0;

  free(input);
  free(output);

  Serial.printf("Audio capture finished: %u samples (%.2f s), real time %u ms, dropped %u\n",
                (unsigned)kept, kept / (float)SAMPLE_RATE,
                (unsigned)captureWallMs, (unsigned)droppedSamples);

  captureFinished = true;   // must be the last use of the ring buffer
  vTaskDelete(nullptr);
}

// =====================================================
// 11. AUDIO UPLOAD TASK
// =====================================================

void uploadAudioTask(void* parameter) {
  uint8_t* buffer = (uint8_t*)malloc(UPLOAD_CHUNK_BYTES);

  if (buffer == nullptr) {
    Serial.println("ERROR: upload buffer allocation failed");
    audioFailed = true;
    stopRequested = true;
    while (!captureFinished) vTaskDelay(pdMS_TO_TICKS(20));
    uploadFinished = true;
    vTaskDelete(nullptr);
    return;
  }

  size_t filled = 0;

  while (true) {
    bool captureDone = captureFinished;     // read BEFORE draining the ring
    size_t got = xStreamBufferReceive(ring, buffer + filled,
                                      UPLOAD_CHUNK_BYTES - filled, pdMS_TO_TICKS(50));
    filled += got;

    bool drained = captureDone && got == 0;

    if (filled == UPLOAD_CHUNK_BYTES || (drained && filled > 0)) {
      if (!audioFailed && !uploadChunk(buffer, filled)) {
        Serial.println("ERROR: chunk upload failed");
        audioFailed = true;
        stopRequested = true;               // stop recording, keep draining
      }
      filled = 0;
    }

    if (drained) break;
  }

  free(buffer);

  if (audioFailed) {
    Serial.println("Audio not finalized because of an earlier error");
    cancelServerRecording();
  } else if (capturedSamples < AUDIO_MIN_SAMPLES) {
    Serial.println("Recording too short");
    audioTooShort = true;
    cancelServerRecording();
  } else if (finishServerRecording()) {
    Serial.println("WAV created by Flask");
  } else {
    Serial.println("ERROR: Flask could not create the WAV");
    audioFailed = true;
  }

  uploadFinished = true;
  vTaskDelete(nullptr);
}

// =====================================================
// 12. START / STOP RECORDING
// =====================================================

void beginMeasurements();   // defined in section 15

bool startRecording() {
  if (!connectWiFi()) {
    showMessage("WiFi failed", "Check connection");
    return false;
  }

  if (!startServerRecording()) {
    showMessage("Server session failed", "Is Flask running?");
    return false;
  }

  ring = xStreamBufferCreate(RING_BYTES, 1);
  if (ring == nullptr) ring = xStreamBufferCreate(RING_BYTES / 2, 1);   // low-memory fallback
  if (ring == nullptr) {
    Serial.println("Could not allocate ring buffer");
    showMessage("Out of memory");
    cancelServerRecording();
    return false;
  }

  stopRequested = false;
  captureFinished = false;
  uploadFinished = false;
  audioFailed = false;
  audioTooShort = false;
  capturedSamples = 0;
  droppedSamples = 0;
  captureWallMs = 0;

  Serial.printf("Free heap before recording: %u bytes\n", (unsigned)ESP.getFreeHeap());

  recordingStarted = millis();
  appState = RECORDING;
  hasCompletedScreening = false;

  if (xTaskCreate(uploadAudioTask, "AudioUpload", 10240, nullptr, 3, &uploadTaskHandle) != pdPASS) {
    Serial.println("Could not start upload task");
    vStreamBufferDelete(ring);
    ring = nullptr;
    cancelServerRecording();
    appState = IDLE;
    showMessage("Upload task failed");
    return false;
  }

  if (xTaskCreate(captureAudioTask, "AudioCapture", 6144, nullptr, 5, &captureTaskHandle) != pdPASS) {
    Serial.println("Could not start capture task");
    audioFailed = true;
    captureFinished = true;                  // lets the upload task end by itself
    unsigned long waitStart = millis();
    while (!uploadFinished && millis() - waitStart < 5000) delay(20);
    vStreamBufferDelete(ring);
    ring = nullptr;
    appState = IDLE;                         // never stay stuck in RECORDING
    showMessage("Capture task failed");
    return false;
  }

  Serial.println("Recording started");
  showMessage("Recording audio", HOLD_TO_RECORD ? "Release to stop" : "Press to stop");
  return true;
}

void requestStopRecording() {
  if (appState == RECORDING) {
    Serial.println("Stopping recording...");
    stopRequested = true;
  }
}

void onRecordingFinished() {
  captureTaskHandle = nullptr;
  uploadTaskHandle = nullptr;

  if (ring != nullptr) {
    vStreamBufferDelete(ring);
    ring = nullptr;
  }

  Serial.printf("Uploaded chunks: %u, dropped samples: %u\n",
                (unsigned)chunkIndex, (unsigned)droppedSamples);

  if (audioTooShort) {
    showMessage("Recording too short", "Hold for 2+ seconds");
    delay(1500);
    appState = IDLE;
    return;
  }

  if (audioFailed) {
    showMessage("Audio upload failed", "See Serial Monitor");
    delay(2000);
    appState = IDLE;
    return;
  }

  if (droppedSamples > 0) {
    showMessage("Audio saved", "but some audio lost", "Check WiFi signal");
    delay(1500);
  } else {
    showMessage("Audio WAV saved", "Starting sensors");
    delay(700);
  }

  beginMeasurements();
}

// =====================================================
// 13. PULSE SENSOR
// =====================================================

void setupBPM() {
  analogReadResolution(12);
  analogSetPinAttenuation(BPM_PIN, ADC_11db);
  Serial.printf("Initial BPM sensor raw: %d\n", analogRead(BPM_PIN));
}

void resetBeatHistory() {
  beatCount = 0;
  beatIndex = 0;
  bpm = 0;
}

float medianBpmFromIntervals() {
  unsigned long sorted[5];
  for (int i = 0; i < beatCount; i++) sorted[i] = beatIntervals[i];
  for (int i = 1; i < beatCount; i++) {                    // tiny insertion sort
    unsigned long key = sorted[i];
    int j = i - 1;
    while (j >= 0 && sorted[j] > key) {
      sorted[j + 1] = sorted[j];
      j--;
    }
    sorted[j + 1] = key;
  }
  return 60000.0f / (float)sorted[beatCount / 2];
}

// Call as often as possible; it samples itself every BPM_SAMPLE_MS.
void readBPM() {
  unsigned long now = millis();
  if (now - lastBpmSample < BPM_SAMPLE_MS) return;
  lastBpmSample = now;

  int raw = analogRead(BPM_PIN);

  bpLow += 0.25f * (raw - bpLow);            // smooth out electrical noise
  bpBase += 0.003f * (bpLow - bpBase);       // slow baseline (finger pressure, DC level)
  float ac = bpLow - bpBase;                 // the pulse wave itself

  // Follow the wave's top and bottom: the threshold adapts to the signal strength.
  if (ac > envMax) envMax = ac; else envMax += 0.002f * (ac - envMax);
  if (ac < envMin) envMin = ac; else envMin += 0.002f * (ac - envMin);

  float amplitude = envMax - envMin;

  if (lastBeat != 0 && now - lastBeat > 3000) {   // no beat for 3 s
    lastBeat = 0;
    resetBeatHistory();
  }

  if (amplitude < PULSE_MIN_AMPLITUDE) {          // no finger / signal too weak
    pulseHigh = false;
    return;
  }

  float highThreshold = envMin + 0.65f * amplitude;
  float lowThreshold  = envMin + 0.40f * amplitude;

  if (!pulseHigh && ac > highThreshold) {
    pulseHigh = true;

    if (lastBeat == 0) {
      lastBeat = now;
    } else if (now - lastBeat >= BEAT_MIN_INTERVAL_MS) {   // ignore the dicrotic notch
      unsigned long interval = now - lastBeat;

      if (interval <= BEAT_MAX_INTERVAL_MS) {
        beatIntervals[beatIndex] = interval;
        beatIndex = (beatIndex + 1) % 5;
        if (beatCount < 5) beatCount++;
        bpm = medianBpmFromIntervals();                    // median rejects single bad beats
      } else {
        resetBeatHistory();                                // missed beat(s): start again
      }
      lastBeat = now;
    }
  } else if (pulseHigh && ac < lowThreshold) {
    pulseHigh = false;
  }
}

// =====================================================
// 14. DS18B20 TEMPERATURE (non-blocking)
// =====================================================

void setupTemperature() {
  tempSensor.begin();
  tempSensor.setResolution(12);
  tempSensor.setWaitForConversion(false);   // do not freeze the loop for 750 ms

  tempPresent = tempSensor.getDeviceCount() > 0 && tempSensor.getAddress(tempAddress, 0);
  Serial.printf("DS18B20 devices: %d\n", tempSensor.getDeviceCount());
  if (!tempPresent) Serial.println("WARNING: DS18B20 not found (check wiring and 4.7k pull-up)");
}

void updateTemperature(unsigned long now) {
  if (!tempPresent) return;

  if (!tempPending) {
    tempSensor.requestTemperatures();
    tempRequestedAt = now;
    tempPending = true;
    return;
  }

  if (now - tempRequestedAt < 800) return;   // 12-bit conversion needs 750 ms
  tempPending = false;

  float value = tempSensor.getTempC(tempAddress);

  // 85.0 is the sensor's power-on default, not a real measurement.
  if (value == DEVICE_DISCONNECTED_C || !isfinite(value) ||
      value == 85.0f || value < -55 || value > 125) {
    Serial.println("DS18B20 read error");
    return;
  }

  temperatureC = value;
  if (!isfinite(maximumTemperatureC) || value > maximumTemperatureC) maximumTemperatureC = value;

  tempSumAll += value;
  tempCountAll++;

  // The skin needs time to warm the probe: also keep the last 10 s separately.
  if (now - measurementStarted >= (unsigned long)(MEASURE_SECONDS - 10) * 1000UL) {
    tempSumLate += value;
    tempCountLate++;
  }

  Serial.printf("Temperature=%.2f C, maximum=%.2f C\n", temperatureC, maximumTemperatureC);
}

// =====================================================
// 15. SENSOR MEASUREMENT AND SUMMARY UPLOAD
// =====================================================

String jsonNumber(float value, bool valid, int decimals) {
  if (!valid || !isfinite(value)) return "null";
  return String(value, decimals);
}

bool uploadSensorSummary() {
  float averageBPM = bpmReadings > 0 ? bpmTotal / bpmReadings : 0;
  bool bpmValid = bpmReadings > 0 && averageBPM >= BPM_MIN && averageBPM <= BPM_MAX;

  float averageTemp = NAN;
  if (tempCountLate > 0) averageTemp = tempSumLate / tempCountLate;
  else if (tempCountAll > 0) averageTemp = tempSumAll / tempCountAll;

  // Save final computed averages for OLED display & phone sync confirmation
  finalAverageBPM = bpmValid ? averageBPM : (bpm > 0 ? bpm : 0);
  finalAverageTemp = isfinite(averageTemp) && averageTemp > 0 ? averageTemp : (isfinite(maximumTemperatureC) ? maximumTemperatureC : temperatureC);

  String json = "{";
  json += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  json += "\"recording_id\":\"" + recordingId + "\",";
  json += "\"subject_id\":\"" + String(SUBJECT_ID) + "\",";
  json += "\"duration_seconds\":" + String(MEASURE_SECONDS) + ",";
  json += "\"average_bpm\":" + jsonNumber(averageBPM, bpmValid, 2) + ",";
  json += "\"bpm_samples\":" + String(bpmReadings) + ",";
  json += "\"average_temperature_c\":" + jsonNumber(averageTemp, tempCountAll > 0, 2) + ",";
  json += "\"maximum_temperature_c\":" + jsonNumber(maximumTemperatureC, tempCountAll > 0, 2);
  json += "}";

  Serial.println("Sensor summary: " + json);
  return postJson(String(SERVER) + "/api/sensor-batch", json);
}

void beginMeasurements() {
  appState = MEASURING;
  measurementStarted = millis();

  bpm = 0;
  bpmTotal = 0;
  bpmReadings = 0;

  float raw = analogRead(BPM_PIN);
  bpLow = raw;
  bpBase = raw;
  envMax = 0;
  envMin = 0;
  pulseHigh = false;
  lastBeat = 0;
  lastBpmSample = 0;
  resetBeatHistory();

  temperatureC = NAN;
  maximumTemperatureC = NAN;
  tempSumAll = tempSumLate = 0;
  tempCountAll = tempCountLate = 0;
  tempPending = false;

  lastBpmSecond = millis();
  lastDisplay = 0;

  showMessage("Measuring sensors", "Finger on pulse", "sensor + probe");
  Serial.println("Sensor measurement started");
}

void collectMeasurements() {
  unsigned long now = millis();

  readBPM();
  updateTemperature(now);

  if (now - lastBpmSecond >= 1000) {
    lastBpmSecond = now;
    if (bpm >= BPM_MIN && bpm <= BPM_MAX) {
      bpmTotal += bpm;
      bpmReadings++;
    }
    Serial.printf("Current BPM: %.1f\n", bpm);
  }

  if (now - lastDisplay >= 1000) {           // OLED refresh blocks ~25 ms, keep it rare
    lastDisplay = now;
    refreshDisplay();
  }

  if (now - measurementStarted >= (unsigned long)MEASURE_SECONDS * 1000UL) {
    Serial.println("Sensor measurement finished");
    showMessage("Uploading to Phone...", "Please wait...");

    bool sent = uploadSensorSummary();
    lastSyncSuccessful = sent;
    hasCompletedScreening = true;

    // Show final sensor data and phone sync confirmation on the OLED screen
    showFinalSensorDisplay(finalAverageBPM, finalAverageTemp, sent);

    Serial.println("\n===========================================");
    Serial.println("  FINAL SENSOR DATA SENT TO PHONE APP");
    Serial.printf("  Final BPM : %.1f BPM\n", finalAverageBPM);
    Serial.printf("  Final Temp: %.2f C\n", finalAverageTemp);
    Serial.printf("  Phone Synced: %s\n", sent ? "YES (HTTP 200)" : "NO (Failed)");
    Serial.println("===========================================\n");

    // Hold the screen for 4 seconds so the user can clearly see the final data
    delay(4000);
    appState = IDLE;
  }

  delay(1);
}

// =====================================================
// 16. BUTTON
// =====================================================

void handleButton() {
  bool reading = digitalRead(BUTTON_PIN);
  unsigned long now = millis();

  if (reading != lastButtonReading) {
    lastButtonReading = reading;
    debounceStarted = now;
  }

  if (now - debounceStarted < 30) return;
  if (reading == stableButtonState) return;

  stableButtonState = reading;

  if (stableButtonState == LOW) {                       // pressed
    if (appState == IDLE) startRecording();
    else if (appState == RECORDING && !HOLD_TO_RECORD) requestStopRecording();
  } else {                                              // released
    if (HOLD_TO_RECORD && appState == RECORDING) requestStopRecording();
  }
}

// =====================================================
// 17. SETUP AND LOOP
// =====================================================

void setup() {
  Serial.begin(115200);
  delay(500);

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(BPM_PIN, INPUT);

  Wire.begin(OLED_SDA, OLED_SCL);
  Wire.setClock(400000);                                // 100 kHz makes every OLED refresh take ~90 ms

  if (display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDRESS)) {
    showMessage("Thyroid Prototype", "Starting WiFi...");
  } else {
    Serial.println("OLED initialization failed");
  }

  setupTemperature();
  setupBPM();
  connectWiFi();

  if (!setupMicrophone()) {
    showMessage("Microphone error", "Check INMP441 wiring");
    Serial.println("Microphone setup failed");
  } else {
    Serial.println("INMP441 ready");
  }

  showMessage("System ready", HOLD_TO_RECORD ? "Hold to record voice" : "Press to record voice");
  Serial.println("System ready - Hold button to record voice");
}

void loop() {
  handleButton();

  if (appState == RECORDING) {
    if (millis() - lastDisplay >= 500) {
      lastDisplay = millis();
      refreshDisplay();
    }
    if (uploadFinished) onRecordingFinished();
    delay(5);

  } else if (appState == MEASURING) {
    collectMeasurements();

  } else {
    if (millis() - lastDisplay >= 1000) {
      lastDisplay = millis();
      refreshDisplay();
    }
    delay(5);
  }
}
