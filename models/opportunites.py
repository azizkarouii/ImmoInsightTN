"""Écart entre le prix affiché et l'estimation des modèles (alertes « opportunités »).

L'estimation doit être hors échantillon : un modèle évalué sur les annonces qui
ont servi à l'entraîner « connaît » leur prix et sous-estime les écarts. On
utilise donc :
- pour les annonces d'entraînement, les prédictions de validation croisée (OOF)
  enregistrées par l'entraînement dans `estimations_oof` ;
- pour les annonces arrivées depuis, la prédiction du modèle courant.
"""
import os
from datetime import datetime, timezone

import numpy as np
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "immoinsight")


def get_db():
    return MongoClient(MONGO_URI)[MONGO_DB]


def save_oof(collection, urls, estimations):
    """Remplace les estimations hors échantillon d'une collection."""
    db = get_db()
    date = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    db["estimations_oof"].delete_many({"collection": collection})
    docs = [{"collection": collection, "url": u, "prix_estime": float(p), "date": date}
            for u, p in zip(urls, estimations) if u and np.isfinite(p) and p > 0]
    if docs:
        db["estimations_oof"].insert_many(docs)
        db["estimations_oof"].create_index([("collection", 1), ("url", 1)])
    print(f"  [OOF] {len(docs)} estimations hors echantillon enregistrees ({collection})")


def _estimer_vente(docs):
    from models.m1_avm_vente.predict import predict_many
    return predict_many(docs)[0]


def _estimer_location(docs):
    from models.m2_loyer_classique.predict import _charger_modele
    from models.m2_loyer_classique.train import to_frame, predict_frame
    from models.zone_encoding import ZoneEncoder

    charge = _charger_modele()
    if charge is None:
        return np.full(len(docs), np.nan)
    model, metrics = charge
    encoders = {k: ZoneEncoder.from_dict(v) for k, v in metrics["encoders"].items()}
    return predict_frame(model, encoders, to_frame(docs))


ESTIMATEURS = {"clean_vente": _estimer_vente, "clean_location": _estimer_location}
METRICS = {
    "clean_vente": os.path.join(os.path.dirname(__file__), "m1_avm_vente", "artifacts", "metrics.json"),
    "clean_location": os.path.join(os.path.dirname(__file__), "m2_loyer_classique", "artifacts", "metrics.json"),
}
# En deçà, écart assimilé à une erreur de saisie / de scraping plutôt qu'à une affaire
ECART_MIN_PCT = -70


def seuil_opportunite(collection):
    """Seuil = 10e percentile du rapport prix réel / estimé hors échantillon : une
    annonce sous ce seuil est plus basse que 90 % des écarts habituels du modèle
    (un seuil fixe de -15 % signalait plus d'un quart des annonces)."""
    import json
    try:
        with open(METRICS[collection]) as f:
            ratio = json.load(f).get("ratio_p10")
    except (OSError, ValueError):
        ratio = None
    return round((ratio - 1) * 100) if ratio else -25


def run():
    print("=" * 50)
    print("ETL - Etape 6: Ecart aux estimations (opportunites)")
    print("=" * 50)
    db = get_db()
    for collection, estimer in ESTIMATEURS.items():
        docs = list(db[collection].find({"prix": {"$gt": 0}, "surface": {"$gt": 0}}))
        if not docs:
            continue
        oof = {d["url"]: d["prix_estime"] for d in db["estimations_oof"].find({"collection": collection})}
        a_predire = [d for d in docs if d.get("url") not in oof]
        try:
            predits = dict(zip((d["_id"] for d in a_predire), estimer(a_predire))) if a_predire else {}
        except FileNotFoundError:
            print(f"  [OPP] {collection}: modele non entraine, etape ignoree")
            continue

        seuil = seuil_opportunite(collection)
        ops = []
        for d in docs:
            estime = oof.get(d.get("url"), predits.get(d["_id"]))
            if estime is None or not np.isfinite(estime) or estime <= 0:
                continue
            # Types Python natifs : Mongo n'encode pas np.float64 / np.bool_
            estime = float(estime)
            ecart = round((float(d["prix"]) - estime) / estime * 100, 1)
            ops.append(UpdateOne({"_id": d["_id"]}, {"$set": {
                "prix_estime": round(estime, 0),
                "ecart_estimation_pct": ecart,
                "opportunite": bool(ECART_MIN_PCT <= ecart <= seuil),
            }}))
        if ops:
            db[collection].bulk_write(ops)
        db["meta"].update_one({"_id": "opportunites"}, {"$set": {collection: seuil}}, upsert=True)
        n_opp = db[collection].count_documents({"opportunite": True})
        print(f"  [OPP] {collection}: {len(ops)} annonces estimees "
              f"({len(docs) - len(a_predire)} OOF, {len(a_predire)} nouvelles), "
              f"{n_opp} opportunites (ecart <= {seuil} %)")


if __name__ == "__main__":
    run()
