// Exemple minimal : deux servos sur un ESP32, langage unifié par le port USB.
#include <ESP32Servo.h>
#include <RoboScenePilote.h>

Servo base, tete;
RoboScenePilote pilote(Serial, "MINIMAL", 2, false);
const float MIN_DEG[2] = {10, 30}, MAX_DEG[2] = {170, 150};

void servos(const float* deg, int n, uint32_t ms) {
  // Bornage local (défense en profondeur), puis consigne immédiate (interpolation laissée au servo)
  base.write(constrain(deg[0], MIN_DEG[0], MAX_DEG[0]));
  tete.write(constrain(deg[1], MIN_DEG[1], MAX_DEG[1]));
}

void figer() { /* servos maintenus à leur position */ }

void setup() {
  Serial.begin(115200);
  base.attach(13);
  tete.attach(14);
  const float repos[2] = {90, 90};
  pilote.definirAngles(repos);
  pilote.surServos(servos);
  pilote.surFiger(figer);
}

void loop() { pilote.boucle(); }
