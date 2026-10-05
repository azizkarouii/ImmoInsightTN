import numpy as np
import pandas as pd
from pymongo import MongoClient
from scipy.spatial import cKDTree
from statistics import mean
from datetime import datetime, timezone
from dotenv import load_dotenv
import os

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "immoinsight")

def get_db():
    return MongoClient(MONGO_URI)[MONGO_DB]

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam/2)**2
    return R * 2 * np.arcsin(np.sqrt(a))

def add_poi_distances(df, poi_df, poi_type):
    poi_subset = poi_df[poi_df["type"] == poi_type][["lat", "lon"]].dropna()
    if poi_subset.empty or df[["lat", "lon"]].dropna().empty:
        df[f"dist_{poi_type}_km"] = None
        return df

    tree = cKDTree(np.radians(poi_subset[["lat", "lon"]].values))

    def dist_to_nearest(row):
        if pd.isna(row.get("lat")) or pd.isna(row.get("lon")):
            return None
        coords = np.radians([[row["lat"], row["lon"]]])
        dist, idx = tree.query(coords)
        poi_lat, poi_lon = poi_subset.iloc[idx[0]]
        return haversine(row["lat"], row["lon"], poi_lat, poi_lon)

    df[f"dist_{poi_type}_km"] = df.apply(dist_to_nearest, axis=1)
    return df

def engineer_features(clean_name):
    db = get_db()
    docs = list(db[clean_name].find({}))
    if not docs:
        print(f"  [FEAT] Aucune donnée dans {clean_name}")
        return

    df = pd.DataFrame(docs)
    print(f"  [FEAT] {clean_name}: {len(df)} annonces")
    now = pd.Timestamp.now(tz=timezone.utc)

    # Load POI data
    poi_docs = list(db["geo_poi"].find({}))
    poi_df = pd.DataFrame(poi_docs)
    if poi_df.empty:
        print(f"  [FEAT] Aucun POI disponible, skipping distances")
    else:
        distance_cols = []
        for poi_type in ["plages", "ecoles", "universites", "hopitaux",
                         "commerces", "pharmacies", "restaurants", "transports"]:
            if "type" in poi_df.columns and poi_type in poi_df["type"].values:
                add_poi_distances(df, poi_df, poi_type)
                distance_cols.append(f"dist_{poi_type}_km")

        if distance_cols:
            df["nearest_poi_km"] = df[distance_cols].min(axis=1, skipna=True)
            df["accessibilite_score"] = np.where(
                df["nearest_poi_km"].notna(),
                np.clip(100 - (df["nearest_poi_km"] * 12), 0, 100),
                None,
            )

    # Prix au m2 (vente/location only)
    if "surface" in df.columns and "prix" in df.columns:
        df["surface"] = pd.to_numeric(df["surface"], errors="coerce")
        df["prix"] = pd.to_numeric(df["prix"], errors="coerce")
        df["prix_m2"] = np.where(
            df["surface"].notna() & (df["surface"] > 0),
            df["prix"] / df["surface"],
            None,
        )

    if "scraped_at" in df.columns:
        scraped_at = pd.to_datetime(df["scraped_at"], errors="coerce", utc=True)
        df["listing_age_days"] = (now - scraped_at).dt.total_seconds().div(86400).round(1)

    if "first_seen" in df.columns:
        first_seen = pd.to_datetime(df["first_seen"], errors="coerce", utc=True)
        df["days_on_market"] = (now - first_seen).dt.total_seconds().div(86400).round(1)

    # Indicateurs binaires equipements
    if "equipements" in df.columns:
        df["equipements_str"] = df["equipements"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else (str(x) if pd.notna(x) else "")
        )
        df["equipements_count"] = df["equipements"].apply(lambda x: len(x) if isinstance(x, list) else 0)
        for kw in ["parking", "ascenseur", "piscine", "jardin", "gardien",
                   "terrasse", "balcon", "climatisation", "meuble"]:
            df[f"has_{kw}"] = df["equipements_str"].apply(
                lambda x: int(kw in x.lower())
            )

        df["amenities_score"] = np.clip(df["equipements_count"] * 12.5, 0, 100)

    # Encodage gouvernorat (frequency encoding)
    if "gouvernorat" in df.columns and df["gouvernorat"].notna().any():
        freq = df["gouvernorat"].value_counts(normalize=True)
        df["gouvernorat_freq"] = df["gouvernorat"].map(freq)

    poi_distance_cols = [c for c in df.columns if c.startswith("dist_") and c.endswith("_km")]
    if poi_distance_cols:
        df["poi_count_5km"] = df[poi_distance_cols].apply(
            lambda row: int(sum(1 for value in row if pd.notna(value) and value <= 5)),
            axis=1,
        )
        df["mean_poi_distance_km"] = df[poi_distance_cols].mean(axis=1, skipna=True)
        df["proximite_score"] = np.where(
            df["mean_poi_distance_km"].notna(),
            np.clip(100 - (df["mean_poi_distance_km"] * 15), 0, 100),
            None,
        )

    if "prix_m2" in df.columns:
        if "gouvernorat" in df.columns and df["gouvernorat"].notna().any():
            df["prix_m2_rank_pct"] = df.groupby("gouvernorat")["prix_m2"].rank(pct=True) * 100
        else:
            df["prix_m2_rank_pct"] = df["prix_m2"].rank(pct=True) * 100

        df["market_position"] = pd.cut(
            df["prix_m2_rank_pct"],
            bins=[-1, 25, 75, 100],
            labels=["sous_marche", "marché", "premium"],
        ).astype(str)

    # Simple data quality score to surface richer, more reliable records in the UI.
    quality_columns = [
        "prix",
        "surface",
        "gouvernorat",
        "ville",
        "lat",
        "lon",
        "type_bien",
        "source",
    ]
    quality_flags = []
    for col in quality_columns:
        if col not in df.columns:
            quality_flags.append(pd.Series([0] * len(df), index=df.index))
            continue
        quality_flags.append(df[col].notna().astype(int))

    if quality_flags:
        df["quality_score"] = np.round(
            (pd.concat(quality_flags, axis=1).mean(axis=1) * 100),
            1,
        )
        df["quality_label"] = pd.cut(
            df["quality_score"],
            bins=[-1, 39, 69, 84, 100],
            labels=["faible", "moyenne", "bonne", "excellente"],
        ).astype(str)

    # Update MongoDB with new features
    updated = 0
    for _, row in df.iterrows():
        update = {}
        for col in df.columns:
            if col in ["_id", "url", "titre", "prix", "surface", "description",
                       "equipements", "photos_urls", "price_history",
                       "content_hash", "scraped_at", "first_seen", "equipements_str"]:
                continue
            val = row.get(col)
            if isinstance(val, (list, dict)):
                continue
            try:
                if pd.isna(val):
                    continue
            except (ValueError, TypeError):
                continue
            if isinstance(val, np.generic):
                val = val.item()
            update[col] = val

        if update:
            db[clean_name].update_one(
                {"_id": row["_id"]},
                {"$set": update},
            )
            updated += 1

    print(f"  [FEAT] {clean_name}: {updated} annonces enrichies")

def run():
    print("=" * 50)
    print("ETL - Etape 4: Feature Engineering")
    print("=" * 50)

    for name in ["clean_vente", "clean_location", "clean_estival"]:
        engineer_features(name)

    print("[FEAT] Terminé.\n")

if __name__ == "__main__":
    run()