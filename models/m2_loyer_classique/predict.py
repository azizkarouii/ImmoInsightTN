import os
import re
import json
import statistics
import joblib
from dotenv import load_dotenv

load_dotenv()
MODEL_DIR = os.path.join(os.path.dirname(__file__), "artifacts")

# Références marché Tunisie (DT/m²/mois) — affinées en Juillet 2026
REF_MANUELLES = {
    "la marsa": 18.0,
    "carthage": 20.0,
    "sidi bou said": 22.0,
    "gammarth": 19.0,
    "les berges du lac": 16.0,
    "lac": 16.0,
    "la goulette": 13.0,
    "tunis": 12.0,
    "el menzah": 12.5,
    "el manar": 12.0,
    "mutuelleville": 13.0,
    "chotrana": 10.0,
    "ariana": 11.0,
    "la soukra": 12.0,
    "raoued": 9.0,
    "hammamet": 14.0,
    "nabeul": 10.0,
    "sousse": 10.0,
    "monastir": 9.0,
    "sfax": 8.0,
    "djerba": 11.0,
    "mahdia": 8.0,
}

# Quartiers/zonings fréquents → ville (pour titres sans ville explicite)
QUARTIER_MAP = {
    "el manar": "tunis",
    "manar": "tunis",
    "chotrana": "tunis",
    "borj louzir": "tunis",
    "sidi hassine": "tunis",
    "la goulette": "la goulette",
    "el menzah": "tunis",
    "mutuelleville": "tunis",
    "lac": "les berges du lac",
    "cité lac": "les berges du lac",
    "le bardo": "tunis",
    "marsa": "la marsa",
    "gammarth": "gammarth",
    "carthage": "carthage",
    "sidi bou said": "sidi bou said",
    "kantaoui": "sousse",
    "hammam sousse": "hammamet",
    "hammamet": "hammamet",
    "monastir": "monastir",
    "nabeul": "nabeul",
    "sfax": "sfax",
    "sousse": "sousse",
    "djerba": "djerba",
    "mahdia": "mahdia",
    "raoued": "raoued",
    "soukra": "la soukra",
}


def _charger_references():
    path = os.path.join(MODEL_DIR, "references.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _contient(texte, zone):
    """Correspondance sur mots entiers : 'tunisie' ne doit pas matcher 'tunis'."""
    return re.search(rf"\b{re.escape(zone)}\b", texte) is not None


def _ville_depuis_titre(titre):
    if not titre:
        return None
    t = titre.lower()
    for key, ville in QUARTIER_MAP.items():
        if _contient(t, key):
            return ville
    return None


# Repli quand la zone est inconnue : médiane des références marché, plutôt qu'une
# valeur mesurée sur une ou deux annonces (un studio meublé à 50 DT/m² rendait
# une ville inconnue plus chère que La Marsa)
REF_MARCHE_MEDIANE = statistics.median(REF_MANUELLES.values())


def _prix_m2_pour(annonce, refs):
    """Retourne (prix/m², source de la référence)."""
    ville = (annonce.get("ville") or "").strip().lower()
    titre = (annonce.get("titre") or "").lower()

    # 1. Référence mesurée par ville (données clean_location, >= 3 annonces)
    for nom, val in refs.get("par_ville", {}).items():
        if ville and nom.lower() == ville:
            return val, f"mesure:{nom}"

    # 2. Ville connue → référence marché
    if ville:
        if ville in REF_MANUELLES:
            return REF_MANUELLES[ville], f"marche:{ville}"
        for zone, val in REF_MANUELLES.items():
            if _contient(ville, zone):
                return val, f"marche:{zone}"
        ville_quartier = _ville_depuis_titre(ville)
        if ville_quartier in REF_MANUELLES:
            return REF_MANUELLES[ville_quartier], f"marche:{ville_quartier}"

    # 3. Quartier/zone connu directement dans le titre (el manar, chotrana...)
    for zone, val in REF_MANUELLES.items():
        if _contient(titre, zone):
            return val, f"marche:{zone}"

    # 4. Ville devinée depuis le titre
    ville_titre = _ville_depuis_titre(titre)
    if ville_titre in REF_MANUELLES:
        return REF_MANUELLES[ville_titre], f"marche:{ville_titre}"

    # 5. Référence mesurée par type de bien (>= 3 annonces)
    type_bien = annonce.get("type_bien") or "appartement"
    if refs.get("par_type", {}).get(type_bien):
        return refs["par_type"][type_bien], f"mesure:{type_bien}"

    # 6. Médiane du marché
    return refs.get("prix_m2_mediane") or REF_MARCHE_MEDIANE, "defaut"


def _charger_modele():
    model_path = os.path.join(MODEL_DIR, "model.pkl")
    metrics_path = os.path.join(MODEL_DIR, "metrics.json")
    if not (os.path.exists(model_path) and os.path.exists(metrics_path)):
        return None
    with open(metrics_path, encoding="utf-8") as f:
        metrics = json.load(f)
    return joblib.load(model_path), metrics


def predict_one(annonce):
    """Loyer estimé par le modèle appris, ou par le barème de références à défaut."""
    charge = _charger_modele()
    if charge is None:
        return predict_reference(annonce)

    from models.zone_encoding import ZoneEncoder
    from models.m2_loyer_classique.train import to_frame, predict_frame

    model, metrics = charge
    encoders = {k: ZoneEncoder.from_dict(v) for k, v in metrics["encoders"].items()}
    df = to_frame([{**annonce, "prix": None}])
    loyer = float(predict_frame(model, encoders, df)[0])
    surface = annonce.get("surface")
    zone = next((annonce.get(k) for k in ["ville", "gouvernorat"] if encoders[k].known(annonce.get(k))), None)
    return {
        "loyer_estime": round(loyer, 2),
        "prix_m2_reference": round(loyer / surface, 2) if surface else None,
        "intervalle_bas": round(loyer * metrics["ratio_p10"], 2),
        "intervalle_haut": round(loyer * metrics["ratio_p90"], 2),
        "modele": "M2-lightgbm",
        "source_reference": f"zone:{zone}" if zone else "zone inconnue",
        "zone_reconnue": zone,
        "n_annonces_entrainement": metrics["n"],
    }


def predict_reference(annonce):
    refs = _charger_references()
    prix_m2, source = _prix_m2_pour(annonce, refs)
    surface = annonce.get("surface")

    loyer = surface * prix_m2 if surface else None

    # Fallback : loyer par pièce (étude marché : studio 650-900, 2P 800-1200, 3P 1000-1500 DT)
    if loyer is None:
        nb_pieces = annonce.get("nb_pieces") or annonce.get("nb_chambres")
        if nb_pieces:
            if nb_pieces <= 1:
                loyer = 800.0
            elif nb_pieces == 2:
                loyer = 1000.0
            elif nb_pieces == 3:
                loyer = 1300.0
            else:
                loyer = 1600.0
        else:
            loyer = prix_m2 * 80  # hypothèse ~80 m²

    return {
        "loyer_estime": round(float(loyer), 2),
        "prix_m2_reference": round(float(prix_m2), 2),
        "intervalle_bas": round(float(loyer * 0.85), 2),
        "intervalle_haut": round(float(loyer * 1.15), 2),
        "modele": "M2-reference",
        "source_reference": source,
    }


def run():
    print("\n" + "=" * 50)
    print("  M2 - Prediction Loyer Classique")
    print("=" * 50)
    from pymongo import MongoClient

    load_dotenv()
    db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[
        os.getenv("MONGO_DB", "immoinsight")
    ]
    docs = list(db["clean_location"].find({}))
    print(f"  {len(docs)} annonces a estimer")

    total, nb_valide = 0, 0
    for doc in docs:
        result = predict_one(doc)
        loyer_reel = doc.get("prix")
        erreur = (
            abs(result["loyer_estime"] - loyer_reel) / loyer_reel * 100
            if loyer_reel
            else None
        )
        if erreur is not None:
            total += 1
            if erreur < 20:
                nb_valide += 1
        print(
            f"  {str(doc.get('titre',''))[:45]:45} reel={loyer_reel} estime={result['loyer_estime']:.0f} ({erreur:.0f}%)"
            if erreur
            else f"  {str(doc.get('titre',''))[:45]:45} reel={loyer_reel}"
        )

    if total:
        print(f"  Precision (<20%): {nb_valide}/{total} ({100*nb_valide/total:.0f}%)")
    print("  [M2] Prediction terminee.\n")


if __name__ == "__main__":
    run()
