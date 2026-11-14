/*
 * ================================================================
 *  SIMANDIRI - ESP32 GERBANG NODE v2.0
 * ================================================================
 *  Komponen yang dikendalikan ESP32 ini:
 *    1. RFID-RC522   → baca kartu → publish ke MQTT
 *    2. Nextion TFT  → terima perintah MQTT → ganti halaman
 *    3. Solenoid Door Lock → terima perintah MQTT → buka/kunci pintu
 *
 *  Library yang dibutuhkan (Install via Arduino Library Manager):
 *    - WiFi          (bawaan ESP32)
 *    - PubSubClient  (by Nick O'Leary)
 *    - MFRC522       (by GithubCommunity / miguelbalboa)
 *    - SoftwareSerial (jika perlu, atau gunakan Serial2 ESP32)
 *
 *  Koneksi Hardware:
 *  ┌──────────────────────────────────────────────┐
 *  │  RFID-RC522 → ESP32                          │
 *  │    SDA (SS) → GPIO 5                         │
 *  │    SCK      → GPIO 18                        │
 *  │    MOSI     → GPIO 23                        │
 *  │    MISO     → GPIO 19                        │
 *  │    RST      → GPIO 27                        │
 *  │    3.3V     → 3.3V                           │
 *  │    GND      → GND                            │
 *  ├──────────────────────────────────────────────┤
 *  │  Nextion TFT → ESP32 (Serial2)               │
 *  │    TX (Nextion) → GPIO 16 (ESP32 RX2)        │
 *  │    RX (Nextion) → GPIO 17 (ESP32 TX2)        │
 *  │    VCC          → 5V                         │
 *  │    GND          → GND                        │
 *  ├──────────────────────────────────────────────┤
 *  │  Solenoid Door Lock (via Relay Module)       │
 *  │    Relay IN → GPIO 26                        │
 *  │    Relay VCC → 5V                            │
 *  │    Relay GND → GND                           │
 *  │    Solenoid → 12V via NC/NO relay contact    │
 *  └──────────────────────────────────────────────┘
 *
 *  CATATAN RELAY:
 *    Solenoid Door Lock 12V membutuhkan daya terpisah (12V adapter).
 *    Relay digunakan sebagai saklar. Saat UNLOCK: relay ON (NC → NO).
 *    Pastikan relay yang digunakan mampu menangani arus 1A @ 12V.
 * ================================================================
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <MFRC522.h>
#include <SPI.h>

// ================================================================
//  KONFIGURASI — SESUAIKAN DENGAN JARINGAN ANDA
// ================================================================

const char* WIFI_SSID     = "iiiaaammm";      // Ganti dengan SSID Wi-Fi
const char* WIFI_PASSWORD = "anakbaikpolman";   // Ganti dengan password Wi-Fi

// EMQX Public Broker - sangat stabil dan cepat
const char* MQTT_BROKER   = "broker.emqx.io";
const int   MQTT_PORT     = 1883;
const char* MQTT_CLIENT   = "simandiri-esp32-lukit"; // Ganti 'lukit' jadi nama unik Anda

// MQTT Topics — harus sama persis dengan config.py di Python!
const char* TOPIC_RFID_TAP      = "simandiri/lukit/rfid/tap";
const char* TOPIC_GATE_LOCK     = "simandiri/lukit/gate/lock";
const char* TOPIC_NEXTION_PAGE  = "simandiri/lukit/nextion/page";
const char* TOPIC_NEXTION_NAME  = "simandiri/lukit/nextion/name";

// ================================================================
//  PIN DEFINITIONS
// ================================================================

// RFID-RC522
#define RFID_SS_PIN   5
#define RFID_RST_PIN  22

// Solenoid Door Lock (via Relay)
// LOW  = relay aktif (solenoid UNLOCK pada relay NC→NO)
// HIGH = relay tidak aktif (solenoid LOCK)
#define RELAY_PIN     26
#define DOOR_LOCKED   HIGH
#define DOOR_UNLOCKED LOW

// Nextion TFT (Serial2: RX=16, TX=17)
#define NEXTION_RX  16
#define NEXTION_TX  17
#define NEXTION_BAUD 9600

// Buzzer kecil (opsional, untuk feedback tap RFID)
#define BUZZER_PIN  25  // Set -1 jika tidak ada buzzer

// ================================================================
//  GLOBAL OBJECTS
// ================================================================

MFRC522   rfid(RFID_SS_PIN, RFID_RST_PIN);
WiFiClient    wifiClient;
PubSubClient  mqttClient(wifiClient);

String currentNextionPage = "";
bool   doorUnlockScheduled = false;
unsigned long doorUnlockTime = 0;
const unsigned long DOOR_UNLOCK_MS = 15000; // 15 detik (Fallback jika server tidak kirim perintah LOCK)

// ================================================================
//  NEXTION HELPER
// ================================================================

void nextionSend(String cmd) {
  Serial2.print(cmd);
  Serial2.write(0xFF);
  Serial2.write(0xFF);
  Serial2.write(0xFF);
}

void nextionSetPage(String pageName) {
  nextionSend("page " + pageName);
  currentNextionPage = pageName;
  Serial.println("[Nextion] Page → " + pageName);
}

void nextionSetText(String componentId, String text) {
  nextionSend(componentId + ".txt=\"" + text + "\"");
}

// ================================================================
//  DOOR LOCK HELPER
// ================================================================

void doorUnlock() {
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, DOOR_UNLOCKED);
  doorUnlockScheduled = true;
  doorUnlockTime = millis() + DOOR_UNLOCK_MS;
  Serial.println("[Door] UNLOCKED");
}

void doorLock() {
  // Menggunakan mode INPUT untuk memutus arus relay dengan aman pada modul tertentu
  pinMode(RELAY_PIN, INPUT); 
  doorUnlockScheduled = false;
  Serial.println("[Door] LOCKED");

  // Re-inisialisasi RC522 untuk mencegah freeze akibat back-EMF dari solenoid
  delay(100);
  rfid.PCD_Init();
}

// ================================================================
//  MQTT CALLBACK
// ================================================================

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }
  message.trim();

  String topicStr = String(topic);
  Serial.println("[MQTT] " + topicStr + " → " + message);

  // --- Perintah pintu ---
  if (topicStr == TOPIC_GATE_LOCK) {
    if (message == "UNLOCK") {
      doorUnlock();
    } else if (message == "LOCK") {
      doorLock();
    }
  }

  // --- Perintah Nextion halaman ---
  else if (topicStr == TOPIC_NEXTION_PAGE) {
    nextionSetPage(message);
  }

  // --- Nama pegawai untuk ditampilkan di Nextion ---
  else if (topicStr == TOPIC_NEXTION_NAME) {
    // Kirim nama ke komponen teks di halaman Verifikasi
    // Sesuaikan nama komponen dengan yang ada di Nextion Editor Anda
    nextionSetText("t_nama", message);
    Serial.println("[Nextion] Nama pegawai: " + message);
  }
}

// ================================================================
//  WIFI & MQTT CONNECT
// ================================================================

void connectWifi() {
  Serial.print("[WiFi] Menghubungkan ke " + String(WIFI_SSID));
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n[WiFi] Terhubung! IP: " + WiFi.localIP().toString());
}

void connectMqtt() {
  while (!mqttClient.connected()) {
    Serial.print("[MQTT] Menghubungkan ke broker...");
    if (mqttClient.connect(MQTT_CLIENT)) {
      Serial.println(" OK!");
      mqttClient.subscribe(TOPIC_GATE_LOCK);
      mqttClient.subscribe(TOPIC_NEXTION_PAGE);
      mqttClient.subscribe(TOPIC_NEXTION_NAME);
      Serial.println("[MQTT] Subscribe ke topik gerbang.");
    } else {
      Serial.print(" Gagal (rc=");
      Serial.print(mqttClient.state());
      Serial.println("). Coba lagi 3 detik...");
      delay(3000);
    }
  }
}

// ================================================================
//  RFID HELPER
// ================================================================

String getRfidUID() {
  String uid = "";
  for (byte i = 0; i < rfid.uid.size; i++) {
    if (rfid.uid.uidByte[i] < 0x10) uid += "0";
    uid += String(rfid.uid.uidByte[i], HEX);
  }
  uid.toUpperCase();
  return uid;
}

void publishRfidTap(String uid) {
  // Format JSON: {"rfid_uid": "A1B2C3D4"}
  String payload = "{\"rfid_uid\":\"" + uid + "\"}";
  mqttClient.publish(TOPIC_RFID_TAP, payload.c_str());
  Serial.println("[RFID] Tap! UID: " + uid + " → dikirim ke server");

  // Buzzer feedback (jika terpasang)
  if (BUZZER_PIN >= 0) {
    digitalWrite(BUZZER_PIN, HIGH);
    delay(100);
    digitalWrite(BUZZER_PIN, LOW);
  }
}

// ================================================================
//  SETUP
// ================================================================

void setup() {
  Serial.begin(115200);
  Serial.println("\n=== SIMANDIRI ESP32 Gate Node v2.0 ===");

  // Inisialisasi pin
  pinMode(RELAY_PIN, OUTPUT);
  doorLock(); // Pastikan pintu terkunci saat startup

  if (BUZZER_PIN >= 0) {
    pinMode(BUZZER_PIN, OUTPUT);
    digitalWrite(BUZZER_PIN, LOW);
  }

  // Inisialisasi SPI & RFID
  SPI.begin();
  rfid.PCD_Init();
  Serial.println("[RFID] RC522 siap.");

  // Inisialisasi Nextion (Serial2)
  Serial2.begin(NEXTION_BAUD, SERIAL_8N1, NEXTION_RX, NEXTION_TX);
  delay(500);
  nextionSetPage("Standby");
  Serial.println("[Nextion] Serial2 siap.");

  // Koneksi Wi-Fi
  connectWifi();

  // Koneksi MQTT
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setKeepAlive(60);
  connectMqtt();

  Serial.println("[SYS] Sistem siap. Menunggu tap kartu RFID...");
}

// ================================================================
//  LOOP
// ================================================================

void loop() {
  // Reconnect jika MQTT terputus
  if (!mqttClient.connected()) {
    connectMqtt();
  }
  mqttClient.loop();

  // Auto-lock pintu setelah durasi buka habis
  if (doorUnlockScheduled && millis() >= doorUnlockTime) {
    doorLock();
  }

  // Cek apakah ada kartu RFID yang ditap
  if (!rfid.PICC_IsNewCardPresent() || !rfid.PICC_ReadCardSerial()) {
    return;
  }

  String uid = getRfidUID();
  publishRfidTap(uid);

  // Hentikan komunikasi dengan kartu
  rfid.PICC_HaltA();
  rfid.PCD_StopCrypto1();

  // Debounce — tunggu sebentar sebelum baca kartu berikutnya
  delay(1500);
}
