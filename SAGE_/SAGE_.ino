#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <ESP_I2S.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <TinyGPSPlus.h>
#include "MAX30105.h"
#include "heartRate.h"
#include "spo2_algorithm.h"

// ================= EDIT secrets.h, NOT THIS FILE =================
// WiFi name, password and the laptop's server URL live in secrets.h,
// which is git-ignored. Copy secrets_example.h to secrets.h and fill it in.
#include "secrets.h"
const char* DEVICE_ID  = "sage-01";
const double HOME_LAT  = 19.0000;   // fake demo walk starts here
const double HOME_LON  = 73.0000;
// =================================================================

// ---------------- SpO2 alert tuning ----------------
const int SPO2_LOW = 90;                        // alert if SpO2 stays below this %
const unsigned long SPO2_LOW_MS = 15000;        // ...for this long (ms)
// To TEST the alert quickly, temporarily set SPO2_LOW to 101.

// ---------------- types (must stay above all functions) ----------------
struct Btn { uint8_t pin; bool down; unsigned long since; bool longFired; };
struct Reading { int bpm; bool finger; double lat, lon; int sats; bool gpsFix; float activity; int mic; int spo2; };

// ---------------- pins ----------------
#define OLED_MOSI 16
#define OLED_CLK  15
#define OLED_DC   38
#define OLED_CS   39
#define OLED_RST  7
#define BTN_SOS   1
#define BTN_TALK  2
#define BTN_DEMO  41
#define BUZZER    21
#define I2S_SCK   4
#define I2S_WS    5
#define I2S_SD    6
// I2C: SDA 8, SCL 9   GPS: TX->18, RX->17

// ---------------- fall tuning ----------------
const float IMPACT_THRESHOLD = 25.0;
const float STILL_LOW = 8.5, STILL_HIGH = 11.0;
const unsigned long STILL_TIME = 2000;

Adafruit_SSD1306 display(128, 64, OLED_MOSI, OLED_CLK, OLED_DC, OLED_RST, OLED_CS);
Adafruit_MPU6050 mpu;
MAX30105 sensor;
TinyGPSPlus gps;
I2SClass i2s;

// ---------------- shared data (main loop writes, net task reads) ----------------
Reading shared = {0, false, 0, 0, 0, false, 0, 0, 0};
char pendingEvent[12] = "";
volatile bool sendNow = false;
volatile bool wifiOk = false;
portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

void queueEvent(const char* e) {
  portENTER_CRITICAL(&mux);
  strncpy(pendingEvent, e, sizeof(pendingEvent) - 1);
  pendingEvent[sizeof(pendingEvent) - 1] = 0;
  sendNow = true;
  portEXIT_CRITICAL(&mux);
}

void netTask(void*) {
  unsigned long last = 0, lastTry = 0;
  for (;;) {
    if (WiFi.status() != WL_CONNECTED) {
      wifiOk = false;
      if (millis() - lastTry > 5000) { lastTry = millis(); WiFi.reconnect(); }
      vTaskDelay(500 / portTICK_PERIOD_MS);
      continue;
    }
    if (sendNow || millis() - last > 2000) {
      last = millis();
      Reading r; char ev[12];
      portENTER_CRITICAL(&mux);
      r = shared;
      strcpy(ev, pendingEvent);
      pendingEvent[0] = 0;
      sendNow = false;
      portEXIT_CRITICAL(&mux);

      char body[420];
      snprintf(body, sizeof(body),
        "{\"device_id\":\"%s\",\"uptime_s\":%lu,\"bpm\":%d,\"spo2\":%d,\"finger\":%s,\"event\":\"%s\","
        "\"lat\":%.6f,\"lon\":%.6f,\"sats\":%d,\"gps_fix\":%s,\"activity\":%.2f,\"mic\":%d}",
        DEVICE_ID, millis() / 1000, r.bpm, r.spo2, r.finger ? "true" : "false", ev,
        r.lat, r.lon, r.sats, r.gpsFix ? "true" : "false", r.activity, r.mic);

      HTTPClient http;
      http.begin(SERVER_URL);
      http.addHeader("Content-Type", "application/json");
      http.setTimeout(3000);
      int code = http.POST(body);
      http.end();
      bool ok = (code > 0 && code < 300);
      wifiOk = ok;
      Serial.printf("POST %s -> %d\n", ev[0] ? ev : "reading", code);
      if (!ok && ev[0]) queueEvent(ev);      // retry important events
    }
    vTaskDelay(100 / portTICK_PERIOD_MS);
  }
}

// ---------------- buzzer (non-blocking) ----------------
int bzRemain = 0, bzOn = 0, bzOff = 0;
bool bzIsOn = false;
unsigned long bzT = 0;

void beepPattern(int onMs, int offMs, int reps) {
  bzOn = onMs; bzOff = offMs; bzRemain = reps;
  bzIsOn = true; bzT = millis();
  digitalWrite(BUZZER, HIGH);
}

void updateBuzzer() {
  if (bzRemain <= 0) return;
  unsigned long now = millis();
  if (bzIsOn && now - bzT >= (unsigned long)bzOn) {
    digitalWrite(BUZZER, LOW);
    bzIsOn = false; bzT = now; bzRemain--;
  } else if (!bzIsOn && now - bzT >= (unsigned long)bzOff) {
    digitalWrite(BUZZER, HIGH);
    bzIsOn = true; bzT = now;
  }
}
// patterns: start (200,0,1)  ack (100,100,2)  fall (500,300,3)  sos (80,80,10)  low spo2 (300,200,3)

// ---------------- mic (background task) ----------------
volatile int micAvg = 0, micPeak = 0;

void micTask(void*) {
  int32_t buf[256];
  long long sum = 0; long cnt = 0; int pk = 0;
  unsigned long t = millis();
  for (;;) {
    size_t n = i2s.readBytes((char*)buf, sizeof(buf));
    int c = n / 4;
    for (int i = 0; i < c; i++) {
      int a = abs((int)(buf[i] >> 16));
      sum += a; cnt++;
      if (a > pk) pk = a;
    }
    if (millis() - t >= 100) {
      micAvg = cnt ? (int)(sum / cnt) : 0;
      micPeak = pk;
      sum = 0; cnt = 0; pk = 0; t = millis();
    }
  }
}

// ---------------- buttons ----------------
Btn bSOS{BTN_SOS, false, 0, false}, bTALK{BTN_TALK, false, 0, false}, bDEMO{BTN_DEMO, false, 0, false};

int pollBtn(Btn& b, unsigned long longMs) {
  bool pressed = digitalRead(b.pin) == LOW;
  unsigned long now = millis();
  if (pressed && !b.down) { b.down = true; b.since = now; b.longFired = false; }
  else if (pressed && b.down) {
    if (!b.longFired && now - b.since >= longMs) { b.longFired = true; return 2; }
  } else if (!pressed && b.down) {
    b.down = false;
    if (!b.longFired && now - b.since > 40) return 1;
  }
  return 0;
}

// ---------------- heart rate ----------------
const int N = 10;
float beats[N];
int beatCount = 0, beatIdx = 0;
long lastBeat = 0;
unsigned long lastFingerSeen = 0;

float medianBPM() {
  float tmp[N];
  for (int i = 0; i < beatCount; i++) tmp[i] = beats[i];
  for (int i = 0; i < beatCount - 1; i++)
    for (int j = i + 1; j < beatCount; j++)
      if (tmp[j] < tmp[i]) { float t = tmp[i]; tmp[i] = tmp[j]; tmp[j] = t; }
  return (beatCount % 2) ? tmp[beatCount / 2] : (tmp[beatCount / 2 - 1] + tmp[beatCount / 2]) / 2.0;
}

bool fingerOn() { return lastFingerSeen > 0 && millis() - lastFingerSeen < 1000; }

// ---------------- SpO2 ----------------
const int SPO2_BUF = 100;
uint32_t irBuf[SPO2_BUF], redBuf[SPO2_BUF];
int spoCount = 0, spoDecim = 0;
int spo2Hist[5];
int spo2HistN = 0, spo2HistIdx = 0;
int spo2Value = 0;                 // 0 = no valid reading yet
unsigned long spo2Time = 0;

void spo2Reset() {
  spoCount = 0; spoDecim = 0;
  spo2HistN = 0; spo2HistIdx = 0;
  spo2Value = 0;
}

void spo2AddSample(uint32_t red, uint32_t ir) {
  if (++spoDecim < 4) return;      // 100 Hz -> 25 Hz, which is what the algorithm expects
  spoDecim = 0;
  irBuf[spoCount] = ir;
  redBuf[spoCount] = red;
  spoCount++;
  if (spoCount < SPO2_BUF) return;

  int32_t spo2, hr;
  int8_t spo2Ok, hrOk;
  maxim_heart_rate_and_oxygen_saturation(irBuf, SPO2_BUF, redBuf, &spo2, &spo2Ok, &hr, &hrOk);

  if (spo2Ok && spo2 >= 80 && spo2 <= 100) {
    spo2Hist[spo2HistIdx] = (int)spo2;
    spo2HistIdx = (spo2HistIdx + 1) % 5;
    if (spo2HistN < 5) spo2HistN++;
    int tmp[5];
    for (int i = 0; i < spo2HistN; i++) tmp[i] = spo2Hist[i];
    for (int i = 0; i < spo2HistN - 1; i++)
      for (int j = i + 1; j < spo2HistN; j++)
        if (tmp[j] < tmp[i]) { int t = tmp[i]; tmp[i] = tmp[j]; tmp[j] = t; }
    spo2Value = tmp[spo2HistN / 2];   // median of the last valid readings
    spo2Time = millis();
  }
  // slide the window: keep the newest 75 samples, collect 25 more
  memmove(irBuf, irBuf + 25, 75 * sizeof(uint32_t));
  memmove(redBuf, redBuf + 25, 75 * sizeof(uint32_t));
  spoCount = 75;
}

int currentSpo2() {
  return (fingerOn() && spo2Value > 0 && millis() - spo2Time < 15000) ? spo2Value : 0;
}

// ---------------- state ----------------
bool impactSeen = false;
unsigned long impactTime = 0, stillStart = 0;
String alertText = "";
unsigned long alertUntil = 0;
bool sosCounting = false;
unsigned long sosDeadline = 0;
int lastTick = -1;
float actSum = 0, activity = 0;
int actN = 0;
bool demoActive = false;
int demoStep = 0;
unsigned long lastDemo = 0, lastAct = 0, lastDraw = 0, lastPrint = 0;
unsigned long lowSince = 0;
bool lowAlerted = false;

void raiseAlert(const char* text) {
  alertText = text;
  alertUntil = millis() + 6000;
  Serial.printf(">>> ALERT: %s\n", text);
}

void drawScreen() {
  bool alerting = millis() < alertUntil;
  display.invertDisplay((alerting || sosCounting) && ((millis() / 400) % 2 == 0));
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print("SAGE");
  display.setCursor(32, 0);
  bool fix = gps.location.isValid() && gps.location.age() < 3000;
  if (demoActive) display.print("DEMO");
  else if (fix) display.print("GPS OK");
  else display.printf("gps:%d", gps.satellites.isValid() ? (int)gps.satellites.value() : 0);
  display.setCursor(86, 0);
  display.print(wifiOk ? "net OK" : "net --");

  if (sosCounting) {
    int left = (int)((sosDeadline - millis()) / 1000) + 1;
    display.setTextSize(2);
    display.setCursor(0, 16);
    display.printf("SOS in %d", left);
    display.setTextSize(1);
    display.setCursor(0, 42);
    display.print("Press SOS to cancel");
  } else if (alerting) {
    display.setTextSize(2);
    display.setCursor(0, 22);
    display.print(alertText);
  } else {
    int sp = currentSpo2();
    // heart rate (left)
    display.setTextSize(3);
    display.setCursor(0, 12);
    if (fingerOn() && beatCount >= 5) display.printf("%.0f", medianBPM());
    else display.print("--");
    display.setTextSize(1);
    display.setCursor(0, 38);
    display.print("BPM");
    // SpO2 (right)
    display.setTextSize(3);
    display.setCursor(70, 12);
    if (sp > 0) display.printf("%d", sp);
    else display.print("--");
    display.setTextSize(1);
    display.setCursor(70, 38);
    display.print("SpO2 %");
    // status line
    display.setCursor(0, 45);
    if (!fingerOn()) display.print("no finger");
    else if (sp == 0) display.print("measuring...");
    else display.print("monitoring");
  }

  // mic level bar
  int bar = map(constrain((int)micAvg, 0, 6000), 0, 6000, 0, 92);
  display.drawRect(0, 54, 96, 10, SSD1306_WHITE);
  display.fillRect(2, 56, bar, 6, SSD1306_WHITE);
  display.setCursor(100, 55);
  display.print("MIC");
  display.display();
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Wire.begin(8, 9);
  Serial1.begin(9600, SERIAL_8N1, 18, 17);
  pinMode(BTN_SOS, INPUT_PULLUP);
  pinMode(BTN_TALK, INPUT_PULLUP);
  pinMode(BTN_DEMO, INPUT_PULLUP);
  pinMode(BUZZER, OUTPUT);
  digitalWrite(BUZZER, LOW);

  display.begin(SSD1306_SWITCHCAPVCC);
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("SAGE starting...");
  display.println("Connecting WiFi");
  display.display();

  if (!mpu.begin(0x68, &Wire)) { Serial.println("MPU6050 not found"); while (true) delay(1000); }
  mpu.setAccelerometerRange(MPU6050_RANGE_16_G);
  mpu.setFilterBandwidth(MPU6050_BAND_44_HZ);

  if (!sensor.begin(Wire, I2C_SPEED_FAST)) { Serial.println("MAX30102 not found"); while (true) delay(1000); }
  sensor.setup(0x1F, 4, 2, 400, 411, 4096);   // mode 2 = red + infrared (needed for SpO2)

  i2s.setPins(I2S_SCK, I2S_WS, -1, I2S_SD, -1);
  if (!i2s.begin(I2S_MODE_STD, 16000, I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO, I2S_STD_SLOT_LEFT)) {
    Serial.println("I2S (mic) init failed");
  } else {
    xTaskCreatePinnedToCore(micTask, "mic", 4096, NULL, 1, NULL, 0);
  }

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 10000) delay(250);
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi OK, wearable IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi not connected yet (will keep retrying)");
  }
  xTaskCreatePinnedToCore(netTask, "net", 8192, NULL, 1, NULL, 0);

  beepPattern(200, 0, 1);      // power-on beep
  Serial.println("SAGE running");
}

void loop() {
  updateBuzzer();

  // ----- heart rate + SpO2 -----
  sensor.check();
  while (sensor.available()) {
    long ir = sensor.getFIFOIR();
    long red = sensor.getFIFORed();
    sensor.nextSample();
    if (ir > 30000) lastFingerSeen = millis();
    if (!fingerOn()) { beatCount = 0; beatIdx = 0; lastBeat = 0; spo2Reset(); continue; }
    spo2AddSample((uint32_t)red, (uint32_t)ir);
    if (checkForBeat(ir)) {
      long now = millis();
      if (lastBeat > 0) {
        float bpm = 60000.0 / (now - lastBeat);
        if (bpm > 40 && bpm < 180) {
          beats[beatIdx] = bpm;
          beatIdx = (beatIdx + 1) % N;
          if (beatCount < N) beatCount++;
        }
      }
      lastBeat = now;
    }
  }

  // ----- GPS -----
  while (Serial1.available()) gps.encode(Serial1.read());

  // ----- motion: fall + activity -----
  sensors_event_t a, g, t;
  mpu.getEvent(&a, &g, &t);
  float mag = sqrt(a.acceleration.x * a.acceleration.x +
                   a.acceleration.y * a.acceleration.y +
                   a.acceleration.z * a.acceleration.z);
  actSum += fabs(mag - 9.81);
  actN++;

  if (!impactSeen && mag > IMPACT_THRESHOLD) {
    impactSeen = true; impactTime = millis(); stillStart = 0;
    Serial.printf("IMPACT peak=%.1f\n", mag);
  }
  if (impactSeen) {
    bool still = (mag > STILL_LOW && mag < STILL_HIGH);
    if (still) {
      if (stillStart == 0) stillStart = millis();
      if (millis() - stillStart > STILL_TIME) {
        raiseAlert("FALL!");
        beepPattern(500, 300, 3);
        queueEvent("FALL");
        impactSeen = false;
      }
    } else stillStart = 0;
    if (millis() - impactTime > 8000) impactSeen = false;
  }

  // ----- low SpO2 alert (value must stay low for SPO2_LOW_MS) -----
  {
    int sp = currentSpo2();
    if (sp > 0 && sp < SPO2_LOW) {
      if (lowSince == 0) lowSince = millis();
      if (!lowAlerted && millis() - lowSince > SPO2_LOW_MS) {
        lowAlerted = true;
        raiseAlert("LOW SPO2");
        beepPattern(300, 200, 3);
        queueEvent("LOW_SPO2");
      }
    } else if (sp >= SPO2_LOW || !fingerOn()) {
      lowSince = 0;
      if (sp >= SPO2_LOW + 2 || !fingerOn()) lowAlerted = false;   // re-arm
    }
  }

  // ----- buttons -----
  int r = pollBtn(bSOS, 2000);
  if (sosCounting) {
    int left = (int)((sosDeadline - millis()) / 1000) + 1;
    if (left != lastTick) { lastTick = left; beepPattern(40, 0, 1); }   // tick each second
    if (r == 1) {                         // tap = cancel
      sosCounting = false;
      raiseAlert("SOS CANCEL");
      beepPattern(100, 100, 2);
      queueEvent("SOS_CANCEL");
    } else if (millis() >= sosDeadline) {
      sosCounting = false;
      raiseAlert("SOS SENT");
      beepPattern(80, 80, 10);
      queueEvent("SOS");
    }
  } else if (r == 2) {                    // hold 2 s = start countdown
    sosCounting = true;
    sosDeadline = millis() + 10000;
    lastTick = -1;
  }

  r = pollBtn(bTALK, 700);
  if (r == 1) { raiseAlert("OK NOTED"); beepPattern(100, 100, 2); queueEvent("ACK"); }
  else if (r == 2) { raiseAlert("LISTENING"); beepPattern(60, 0, 1); queueEvent("TALK"); }

  r = pollBtn(bDEMO, 1500);
  if (r == 1) {                           // tap = start/stop fake GPS walk-out
    demoActive = !demoActive;
    demoStep = 0;
    lastDemo = millis();
    if (demoActive) { raiseAlert("DEMO WALK"); queueEvent("DEMO"); }
  } else if (r == 2) {                    // hold = fake fall
    raiseAlert("DEMO FALL");
    beepPattern(500, 300, 3);
    queueEvent("FALL");
  }

  // ----- demo walk: fake GPS leaving the safe zone -----
  if (demoActive && millis() - lastDemo > 2000) {
    lastDemo = millis();
    demoStep++;
    if (demoStep > 40) demoActive = false;
  }

  // ----- every 2 s: activity average + update shared data for the net task -----
  if (millis() - lastAct > 2000) {
    lastAct = millis();
    activity = actN ? actSum / actN : 0;
    actSum = 0; actN = 0;

    bool fix = gps.location.isValid() && gps.location.age() < 3000;
    portENTER_CRITICAL(&mux);
    shared.bpm = (fingerOn() && beatCount >= 5) ? (int)medianBPM() : 0;
    shared.spo2 = currentSpo2();
    shared.finger = fingerOn();
    shared.activity = activity;
    shared.mic = (int)micAvg;
    if (demoActive) {
      shared.lat = HOME_LAT + demoStep * 0.0003;
      shared.lon = HOME_LON;
      shared.sats = 8;
      shared.gpsFix = true;
    } else {
      shared.gpsFix = fix;
      shared.lat = fix ? gps.location.lat() : 0;
      shared.lon = fix ? gps.location.lng() : 0;
      shared.sats = gps.satellites.isValid() ? (int)gps.satellites.value() : 0;
    }
    portEXIT_CRITICAL(&mux);
  }

  // ----- serial summary every 2 s -----
  if (millis() - lastPrint > 2000) {
    lastPrint = millis();
    Serial.printf("bpm=%d spo2=%d finger=%d act=%.2f gps_fix=%d mic=%d net=%d\n",
                  shared.bpm, shared.spo2, shared.finger, activity, shared.gpsFix, (int)micAvg, (int)wifiOk);
  }

  // ----- screen -----
  if (millis() - lastDraw > 250) { lastDraw = millis(); drawScreen(); }
}