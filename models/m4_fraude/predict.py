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
FRAUD_FEATURES = ["prix", "surface", "dist_transports_km"]


def load_model():
    iso = joblib.load(os.path.join(MODEL_DIR, "isolation_forest.pkl"))
    scaler = joblib.load(os.path.join(MODEL_DIR, "scaler.pkl"))
    return iso, scaler


def predict_one(annonce):
    iso, scaler = load_model()
    row = {f: annonce.get(f, np.nan) for f in FRAUD_FEATURES}
    row_df = pd.DataFrame([row])
    row_df = row_df.fillna(row_df.median(numeric_only=True))
    X = scaler.transform(row_df)
    score = iso.score_samples(X)[0]
    label = "anomalie" if iso.predict(X)[0] == -1 else "normal"
    fiabilite = max(0, min(100, 100 * (score + 0.5)))
    return {"label": label, "fiabilite": round(fiabilite, 1)}


def run():
    print("\n" + "=" * 50)
    print("  M4 - Prediction Fiabilite")
    print("=" * 50)

    db = MongoClient(MONGO_URI)[MONGO_DB]
    docs = list(db["clean_vente"].find({}))
    print(f"  {len(docs)} annonces")

    anomalies = 0
    for doc in docs:
        result = predict_one(doc)
        if result["label"] == "anomalie":
            anomalies += 1

    print(f"  Anomalies: {anomalies}/{len(docs)} ({100*anomalies/len(docs):.0f}%)")
    print("  [M4] Prediction terminee.\n")


if __name__ == "__main__":
    run()