"""
Score ROI investisseur — rentabilité d'un bien immobilier tunisien.

Deux stratégies de revenus :
- Location classique : loyer mensuel (donné ou estimé via un rendement moyen)
- Location estivale : prix de nuit estimé (modèle M3) x nombre de nuits louées/an
"""

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

FRAIS_ACQUISITION_PCT = 5.0      # frais de notaire/enregistrement ~5%
TAXE_FONCIERE_PCT = 0.5          # taxe foncière annuelle approximative
NUITS_ESTIVALES_AN = 90          # saison estivale tunisienne ~3 mois


def _norm(v):
    if v is None:
        return ""
    if isinstance(v, float) and v != v:  # NaN
        return ""
    return str(v).strip().lower()


def _clean_zone_label(value):
    text = _norm(value)
    if not text:
        return ""
    if any(char.isdigit() for char in text):
        return ""
    text = re.sub(r"[^a-zà-ÿ\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 3:
        return ""
    return text


def compute_roi(prix, loyer_mensuel=None, prix_nuit=None, nuits_an=NUITS_ESTIVALES_AN):
    """Calcule le ROI d'un bien.

    Args:
        prix: prix d'achat en TND
        loyer_mensuel: loyer classique mensuel en TND (optionnel)
        prix_nuit: prix de nuit estival en TND (optionnel)
        nuits_an: nuits louées par an en estival

    Returns:
        dict avec revenus, rendements et score 0-100.
    """
    if not prix or prix <= 0:
        return {"statut": "erreur", "message": "prix invalide"}

    cout_total = prix * (1 + FRAIS_ACQUISITION_PCT / 100)
    revenu_classique = (loyer_mensuel or 0) * 12
    revenu_estival = (prix_nuit or 0) * nuits_an
    revenu_annuel = revenu_classique + revenu_estival

    rendement_brut = revenu_annuel / cout_total * 100 if cout_total else 0
    rendement_net = rendement_brut - TAXE_FONCIERE_PCT
    temps_retour_annees = cout_total / revenu_annuel if revenu_annuel else None

    score = score_roi(rendement_net, revenu_classique > 0, revenu_estival > 0)
    label = label_roi(rendement_net)

    return {
        "statut": "succes",
        "prix": prix,
        "cout_total_acquisition": round(cout_total, 2),
        "loyer_mensuel": loyer_mensuel,
        "prix_nuit": prix_nuit,
        "revenu_annuel_classique": round(revenu_classique, 2),
        "revenu_annuel_estival": round(revenu_estival, 2),
        "revenu_annuel_total": round(revenu_annuel, 2),
        "rendement_brut_pct": round(rendement_brut, 2),
        "rendement_net_pct": round(rendement_net, 2),
        "temps_retour_annees": round(temps_retour_annees, 1) if temps_retour_annees else None,
        "score_roi": score,
        "label_roi": label,
    }


def score_roi(rendement_net, a_classique, a_estival):
    """Score composite 0-100 : rendement + diversification des revenus."""
    score = 0.0
    if rendement_net > 0:
        # 4% -> 50 pts ; 8% -> 100 pts
        score += min(50, max(0, rendement_net / 8 * 100))
    if a_classique:
        score += 25
    if a_estival:
        score += 25
    return round(min(100, score), 1)


def label_roi(rendement_net):
    if rendement_net >= 8:
        return "excellent"
    if rendement_net >= 6:
        return "bon"
    if rendement_net >= 4:
        return "moyen"
    if rendement_net >= 0:
        return "faible"
    return "deficitaire"


def top_zones(limit=10):
    """Meilleures zones par rendement estival estimé (M3) + loyer classique.

    Pour chaque annonce de clean_vente (gouvernorat/ville renseignés),
    estime le revenu estival via M3 et calcule le rendement.
    """
    from pymongo import MongoClient
    from dotenv import load_dotenv

    load_dotenv()
    db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[
        os.getenv("MONGO_DB", "immoinsight")
    ]

    vente = list(db["clean_vente"].find({}))
    estival = list(db["clean_estival"].find({}))

    # Loyer mensuel moyen réel par ville (location classique)
    loyers = {}
    for a in db["clean_location"].find({}):
        ville = _clean_zone_label(a.get("ville"))
        if ville and a.get("prix"):
            loyers.setdefault(ville, []).append(a["prix"])
    loyer_moyen = {v: sum(p) / len(p) for v, p in loyers.items()}

    # Prix nuit moyen réel par ville (estival)
    prix_nuits = {}
    for a in estival:
        ville = _clean_zone_label(a.get("ville"))
        if ville and a.get("prix"):
            prix_nuits.setdefault(ville, []).append(a["prix"])
    prix_nuit_moyen = {v: sum(p) / len(p) for v, p in prix_nuits.items()}

    zones = {}
    for a in vente:
        ville = _clean_zone_label(a.get("ville"))
        gov = _clean_zone_label(a.get("gouvernorat"))
        prix = a.get("prix")
        if not prix or prix <= 0:
            continue
        key = ville or gov
        if not key:
            continue
        zone = zones.setdefault(
            key,
            {"gouvernorat": gov, "ville": ville, "zone_label": key, "total_prix": 0.0, "n": 0},
        )
        zone["total_prix"] += prix
        zone["n"] += 1

    # Loyer estimé : rendement locatif moyen tunisien ~6.5% si pas de donnée
    RENDEMENT_LOUER_DEFAUT = 0.065
    resultats = []
    for key, z in zones.items():
        prix_moyen = z["total_prix"] / z["n"]
        loyer = loyer_moyen.get(z["ville"]) or loyer_moyen.get(z["gouvernorat"]) or None
        if not loyer:
            loyer = prix_moyen * RENDEMENT_LOUER_DEFAUT / 12
        pn = prix_nuit_moyen.get(z["ville"]) or prix_nuit_moyen.get(z["gouvernorat"])
        r = compute_roi(prix_moyen, loyer_mensuel=round(loyer, 0), prix_nuit=pn)
        resultats.append({
            "gouvernorat": z["gouvernorat"],
            "ville": z["ville"],
            "zone_label": z["zone_label"],
            "nb_annonces": z["n"],
            "prix_moyen": round(prix_moyen, 0),
            "loyer_mensuel_estime": round(loyer, 0),
            "prix_nuit_estival_moyen": round(pn, 0) if pn else None,
            **{k: v for k, v in r.items() if k != "statut"},
        })

    resultats.sort(key=lambda x: x.get("rendement_net_pct") or 0, reverse=True)
    return resultats[:limit]


def run():
    print("\n" + "=" * 50)
    print("  ROI - Top zones investissement")
    print("=" * 50)
    for z in top_zones():
        print(
            f"  {z.get('gouvernorat') or z.get('ville'):20s} "
            f"rendement: {z.get('rendement_net_pct')}%  "
            f"score: {z.get('score_roi')}  "
            f"({z.get('label_roi')})"
        )


if __name__ == "__main__":
    run()
