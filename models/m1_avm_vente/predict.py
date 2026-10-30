import os
import json
from functools import lru_cache
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


def _signature():
    """Change quand les modèles sont ré-entraînés (invalide le cache)."""
    return tuple(os.path.getmtime(os.path.join(MODEL_DIR, f)) for f in ["xgb.pkl", "lgb.pkl", "meta.pkl"])


@lru_cache(maxsize=1)
def _load_model_cached(signature):
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


def load_model():
    return _load_model_cached(_signature())


def _zone_profile(annonce, zones):
    for field in ["ville", "gouvernorat"]:
        key = norm_zone(annonce.get(field))
        if key and key in zones:
            return key, zones[key]
    return None, {}


def _row(annonce, feature_names, zones):
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
    return row, zone


def predict_many(annonces):
    """Prix estimés pour une liste d'annonces (modèles chargés une seule fois)."""
    xgb_model, lgb_model, meta, feature_names, metrics, zones = load_model()
    rows, zone_list = zip(*[_row(a, feature_names, zones) for a in annonces]) if annonces else ([], [])
    # Les champs optionnels arrivent à None : sans conversion la colonne est de
    # dtype object et XGBoost refuse la prédiction. NaN est géré nativement.
    X = pd.DataFrame(list(rows), columns=feature_names).apply(pd.to_numeric, errors="coerce").astype(float)
    pred_xgb = xgb_model.predict(X)
    pred_lgb = lgb_model.predict(X)
    prix = meta.predict(np.column_stack([pred_xgb, pred_lgb]))
    if metrics.get("target_transform") == "log1p":
        pred_xgb, pred_lgb, prix = np.expm1(pred_xgb), np.expm1(pred_lgb), np.expm1(prix)
    return prix, pred_xgb, pred_lgb, list(zone_list), metrics


def predict_one(annonce):
    prix, pred_xgb, pred_lgb, zones, metrics = predict_many([annonce])
    prix_estime = prix[0]
    # Intervalle à 80 % mesuré en validation croisée (±10 % fixe auparavant,
    # alors que l'erreur médiane réelle dépasse 20 %)
    bas, haut = metrics.get("ratio_p10", 0.9), metrics.get("ratio_p90", 1.1)
    return {
        "prix_estime": round(float(prix_estime), 2),
        "intervalle_bas": round(float(prix_estime * bas), 2),
        "intervalle_haut": round(float(prix_estime * haut), 2),
        "prix_xgb": round(float(pred_xgb[0]), 2),
        "prix_lgb": round(float(pred_lgb[0]), 2),
        "zone_reconnue": zones[0],
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