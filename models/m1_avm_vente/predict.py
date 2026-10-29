import os
import json
import joblib
import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv
from models.m1_avm_vente.train import norm_zone

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
    try:
        with open(os.path.join(MODEL_DIR, "metrics.json")) as f:
            metrics = json.load(f)
    except (OSError, ValueError):
        metrics = {}
    try:
        with open(os.path.join(MODEL_DIR, "zone_profiles.json"), encoding="utf-8") as f:
            zones = json.load(f)
    except (OSError, ValueError):
        zones = {}
    return xgb_model, lgb_model, meta, features, metrics, zones


def _zone_profile(annonce, zones):
    for field in ["ville", "gouvernorat"]:
        key = norm_zone(annonce.get(field))
        if key and key in zones:
            return key, zones[key]
    return None, {}


def predict_one(annonce):
    xgb_model, lgb_model, meta, feature_names, metrics, zones = load_model()
    log_target = metrics.get("target_transform") == "log1p"

    row = {f: annonce.get(f, np.nan) for f in feature_names}

    # Localisation : features géographiques médianes de la zone demandée
    zone, profile = _zone_profile(annonce, zones)
    for col, value in profile.items():
        if col in row and (row[col] is None or pd.isna(row[col])):
            row[col] = value

    # Encodage one-hot identique à train.prepare_features
    type_bien = annonce.get("type_bien")
    for t in ["appartement", "villa", "terrain"]:
        if f"type_{t}" in row:
            row[f"type_{t}"] = float(type_bien == t)

    # Les champs optionnels arrivent à None : sans conversion la colonne est de
    # dtype object et XGBoost refuse la prédiction. NaN est géré nativement.
    row_df = pd.DataFrame([row], columns=feature_names).apply(pd.to_numeric, errors="coerce").astype(float)

    pred_xgb = xgb_model.predict(row_df)[0]
    pred_lgb = lgb_model.predict(row_df)[0]
    stack_input = np.array([[pred_xgb, pred_lgb]])
    prix_estime = meta.predict(stack_input)[0]
    if log_target:
        pred_xgb, pred_lgb, prix_estime = np.expm1([pred_xgb, pred_lgb, prix_estime])

    # Intervalle à 80 % mesuré en validation croisée (±10 % fixe auparavant,
    # alors que l'erreur médiane réelle dépasse 20 %)
    bas, haut = metrics.get("ratio_p10", 0.9), metrics.get("ratio_p90", 1.1)
    return {
        "prix_estime": round(float(prix_estime), 2),
        "intervalle_bas": round(float(prix_estime * bas), 2),
        "intervalle_haut": round(float(prix_estime * haut), 2),
        "prix_xgb": round(float(pred_xgb), 2),
        "prix_lgb": round(float(pred_lgb), 2),
        "zone_reconnue": zone,
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