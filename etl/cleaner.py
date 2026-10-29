import pandas as pd
import re
import numpy as np
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv
import os

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "immoinsight")

def get_db():
    return MongoClient(MONGO_URI)[MONGO_DB]

def clean_prix(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (float, np.floating)):
        return int(round(float(val)))
    val = str(val).lower().strip()
    if any(term in val for term in ["consulter", "prix sur demande", "négociable", "negociable"]):
        return None
    val = val.replace("\u00a0", " ").replace("'", "")
    match = re.search(r"(\d[\d\s.,]*)\s*([km])?", val)
    if not match:
        nums = re.sub(r"[^\d]", "", val)
        return int(nums) if nums else None

    raw = match.group(1).replace(" ", "")
    suffix = match.group(2)

    if "," in raw or "." in raw:
        separators = [sep for sep in [",", "."] if sep in raw]
        if len(separators) > 1:
            raw = re.sub(r"[.,]", "", raw)
        else:
            sep = separators[0]
            before, after = raw.split(sep, 1)
            if len(after) == 3 and len(before) <= 3:
                raw = before + after
            else:
                raw = before + "." + after

    number = float(raw)
    suffix = match.group(2)
    if suffix == "k":
        number *= 1000
    elif suffix == "m":
        number *= 1000000
    return int(round(number))

def clean_surface(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if isinstance(val, (int, np.integer, float, np.floating)):
        return float(val)

    text = str(val).lower().replace("\u00a0", " ").replace("m²", "").strip()
    match = re.search(r"(\d[\d\s.,]*)", text)
    if not match:
        return None

    raw = match.group(1).replace(" ", "")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        parts = raw.split(",")
        raw = ".".join(parts) if len(parts[-1]) in (1, 2) else "".join(parts)
    elif "." in raw:
        parts = raw.split(".")
        raw = ".".join(parts) if len(parts[-1]) in (1, 2) else "".join(parts)

    try:
        return float(raw)
    except ValueError:
        nums = re.sub(r"[^\d]", "", raw)
        return float(nums) if nums else None


def clean_text_field(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    text = str(val).strip()
    if not text or text.lower() in ("nan", "none", "null"):
        return None
    return text


def clean_titre(val):
    text = clean_text_field(val)
    if text is None:
        return None
    # Tayara suffixe ses titres de page par " | Tayara"
    return re.sub(r"\s*[|\-]\s*Tayara\s*$", "", text, flags=re.IGNORECASE) or None


SURFACE_MIN, SURFACE_MAX = 15, 2000


RENTAL_TITLE_RE = re.compile(r"(?:\b[àa]\s+louer\b|\blocation\b)", re.IGNORECASE)


def is_rental_title(titre):
    """Annonce de location publiée dans une rubrique vente (fréquent sur Tayara)."""
    return bool(titre) and bool(RENTAL_TITLE_RE.search(str(titre)))


def bucket_value(value, bins, labels, default=None):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return default
    for upper, label in zip(bins, labels):
        if value <= upper:
            return label
    return labels[-1] if labels else default

def normalize_type_bien(titre, type_bien):
    if titre is None or (isinstance(titre, float) and np.isnan(titre)) or str(titre).strip() == "":
        return type_bien or "appartement"
    t = titre.lower()
    if any(k in t for k in ["villa", "maison", "duplex", "bungalow"]):
        return "villa"
    if "terrain" in t:
        return "terrain"
    if "local" in t or "commercial" in t:
        return "local_commercial"
    if "bureau" in t:
        return "bureau"
    if "studio" in t:
        return "appartement"
    return type_bien or "appartement"

def clean_collection(collection_name):
    db = get_db()
    raw = list(db[collection_name].find({}))
    if not raw:
        print(f"  [CLEAN] Aucune donnée dans {collection_name}")
        return pd.DataFrame()

    df = pd.DataFrame(raw)

    # Normalize prix (or prix_nuit for estival) — décider par collection,
    # pas par colonnes (une annonce mubawab peut introduire un champ "prix"
    # qui détournerait la branche pour tout le lot booking).
    if "estival" in collection_name:
        if "prix_nuit" in df.columns:
            df["prix_nuit"] = df["prix_nuit"].apply(clean_prix)
        else:
            df["prix_nuit"] = None
        if "prix" in df.columns:
            df["prix"] = df["prix"].apply(clean_prix)
        else:
            df["prix"] = None
        df["prix"] = df["prix_nuit"].fillna(df["prix"])
    else:
        df["prix"] = df["prix"].apply(clean_prix)

    if "surface" in df.columns:
        df["surface"] = df["surface"].apply(clean_surface)
        # Surfaces d'erreurs de scraping (1 m², 2935 m²...) : inconnues plutôt que fausses
        df["surface"] = df["surface"].apply(
            lambda v: v if v is not None and not pd.isna(v) and SURFACE_MIN <= v <= SURFACE_MAX else None
        )

    # Titre manquant (booking stocke "nom")
    if "nom" in df.columns and ("titre" not in df.columns or df["titre"].isna().all()):
        df["titre"] = df["nom"]

    for field in ["titre", "description", "ville", "gouvernorat", "quartier", "adresse_brute", "source"]:
        if field in df.columns:
            df[field] = df[field].apply(clean_text_field)
    if "titre" in df.columns:
        df["titre"] = df["titre"].apply(clean_titre)

    if "titre" in df.columns:
        df["titre_len"] = df["titre"].fillna("").astype(str).str.len()
    if "description" in df.columns:
        df["description_len"] = df["description"].fillna("").astype(str).str.len()
        df["has_description"] = df["description"].fillna("").astype(str).str.len().gt(0).astype(int)
    if "photos_urls" in df.columns:
        df["photos_count"] = df["photos_urls"].apply(lambda x: len(x) if isinstance(x, list) else 0)
    if "equipements" in df.columns:
        df["equipements_count"] = df["equipements"].apply(lambda x: len(x) if isinstance(x, list) else 0)

    if "surface" in df.columns:
        df["surface_band"] = df["surface"].apply(
            lambda v: bucket_value(float(v) if v is not None and not pd.isna(v) else None,
                                   [40, 70, 100, 150, 250],
                                   ["t0_40", "t40_70", "t70_100", "t100_150", "t150_250", "t250_plus"])
        )

    if "prix" in df.columns:
        df["prix_band"] = df["prix"].apply(
            lambda v: bucket_value(float(v) if v is not None and not pd.isna(v) else None,
                                   [100000, 250000, 500000, 1000000, 2000000],
                                   ["p0_100k", "p100k_250k", "p250k_500k", "p500k_1m", "p1m_2m", "p2m_plus"])
        )

    if "surface" in df.columns and "prix" in df.columns:
        df["prix_m2"] = np.where(
            pd.to_numeric(df["surface"], errors="coerce").notna()
            & (pd.to_numeric(df["surface"], errors="coerce") > 0),
            pd.to_numeric(df["prix"], errors="coerce") / pd.to_numeric(df["surface"], errors="coerce"),
            None,
        )
        df["prix_m2_band"] = df["prix_m2"].apply(
            lambda v: bucket_value(float(v) if v is not None and not pd.isna(v) else None,
                                   [2500, 5000, 7500, 10000, 15000],
                                   ["m2_0_2500", "m2_2500_5000", "m2_5000_7500", "m2_7500_10000", "m2_10000_15000", "m2_15000_plus"])
        )

    # Drop rows without a valid price after normalization
    df = df.dropna(subset=["prix"])

    # Normalize type_bien
    if "type_bien" not in df.columns:
        df["type_bien"] = "appartement"
    df["type_bien"] = df.apply(
        lambda r: normalize_type_bien(r.get("titre"), r.get("type_bien")), axis=1
    )

    # Normalize gouvernorat (fallback sur ville — booking n'a que "ville")
    if "gouvernorat" not in df.columns:
        df["gouvernorat"] = df.get("ville", "")
    else:
        df["gouvernorat"] = df["gouvernorat"].fillna(df.get("ville", ""))

    # Remove duplicates by URL
    if "url" in df.columns:
        df["url"] = df["url"].fillna("")
        df = df.drop_duplicates(subset=["url"], keep="last")

    # Filter out non-residential types from vente/location
    if "vente" in collection_name or ("location" in collection_name and "estival" not in collection_name):
        residential = ["appartement", "villa", "maison", "duplex", "bungalow"]
        before = len(df)
        df = df[df["type_bien"].isin(residential)]
        print(f"  [CLEAN] {before - len(df)} non-residentiels supprimes")

    # Les locations mal classées faussent les prix de vente (loyers de 10 000 DT...)
    if "vente" in collection_name and "titre" in df.columns:
        before = len(df)
        df = df[~df["titre"].apply(is_rental_title)]
        print(f"  [CLEAN] {before - len(df)} locations retirees de {collection_name}")

    # Filter outliers for vente
    if "vente" in collection_name:
        df = df[(df["prix"].isna()) | ((df["prix"] >= 10000) & (df["prix"] <= 5000000))]
    elif "location" in collection_name and "estival" not in collection_name:
        df = df[(df["prix"].isna()) | ((df["prix"] >= 100) & (df["prix"] <= 10000))]

    # Remove entries without price
    df = df[df["prix"].notna()]

    print(f"  [CLEAN] {collection_name}: {len(raw)} -> {len(df)} annonces propres")
    return df

def save_clean(df, clean_name):
    if df.empty:
        return
    db = get_db()
    col = db[clean_name]
    col.drop()  # Reset clean collection
    records = df.to_dict("records")
    for r in records:
        r.pop("_id", None)
        # NaN pandas -> null Mongo (sinon "nan" est relu comme texte, ex. par le géocodeur)
        for k, v in r.items():
            if isinstance(v, float) and np.isnan(v):
                r[k] = None
    col.insert_many(records)
    col.create_index([("url", ASCENDING)], unique=True)
    if "lat" in df.columns:
        col.create_index([("lat", ASCENDING), ("lon", ASCENDING)])
    print(f"  [CLEAN] Sauvegardé {len(records)} dans {clean_name}")

def run():
    print("=" * 50)
    print("ETL - Etape 1: Nettoyage")
    print("=" * 50)

    for raw, clean in [
        ("raw_vente", "clean_vente"),
        ("raw_location", "clean_location"),
        ("raw_estival", "clean_estival"),
    ]:
        df = clean_collection(raw)
        if not df.empty:
            save_clean(df, clean)

    print("[CLEAN] Terminé.\n")

if __name__ == "__main__":
    run()