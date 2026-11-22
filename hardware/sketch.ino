/*
 * TFB2093 Internet-of-Things — Bonus (a) Standalone Rain-Indicator Hardware
 * Location: Seri Iskandar, Perak, Malaysia (Lat: 4.3590 N, Lon: 100.9849 E)
 * Target MCU: ESP32 DevKit V1 (Wokwi Simulator & Physical Node)
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// Wi-Fi Credentials (Wokwi Virtual Wi-Fi works out of the box with zero cost)
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";

// Open-Meteo Endpoint for Seri Iskandar, Perak, Malaysia (forecast_hours=3 starts from current hour)
const char* OPEN_METEO_URL =
  "https://api.open-meteo.com/v1/forecast?latitude=4.3590&longitude=100.9849"
  "&current=temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"
  "&hourly=precipitation_probability,precipitation&forecast_hours=3&timezone=Asia%2FKuala_Lumpur";

// Pin Definitions
#define PIN_LED_GREEN   14
#define PIN_LED_YELLOW  27
#define PIN_LED_RED     26
#define PIN_BUZZER      25
#define PIN_BTN_MODE     4

// OLED Display Settings
#define SCREEN_WIDTH   128
#define SCREEN_HEIGHT   64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// Telemetry State
float curTemp = 27.5;
float curRH = 84.0;
float curPrecip = 0.0;
float max3hPrecip = 0.0;
float max3hProb = 15.0;
int demoMode = 0; // 0 = Live API, 1 = Force Clear, 2 = Force Watch, 3 = Force Imminent Rain
unsigned long lastPollMs = 0;
const unsigned long POLL_INTERVAL_MS = 60000; // Poll every 60s in simulator

void setIndicators(bool greenOn, bool yellowOn, bool redOn, bool buzzerOn, const char* statusLine) {
  digitalWrite(PIN_LED_GREEN, greenOn ? HIGH : LOW);
  digitalWrite(PIN_LED_YELLOW, yellowOn ? HIGH : LOW);
  digitalWrite(PIN_LED_RED, redOn ? HIGH : LOW);

  if (buzzerOn) {
    tone(PIN_BUZZER, 2400, 350);
  } else {
    noTone(PIN_BUZZER);
  }

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  display.setCursor(0, 0);
  display.println("UTP SERI ISKANDAR IoT");
  display.drawLine(0, 10, 127, 10, SSD1306_WHITE);

  display.setCursor(0, 15);
  display.printf("Temp: %.1fC  RH: %.0f%%\n", curTemp, curRH);

  display.setCursor(0, 29);
  display.printf("3h Rain: %.1fmm (%.0f%%)\n", max3hPrecip, max3hProb);

  display.drawRect(0, 44, 128, 20, SSD1306_WHITE);
  display.setCursor(5, 50);
  display.print(statusLine);
  display.display();

  Serial.printf("[TELEMETRY] T=%.1fC, RH=%.0f%%, 3hRain=%.2fmm, 3hProb=%.0f%% -> %s\n",
                curTemp, curRH, max3hPrecip, max3hProb, statusLine);
}

void evaluateWeatherAlert() {
  if (curPrecip >= 0.2 || max3hPrecip >= 0.5 || max3hProb >= 70.0) {
    setIndicators(false, false, true, true, "ALERT: RAIN IMMINENT");
  } else if (curPrecip >= 0.05 || max3hPrecip >= 0.1 || max3hProb >= 40.0) {
    setIndicators(false, true, false, false, "WATCH: RAIN < 3 HRS");
  } else {
    setIndicators(true, false, false, false, "STATUS: CLEAR [OK]");
  }
}

void fetchSeriIskandarWeather() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(OPEN_METEO_URL);
  int httpCode = http.GET();

  if (httpCode == HTTP_CODE_OK) {
    String payload = http.getString();
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, payload);
    if (!err) {
      curTemp = doc["current"]["temperature_2m"] | 27.5;
      curRH = doc["current"]["relative_humidity_2m"] | 82.0;
      curPrecip = doc["current"]["precipitation"] | 0.0;

      JsonArray probs = doc["hourly"]["precipitation_probability"].as<JsonArray>();
      JsonArray precs = doc["hourly"]["precipitation"].as<JsonArray>();

      max3hProb = 0.0;
      max3hPrecip = curPrecip;
      for (int i = 0; i < 3 && i < probs.size(); i++) {
        float p = probs[i] | 0.0;
        float r = precs[i] | 0.0;
        if (p > max3hProb) max3hProb = p;
        if (r > max3hPrecip) max3hPrecip = r;
      }
      evaluateWeatherAlert();
    }
  } else {
    Serial.printf("[HTTP] Open-Meteo GET failed, code: %d\n", httpCode);
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_BTN_MODE, INPUT_PULLUP);

  Wire.begin(21, 22);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("SSD1306 allocation failed");
  }

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 10);
  display.println("Connecting Wi-Fi...");
  display.println("Node: Seri Iskandar");
  display.display();

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20) {
    delay(400);
    Serial.print(".");
    retries++;
  }
  Serial.println("\nConnected to Wokwi-GUEST Wi-Fi!");
  fetchSeriIskandarWeather();
  lastPollMs = millis();
}

void loop() {
  // Pushbutton cycles demo scenarios for video presentation convenience
  if (digitalRead(PIN_BTN_MODE) == LOW) {
    delay(250);
    demoMode = (demoMode + 1) % 4;
    if (demoMode == 1) {
      curTemp = 31.4; curRH = 68; curPrecip = 0.0; max3hPrecip = 0.0; max3hProb = 15.0;
      evaluateWeatherAlert();
    } else if (demoMode == 2) {
      curTemp = 28.2; curRH = 84; curPrecip = 0.0; max3hPrecip = 0.3; max3hProb = 55.0;
      evaluateWeatherAlert();
    } else if (demoMode == 3) {
      curTemp = 25.1; curRH = 96; curPrecip = 1.4; max3hPrecip = 3.8; max3hProb = 92.0;
      evaluateWeatherAlert();
    } else {
      fetchSeriIskandarWeather();
    }
  }

  if (demoMode == 0 && (millis() - lastPollMs >= POLL_INTERVAL_MS)) {
    fetchSeriIskandarWeather();
    lastPollMs = millis();
  }
  delay(50);
}
