import os
import json
import statistics
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

# Une médiane mesurée sur moins d'annonces n'est pas utilisée comme référence :
# avec 3-4 locations, un seul studio meublé suffit à fausser la valeur
MIN_ECHANTILLONS = 10
# En dessous, le modèle appris n'est pas entraîné (barème de références seul)
MIN_ANNONCES_MODELE = 60

FEATURES = ["log_surface", "chambres", "sdb", "villa", "meuble", "zone_ville", "zone_gouv"]

PARAMS_LGB = {
    "n_estimators": 400, "learning_rate": 0.03, "num_leaves": 7, "max_depth": 3,
    "min_child_samples": 8, "subsample": 0.8, "subsample_freq": 1,
    "colsample_bytree": 0.9, "reg_lambda": 5.0, "random_state": 42, "verbose": -1,
    # Loyer croissant avec la surface et le nombre de chambres
    "monotone_constraints": [1, 1, 0, 0, 0, 0, 0],
}


def load_data():
    db = MongoClient(MONGO_URI)[MONGO_DB]
    docs = list(db["clean_location"].find({}))
    print(f"  [M2] Charge {len(docs)} annonces clean_location")
    return docs


# ----------------------------------------------------------------------------
# Barème de références (repli quand le modèle n'est pas disponible)
# ----------------------------------------------------------------------------
def build_references(docs):
    refs = {"par_ville": {}, "par_type": {}, "global": [], "par_piece": []}
    for d in docs:
        prix, surface = d.get("prix"), d.get("surface")
        if not prix or not surface or surface <= 0:
            continue
        prix_m2 = prix / surface
        refs["global"].append(prix_m2)
        ville = d.get("ville")
        if ville and isinstance(ville, str):
            refs["par_ville"].setdefault(ville, []).append(prix_m2)
        type_bien = d.get("type_bien") or "appartement"
        refs["par_type"].setdefault(type_bien, []).append(prix_m2)
        if d.get("nb_pieces"):
            refs["par_piece"].append((prix, d["nb_pieces"]))
    for k in ["par_ville", "par_type"]:
        refs[k] = {
            zone: statistics.median(vals)
            for zone, vals in refs[k].items()
            if len(vals) >= MIN_ECHANTILLONS
        }
    refs["prix_m2_mediane"] = (
        statistics.median(refs["global"]) if len(refs["global"]) >= MIN_ECHANTILLONS else None
    )
    refs["n"] = len(refs["global"])
    return refs


# ----------------------------------------------------------------------------
# Modèle appris
# ----------------------------------------------------------------------------
def _texte(doc):
    eq = doc.get("equipements")
    eq = " ".join(eq) if isinstance(eq, list) else ""
    return f"{doc.get('titre') or ''} {doc.get('description') or ''} {eq}".lower()


def to_frame(docs):
    """Annonces (dicts) -> DataFrame des variables brutes."""
    rows = []
    for d in docs:
        chambres = d.get("nb_chambres")
        if chambres is None and d.get("nb_pieces"):
            chambres = max(int(d["nb_pieces"]) - 1, 0)
        surface = d.get("surface")
        rows.append({
            "loyer": d.get("prix"),
            "surface": float(surface) if surface else np.nan,
            "chambres": float(chambres) if chambres is not None else np.nan,
            "sdb": float(d["nb_sdb"]) if d.get("nb_sdb") is not None else np.nan,
            "villa": float((d.get("type_bien") or "") == "villa"),
            "meuble": float(bool(d.get("meuble")) or "meubl" in _texte(d)),
            "ville": norm_zone(d.get("ville")),
            "gouvernorat": norm_zone(d.get("gouvernorat")),
        })
    df = pd.DataFrame(rows)
    df["log_surface"] = np.log(df["surface"])
    return df


def fit_encoders(df):
    """Encodeurs de zone sur log(loyer/m²) (annonces avec surface uniquement)."""
    with_surface = df[df["surface"].notna()]
    target = np.log(with_surface["loyer"] / with_surface["surface"])
    return {
        "ville": ZoneEncoder(smoothing=5).fit(with_surface["ville"], target),
        "gouvernorat": ZoneEncoder(smoothing=5).fit(with_surface["gouvernorat"], target),
    }


def features(df, encoders):
    X = df.copy()
    X["zone_ville"] = encoders["ville"].transform(X["ville"])
    X["zone_gouv"] = encoders["gouvernorat"].transform(X["gouvernorat"])
    return X[FEATURES]


def fit_model(df):
    encoders = fit_encoders(df)
    model = lgb.LGBMRegressor(**PARAMS_LGB).fit(features(df, encoders), np.log(df["loyer"]))
    return model, encoders


def predict_frame(model, encoders, df):
    return np.exp(model.predict(features(df, encoders)))


def baseline_zone(train, test):
    """Référence : loyer/m² médian de la ville (repli gouvernorat, global) × surface."""
    tr = train[train["surface"].notna()]
    m2 = tr["loyer"] / tr["surface"]
    par_ville = m2.groupby(tr["ville"]).median()[tr.groupby("ville").size() >= 3]
    par_gouv = m2.groupby(tr["gouvernorat"]).median()[tr.groupby("gouvernorat").size() >= 3]
    loyer_median = train["loyer"].median()
    preds = []
    for _, r in test.iterrows():
        ref = par_ville.get(r["ville"], par_gouv.get(r["gouvernorat"], m2.median()))
        preds.append(ref * r["surface"] if not np.isnan(r["surface"]) else loyer_median)
    return np.array(preds)


def evaluate(docs, n_splits=5, repeats=3):
    from models.m2_loyer_classique.predict import predict_reference

    df = to_frame(docs)
    y = df["loyer"].values
    preds = {"modele": np.zeros(len(df)), "zone_x_surface": np.zeros(len(df)), "bareme": np.zeros(len(df))}
    ratios = []
    for rep in range(repeats):
        for tr, te in KFold(n_splits, shuffle=True, random_state=rep).split(df):
            model, encoders = fit_model(df.iloc[tr])
            p = predict_frame(model, encoders, df.iloc[te])
            preds["modele"][te] += p / repeats
            ratios.extend(y[te] / p)
            preds["zone_x_surface"][te] += baseline_zone(df.iloc[tr], df.iloc[te]) / repeats
    preds["bareme"] = np.array([predict_reference(d)["loyer_estime"] for d in docs])

    def scores(p):
        err = np.abs(p - y) / y
        return {"mae": round(float(np.mean(np.abs(p - y))), 1),
                "erreur_mediane_pct": round(float(np.median(err) * 100), 1),
                "part_a_20pct": round(float(np.mean(err <= 0.2) * 100), 1)}

    return {name: scores(p) for name, p in preds.items()}, ratios


def run():
    print("\n" + "=" * 50)
    print("  M2 - LOYER CLASSIQUE")
    print("=" * 50)

    docs = [d for d in load_data() if d.get("prix")]
    if not docs:
        print("  [M2] Aucune donnee location")
        return

    os.makedirs(MODEL_DIR, exist_ok=True)
    refs = build_references(docs)
    with open(os.path.join(MODEL_DIR, "references.json"), "w", encoding="utf-8") as f:
        json.dump(refs, f, ensure_ascii=False, indent=2)
    print(f"  [M2] Bareme: {refs['n']} annonces avec surface, {len(refs['par_ville'])} villes mesurees")

    model_path = os.path.join(MODEL_DIR, "model.pkl")
    if len(docs) < MIN_ANNONCES_MODELE:
        print(f"  [M2] {len(docs)} annonces < {MIN_ANNONCES_MODELE} : modele appris non entraine (bareme seul)")
        if os.path.exists(model_path):
            os.remove(model_path)
        return

    resultats, ratios = evaluate(docs)
    for name, sc in resultats.items():
        print(f"  [M2] CV {name:15} erreur mediane={sc['erreur_mediane_pct']:5.1f}%  "
              f"<=20%: {sc['part_a_20pct']:4.1f}%  MAE={sc['mae']:.0f} DT")

    meilleur_ref = min(resultats["zone_x_surface"]["erreur_mediane_pct"], resultats["bareme"]["erreur_mediane_pct"])
    if resultats["modele"]["erreur_mediane_pct"] >= meilleur_ref:
        print("  [M2] Le modele ne bat pas les references : bareme conserve")
        if os.path.exists(model_path):
            os.remove(model_path)
        return

    df = to_frame(docs)
    model, encoders = fit_model(df)
    joblib.dump(model, model_path)
    metrics = {
        "n": len(df),
        "cv": resultats,
        "ratio_p10": round(float(np.percentile(ratios, 10)), 3),
        "ratio_p90": round(float(np.percentile(ratios, 90)), 3),
        "encoders": {k: e.to_dict() for k, e in encoders.items()},
    }
    with open(os.path.join(MODEL_DIR, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=1)
    print(f"  [M2] Modele sauvegarde ({len(df)} annonces), intervalle 80%: "
          f"x{metrics['ratio_p10']} - x{metrics['ratio_p90']}")
    print("  [M2] Entrainement termine.\n")


if __name__ == "__main__":
    run()
