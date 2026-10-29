import os
import json
import joblib
import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "immoinsight")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "artifacts")

FRAUD_FEATURES = ["prix", "surface", "dist_transports_km"]


def load_data():
    db = MongoClient(MONGO_URI)[MONGO_DB]
    docs = list(db["clean_vente"].find({}))
    df = pd.DataFrame(docs)
    print(f"  [M4] Charge {len(df)} annonces clean_vente")
    return df


def prepare_features(df):
    X = df[FRAUD_FEATURES].apply(pd.to_numeric, errors="coerce")
    medians = X.median()
    X = X.fillna(medians)
    print(f"  [M4] {len(X)} echantillons, {len(X.columns)} features")
    return X, df["_id"], medians


def train_model(X):
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X)

    iso = IsolationForest(
        n_estimators=200,
        contamination=0.05,
        random_state=42,
        n_jobs=-1,
    )
    iso.fit(X_s)

    scores = iso.score_samples(X_s)
    # Normalize to [0, 100] where higher = more trustworthy
    min_s, max_s = scores.min(), scores.max()
    fiabilite = 100 * (scores - min_s) / (max_s - min_s)

    n_anomalies = (iso.predict(X_s) == -1).sum()
    print(f"  [M4] {n_anomalies}/{len(X)} anomalies detectees (contamination=5%)")
    print(f"  [M4] Score fiabilite: min={fiabilite.min():.0f}, max={fiabilite.max():.0f}, mean={fiabilite.mean():.0f}")

    return iso, scaler, fiabilite


def save_model(iso, scaler, fiabilite, metrics):
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(iso, os.path.join(MODEL_DIR, "isolation_forest.pkl"))
    joblib.dump(scaler, os.path.join(MODEL_DIR, "scaler.pkl"))
    with open(os.path.join(MODEL_DIR, "metrics.json"), "w") as f:
        json.dump(metrics, f)
    print(f"  [M4] Modele sauvegarde dans {MODEL_DIR}")


def save_fiabilite(ids, fiabilite):
    # Mise à jour par _id (l'ancienne version ré-interrogeait la collection et
    # associait les scores par position, sans garantie d'ordre)
    db = MongoClient(MONGO_URI)[MONGO_DB]
    for _id, score in zip(ids, fiabilite):
        db["clean_vente"].update_one(
            {"_id": _id},
            {"$set": {"fiabilite": round(float(score), 1)}}
        )
    print(f"  [M4] Scores fiabilite sauvegardes dans clean_vente")


def run():
    print("\n" + "=" * 50)
    print("  M4 - DETECTION FRAUDE (Isolation Forest)")
    print("=" * 50)

    df = load_data()
    X, ids, medians = prepare_features(df)
    if len(X) < 10:
        print("  [M4] Pas assez de donnees")
        return

    iso, scaler, fiabilite = train_model(X)
    save_model(iso, scaler, fiabilite, {
        "n_echantillons": len(X),
        "n_features": len(FRAUD_FEATURES),
        "contamination": 0.05,
        "fiabilite_mean": round(float(fiabilite.mean()), 1),
        # Valeurs de remplacement des features manquantes, réutilisées à la prédiction
        "medians": {k: float(v) for k, v in medians.items()},
        "score_min": float(iso.score_samples(scaler.transform(X)).min()),
        "score_max": float(iso.score_samples(scaler.transform(X)).max()),
    })
    save_fiabilite(ids, fiabilite)
    print("  [M4] Entrainement termine.\n")


if __name__ == "__main__":
    run()