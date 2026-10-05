import pandas as pd
from datetime import datetime
from .utils import get_db

def load_inside_airbnb():
    db = get_db()
    collection = db["raw_estival"]

    DATASETS = {
        "tunis":    "http://data.insideairbnb.com/tunisia/tunis-governorate/tunis/visualisations/listings.csv",
        "djerba":   "http://data.insideairbnb.com/tunisia/medenine/djerba/visualisations/listings.csv",
        "sousse":   "http://data.insideairbnb.com/tunisia/sousse/sousse/visualisations/listings.csv",
        "hammamet": "http://data.insideairbnb.com/tunisia/nabeul/hammamet/visualisations/listings.csv",
    }

    for city, url in DATASETS.items():
        print(f"[AIRBNB] Chargement {city}...")
        try:
            df = pd.read_csv(url)

            colonnes_utiles = [
                "id", "name", "neighbourhood", "latitude", "longitude",
                "room_type", "price", "minimum_nights", "number_of_reviews",
                "reviews_per_month", "availability_365", "calculated_host_listings_count"
            ]
            colonnes_presentes = [c for c in colonnes_utiles if c in df.columns]
            df = df[colonnes_presentes].copy()

            df["source"]    = "inside_airbnb"
            df["city"]      = city
            df["type_offre"] = "location_estivale"
            df["loaded_at"] = datetime.utcnow().isoformat()

            if "price" in df.columns:
                df["prix_nuit"] = df["price"].astype(str).str.replace(r"[$,€]", "", regex=True)
                df["prix_nuit"] = pd.to_numeric(df["prix_nuit"], errors="coerce")

            records = df.where(pd.notnull(df), None).to_dict("records")

            for record in records:
                record_id = f"airbnb_{city}_{record.get('id', '')}"
                collection.update_one(
                    {"_airbnb_key": record_id},
                    {"$set": {**record, "_airbnb_key": record_id}},
                    upsert=True
                )

            print(f"  → {len(records)} annonces Airbnb chargées pour {city}")

        except Exception as e:
            print(f"[AIRBNB] Erreur pour {city}: {e}")


if __name__ == "__main__":
    load_inside_airbnb()
