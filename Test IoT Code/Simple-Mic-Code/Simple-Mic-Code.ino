#include <Arduino.h>
#include <driver/i2s.h>

#define I2S_PORT I2S_NUM_0

#define I2S_SCK 4   // INMP441 SCK
#define I2S_WS  5   // INMP441 WS
#define I2S_SD  6   // INMP441 SD

#define SAMPLE_RATE 16000
#define BUFFER_SIZE 512

int32_t samples[BUFFER_SIZE];

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("==============================");
  Serial.println("ESP32-C3 + INMP441 TEST");
  Serial.println("==============================");

  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = 0,
    .dma_buf_count = 8,
    .dma_buf_len = 256,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK,
    .ws_io_num = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_SD
  };

  i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_PORT, &pin_config);
  i2s_zero_dma_buffer(I2S_PORT);

  Serial.println("I2S initialized!");
  Serial.println("Speak or clap near the microphone...");
}

void loop() {

  size_t bytes_read = 0;

  i2s_read(
    I2S_PORT,
    samples,
    sizeof(samples),
    &bytes_read,
    portMAX_DELAY
  );

  int count = bytes_read / sizeof(int32_t);

  int64_t sum = 0;

  for (int i = 0; i < count; i++) {

    int32_t sample = samples[i] >> 14;

    sum += abs(sample);
  }

  int average = sum / count;

  Serial.println(average);

  delay(20);
}