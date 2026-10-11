// Trousse C++17 (un seul en-tête, sans dépendance) pour écrire le pilote d'un robot ROBO-SCÈNE.
// Langage unifié : PROTOCOLE.md v2 — un objet JSON par ligne sur l'entrée et la sortie standard
// (profil : pilote = "externe", commande = ["chemin/vers/le/programme"]).
//
// Usage :
//   struct MonRobot : robo_scene::PiloteRobot {
//     MonRobot() : PiloteRobot("MON-ROBOT", {{"base", 10, 170, 90}, {"tete", 30, 150, 90}}, true) {}
//     void appliquer_servos(const std::vector<double>& deg, int ms) override { /* matériel */ }
//     void appliquer_propulsion(double g, double d) override { /* matériel */ }
//     void figer() override { /* arrêt immédiat, sans couper le couple d'un bipède */ }
//   };
//   int main() { MonRobot r; r.executer(); }
//
// Le petit lecteur JSON ci-dessous ne reconnaît que les champs du langage unifié (t, deg, ms, l, r, nom) ;
// toute ligne illisible est ignorée, jamais interprétée partiellement.
#pragma once
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <iostream>
#include <mutex>
#include <optional>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace robo_scene {

struct Articulation { std::string nom; double min, max, repos; };

namespace json {
inline std::optional<std::string> chaine(const std::string& s, const std::string& cle) {
  auto p = s.find("\"" + cle + "\"");
  if (p == std::string::npos) return std::nullopt;
  p = s.find(':', p);
  if (p == std::string::npos) return std::nullopt;
  p = s.find('"', p);
  if (p == std::string::npos) return std::nullopt;
  std::string out;
  for (size_t i = p + 1; i < s.size(); ++i) {
    if (s[i] == '\\' && i + 1 < s.size()) { out += s[++i]; continue; }
    if (s[i] == '"') return out;
    out += s[i];
  }
  return std::nullopt;
}
inline std::optional<double> nombre(const std::string& s, const std::string& cle) {
  auto p = s.find("\"" + cle + "\"");
  if (p == std::string::npos) return std::nullopt;
  p = s.find(':', p);
  if (p == std::string::npos) return std::nullopt;
  try { size_t n; double v = std::stod(s.substr(p + 1), &n); return v; } catch (...) { return std::nullopt; }
}
inline std::optional<std::vector<double>> liste(const std::string& s, const std::string& cle) {
  auto p = s.find("\"" + cle + "\"");
  if (p == std::string::npos) return std::nullopt;
  auto a = s.find('[', p), b = s.find(']', p);
  if (a == std::string::npos || b == std::string::npos || b < a) return std::nullopt;
  std::vector<double> v;
  std::stringstream ss(s.substr(a + 1, b - a - 1));
  std::string morceau;
  while (std::getline(ss, morceau, ',')) {
    try { v.push_back(std::stod(morceau)); } catch (...) { return std::nullopt; }
  }
  return v;
}
}  // namespace json

class PiloteRobot {
 public:
  PiloteRobot(std::string nom, std::vector<Articulation> arts, bool propulsion)
      : nom_(std::move(nom)), arts_(std::move(arts)), propulsion_(propulsion) {
    for (auto& a : arts_) deg_.push_back(a.repos);
  }
  virtual ~PiloteRobot() = default;
  virtual void appliquer_servos(const std::vector<double>&, int) {}
  virtual void appliquer_propulsion(double, double) {}
  virtual void figer() {}
  virtual std::string etat_supplementaire() { return ""; }   // ex. ",\"vbat\":7.9"

  void executer() {
    std::atomic<bool> actif{true};
    envoyer(info());
    std::thread tel([&] {
      while (actif) {
        auto maintenant = horloge::now();
        { std::lock_guard<std::mutex> v(m_);
          if (maintenant - dernier_ > std::chrono::milliseconds(500) && (roues_[0] != 0 || roues_[1] != 0)) {
            roues_[0] = roues_[1] = 0; appliquer_propulsion(0, 0);
          } }
        envoyer(telemetrie());
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
      }
    });
    std::string ligne;
    while (std::getline(std::cin, ligne)) traiter(ligne);
    actif = false;
    tel.join();
    figer();
  }

  void traiter(const std::string& ligne) {
    auto debut = ligne.find_first_not_of(" \t\r");
    if (debut == std::string::npos || ligne[debut] != '{') return;
    auto t = json::chaine(ligne, "t");
    if (!t) return;
    std::lock_guard<std::mutex> v(m_);
    dernier_ = horloge::now();
    if (*t == "hello") envoyer(info());
    else if (*t == "estop") { estop_ = true; roues_[0] = roues_[1] = 0; figer(); }
    else if (*t == "reset") estop_ = false;
    else if ((*t == "servos" || *t == "drive" || *t == "geste") && estop_) envoyer("{\"t\":\"err\",\"msg\":\"estop\"}");
    else if (*t == "servos") {
      auto deg = json::liste(ligne, "deg");
      if (!deg || deg->size() != arts_.size()) { envoyer("{\"t\":\"err\",\"msg\":\"nombre d'angles incorrect\"}"); return; }
      for (size_t i = 0; i < arts_.size(); ++i) deg_[i] = std::clamp((*deg)[i], arts_[i].min, arts_[i].max);
      appliquer_servos(deg_, static_cast<int>(json::nombre(ligne, "ms").value_or(0)));
    } else if (*t == "drive" && propulsion_) {
      roues_[0] = std::clamp(json::nombre(ligne, "l").value_or(0), -1.0, 1.0);
      roues_[1] = std::clamp(json::nombre(ligne, "r").value_or(0), -1.0, 1.0);
      appliquer_propulsion(roues_[0], roues_[1]);
    }
  }

 private:
  using horloge = std::chrono::steady_clock;
  std::string info() const {
    std::ostringstream o;
    o << "{\"t\":\"info\",\"nom\":\"" << nom_ << "\",\"fw\":\"sdk-cpp-1.0.0\",\"servos\":" << arts_.size()
      << ",\"propulsion\":" << (propulsion_ ? "true" : "false") << "}";
    return o.str();
  }
  std::string telemetrie() {
    std::lock_guard<std::mutex> v(m_);
    std::ostringstream o;
    o << "{\"t\":\"tel\",\"ms\":" << std::chrono::duration_cast<std::chrono::milliseconds>(horloge::now() - t0_).count()
      << ",\"deg\":[";
    for (size_t i = 0; i < deg_.size(); ++i) o << (i ? "," : "") << deg_[i];
    o << "],\"drive\":[" << roues_[0] << "," << roues_[1] << "],\"estop\":" << (estop_ ? "true" : "false")
      << etat_supplementaire() << "}";
    return o.str();
  }
  void envoyer(const std::string& s) {
    std::lock_guard<std::mutex> v(sortie_);
    std::cout << s << "\n" << std::flush;
  }
  std::string nom_;
  std::vector<Articulation> arts_;
  bool propulsion_;
  std::vector<double> deg_;
  double roues_[2] = {0, 0};
  bool estop_ = false;
  horloge::time_point dernier_ = horloge::now(), t0_ = horloge::now();
  std::mutex m_, sortie_;
};

}  // namespace robo_scene
