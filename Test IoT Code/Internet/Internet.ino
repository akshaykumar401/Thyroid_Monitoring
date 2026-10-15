// #include <WiFi.h>
// #include "esp_wifi.h"

// const char* ssid = "moto";
// const char* password = "Akshaykumar401";

// void setup() {
//   Serial.begin(115200);
//   delay(1000);

//   // Set lower TX power to prevent brownouts/disconnections on Super Mini
//   WiFi.mode(WIFI_STA);
//   WiFi.begin(ssid, password);
//   esp_wifi_set_max_tx_power(WIFI_POWER_8_5dBm); 

//   Serial.print("Connecting to WiFi");
//   while (WiFi.status() != WL_CONNECTED) {
//     delay(500);
//     Serial.print(".");
//   }

//   Serial.println("\nConnected!");
//   Serial.print("IP Address: ");
//   Serial.println(WiFi.localIP());
// }

// void loop() {
// }





#include <WiFi.h>
#include "esp_wifi.h"

// const char* ssid = "Galaxy";
// const char* password = "mummy123";

const char* ssid = "moto";
const char* password = "Akshaykumar401";
#define LED_BUILTIN 8  // Native blue LED pin on Super Mini

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  delay(2000); 

  Serial.println("Initializing System...");

  // CRITICAL STEP: Turn on Wi-Fi settings *without* activating the radio transceiver
  WiFi.mode(WIFI_STA);
  
  // Force the hardware to restrict its power draw BEFORE connecting
  // Lowering it to 8.5dBm prevents the sudden 500mA spike
  esp_wifi_set_max_tx_power(WIFI_POWER_8_5dBm); 

  Serial.println("Power restricted. Now starting Wi-Fi radio...");
  
  // Now it is safe to attempt the connection
  WiFi.begin(ssid, password); 
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    digitalWrite(LED_BUILTIN, HIGH);
    delay(100);
    digitalWrite(LED_BUILTIN, LOW);
    delay(900); 
    Serial.print(".");
  } else {
    // Light stays permanently ON when connected successfully
    digitalWrite(LED_BUILTIN, HIGH); 
    Serial.println("\nSuccessfully Connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
    delay(5000);
    
  }
}

