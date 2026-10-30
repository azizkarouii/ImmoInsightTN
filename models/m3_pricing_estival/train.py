import os
import json
import joblib
import numpy as np
import pandas as pd
import lightgbm as lgb
from pymongo import MongoClient
from dotenv import load_dotenv
from sklearn.model_selection import KFold

from models.zone_encoding import ZoneEncoder, norm_zone

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "immoinsight")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "artifacts")

# En dessous, une ville n'a pas de référence propre : la référence globale est utilisée
MIN_ANNONCES_VILLE = 8
# En dessous, le modèle appris n'est pas entraîné (références par ville seules)
MIN_ANNONCES_MODELE = 80

# Deux niveaux :
# - références par ville (médiane + quartiles du prix/nuit), toujours calculées ;
# - modèle LightGBM sur les caractéristiques du logement (scrapées sur Booking
#   depuis Octobre 2026), adopté seulement s'il bat la médiane par ville en
#   validation croisée. Note et nombre d'avis sont exclus : un bien qui n'est
#   pas encore loué n'en a pas.
FEATURES = ["zone_ville", "villa", "maison", "chambres", "log_surface", "lits", "sdb",
            "front_de_mer", "dist_plage_km"]

PARAMS_LGB = {
    "n_estimators": 400, "learning_rate": 0.03, "num_leaves": 7, "max_depth": 3,
    "min_child_samples": 10, "subsample": 0.8, "subsample_freq": 1,
    "colsample_bytree": 0.9, "reg_lambda": 5.0, "random_state": 42, "verbose": -1,
    # Prix croissant avec les chambres, la surface et le nombre de lits
    "monotone_constraints": [0, 0, 0, 1, 1, 1, 0, 0, 0],
}


def load_docs():
    db = MongoClient(MONGO_URI)[MONGO_DB]
    docs = [d for d in db["clean_estival"].find({}) if d.get("prix") and d.get("ville")]
    print(f"  [M3] Charge {len(docs)} annonces clean_estival avec prix/nuit et ville")
    return docs


def _num(value):
    try:
        number = float(value)
        return number if np.isfinite(number) else np.nan
    except (TypeError, ValueError):
        return np.nan


def to_frame(docs):
    rows = []
    for d in docs:
        categorie = d.get("categorie") or d.get("type_bien") or "appartement"
        rows.append({
            "prix": _num(d.get("prix")),
            "ville": norm_zone(d.get("ville")),
            "ville_label": d.get("ville"),
            "villa": float(categorie == "villa"),
            "maison": float(categorie == "maison_vacances"),
            "chambres": _num(d.get("nb_chambres")),
            "surface": _num(d.get("surface")),
            "lits": _num(d.get("nb_lits")),
            "sdb": _num(d.get("nb_sdb")),
            "front_de_mer": float(bool(d.get("front_de_mer"))),
            "dist_plage_km": _num(d.get("dist_plage_km")),
        })
    df = pd.DataFrame(rows)
    df["log_surface"] = np.log(df["surface"])
    return df


# ----------------------------------------------------------------------------
# Références par ville
# ----------------------------------------------------------------------------
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
    for ville, prix in df.groupby("ville_label")["prix"]:
        if len(prix) >= MIN_ANNONCES_VILLE:
            refs["par_ville"][ville] = _stats(prix)
    return refs


# ----------------------------------------------------------------------------
# Modèle appris
# ----------------------------------------------------------------------------
def fit_model(df):
    encoder = ZoneEncoder(smoothing=5).fit(df["ville"], np.log(df["prix"]))
    X = df.assign(zone_ville=encoder.transform(df["ville"]))[FEATURES]
    model = lgb.LGBMRegressor(**PARAMS_LGB).fit(X, np.log(df["prix"]))
    return model, encoder


def predict_frame(model, encoder, df):
    X = df.assign(zone_ville=encoder.transform(df["ville"]))[FEATURES]
    return np.exp(model.predict(X))


def evaluate(df, n_splits=5, repeats=3):
    y = df["prix"].values
    preds = {"modele": np.zeros(len(df)), "mediane_ville": np.zeros(len(df))}
    inside, ratios = np.zeros(len(df)), []
    for rep in range(repeats):
        for tr, te in KFold(n_splits, shuffle=True, random_state=rep).split(df):
            train, test = df.iloc[tr], df.iloc[te]
            model, encoder = fit_model(train)
            p = predict_frame(model, encoder, test)
            preds["modele"][te] += p / repeats
            ratios.extend(y[te] / p)
            refs = build_references(train)
            for j, i in enumerate(te):
                ref = refs["par_ville"].get(df["ville_label"].iloc[i], refs["global"])
                preds["mediane_ville"][i] += ref["median"] / repeats
                inside[i] += (ref["p25"] <= y[i] <= ref["p75"]) / repeats

    def scores(p):
        err = np.abs(p - y) / y
        return {"mae": round(float(np.mean(np.abs(p - y))), 1),
                "erreur_mediane_pct": round(float(np.median(err) * 100), 1),
                "part_a_20pct": round(float(np.mean(err <= 0.2) * 100), 1)}

    resultats = {name: scores(p) for name, p in preds.items()}
    resultats["mediane_ville"]["couverture_intervalle_pct"] = round(float(inside.mean() * 100), 1)
    return resultats, ratios


def run():
    print("\n" + "=" * 50)
    print("  M3 - PRICING ESTIVAL")
    print("=" * 50)

    docs = load_docs()
    df = to_frame(docs)
    df = df[df["prix"] > 0].reset_index(drop=True)
    if len(df) < 20:
        print("  [M3] Pas assez de donnees")
        return

    os.makedirs(MODEL_DIR, exist_ok=True)
    refs = build_references(df)
    with open(os.path.join(MODEL_DIR, "references.json"), "w", encoding="utf-8") as f:
        json.dump(refs, f, ensure_ascii=False, indent=2)
    for ville, ref in sorted(refs["par_ville"].items()):
        print(f"  [M3]   {ville:16} n={ref['n']:3}  mediane={ref['median']:.0f} DT  [{ref['p25']:.0f} - {ref['p75']:.0f}]")

    model_path = os.path.join(MODEL_DIR, "model.pkl")
    metrics = {"n": int(len(df)), "methode": "mediane_par_ville"}
    adopte = False
    if len(df) >= MIN_ANNONCES_MODELE and df["chambres"].notna().mean() > 0.5:
        resultats, ratios = evaluate(df)
        metrics["cv"] = resultats
        for name, sc in resultats.items():
            print(f"  [M3] CV {name:14} erreur mediane={sc['erreur_mediane_pct']:5.1f}%  "
                  f"<=20%: {sc['part_a_20pct']:4.1f}%  MAE={sc['mae']:.0f} DT")
        adopte = resultats["modele"]["erreur_mediane_pct"] < resultats["mediane_ville"]["erreur_mediane_pct"]
        if adopte:
            model, encoder = fit_model(df)
            joblib.dump(model, model_path)
            metrics.update({
                "methode": "lightgbm",
                "ratio_p10": round(float(np.percentile(ratios, 10)), 3),
                "ratio_p90": round(float(np.percentile(ratios, 90)), 3),
                "encoder": encoder.to_dict(),
            })
            print(f"  [M3] Modele adopte, intervalle 80%: x{metrics['ratio_p10']} - x{metrics['ratio_p90']}")
        else:
            print("  [M3] Le modele ne bat pas la mediane par ville : references conservees")
    else:
        print("  [M3] Donnees insuffisantes (caracteristiques des logements) : references seules")

    if not adopte and os.path.exists(model_path):
        os.remove(model_path)
    with open(os.path.join(MODEL_DIR, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=1)
    print("  [M3] Entrainement termine.\n")


if __name__ == "__main__":
    run()
