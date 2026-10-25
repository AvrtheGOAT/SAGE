/*
  SAGE: SOS button + siren test sketch (ESP32 DevKit V1, Arduino IDE)

  Wiring
    Push button : one leg to GPIO 27, other leg to GND (uses the internal pull-up)
    Buzzer      : active buzzer + to GPIO 26, - to GND
                  (for a passive buzzer, set PASSIVE_BUZZER to true below)

  Behaviour
    Press once        -> SOS: siren starts immediately, alert sent to the dashboard
    Press twice fast  -> while an SOS is active: cancels a mistaken SOS, siren stops
    Every 3 s         -> asks the backend whether the siren should keep going
                         (it stops when the family responds on the dashboard)
    No WiFi?          -> the siren still works locally; the alert is retried

  Libraries: ArduinoJson (Library Manager). WiFi + HTTPClient are built in.
*/
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ---------- change these ----------
const char* WIFI_SSID   = "YourHotspot";
const char* WIFI_PASS   = "yourpassword";
const char* SERVER      = "http://192.168.1.5:5000";   // laptop's IP (ipconfig), never localhost
const char* DEVICE_KEY  = "change-me-too";              // same as DEVICE_KEY in backend/.env
const char* DEVICE_ID   = "wearable1";
// -----------------------------------

const int  BUTTON_PIN = 27;
const int  BUZZER_PIN = 26;
const bool PASSIVE_BUZZER = false;

const unsigned long DEBOUNCE_MS     = 40;
const unsigned long DOUBLE_PRESS_MS = 700;   // two presses within this window = cancel
const unsigned long POLL_MS         = 3000;

bool sosActive = false;        // siren running
bool sosPending = false;       // SOS not yet delivered to the backend (retry)
bool cancelPending = false;    // cancel not yet delivered
unsigned long lastPoll = 0, lastPressAt = 0, lastEdge = 0;
int  pressCount = 0;
bool lastLevel = HIGH;

// ---------- siren: two-tone, non-blocking ----------
void sirenUpdate() {
  if (!sosActive) { if (PASSIVE_BUZZER) noTone(BUZZER_PIN); else digitalWrite(BUZZER_PIN, LOW); return; }
  bool high = (millis() / 400) % 2;            // alternate every 400 ms
  if (PASSIVE_BUZZER) tone(BUZZER_PIN, high ? 1800 : 1200);
  else digitalWrite(BUZZER_PIN, high ? HIGH : LOW);
}

// ---------- HTTP helpers (short timeouts so the loop never hangs) ----------
int postJson(const char* path, const String& body, String* reply = nullptr) {
  if (WiFi.status() != WL_CONNECTED) return -1;
  HTTPClient http;
  http.begin(String(SERVER) + path);
  http.setTimeout(2500);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  int code = http.POST(body);
  if (reply && code > 0) *reply = http.getString();
  http.end();
  return code;
}

void sendSos() {
  int code = postJson("/api/emergency", String("{\"device\":\"") + DEVICE_ID + "\"}");
  Serial.printf("SOS sent -> %d\n", code);
  sosPending = (code != 200);
}

void sendCancel() {
  String reply;
  int code = postJson("/api/emergency/cancel", String("{\"device\":\"") + DEVICE_ID + "\"}", &reply);
  Serial.printf("Cancel sent -> %d %s\n", code, reply.c_str());
  cancelPending = (code != 200);
}

void pollSiren() {
  if (WiFi.status() != WL_CONNECTED || sosPending || cancelPending) return;
  HTTPClient http;
  http.begin(String(SERVER) + "/api/commands/" + DEVICE_ID);
  http.setTimeout(2500);
  http.addHeader("X-Device-Key", DEVICE_KEY);
  int code = http.GET();
  if (code == 200) {
    JsonDocument doc;
    if (!deserializeJson(doc, http.getString())) {
      bool want = doc["siren"] | false;
      if (want != sosActive) Serial.printf("Siren %s (from dashboard)\n", want ? "ON" : "OFF");
      sosActive = want;
    }
  } else if (code == 401) {
    Serial.println("Backend rejected the device key: check DEVICE_KEY");
  }
  http.end();
}

// ---------- button: single press = SOS, double press while active = cancel ----------
void handleButton() {
  bool level = digitalRead(BUTTON_PIN);
  unsigned long now = millis();
  if (level != lastLevel && now - lastEdge > DEBOUNCE_MS) {
    lastEdge = now;
    lastLevel = level;
    if (level == LOW) {                         // pressed
      if (!sosActive) {                         // first press: raise the alarm straight away
        sosActive = true; sosPending = true; cancelPending = false;
        pressCount = 1; lastPressAt = now;
        Serial.println("SOS pressed: siren ON");
        sendSos();
      } else if (now - lastPressAt <= DOUBLE_PRESS_MS) {
        pressCount = 0;                         // second quick press: cancel
        sosActive = false; sosPending = false; cancelPending = true;
        Serial.println("Double press: SOS cancelled, siren OFF");
        sendCancel();
      } else {
        lastPressAt = now;                      // a slow single press while active: start a new double-press window
      }
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 10000) { delay(300); Serial.print("."); }
  Serial.println(WiFi.status() == WL_CONNECTED ? "\nWiFi connected: " + WiFi.localIP().toString() : "\nNo WiFi yet: SOS siren still works offline");
}

void loop() {
  handleButton();
  sirenUpdate();
  unsigned long now = millis();
  if (now - lastPoll > POLL_MS) {
    lastPoll = now;
    if (WiFi.status() != WL_CONNECTED) WiFi.reconnect();   // at most every 3 s
    if (sosPending) sendSos();                  // retry until the dashboard has it
    if (cancelPending) sendCancel();
    pollSiren();
  }
}
