import os
import json
import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv
from sklearn.model_selection import KFold

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "immoinsight")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "artifacts")

# En dessous, une ville n'a pas de référence propre : la référence globale est utilisée
MIN_ANNONCES_VILLE = 8

# Modèle de référence par ville (médiane + quartiles du prix/nuit).
# Évalué en validation croisée (Octobre 2026) : XGBoost / Ridge sur ville, score
# d'avis et distances POI ne font pas mieux que la médiane par ville. Booking ne
# fournit que la ville (distances identiques au sein d'une ville) et le score
# d'avis n'est pas corrélé au prix ; la capacité / le nombre de chambres, qui
# expliqueraient la dispersion, ne sont pas scrapés.


def load_data():
    db = MongoClient(MONGO_URI)[MONGO_DB]
    docs = list(db["clean_estival"].find({}, {"prix": 1, "ville": 1}))
    df = pd.DataFrame(docs)
    print(f"  [M3] Charge {len(df)} annonces clean_estival")
    return df


def prepare_data(df):
    df = df.dropna(subset=["prix", "ville"]).copy()
    df["prix"] = pd.to_numeric(df["prix"], errors="coerce")
    df = df[df["prix"] > 0]
    print(f"  [M3] {len(df)} annonces avec prix/nuit et ville")
    return df


def _stats(values):
    values = np.asarray(values, dtype=float)
    return {
        "n": int(len(values)),
        "median": round(float(np.median(values)), 2),
        "p25": round(float(np.percentile(values, 25)), 2),
        "p75": round(float(np.percentile(values, 75)), 2),
    }


def build_references(df):
    refs = {"global": _stats(df["prix"]), "par_ville": {}}
    for ville, prix in df.groupby("ville")["prix"]:
        if len(prix) >= MIN_ANNONCES_VILLE:
            refs["par_ville"][ville] = _stats(prix)
    return refs


def evaluate(df, n_splits=5):
    """Erreurs hors échantillon de la médiane par ville, et part des prix dans l'intervalle P25-P75."""
    preds = np.zeros(len(df))
    inside = np.zeros(len(df), dtype=bool)
    y = df["prix"].values
    for tr, te in KFold(n_splits, shuffle=True, random_state=42).split(df):
        refs = build_references(df.iloc[tr])
        for i in te:
            ref = refs["par_ville"].get(df["ville"].iloc[i], refs["global"])
            preds[i] = ref["median"]
            inside[i] = ref["p25"] <= y[i] <= ref["p75"]
    err = np.abs(preds - y) / y
    return {
        "mae": round(float(np.mean(np.abs(preds - y))), 1),
        "erreur_mediane_pct": round(float(np.median(err) * 100), 1),
        "part_a_20pct": round(float(np.mean(err <= 0.2) * 100), 1),
        "couverture_intervalle_pct": round(float(inside.mean() * 100), 1),
        "n": int(len(df)),
        "methode": "mediane_par_ville",
    }


def save_model(refs, metrics):
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(os.path.join(MODEL_DIR, "references.json"), "w", encoding="utf-8") as f:
        json.dump(refs, f, ensure_ascii=False, indent=2)
    with open(os.path.join(MODEL_DIR, "metrics.json"), "w") as f:
        json.dump(metrics, f)
    # Artefacts de l'ancien modèle XGBoost, devenus inutilisés
    for obsolete in ["model.pkl", "scaler.pkl", "features.json"]:
        path = os.path.join(MODEL_DIR, obsolete)
        if os.path.exists(path):
            os.remove(path)
    print(f"  [M3] References sauvegardees dans {MODEL_DIR}")


def run():
    print("\n" + "=" * 50)
    print("  M3 - PRICING ESTIVAL (reference par ville)")
    print("=" * 50)

    df = prepare_data(load_data())
    if len(df) < 20:
        print("  [M3] Pas assez de donnees")
        return

    metrics = evaluate(df)
    refs = build_references(df)
    save_model(refs, metrics)

    for ville, ref in sorted(refs["par_ville"].items()):
        print(f"  [M3]   {ville:10} n={ref['n']:3}  mediane={ref['median']:.0f} DT  [{ref['p25']:.0f} - {ref['p75']:.0f}]")
    print(f"  [M3] CV: erreur mediane={metrics['erreur_mediane_pct']}%, "
          f"prix dans l'intervalle P25-P75: {metrics['couverture_intervalle_pct']}%")
    print("  [M3] Entrainement termine.\n")


if __name__ == "__main__":
    run()
