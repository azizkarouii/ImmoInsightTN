import os
import json
import joblib
import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "immoinsight")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "artifacts")


def load_model():
    model = joblib.load(os.path.join(MODEL_DIR, "model.pkl"))
    scaler = joblib.load(os.path.join(MODEL_DIR, "scaler.pkl"))
    with open(os.path.join(MODEL_DIR, "features.json")) as f:
        features = json.load(f)
    return model, scaler, features


def predict_one(ville, score_avis=None, dist_plages=None):
    model, scaler, feature_names = load_model()

    row = {f: np.nan for f in feature_names}
    row["score_avis"] = score_avis or 7.0
    row["ville_" + ville] = 1.0

    row_df = pd.DataFrame([row])
    row_df = row_df.fillna(row_df.median(numeric_only=True))
    row_df = scaler.transform(row_df)

    prix = model.predict(row_df)[0]
    return {
        "prix_nuit_estime": round(float(prix), 2),
        "intervalle_bas": round(float(prix * 0.85), 2),
        "intervalle_haut": round(float(prix * 1.15), 2),
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
        result = predict_one(
            doc.get("ville", ""),
            doc.get("score_avis"),
        )
        reel = doc.get("prix")
        erreur = abs(result["prix_nuit_estime"] - reel) / reel * 100 if reel else None
        if erreur is not None:
            total += 1
            if erreur < 15:
                nb_precis += 1

    if total:
        print(f"  Precision (<15%): {nb_precis}/{total} ({100*nb_precis/total:.0f}%)")
    print("  [M3] Prediction terminee.\n")


if __name__ == "__main__":
    run()