// Exemple de pilote C++ : robot simulé à deux servos et deux roues (robots/exemple_externe_cpp.toml).
// Compilation : g++ -std=c++17 -O2 -pthread sdk/cpp/exemple_simule.cpp -o sdk/cpp/build/exemple_simule
#include "robo_scene_pilote.hpp"

struct RobotSimule : robo_scene::PiloteRobot {
  RobotSimule() : PiloteRobot("SIM-CPP", {{"base", 10, 170, 90}, {"tete", 30, 150, 90}}, true) {}
  void appliquer_servos(const std::vector<double>&, int) override { /* appel au matériel */ }
  std::string etat_supplementaire() override { return ",\"vbat\":7.9"; }
};

int main() {
  RobotSimule r;
  r.executer();
  return 0;
}
