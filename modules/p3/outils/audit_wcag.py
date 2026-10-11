"""Audit automatisé WCAG 2.2 (A et AA) des pages de l'interface spectateur, par axe-core et Playwright.

    npm install axe-core@4          # dans un dossier de travail ; fournit node_modules/axe-core/axe.min.js
    pip install playwright && playwright install chromium
    python outils/audit_wcag.py --axe chemin/vers/axe.min.js --sortie rapport_axe.json

L'outil lance un serveur P3.2 de démonstration, parcourt chaque écran du public (français et anglais, contraste
élevé, texte agrandi à 200 %) et la page de régie, et consigne les violations par règle et par écran.
Un audit automatisé ne couvre qu'une partie des critères : il complète la revue manuelle et les tests I-8.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from p3_spectateur import Seance  # noqa: E402
from p3_spectateur.serveur import creer_serveur  # noqa: E402

ETIQUETTES = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]


def auditer(page, axe: str, ecran: str) -> dict:
    page.add_script_tag(content=axe)
    r = page.evaluate("""(tags) => axe.run(document, {runOnly: {type: 'tag', values: tags}, resultTypes: ['violations','incomplete']})""",
                      ETIQUETTES)
    return {
        "ecran": ecran,
        "violations": [{"regle": v["id"], "impact": v["impact"], "aide": v["help"], "criteres": [t for t in v["tags"] if t.startswith("wcag") and t[4:5].isdigit()],
                        "noeuds": [n["target"] for n in v["nodes"]][:5]} for v in r["violations"]],
        "a_verifier": [{"regle": v["id"], "aide": v["help"], "noeuds": len(v["nodes"])} for v in r["incomplete"]],
        "regles_reussies": None,
    }


def main(argv=None):
    from playwright.sync_api import sync_playwright
    ap = argparse.ArgumentParser()
    ap.add_argument("--axe", required=True, help="chemin de axe.min.js")
    ap.add_argument("--sortie", default="rapport_axe.json")
    ap.add_argument("--port", type=int, default=8771)
    a = ap.parse_args(argv)
    axe = Path(a.axe).read_text(encoding="utf-8")
    s = Seance(titre="Audit", code="4729", delai_min_s=0, seuil_diffusion=1, afficher_provenance=True)
    httpd = creer_serveur(s, "127.0.0.1", a.port, None, journal=lambda *_: None)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{a.port}"
    resultats = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for langue in ("fr-CA", "en-CA"):
            ctx = b.new_context(viewport={"width": 390, "height": 844}, locale=langue)
            pg = ctx.new_page()
            pg.goto(f"{base}/?code=4729"); pg.wait_for_timeout(300)
            resultats.append(auditer(pg, axe, f"{langue} · accueil"))
            pg.click("#joinBtn"); pg.wait_for_timeout(300)
            s.etiqueter("mixte", "3"); pg.wait_for_timeout(300)
            pg.click(".emo[data-k=saisi]"); pg.wait_for_timeout(300)
            resultats.append(auditer(pg, axe, f"{langue} · saisie (grille, provenance affichée)"))
            pg.click("[data-mode=curseurs]"); pg.wait_for_timeout(200)
            resultats.append(auditer(pg, axe, f"{langue} · saisie (curseurs)"))
            pg.click("nav.tabs [data-go=reglages]"); pg.click("#contrastBtn")
            for _ in range(5):
                pg.click("#larger")
            pg.wait_for_timeout(200)
            resultats.append(auditer(pg, axe, f"{langue} · réglages (contraste élevé, texte 200 %)"))
            pg.click("nav.tabs [data-go=ia]"); pg.wait_for_timeout(200)
            resultats.append(auditer(pg, axe, f"{langue} · IA dans ce spectacle"))
            pg.click("nav.tabs [data-go=aide]"); pg.wait_for_timeout(200)
            resultats.append(auditer(pg, axe, f"{langue} · aide affichée"))
            ctx.close()
        r = b.new_page(viewport={"width": 1280, "height": 900})
        r.goto(f"{base}/regie?cle={s.cle_regie}"); r.wait_for_timeout(800)
        resultats.append(auditer(r, axe, "régie"))
        s.terminer()
        pg = b.new_page(viewport={"width": 390, "height": 844}, locale="fr-CA")
        pg.goto(f"{base}/?code=4729"); pg.click("#joinBtn"); pg.wait_for_timeout(300)
        resultats.append(auditer(pg, axe, "fr-CA · fin de séance"))
        b.close()
    httpd.arret_demande = True
    httpd.shutdown()
    Path(a.sortie).write_text(json.dumps(resultats, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(x["violations"]) for x in resultats)
    print(f"{len(resultats)} écrans audités ; {total} violations (par règle et par écran) ; rapport : {a.sortie}")
    for x in resultats:
        for v in x["violations"]:
            print(f"  [{x['ecran']}] {v['regle']} ({v['impact']}) {v['criteres']} — {v['aide']} — {v['noeuds'][:2]}")
    return total


if __name__ == "__main__":
    main()
