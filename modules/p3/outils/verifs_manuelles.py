"""Vérifications semi-automatisées complémentaires de l'audit axe (P3.3) :
2.1.1 clavier et 2.4.7 focus visible, 2.4.11 focus non masqué par la barre fixe, 1.4.10 redistribution à 320 px,
1.4.12 espacement du texte, 2.5.8 taille des cibles (24 px minimum ; 56 px visés).

    python outils/verifs_manuelles.py
"""
from __future__ import annotations
import json, sys, threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from p3_spectateur import Seance  # noqa: E402
from p3_spectateur.serveur import creer_serveur  # noqa: E402

ESPACEMENT = "*{line-height:1.5!important;letter-spacing:.12em!important;word-spacing:.16em!important} p{margin-bottom:2em!important}"


def main(port=8773):
    from playwright.sync_api import sync_playwright
    s = Seance(code="4729", delai_min_s=0, afficher_provenance=True)
    h = creer_serveur(s, "127.0.0.1", port, None, journal=lambda *_: None)
    threading.Thread(target=h.serve_forever, daemon=True).start()
    base, res = f"http://127.0.0.1:{port}", {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 390, "height": 600}, locale="fr-CA")
        pg.goto(base + "/?code=4729"); pg.click("#joinBtn"); pg.wait_for_timeout(300)
        # Clavier : parcours complet au tabulateur depuis le haut de la page.
        pg.evaluate("document.activeElement && document.activeElement.blur()")
        vus, masques, sans_contour = [], [], []
        for _ in range(40):
            pg.keyboard.press("Tab")
            info = pg.evaluate("""() => { const e=document.activeElement; if(!e||e===document.body) return null;
                const r=e.getBoundingClientRect(), nav=document.querySelector('nav.tabs').getBoundingClientRect();
                const cs=getComputedStyle(e); const dansNav=!!e.closest('nav.tabs');
                const cache = !dansNav && r.top >= nav.top - 1;          // entièrement sous la barre fixe
                return {id: e.id || e.dataset.k || e.dataset.go || e.dataset.mode || e.textContent.trim().slice(0,20),
                        cache, contour: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) >= 2,
                        w: r.width, h: r.height}; }""")
            if info is None or info["id"] in [v["id"] for v in vus]:
                break
            vus.append(info)
            if info["cache"]: masques.append(info["id"])
            if not info["contour"]: sans_contour.append(info["id"])
        res["clavier_elements_atteints"] = len(vus)
        res["focus_masque_par_barre_fixe"] = masques
        res["focus_sans_contour_visible"] = sans_contour
        res["cible_min_px"] = round(min(min(v["w"], v["h"]) for v in vus if v["w"] > 0), 1)
        res["cibles_sous_24px"] = [v["id"] for v in vus if 0 < min(v["w"], v["h"]) < 24]
        # Redistribution : 320 px de large, aucun défilement horizontal.
        pg2 = b.new_page(viewport={"width": 320, "height": 640}, locale="fr-CA")
        pg2.goto(base + "/?code=4729"); pg2.click("#joinBtn"); pg2.wait_for_timeout(200)
        res["redistribution_320px_defilement_horizontal"] = pg2.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        # Espacement du texte (1.4.12) : aucun texte tronqué dans les boutons.
        pg2.add_style_tag(content=ESPACEMENT); pg2.wait_for_timeout(200)
        res["espacement_texte_elements_tronques"] = pg2.evaluate("""() => [...document.querySelectorAll('button, p, h1, label')]
             .filter(e => e.offsetParent && (e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1)
                          && getComputedStyle(e).overflow === 'hidden').map(e => e.id || e.textContent.trim().slice(0,20))""")
        res["espacement_defilement_horizontal"] = pg2.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        b.close()
    h.shutdown()
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return res


if __name__ == "__main__":
    main()
