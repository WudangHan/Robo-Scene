// Bibliothèque Arduino « RoboScenePilote » : le langage unifié ROBO-SCÈNE (PROTOCOLE.md v2) pour tout
// microcontrôleur (ESP32, Arduino, Raspberry Pi Pico, Teensy). Dépendance : ArduinoJson 7.
//
// Le micrologiciel firmware/esp32_robot/esp32_robot.ino en est l'exemple complet (servos et roues) ;
// cette bibliothèque en extrait la mécanique commune pour d'autres robots :
//   RoboScenePilote pilote(Serial, "MON-ROBOT", 4, true);
//   pilote.surServos([](const float* deg, int n, uint32_t ms) { /* servos */ });
//   pilote.surPropulsion([](float g, float d) { /* roues */ });
//   pilote.surFiger([]() { /* arrêt immédiat */ });
//   void loop() { pilote.boucle(); }
// Règles imposées : chien de garde (500 ms sans message → roues arrêtées), verrou d'arrêt jusqu'à « reset »,
// lignes illisibles ignorées. Le bornage des angles se fait dans le rappel surServos (limites du montage).
#pragma once
#include <Arduino.h>
#include <ArduinoJson.h>

class RoboScenePilote {
 public:
  typedef void (*FServos)(const float* deg, int n, uint32_t ms);
  typedef void (*FPropulsion)(float g, float d);
  typedef void (*FFiger)();

  RoboScenePilote(Stream& flux, const char* nom, int nServos, bool propulsion)
      : flux_(flux), nom_(nom), n_(nServos), propulsion_(propulsion) {}

  void surServos(FServos f) { fServos_ = f; }
  void surPropulsion(FPropulsion f) { fProp_ = f; }
  void surFiger(FFiger f) { fFiger_ = f; }
  void definirAngles(const float* deg) { for (int i = 0; i < n_ && i < 24; i++) deg_[i] = deg[i]; }
  bool arretActif() const { return estop_; }

  void boucle() {
    while (flux_.available()) {
      char c = flux_.read();
      if (c == '\n') { traiter(); pos_ = 0; }
      else if (pos_ < sizeof(tampon_) - 1) tampon_[pos_++] = c;
    }
    uint32_t t = millis();
    if (t - dernier_ > 500 && (roues_[0] != 0 || roues_[1] != 0)) {
      roues_[0] = roues_[1] = 0;
      if (fProp_) fProp_(0, 0);
    }
    if (t - derniereTel_ >= 50) { derniereTel_ = t; telemetrie(); }
  }

 private:
  void traiter() {
    tampon_[pos_] = 0;
    JsonDocument doc;
    if (deserializeJson(doc, tampon_)) return;            // illisible : ignorée
    dernier_ = millis();
    const char* t = doc["t"] | "";
    if (!strcmp(t, "hello")) info();
    else if (!strcmp(t, "estop")) { estop_ = true; roues_[0] = roues_[1] = 0; if (fFiger_) fFiger_(); }
    else if (!strcmp(t, "reset")) estop_ = false;
    else if (estop_ && (!strcmp(t, "servos") || !strcmp(t, "drive"))) flux_.println("{\"t\":\"err\",\"msg\":\"estop\"}");
    else if (!strcmp(t, "servos")) {
      JsonArray a = doc["deg"];
      if ((int)a.size() != n_) { flux_.println("{\"t\":\"err\",\"msg\":\"nombre d'angles incorrect\"}"); return; }
      for (int i = 0; i < n_ && i < 24; i++) deg_[i] = a[i] | deg_[i];
      if (fServos_) fServos_(deg_, n_, doc["ms"] | 0);
    } else if (!strcmp(t, "drive") && propulsion_) {
      roues_[0] = constrain((float)(doc["l"] | 0.0), -1.0f, 1.0f);
      roues_[1] = constrain((float)(doc["r"] | 0.0), -1.0f, 1.0f);
      if (fProp_) fProp_(roues_[0], roues_[1]);
    }
  }
  void info() {
    JsonDocument d;
    d["t"] = "info"; d["nom"] = nom_; d["fw"] = "sdk-arduino-1.0.0"; d["servos"] = n_; d["propulsion"] = propulsion_;
    serializeJson(d, flux_); flux_.println();
  }
  void telemetrie() {
    JsonDocument d;
    d["t"] = "tel"; d["ms"] = millis();
    JsonArray a = d["deg"].to<JsonArray>();
    for (int i = 0; i < n_ && i < 24; i++) a.add(deg_[i]);
    JsonArray r = d["drive"].to<JsonArray>(); r.add(roues_[0]); r.add(roues_[1]);
    d["estop"] = estop_;
    serializeJson(d, flux_); flux_.println();
  }
  Stream& flux_;
  const char* nom_;
  int n_;
  bool propulsion_;
  float deg_[24] = {0};
  float roues_[2] = {0, 0};
  bool estop_ = false;
  uint32_t dernier_ = 0, derniereTel_ = 0;
  char tampon_[512];
  size_t pos_ = 0;
  FServos fServos_ = nullptr;
  FPropulsion fProp_ = nullptr;
  FFiger fFiger_ = nullptr;
};
