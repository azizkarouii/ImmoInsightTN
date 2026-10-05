import time
import requests
from .utils import get_db

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "ImmoInsightTN/1.0 (educational project)"}

POI_CATEGORIES = {
    "plages":     "beach",
    "ecoles":     "school",
    "universites": "university",
    "hopitaux":   "hospital",
    "commerces":  "supermarket",
    "pharmacies": "pharmacy",
    "restaurants": "restaurant",
    "transports": "station",
}

CITIES = [
    ("Tunis", 36.8065, 10.1815),
    ("Sfax", 34.7400, 10.7600),
    ("Sousse", 35.8256, 10.6364),
    ("Djerba", 33.8760, 10.8570),
    ("Hammamet", 36.3900, 10.6100),
    ("Monastir", 35.7700, 10.8300),
    ("Nabeul", 36.4500, 10.7300),
    ("Mahdia", 35.5000, 11.0600),
    ("Tabarka", 36.9500, 8.7600),
    ("Bizerte", 37.2700, 9.8700),
    ("Gabès", 33.8800, 10.1000),
    ("Kairouan", 35.6800, 10.1000),
    ("La Marsa", 36.8800, 10.3300),
    ("Ariana", 36.8600, 10.2000),
]

def collect_osm_poi():
    db = get_db()
    collection = db["geo_poi"]

    collection.create_index([("lat", 1), ("lon", 1)])
    collection.create_index([("type", 1)])

    total = 0

    for poi_fr, poi_en in POI_CATEGORIES.items():
        for city, lat, lon in CITIES:
            url = (
                f"{NOMINATIM_URL}"
                f"?q={poi_en}+in+{city}+Tunisia"
                f"&format=json&limit=20&countrycodes=tn"
                f"&bounded=1&viewbox={lon-0.5},{lat-0.5},{lon+0.5},{lat+0.5}"
            )
            try:
                response = requests.get(url, headers=NOMINATIM_HEADERS, timeout=15)
                results = response.json()

                for res in results:
                    poi = {
                        "type": poi_fr,
                        "lat":  float(res["lat"]),
                        "lon":  float(res["lon"]),
                        "name": res.get("display_name", "").split(",")[0],
                        "city": city,
                        "osm_id": res.get("osm_id"),
                        "osm_type": res.get("osm_type"),
                    }
                    collection.update_one(
                        {"osm_id": poi["osm_id"], "osm_type": poi["osm_type"]},
                        {"$set": poi},
                        upsert=True
                    )
                    total += 1

                if results:
                    print(f"  {poi_fr} à {city}: {len(results)} POI")

            except Exception as e:
                pass

            time.sleep(1)

    count = collection.count_documents({})
    print(f"\n[OSM] Collecte terminée : {total} POI insérés (total: {count})")


if __name__ == "__main__":
    collect_osm_poi()
