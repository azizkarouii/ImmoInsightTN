import os
import json
import unicodedata
import joblib
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "immoinsight")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "artifacts")

ALIAS_VILLES = {
    "jerba": "djerba",
    "marsa": "la marsa",
    "houmt souk": "djerba",
    "yasmine hammamet": "hammamet",
}


class VilleInconnue(ValueError):
    """La ville demandée n'a pas de référence estivale."""


def _norm(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace("-", " ").split())


def load_model():
    with open(os.path.join(MODEL_DIR, "references.json"), encoding="utf-8") as f:
        return json.load(f)


def _charger_modele():
    model_path = os.path.join(MODEL_DIR, "model.pkl")
    metrics_path = os.path.join(MODEL_DIR, "metrics.json")
    if not (os.path.exists(model_path) and os.path.exists(metrics_path)):
        return None
    with open(metrics_path, encoding="utf-8") as f:
        metrics = json.load(f)
    return joblib.load(model_path), metrics


def villes_couvertes():
    return sorted(load_model()["par_ville"])


def _resoudre_ville(ville, refs):
    par_ville = {_norm(v): v for v in refs["par_ville"]}
    key = _norm(ville)
    key = ALIAS_VILLES.get(key, key)
    if key not in par_ville:
        raise VilleInconnue(
            f"Ville '{ville}' non couverte. Villes disponibles : {', '.join(sorted(refs['par_ville']))}"
        )
    return par_ville[key]


def predict_one(ville, categorie=None, nb_chambres=None, surface=None, nb_lits=None,
                nb_sdb=None, front_de_mer=None, dist_plage_km=None):
    refs = load_model()
    nom_ville = _resoudre_ville(ville, refs)
    ref = refs["par_ville"][nom_ville]
    caracteristiques = {
        "categorie": categorie, "nb_chambres": nb_chambres, "surface": surface,
        "nb_lits": nb_lits, "nb_sdb": nb_sdb, "front_de_mer": front_de_mer,
        "dist_plage_km": dist_plage_km,
    }
    charge = _charger_modele()

    # Sans caractéristiques du logement, la référence de la ville est la meilleure estimation
    if charge is None or all(v is None for v in caracteristiques.values()):
        return {
            "ville": nom_ville,
            "prix_nuit_estime": ref["median"],
            # Intervalle = moitié centrale des annonces observées (P25-P75)
            "intervalle_bas": ref["p25"],
            "intervalle_haut": ref["p75"],
            "nb_annonces": ref["n"],
            "modele": "M3-reference-ville",
        }

    from models.zone_encoding import ZoneEncoder
    from models.m3_pricing_estival.train import to_frame, predict_frame

    model, metrics = charge
    encoder = ZoneEncoder.from_dict(metrics["encoder"])
    df = to_frame([{**caracteristiques, "ville": nom_ville, "prix": None}])
    prix = float(predict_frame(model, encoder, df)[0])
    return {
        "ville": nom_ville,
        "prix_nuit_estime": round(prix, 2),
        "intervalle_bas": round(prix * metrics["ratio_p10"], 2),
        "intervalle_haut": round(prix * metrics["ratio_p90"], 2),
        "nb_annonces": ref["n"],
        "mediane_ville": ref["median"],
        "modele": "M3-lightgbm",
    }


def run():
    print("\n" + "=" * 50)
    print("  M3 - Prediction Prix Estival")
    print("=" * 50)

    db = MongoClient(MONGO_URI)[MONGO_DB]
    docs = list(db["clean_estival"].find({}))
    print(f"  {len(docs)} annonces")

    total, nb_precis = 0, 0
    for doc in docs:
        try:
            result = predict_one(doc.get("ville", ""))
        except VilleInconnue:
            continue
        reel = doc.get("prix")
        if reel:
            total += 1
            if abs(result["prix_nuit_estime"] - reel) / reel * 100 < 15:
                nb_precis += 1

    if total:
        print(f"  Precision (<15%): {nb_precis}/{total} ({100*nb_precis/total:.0f}%)")
    print("  [M3] Prediction terminee.\n")


if __name__ == "__main__":
    run()
