import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from etl.cleaner import run as run_cleaner
from etl.deduplicator import run as run_dedup
from etl.geocoder import run as run_geocoder
from etl.feature_engineer import run as run_features

def run_pipeline():
    print("\n" + "=" * 50)
    print("  IMMOINSIGHT TN - PIPELINE ETL COMPLET")
    print("=" * 50)

    run_cleaner()
    run_dedup()
    run_geocoder()
    run_features()

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