#include <WiFi.h>
#include "esp_wifi.h"
#include <driver/i2s.h>

// --- Network Settings ---
const char* ssid = "moto";
const char* password = "Akshaykumar401";

// Server Details (Update with your computer's local IPv4)
const char* serverIP = "192.168.3.234"; 
const int serverPort = 5000;

// --- Hardware Pins ---
#define LED_BUILTIN 8   // Onboard Blue LED
#define BUTTON_PIN 9    // Onboard BOOT Button
#define I2S_SD 4        // INMP441 SD (Serial Data)
#define I2S_WS 5        // INMP441 WS (Word Select)
#define I2S_SCK 6       // INMP441 SCK (Clock)

#define I2S_PORT I2S_NUM_0
#define SAMPLE_RATE 16000
#define RECORD_TIME_SEC 60 // Max 1 minute recording

// Processing 512 16-bit samples (1024 bytes) per chunk prevents Wi-Fi stutter
#define SAMPLES_PER_CHUNK 512  

void setupI2S() {
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT, // Native 24/32-bit format of INMP441
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = i2s_comm_format_t(I2S_COMM_FORMAT_STAND_I2S),
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = 512,
    .use_apll = false
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK,
    .ws_io_num = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_SD
  };

  i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_PORT, &pin_config);
}

void streamAudioToServer() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi disconnected!");
    return;
  }

  WiFiClient client;

  Serial.println("Connecting to server...");
  if (!client.connect(serverIP, serverPort)) {
    Serial.println("Server connection failed!");
    return;
  }

  Serial.println("Connected! Streaming clear audio...");

  // Send Chunked HTTP Headers
  client.println("POST /upload HTTP/1.1");
  client.printf("Host: %s:%d\r\n", serverIP, serverPort);
  client.println("Content-Type: audio/l16; rate=16000; channels=1");
  client.println("Transfer-Encoding: chunked");
  client.println("Connection: close");
  client.println();

  int32_t raw_i2s[SAMPLES_PER_CHUNK];
  int16_t pcm16[SAMPLES_PER_CHUNK];
  size_t bytes_read = 0;
  size_t total_sent = 0;

  unsigned long startTime = millis();

  while ((millis() - startTime < RECORD_TIME_SEC * 1000) && (digitalRead(BUTTON_PIN) == LOW)) {
    // Read 32-bit audio samples from I2S DMA
    i2s_read(I2S_PORT, &raw_i2s, sizeof(raw_i2s), &bytes_read, portMAX_DELAY);

    int samplesCount = bytes_read / 4;
    if (samplesCount > 0) {
      for (int i = 0; i < samplesCount; i++) {
        // Shift 14 bits to extract 16-bit PCM and apply 3x clean gain
        int32_t val = (raw_i2s[i] >> 14) * 3;

        // Hard soft-limiting to prevent clipping noise
        if (val > 32767) val = 32767;
        if (val < -32768) val = -32768;

        pcm16[i] = (int16_t)val;
      }

      size_t send_size = samplesCount * 2; // 2 bytes per 16-bit sample

      // Send chunk in standard HTTP Chunked format
      client.printf("%X\r\n", send_size);
      client.write((uint8_t*)pcm16, send_size);
      client.print("\r\n");

      total_sent += send_size;
      
      // Crucial delay to yield CPU time to the Wi-Fi stack and prevent frame drop stutter
      vTaskDelay(1); 
    }
  }

  // End HTTP Chunked Stream
  client.println("0\r\n\r\n");

  Serial.printf("Recording finished! Total bytes sent: %d\n", total_sent);
  client.stop();

  digitalWrite(LED_BUILTIN, HIGH);
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  delay(2000); 

  Serial.println("Initializing System...");

  // Cap Wi-Fi TX power to 8.5dBm to eliminate peak power noise
  WiFi.mode(WIFI_STA);
  esp_wifi_set_max_tx_power(WIFI_POWER_8_5dBm); 

  Serial.println("Connecting Wi-Fi...");
  WiFi.begin(ssid, password); 

  while (WiFi.status() != WL_CONNECTED) {
    digitalWrite(LED_BUILTIN, HIGH);
    delay(100);
    digitalWrite(LED_BUILTIN, LOW);
    delay(900); 
    Serial.print(".");
  }

  digitalWrite(LED_BUILTIN, HIGH); 
  Serial.println("\nSuccessfully Connected!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  setupI2S();
  Serial.println("I2S Microphone Ready. Press BOOT button to record!");
}

void loop() {
  if (digitalRead(BUTTON_PIN) == LOW) {
    delay(50); // Debounce
    if (digitalRead(BUTTON_PIN) == LOW) {
      streamAudioToServer();
      while (digitalRead(BUTTON_PIN) == LOW); // Wait until button is released
    }
  }
}