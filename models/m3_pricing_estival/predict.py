import os
import json
import unicodedata
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


def villes_couvertes():
    return sorted(load_model()["par_ville"])


def predict_one(ville):
    refs = load_model()
    par_ville = {_norm(v): v for v in refs["par_ville"]}
    key = _norm(ville)
    key = ALIAS_VILLES.get(key, key)
    if key not in par_ville:
        raise VilleInconnue(
            f"Ville '{ville}' non couverte. Villes disponibles : {', '.join(sorted(refs['par_ville']))}"
        )
    ref = refs["par_ville"][par_ville[key]]
    return {
        "ville": par_ville[key],
        "prix_nuit_estime": ref["median"],
        # Intervalle = moitié centrale des annonces observées (P25-P75)
        "intervalle_bas": ref["p25"],
        "intervalle_haut": ref["p75"],
        "nb_annonces": ref["n"],
        "modele": "M3-reference-ville",
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
