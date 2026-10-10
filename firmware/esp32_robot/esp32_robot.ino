/*
 * ROBO-SCÈNE — micrologiciel ESP32
 * ------------------------------------------------------------------
 * Protocole : un objet JSON par ligne, sur le port série (USB, 115200 bauds)
 * ET sur un serveur TCP Wi-Fi (port 3333). Voir PROTOCOLE.md.
 *
 * Bibliothèques (gestionnaire de bibliothèques de l'IDE Arduino) :
 *   - ESP32Servo  (Kevin Harrington, John K. Bennett)
 *   - ArduinoJson (Benoît Blanchon), version 7.x
 * Carte : « ESP32 Dev Module ». Compilé sans erreur avec le paquet esp32 3.3.12,
 * ESP32Servo 3.2.1 et ArduinoJson 7.4.3 (8 octobre 2026). La branche 2.x du
 * paquet est prévue dans le code mais n’a pas été compilée.
 *
 * SÉCURITÉ : ce code comporte un chien de garde et un arrêt logiciel, mais
 * l'arrêt d'urgence réel doit être un interrupteur coup-de-poing qui COUPE
 * L'ALIMENTATION des moteurs et des servos, indépendamment de l'ESP32.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <ESP32Servo.h>
#include <ArduinoJson.h>

// ───────────── Configuration à adapter ─────────────
#define NOM_ROBOT        "ROBO-SCENE-01"
#define VERSION_FW       "1.0.0"
#define WIFI_MODE_AP     1                 // 1 : l'ESP32 crée son réseau ; 0 : il rejoint le vôtre
#define WIFI_SSID        "ROBO-SCENE-01"
#define WIFI_MDP         "changez-moi-123" // 8 caractères minimum
#define PORT_TCP         3333

const uint8_t N_SERVOS = 4;
const uint8_t BROCHES_SERVOS[N_SERVOS] = {13, 14, 27, 26};
const float   MIN_DEG[N_SERVOS]  = {10, 20, 15, 30};   // doivent égaler config.toml
const float   MAX_DEG[N_SERVOS]  = {170, 160, 165, 150};
const float   REPOS[N_SERVOS]    = {90, 90, 90, 90};

#define PROPULSION       1                 // 0 si le robot n'a pas de roues
// Pilote TB6612FNG (ou L298N en adaptant)
#define PIN_PWMA 25
#define PIN_AIN1 33
#define PIN_AIN2 32
#define PIN_PWMB 4
#define PIN_BIN1 16
#define PIN_BIN2 17
#define PIN_STBY 18
const float PROPULSION_MAX = 0.6;          // plafond embarqué, en plus de celui du pont

#define PIN_VBAT   34      // entrée ADC via pont diviseur
const float RATIO_VBAT = (10.0 + 3.3) / 3.3; // R1 = 10 kΩ, R2 = 3,3 kΩ : 8,4 V → 2,08 V
#define PIN_TRIG   19      // HC-SR04 ; ECHO en 5 V → diviseur de tension obligatoire !
#define PIN_ECHO   23
#define BOUTON_ARRET 1     // 1 si un bouton local est câblé, sinon 0 (broche flottante = arrêt permanent !)
#define PIN_BOUTON 22      // bouton d'arrêt à contact NF vers GND (ouvert = arrêt)

const uint32_t CHIEN_DE_GARDE_MS = 500;
const uint32_t PERIODE_TEL_MS    = 50;
const uint32_t PERIODE_SERVO_MS  = 20;
const uint32_t PERIODE_SONAR_MS  = 100;

// ───────────── État ─────────────
Servo servos[N_SERVOS];
float degActuel[N_SERVOS], degDepart[N_SERVOS], degCible[N_SERVOS];
uint32_t tDebut = 0, duree = 0;
float roueG = 0, roueD = 0;
bool arret = false;
uint32_t dernierMsg = 0, derniereTel = 0, dernierServo = 0, dernierSonar = 0;
float distanceCm = -1;

WiFiServer serveur(PORT_TCP);
WiFiClient client;
String tamponSerie, tamponTcp;

// ───────────── Utilitaires ─────────────
float borner(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

void emettre(JsonDocument &doc) {
  serializeJson(doc, Serial);
  Serial.print('\n');
  if (client && client.connected()) {
    serializeJson(doc, client);
    client.print('\n');
  }
}

void envoyerInfo() {
  JsonDocument d;
  d["t"] = "info"; d["nom"] = NOM_ROBOT; d["fw"] = VERSION_FW;
  d["servos"] = N_SERVOS; d["propulsion"] = (bool)PROPULSION;
  emettre(d);
}

void envoyerErreur(const char *msg) {
  JsonDocument d;
  d["t"] = "err"; d["msg"] = msg;
  emettre(d);
}

// ───────────── Moteurs ─────────────
#if PROPULSION
void pwmInit() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(PIN_PWMA, 20000, 8);
  ledcAttach(PIN_PWMB, 20000, 8);
#else
  ledcSetup(14, 20000, 8); ledcAttachPin(PIN_PWMA, 14);
  ledcSetup(15, 20000, 8); ledcAttachPin(PIN_PWMB, 15);
#endif
}
void pwmEcrire(uint8_t broche, uint8_t canal, uint32_t v) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  (void)canal; ledcWrite(broche, v);
#else
  (void)broche; ledcWrite(canal, v);
#endif
}
void moteur(float v, uint8_t in1, uint8_t in2, uint8_t pwm, uint8_t canal) {
  v = borner(v, -PROPULSION_MAX, PROPULSION_MAX);
  digitalWrite(in1, v > 0.01);
  digitalWrite(in2, v < -0.01);
  pwmEcrire(pwm, canal, (uint32_t)(fabs(v) * 255));
}
#endif

void appliquerRoues(float g, float d) {
  roueG = (arret ? 0 : borner(g, -PROPULSION_MAX, PROPULSION_MAX));
  roueD = (arret ? 0 : borner(d, -PROPULSION_MAX, PROPULSION_MAX));
#if PROPULSION
  moteur(roueG, PIN_AIN1, PIN_AIN2, PIN_PWMA, 14);
  moteur(roueD, PIN_BIN1, PIN_BIN2, PIN_PWMB, 15);
#endif
}

void declencherArret() {
  arret = true;
  appliquerRoues(0, 0);
  for (uint8_t i = 0; i < N_SERVOS; i++) { degDepart[i] = degCible[i] = degActuel[i]; }
  duree = 0;
}

// ───────────── Commandes ─────────────
void traiter(const String &ligne) {
  JsonDocument doc;
  if (deserializeJson(doc, ligne)) return;          // ligne illisible : ignorée
  dernierMsg = millis();
  const char *t = doc["t"] | "";

  if (!strcmp(t, "hb")) return;
  if (!strcmp(t, "hello")) { envoyerInfo(); return; }
  if (!strcmp(t, "estop")) { declencherArret(); return; }
  if (!strcmp(t, "reset")) {
    if (BOUTON_ARRET && digitalRead(PIN_BOUTON) == HIGH) { envoyerErreur("bouton d'arret enfonce"); return; }
    arret = false; return;
  }
  if (arret) { envoyerErreur("estop"); return; }

  if (!strcmp(t, "servos")) {
    JsonArray deg = doc["deg"].as<JsonArray>();
    if (deg.isNull() || deg.size() != N_SERVOS) { envoyerErreur("deg: taille invalide"); return; }
    for (uint8_t i = 0; i < N_SERVOS; i++) {
      degDepart[i] = degActuel[i];
      float v = deg[i].isNull() ? degActuel[i] : deg[i].as<float>();
      degCible[i] = borner(v, MIN_DEG[i], MAX_DEG[i]);   // défense en profondeur
    }
    duree = doc["ms"] | 0;
    tDebut = millis();
    return;
  }
  if (!strcmp(t, "drive")) {
    appliquerRoues(doc["l"] | 0.0f, doc["r"] | 0.0f);
    return;
  }
  envoyerErreur("commande inconnue");
}

void lireFlux(Stream &s, String &tampon) {
  while (s.available()) {
    char c = s.read();
    if (c == '\n') { traiter(tampon); tampon = ""; }
    else if (c != '\r' && tampon.length() < 512) tampon += c;
  }
}

// ───────────── Capteurs ─────────────
float lireVbat() {
  return analogReadMilliVolts(PIN_VBAT) / 1000.0 * RATIO_VBAT;
}

float lireSonar() {
  digitalWrite(PIN_TRIG, LOW); delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long us = pulseIn(PIN_ECHO, HIGH, 15000);  // ~2,5 m maximum
  return us == 0 ? 250.0 : us / 58.0;
}

// ───────────── Programme ─────────────
void setup() {
  Serial.begin(115200);
  pinMode(PIN_BOUTON, INPUT_PULLUP);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
#if PROPULSION
  pinMode(PIN_AIN1, OUTPUT); pinMode(PIN_AIN2, OUTPUT);
  pinMode(PIN_BIN1, OUTPUT); pinMode(PIN_BIN2, OUTPUT);
  pinMode(PIN_STBY, OUTPUT); digitalWrite(PIN_STBY, HIGH);
  pwmInit();
  appliquerRoues(0, 0);
#endif
  for (uint8_t i = 0; i < N_SERVOS; i++) {
    servos[i].setPeriodHertz(50);
    servos[i].attach(BROCHES_SERVOS[i], 500, 2400);
    degActuel[i] = degDepart[i] = degCible[i] = REPOS[i];
    servos[i].write((int)REPOS[i]);
  }
#if WIFI_MODE_AP
  WiFi.softAP(WIFI_SSID, WIFI_MDP);
#else
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_MDP);
#endif
  serveur.begin();
  serveur.setNoDelay(true);
  dernierMsg = millis();
  envoyerInfo();
}

void loop() {
  uint32_t now = millis();

  // Connexion TCP (un seul client à la fois : le pont)
  if (serveur.hasClient()) {
    WiFiClient nouveau = serveur.available();
    if (client && client.connected()) nouveau.stop();
    else { client = nouveau; client.setNoDelay(true); tamponTcp = ""; }
  }
  lireFlux(Serial, tamponSerie);
  if (client && client.connected()) lireFlux(client, tamponTcp);

  // Bouton d'arrêt local (contact NF : HIGH = circuit ouvert = arrêt)
  if (BOUTON_ARRET && digitalRead(PIN_BOUTON) == HIGH && !arret) declencherArret();

  // Chien de garde : silence du pont → roues à l'arrêt, servos immobiles
  if (now - dernierMsg > CHIEN_DE_GARDE_MS && (roueG != 0 || roueD != 0)) appliquerRoues(0, 0);

  // Interpolation linéaire des servos
  if (now - dernierServo >= PERIODE_SERVO_MS) {
    dernierServo = now;
    float a = (duree == 0) ? 1.0f : borner((float)(now - tDebut) / duree, 0, 1);
    for (uint8_t i = 0; i < N_SERVOS; i++) {
      if (!arret) degActuel[i] = degDepart[i] + (degCible[i] - degDepart[i]) * a;
      servos[i].write((int)roundf(degActuel[i]));
    }
  }

  if (now - dernierSonar >= PERIODE_SONAR_MS) { dernierSonar = now; distanceCm = lireSonar(); }

  // Télémétrie
  if (now - derniereTel >= PERIODE_TEL_MS) {
    derniereTel = now;
    JsonDocument d;
    d["t"] = "tel"; d["ms"] = now;
    JsonArray deg = d["deg"].to<JsonArray>();
    for (uint8_t i = 0; i < N_SERVOS; i++) deg.add(roundf(degActuel[i] * 10) / 10);
    JsonArray dr = d["drive"].to<JsonArray>();
    dr.add(roueG); dr.add(roueD);
    d["vbat"] = roundf(lireVbat() * 100) / 100;
    d["dist"] = roundf(distanceCm * 10) / 10;
    d["estop"] = arret;
    emettre(d);
  }
}
