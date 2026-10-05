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
    xgb_model = joblib.load(os.path.join(MODEL_DIR, "xgb.pkl"))
    lgb_model = joblib.load(os.path.join(MODEL_DIR, "lgb.pkl"))
    meta = joblib.load(os.path.join(MODEL_DIR, "meta.pkl"))
    with open(os.path.join(MODEL_DIR, "features.json")) as f:
        features = json.load(f)
    return xgb_model, lgb_model, meta, features


def predict_one(annonce):
    xgb_model, lgb_model, meta, feature_names = load_model()

    row = {f: annonce.get(f, np.nan) for f in feature_names}

    row_df = pd.DataFrame([row])

    for col in ["type_appartement", "type_villa", "type_terrain"]:
        if col not in row_df.columns:
            row_df[col] = 0.0

    if "type_bien" in row_df.columns:
        row_df = row_df.drop(columns=["type_bien"])

    row_df = row_df.fillna(row_df.median(numeric_only=True))

    pred_xgb = xgb_model.predict(row_df)[0]
    pred_lgb = lgb_model.predict(row_df)[0]
    stack_input = np.array([[pred_xgb, pred_lgb]])
    prix_estime = meta.predict(stack_input)[0]

    return {
        "prix_estime": round(float(prix_estime), 2),
        "intervalle_bas": round(float(prix_estime * 0.9), 2),
        "intervalle_haut": round(float(prix_estime * 1.1), 2),
        "prix_xgb": round(float(pred_xgb), 2),
        "prix_lgb": round(float(pred_lgb), 2),
    }


def run():
    print("\n" + "=" * 50)
    print("  M1 - Prediction AVM Vente")
    print("=" * 50)

    db = MongoClient(MONGO_URI)[MONGO_DB]
    docs = list(db["clean_vente"].find({}))
    print(f"  {len(docs)} annonces a estimer")

    total, nb_valide = 0, 0
    for doc in docs:
        result = predict_one(doc)
        prix_reel = doc.get("prix")
        erreur = abs(result["prix_estime"] - prix_reel) / prix_reel * 100 if prix_reel else None
        if erreur is not None:
            total += 1
            if erreur < 15:
                nb_valide += 1

    print(f"  Precision (<15%): {nb_valide}/{total} ({100*nb_valide/total:.0f}%)")
    print("  [M1] Prediction terminee.\n")


if __name__ == "__main__":
    run()