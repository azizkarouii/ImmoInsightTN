import os
import re
import json
import joblib
import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "immoinsight")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "artifacts")

FEATURES = [
    "score_avis",
    "gouvernorat_freq",
    "dist_plages_km", "dist_ecoles_km", "dist_hopitaux_km",
    "dist_transports_km", "dist_commerces_km", "dist_restaurants_km",
    "dist_pharmacies_km", "dist_universites_km",
]


def load_data():
    db = MongoClient(MONGO_URI)[MONGO_DB]
    docs = list(db["clean_estival"].find({}))
    df = pd.DataFrame(docs)
    print(f"  [M3] Charge {len(df)} annonces clean_estival")
    return df


def clean_score_avis(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return np.nan
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"(\d+[.,]\d)", str(val))
    if m:
        return float(m.group(1).replace(",", "."))
    return np.nan


def prepare_features(df):
    df = df.dropna(subset=["prix"]).copy()
    df["score_avis"] = df["score_avis"].apply(clean_score_avis)
    X = df[FEATURES].copy()
    y = df["prix"].copy()

    # One-hot encode ville
    ville_dummies = pd.get_dummies(df["ville"], prefix="ville")
    X = pd.concat([X, ville_dummies], axis=1)

    # Fill NaN score_avis with median
    X = X.fillna(X.median(numeric_only=True))

    print(f"  [M3] {len(X)} echantillons, {len(X.columns)} features")
    return X, y


def train_model(X, y):
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_te_s = scaler.transform(X_te)

    model = xgb.XGBRegressor(
        n_estimators=500, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=1.0,
        random_state=42, verbosity=0,
    )
    model.fit(X_tr_s, y_tr, eval_set=[(X_te_s, y_te)], verbose=False)

    preds = model.predict(X_te_s)
    mae = mean_absolute_error(y_te, preds)
    r2 = r2_score(y_te, preds)

    print(f"  [M3] Test MAE={mae:.0f} DT, R2={r2:.3f}")
    print(f"  [M3] Prix moyen: {y.mean():.0f} DT, Erreur relative: {mae/y.mean()*100:.1f}%")

    return model, scaler, {"mae": mae, "r2": r2}


def save_model(model, scaler, metrics, feature_names):
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, os.path.join(MODEL_DIR, "model.pkl"))
    joblib.dump(scaler, os.path.join(MODEL_DIR, "scaler.pkl"))
    with open(os.path.join(MODEL_DIR, "features.json"), "w") as f:
        json.dump(feature_names, f)
    with open(os.path.join(MODEL_DIR, "metrics.json"), "w") as f:
        json.dump(metrics, f)
    print(f"  [M3] Modele sauvegarde dans {MODEL_DIR}")


def run():
    print("\n" + "=" * 50)
    print("  M3 - PRICING ESTIVAL (XGBoost)")
    print("=" * 50)

    df = load_data()
    X, y = prepare_features(df)
    if len(X) < 20:
        print("  [M3] Pas assez de donnees")
        return

    model, scaler, metrics = train_model(X, y)
    save_model(model, scaler, metrics, list(X.columns))

    # Feature importance
    imp = sorted(zip(X.columns, model.feature_importances_),
                 key=lambda x: x[1], reverse=True)
    print("\n  Top 10 features:")
    for name, val in imp[:10]:
        print(f"    {name}: {val:.3f}")

    print("  [M3] Entrainement termine.\n")


if __name__ == "__main__":
    run()