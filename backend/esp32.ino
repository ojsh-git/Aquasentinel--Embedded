/*
  AquaSentinel V1.2 - ESP32 flood-risk node + Wi-Fi data endpoint + Flask upload
  Sense -> Understand -> Predict -> Decide -> Act

  Board   : ESP32 Dev Module (Arduino core)
  Library : ESP32Servo (Library Manager). WiFi, WebServer, ESPmDNS, HTTPClient come with the ESP32 core.

  The ESP32 joins the Wi-Fi below and:
    - serves the latest reading as JSON at http://<ESP32-IP>/data   (dashboard "ESP32 direct")
    - sends every reading to the Flask server at SERVER_URL         (dashboard "Server (Flask)")

  If Wi-Fi or the server fails, the node still runs offline: LEDs, buzzer, gate and Serial log all work.
*/

#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <ESP32Servo.h>
#include <HTTPClient.h>   // NEW: to send readings to Flask

// ---------------- WI-FI ----------------
// ESP32 only connects to 2.4 GHz networks. Set the hotspot to 2.4 GHz if it fails.
const char* WIFI_SSID = "Your_WIFI";
const char* WIFI_PASS = "Your_PASSWORD";
const char* HOSTNAME  = "aquasentinel";

WebServer server(80);

// ---------------- FLASK SERVER (NEW) ----------------
// The laptop running `python backend/app.py`, on the SAME Wi-Fi as the ESP32.
// On the Mac run:  ipconfig getifaddr en0   and put that IP below.
const char* SERVER_URL = "http://<YOUR_SERVER_IP>:5001/api/reading";
const char* DEVICE_ID  = "AquaSentinel-01";
const unsigned long POST_MS       = 2000;   // send a reading every 2 s
const unsigned long POST_RETRY_MS = 10000;  // if the server is down, try again every 10 s
unsigned long lastPost = 0;
bool lastPostOk = true;

// ---------------- PINS ----------------
const int PIN_TRIG   = 18;  // Ultrasonic TRIG
const int PIN_ECHO   = 19;  // Ultrasonic ECHO (through 10k / 20k-22k divider)
const int PIN_RAIN   = 34;  // Rain sensor AO (ADC1 - keeps working with Wi-Fi on)
const int PIN_SERVO  = 13;  // SG90 signal
const int PIN_LED_G  = 25;  // Green  = Low
const int PIN_LED_Y  = 26;  // Yellow = Moderate
const int PIN_LED_R  = 27;  // Red    = High / Critical
const int PIN_BUZZER = 32;  // Active buzzer

// ---------------- CALIBRATION ----------------
// Distance from the sensor face to the EMPTY tank bottom, in cm.
const float SENSOR_TO_BOTTOM_CM = 52.7;

// Water depth that counts as 100% (tank "flood" level), in cm.
const float MAX_LEVEL_CM = 21;

// Rise rate that earns the full rise-rate score, in cm per minute.
const float MAX_RISE_CM_PER_MIN = 5;

// Rain sensor raw ADC values (dry board / fully wet board).
const int RAIN_ADC_DRY = 4095;
const int RAIN_ADC_WET = 1300;

// Servo angles for the gate.
const int GATE_CLOSED_DEG = 0;
const int GATE_OPEN_DEG   = 90;

// ---------------- TIMING ----------------
const unsigned long SAMPLE_MS = 1000;  // one full reading per second
const int HISTORY = 10;                // rise rate is measured over 10 samples

// ---------------- RISK WEIGHTS (sum = 100) ----------------
const float W_LEVEL = 45.0;
const float W_RISE  = 25.0;
const float W_RAIN  = 20.0;
const float W_TREND = 10.0;

// ---------------- STATE ----------------
enum RiskLevel { RISK_LOW, RISK_MODERATE, RISK_HIGH, RISK_CRITICAL };
const char* RISK_NAMES[] = { "LOW", "MODERATE", "HIGH", "CRITICAL" };
const char* RAIN_NAMES[] = { "NO RAIN", "LIGHT", "MODERATE", "HEAVY" };

Servo gate;
bool gateOpen = false;

float history[HISTORY];
int   histIndex = 0;
int   histCount = 0;

float lastLevelCm = 0.0;   // last valid water depth
int   risingCount = 0;     // consecutive samples with a rising trend
unsigned long lastSample = 0;

// Latest reading, sent to the dashboard by /data
bool          haveReading = false;
unsigned long curMs = 0;
float curDistance = -1, curLevelCm = 0, curLevelPct = 0, curRise = 0, curRainPct = 0, curScore = 0;
int   curRainClass = 0;
RiskLevel curRisk = RISK_LOW;

// ---------------- SENSE ----------------

// One ultrasonic ping. Returns distance in cm, or -1 if no echo.
float pingCm() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(20);
  digitalWrite(PIN_TRIG, LOW);

  unsigned long us = pulseIn(PIN_ECHO, HIGH, 30000UL);  // 30 ms timeout
  if (us == 0) return -1.0;
  return us * 0.0343 / 2.0;  // speed of sound ~343 m/s at ~20 C
}

// Median of 5 pings. Rejects single bad readings.
float readDistanceCm() {
  float v[5];
  int n = 0;
  for (int i = 0; i < 5; i++) {
    float d = pingCm();
    if (d > 0) v[n++] = d;
    delay(60);  // let the previous echo die out
  }
  if (n == 0) return -1.0;

  for (int i = 0; i < n - 1; i++) {
    for (int j = i + 1; j < n; j++) {
      if (v[j] < v[i]) { float t = v[i]; v[i] = v[j]; v[j] = t; }
    }
  }
  return v[n / 2];
}

// Rain intensity as 0-100 %.
float readRainPct() {
  long sum = 0;
  for (int i = 0; i < 8; i++) sum += analogRead(PIN_RAIN);
  int raw = sum / 8;

  float pct = 100.0 * (RAIN_ADC_DRY - raw) / (float)(RAIN_ADC_DRY - RAIN_ADC_WET);
  return constrain(pct, 0.0, 100.0);
}

int classifyRain(float pct) {
  if (pct < 10) return 0;  // No rain
  if (pct < 40) return 1;  // Light
  if (pct < 70) return 2;  // Moderate
  return 3;                // Heavy
}

// ---------------- UNDERSTAND ----------------

// Rise rate in cm/min, comparing now against the reading HISTORY samples ago.
float updateRiseRate(float levelCm) {
  float rate = 0.0;
  if (histCount == HISTORY) {
    float oldest = history[histIndex];
    float minutes = (HISTORY * SAMPLE_MS) / 60000.0;
    rate = (levelCm - oldest) / minutes;
  }
  history[histIndex] = levelCm;
  histIndex = (histIndex + 1) % HISTORY;
  if (histCount < HISTORY) histCount++;
  return rate;
}

// ---------------- PREDICT ----------------

float computeRisk(float levelPct, float riseRate, float rainPct) {
  float levelScore = constrain(levelPct, 0.0, 100.0) / 100.0 * W_LEVEL;
  float riseScore  = constrain(riseRate, 0.0, MAX_RISE_CM_PER_MIN) / MAX_RISE_CM_PER_MIN * W_RISE;
  float rainScore  = rainPct / 100.0 * W_RAIN;
  float trendScore = min(risingCount, 5) / 5.0 * W_TREND;

  float score = levelScore + riseScore + rainScore + trendScore;

  // Safety floor: a nearly full tank is dangerous even if it is stable.
  if (levelPct >= 90) score = max(score, 75.0f);
  else if (levelPct >= 75) score = max(score, 50.0f);

  return constrain(score, 0.0, 100.0);
}

// ---------------- DECIDE ----------------

RiskLevel classifyRisk(float score) {
  if (score < 25) return RISK_LOW;
  if (score < 50) return RISK_MODERATE;
  if (score < 75) return RISK_HIGH;
  return RISK_CRITICAL;
}

// ---------------- ACT ----------------

void applyOutputs(RiskLevel level) {
  digitalWrite(PIN_LED_G, level == RISK_LOW);
  digitalWrite(PIN_LED_Y, level == RISK_MODERATE);
  digitalWrite(PIN_LED_R, level >= RISK_HIGH);
  digitalWrite(PIN_BUZZER, level == RISK_CRITICAL);

  // Gate opens at HIGH, and only closes again once risk is back to LOW.
  if (!gateOpen && level >= RISK_HIGH) {
    gate.write(GATE_OPEN_DEG);
    gateOpen = true;
  } else if (gateOpen && level == RISK_LOW) {
    gate.write(GATE_CLOSED_DEG);
    gateOpen = false;
  }
}

// ---------------- SEND TO FLASK (NEW) ----------------
// Converts to the units the Flask server expects:
//   water_level : % of flood mark, 0-100
//   rise_rate   : % of flood mark per minute (sketch measures cm/min)
//   rain        : 0-1 (sketch measures 0-100 %)
// This node has no temperature/humidity sensor; 25 C / 60 % add 0 risk points.
void postToServer(float levelPct, float riseCmPerMin, float rainPct) {
  if (WiFi.status() != WL_CONNECTED) return;
  unsigned long wait = lastPostOk ? POST_MS : POST_RETRY_MS;
  if (millis() - lastPost < wait) return;
  lastPost = millis();

  float pct     = constrain(levelPct, 0.0, 100.0);
  float risePct = riseCmPerMin / MAX_LEVEL_CM * 100.0;

  char body[220];
  snprintf(body, sizeof(body),
    "{\"water_level\":%.2f,\"rise_rate\":%.2f,\"rain\":%.2f,"
    "\"temperature\":25,\"humidity\":60,\"source\":\"LIVE\",\"device_id\":\"%s\"}",
    pct, risePct, rainPct / 100.0, DEVICE_ID);

  HTTPClient http;
  http.setConnectTimeout(800);   // short, so the sensor loop is never held up for long
  http.setTimeout(1000);
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  int code = http.POST((uint8_t*)body, strlen(body));
  http.end();

  bool ok = (code == 200);
  if (ok != lastPostOk) {        // print only when it changes, so the CSV log stays clean
    Serial.print(ok ? "# server OK: " : "# server POST failed, code ");
    Serial.println(ok ? SERVER_URL : String(code));
  }
  lastPostOk = ok;
}

// ---------------- WEB ----------------

void sendCors() {
  server.sendHeader("Access-Control-Allow-Origin", "*");   // lets the dashboard on the laptop read it
  server.sendHeader("Cache-Control", "no-store");
}

void handleData() {
  char buf[360];
  snprintf(buf, sizeof(buf),
    "{\"ok\":%s,\"ms\":%lu,\"distance\":%.1f,\"level_cm\":%.2f,\"level_pct\":%.1f,"
    "\"rise\":%.2f,\"rain_pct\":%.0f,\"rain_class\":\"%s\",\"score\":%.1f,"
    "\"risk\":\"%s\",\"gate\":\"%s\",\"rssi\":%d}",
    haveReading ? "true" : "false", curMs, curDistance, curLevelCm, curLevelPct,
    curRise, curRainPct, RAIN_NAMES[curRainClass], curScore,
    RISK_NAMES[curRisk], gateOpen ? "OPEN" : "CLOSED", (int)WiFi.RSSI());
  sendCors();
  server.send(200, "application/json", buf);
}

void handleRoot() {
  sendCors();
  server.send(200, "text/plain",
    "AquaSentinel node is running.\nLive data: /data\nOpen the dashboard on your laptop.");
}

void setupWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(HOSTNAME);
  WiFi.setSleep(false);            // faster replies to the dashboard
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  Serial.print("Connecting to Wi-Fi \"");
  Serial.print(WIFI_SSID);
  Serial.print("\"");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(300);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi connected. Dashboard address: ");
    Serial.println(WiFi.localIP());
    if (MDNS.begin(HOSTNAME)) {
      MDNS.addService("http", "tcp", 80);
      Serial.println("Also try: aquasentinel.local");
    }
  } else {
    Serial.println("Wi-Fi NOT connected. Running offline; will keep retrying in the background.");
  }

  server.on("/", handleRoot);
  server.on("/data", handleData);
  server.begin();
}

// ---------------- SETUP / LOOP ----------------

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_LED_G, OUTPUT);
  pinMode(PIN_LED_Y, OUTPUT);
  pinMode(PIN_LED_R, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_TRIG, LOW);
  digitalWrite(PIN_BUZZER, LOW);

  gate.setPeriodHertz(50);
  gate.attach(PIN_SERVO, 500, 2400);
  gate.write(GATE_CLOSED_DEG);

  setupWiFi();

  Serial.print("Sending readings to: ");      // NEW
  Serial.println(SERVER_URL);                 // NEW

  Serial.println("ms,distance_cm,level_cm,level_pct,rise_cm_min,rain_pct,rain_class,risk_score,risk_level,gate");
}

void loop() {
  server.handleClient();   // answer the dashboard - must stay ABOVE the timing check

  // Print the IP again whenever Wi-Fi (re)connects
  static bool wasConnected = false;
  bool connected = (WiFi.status() == WL_CONNECTED);
  if (connected && !wasConnected) {
    Serial.print("Wi-Fi connected. Dashboard address: ");
    Serial.println(WiFi.localIP());
  }
  wasConnected = connected;

  if (millis() - lastSample < SAMPLE_MS) return;
  lastSample = millis();

  // SENSE
  float distance = readDistanceCm();
  float rainPct  = readRainPct();

  // If the ultrasonic gave no echo, keep the last valid level.
  float levelCm = lastLevelCm;
  if (distance > 0) {
    levelCm = constrain(SENSOR_TO_BOTTOM_CM - distance, 0.0, SENSOR_TO_BOTTOM_CM);
    lastLevelCm = levelCm;
  }
  float levelPct = levelCm / MAX_LEVEL_CM * 100.0;

  // UNDERSTAND
  float riseRate = updateRiseRate(levelCm);
  if (riseRate > 0.5) risingCount++;
  else risingCount = 0;

  // PREDICT + DECIDE + ACT
  float score = computeRisk(levelPct, riseRate, rainPct);
  RiskLevel level = classifyRisk(score);
  applyOutputs(level);

  // Save for the dashboard
  curMs = millis();
  curDistance = distance;
  curLevelCm = levelCm;
  curLevelPct = levelPct;
  curRise = riseRate;
  curRainPct = rainPct;
  curRainClass = classifyRain(rainPct);
  curScore = score;
  curRisk = level;
  haveReading = true;

  // SEND TO FLASK (NEW) - every 2 s, skipped quietly if Wi-Fi or server is down
  postToServer(levelPct, riseRate, rainPct);

  // LOG (CSV, one line per second)
  Serial.print(millis());            Serial.print(',');
  Serial.print(distance, 1);         Serial.print(',');
  Serial.print(levelCm, 1);          Serial.print(',');
  Serial.print(levelPct, 0);         Serial.print(',');
  Serial.print(riseRate, 1);         Serial.print(',');
  Serial.print(rainPct, 0);          Serial.print(',');
  Serial.print(RAIN_NAMES[curRainClass]); Serial.print(',');
  Serial.print(score, 0);            Serial.print(',');
  Serial.print(RISK_NAMES[level]);   Serial.print(',');
  Serial.println(gateOpen ? "OPEN" : "CLOSED");
}