import os
import json
import joblib
import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv
import xgboost as xgb
import lightgbm as lgb
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.metrics import mean_absolute_error, r2_score

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "immoinsight")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "artifacts")

FEATURES = [
    "surface", "nb_pieces", "nb_chambres", "nb_sdb", "etage",
    "has_parking", "has_ascenseur", "has_piscine", "has_gardien",
    "gouvernorat_freq",
    "dist_plages_km", "dist_ecoles_km", "dist_hopitaux_km",
    "dist_transports_km", "dist_commerces_km",
    "type_bien",
]


def load_data():
    db = MongoClient(MONGO_URI)[MONGO_DB]
    docs = list(db["clean_vente"].find({}))
    df = pd.DataFrame(docs)
    print(f"  [M1] Charge {len(df)} annonces clean_vente")
    return df


def prepare_features(df):
    df = df.dropna(subset=["prix"]).copy()
    X = df[FEATURES].copy()
    y = df["prix"].copy()

    X["type_appartement"] = (X["type_bien"] == "appartement").astype(float)
    X["type_villa"] = (X["type_bien"] == "villa").astype(float)
    X["type_terrain"] = (X["type_bien"] == "terrain").astype(float)
    X = X.drop(columns=["type_bien"])

    # Drop rows missing surface (essential for AVM)
    before = len(X)
    X = X.dropna(subset=["surface"])
    y = y.loc[X.index]
    print(f"  [M1] {before - len(X)} lignes supprimees (surface manquante)")

    # Fill remaining NaN with median
    X = X.fillna(X.median(numeric_only=True))

    print(f"  [M1] {len(X)} echantillons, {len(X.columns)} features")
    return X, y


def train_stacking(X, y, n_splits=5):
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
    oof_xgb = np.zeros(len(X))
    oof_lgb = np.zeros(len(X))
    scores_mae, scores_r2 = [], []

    params_xgb = {"n_estimators": 800, "max_depth": 7, "learning_rate": 0.05,
                   "subsample": 0.8, "colsample_bytree": 0.8,
                   "reg_alpha": 0.1, "random_state": 42, "verbosity": 0}
    params_lgb = {"n_estimators": 800, "max_depth": 7, "learning_rate": 0.05,
                   "subsample": 0.8, "feature_fraction": 0.8,
                   "reg_alpha": 0.1, "random_state": 42, "verbose": -1}

    for fold, (tr_idx, va_idx) in enumerate(kf.split(X)):
        X_tr, X_va = X.iloc[tr_idx], X.iloc[va_idx]
        y_tr, y_va = y.iloc[tr_idx], y.iloc[va_idx]

        m_xgb = xgb.XGBRegressor(**params_xgb)
        m_xgb.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
        oof_xgb[va_idx] = m_xgb.predict(X_va)

        m_lgb = lgb.LGBMRegressor(**params_lgb)
        m_lgb.fit(X_tr, y_tr, eval_set=[(X_va, y_va)])
        oof_lgb[va_idx] = m_lgb.predict(X_va)

        fold_mae = mean_absolute_error(y_va, oof_xgb[va_idx])
        fold_r2 = r2_score(y_va, oof_xgb[va_idx])
        scores_mae.append(fold_mae)
        scores_r2.append(fold_r2)
        print(f"    Fold {fold+1}: MAE={fold_mae:.0f} DT, R2={fold_r2:.3f}")

    # Train final base models on full data
    final_xgb = xgb.XGBRegressor(**params_xgb)
    final_xgb.fit(X, y, eval_set=[(X, y)], verbose=False)
    final_lgb = lgb.LGBMRegressor(**params_lgb)
    final_lgb.fit(X, y, eval_set=[(X, y)])

    # Meta-model: Ridge on OOF predictions
    stack_X = np.column_stack([oof_xgb, oof_lgb])
    meta = Ridge(alpha=1.0)
    meta.fit(stack_X, y)

    oof_stack = meta.predict(stack_X)
    mae = mean_absolute_error(y, oof_stack)
    r2 = r2_score(y, oof_stack)

    print(f"\n  [M1] Stacking final: MAE={mae:.0f} DT, R2={r2:.3f}")
    print(f"  [M1] Poids meta: XGB={meta.coef_[0]:.3f}, LGB={meta.coef_[1]:.3f}")

    return final_xgb, final_lgb, meta, {"mae": mae, "r2": r2}


def save_model(xgb_model, lgb_model, meta, metrics, feature_names):
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(xgb_model, os.path.join(MODEL_DIR, "xgb.pkl"))
    joblib.dump(lgb_model, os.path.join(MODEL_DIR, "lgb.pkl"))
    joblib.dump(meta, os.path.join(MODEL_DIR, "meta.pkl"))
    with open(os.path.join(MODEL_DIR, "features.json"), "w") as f:
        json.dump(feature_names, f)
    with open(os.path.join(MODEL_DIR, "metrics.json"), "w") as f:
        json.dump(metrics, f)
    print(f"  [M1] Modeles sauvegardes dans {MODEL_DIR}")


def run():
    print("\n" + "=" * 50)
    print("  M1 - AVM VENTE (XGBoost + LightGBM Stacking)")
    print("=" * 50)

    df = load_data()
    X, y = prepare_features(df)
    if len(X) < 20:
        print("  [M1] Pas assez de donnees pour l'entrainement")
        return

    xgb_model, lgb_model, meta, metrics = train_stacking(X, y)
    save_model(xgb_model, lgb_model, meta, metrics, list(X.columns))

    print("  [M1] Entrainement termine.\n")


if __name__ == "__main__":
    run()