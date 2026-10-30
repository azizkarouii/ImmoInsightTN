import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from etl.cleaner import run as run_cleaner
from etl.deduplicator import run as run_dedup
from etl.geocoder import run as run_geocoder
from etl.feature_engineer import run as run_features
from etl import qualite

def run_pipeline():
    print("\n" + "=" * 50)
    print("  IMMOINSIGHT TN - PIPELINE ETL COMPLET")
    print("=" * 50)

    qualite.reinitialiser()
    run_cleaner()
    run_dedup()
    run_geocoder()
    run_features()

    # Scores de fiabilité (M4) : dépendent des prix et distances qui viennent d'être recalculés
    from models.m4_fraude.train import run as run_fiabilite
    run_fiabilite()

    # Écart prix affiché / estimation des modèles (alertes « opportunités »)
    from models.opportunites import run as run_opportunites
    run_opportunites()

    # Bilan final
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv()
    db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[os.getenv("MONGO_DB", "immoinsight")]

    print("\n" + "=" * 50)
    print("  BILAN ETL")
    print("=" * 50)
    for col in ["raw_vente", "raw_location", "raw_estival",
                "clean_vente", "clean_location", "clean_estival"]:
        count = db[col].count_documents({})
        print(f"  {col}: {count} docs")

    # Rapport qualité du passage (visible dans la page Statistiques)
    volumes = {
        clean: {
            "annonces_brutes": db[clean.replace("clean_", "raw_")].count_documents({}),
            "annonces_propres": db[clean].count_documents({}),
            "sans_coordonnees": db[clean].count_documents({"lat": None}),
            "sans_surface": db[clean].count_documents({"surface": None}),
        }
        for clean in ["clean_vente", "clean_location", "clean_estival"]
    }
    rapport = qualite.sauvegarder_rapport(db, volumes)
    print("\n  QUALITE")
    for col, compteurs in rapport["collections"].items():
        print(f"  {col}: " + ", ".join(f"{k}={v}" for k, v in compteurs.items()))
    print("[ETL] Termine")

    # Show sample features
    print("\n  Echantillon features clean_vente:")
    sample = db["clean_vente"].find_one({}, {
        "_id": 0, "url": 0, "description": 0, "photos_urls": 0,
        "price_history": 0, "content_hash": 0, "scraped_at": 0,
    })
    if sample:
        for k, v in sorted(sample.items()):
            print(f"    {k}: {v}")


if __name__ == "__main__":
    run_pipeline()