from fastapi import APIRouter, Query
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from .. import clean_doc
from collections import defaultdict
import math

load_dotenv()
router = APIRouter()
db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[os.getenv("MONGO_DB", "immoinsight")]


@router.get("/")
def list_annonces(
    collection: str = Query("clean_vente", pattern="^(clean_vente|clean_location|clean_estival)$"),
    limit: int = Query(20, le=100),
    offset: int = 0,
    sort: str = "-scraped_at",
):
    sort_field = sort.lstrip("-")
    sort_dir = -1 if sort.startswith("-") else 1
    docs = list(
        db[collection]
        .find({}, {"_id": 0, "content_hash": 0, "price_history": 0})
        .sort(sort_field, sort_dir)
        .skip(offset)
        .limit(limit)
    )
    total = db[collection].count_documents({})
    return clean_doc({"total": total, "offset": offset, "limit": limit, "data": docs})


@router.get("/recentes")
def annonces_recentes(
    collection: str = Query("clean_vente", pattern="^(clean_vente|clean_location|clean_estival)$"),
    jours: int = 7,
):
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=jours)
    docs = list(
        db[collection]
        .find({"is_new": True, "scraped_at": {"$gte": cutoff}},
              {"_id": 0, "content_hash": 0, "price_history": 0})
        .sort("scraped_at", -1)
        .limit(50)
    )
    return clean_doc({"collection": collection, "jours": jours, "count": len(docs), "data": docs})


@router.get("/carte")
def annonces_carte(
    collection: str = Query("clean_vente", pattern="^(clean_vente|clean_estival)$"),
    limit: int = 400,
):
    query = {
        "lat": {"$gte": 30, "$lte": 38},
        "lon": {"$gte": 7, "$lte": 12},
    }
    docs = list(
        db[collection]
        .find(query, {
            "_id": 0, "titre": 1, "prix": 1, "surface": 1,
            "lat": 1, "lon": 1, "type_bien": 1, "url": 1,
            "prix_m2": 1, "fiabilite": 1,
            "dist_plages_km": 1, "dist_transports_km": 1,
            "quality_score": 1, "quality_label": 1, "nearest_poi_km": 1,
            "surface_band": 1, "prix_band": 1, "prix_m2_band": 1,
            "amenities_score": 1, "equipements_count": 1,
            "listing_age_days": 1, "days_on_market": 1,
            "market_position": 1, "proximite_score": 1,
            "gouvernorat": 1, "ville": 1, "source": 1,
            "nb_pieces": 1, "nb_chambres": 1,
        })
        .limit(limit)
    )
    # If multiple documents share the exact same coordinates, slightly offset them
    groups = defaultdict(list)
    for i, d in enumerate(docs):
        try:
            lat = float(d.get('lat'))
            lon = float(d.get('lon'))
            key = (round(lat, 6), round(lon, 6))
        except Exception:
            key = (None, None)
        groups[key].append((i, d))

    for key, items in groups.items():
        if key == (None, None):
            continue
        n = len(items)
        if n <= 1:
            continue
        # spread points in a small circle of radius ~7-12 meters (approx degrees)
        base_radius = 0.00006
        for idx, (i, doc) in enumerate(items):
            angle = (2 * math.pi * idx) / n
            radius = base_radius * (1 + (idx % 3) * 0.25)
            try:
                doc['lat'] = float(doc.get('lat')) + math.cos(angle) * radius
                doc['lon'] = float(doc.get('lon')) + math.sin(angle) * radius
            except Exception:
                continue

    return clean_doc({"total": len(docs), "data": docs})