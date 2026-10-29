from fastapi import APIRouter, Query
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from .. import clean_doc
import math
import re

load_dotenv()
router = APIRouter()
db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[os.getenv("MONGO_DB", "immoinsight")]


def _to_float(value):
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError):
        pass
    return None


def fix_url(url):
    """Le scraper Booking préfixait des liens déjà absolus : https://www.booking.comhttps://..."""
    if not isinstance(url, str):
        return url
    return re.sub(r"^(?:https?://[^/]+)+(?=https?://)", "", url)


def sanitize_map_points(docs):
    """Ne garde que les points aux coordonnées numériques situées en Tunisie.

    Les coordonnées ne sont pas modifiées : le regroupement des annonces qui
    partagent une même position est géré côté carte (clustering).
    """
    sanitized = []
    for doc in docs:
        lat = _to_float(doc.get("lat"))
        lon = _to_float(doc.get("lon"))
        if lat is None or lon is None:
            continue
        if not (30 <= lat <= 38 and 7 <= lon <= 12):
            continue
        sanitized.append({**doc, "lat": lat, "lon": lon, "url": fix_url(doc.get("url"))})
    return sanitized


@router.get("/")
def list_annonces(
    collection: str = Query("clean_vente", pattern="^(clean_vente|clean_location|clean_estival)$"),
    limit: int = Query(20, le=100),
    offset: int = 0,
    sort: str = "-scraped_at",
    with_history: bool = Query(False, description="Uniquement les annonces ayant au moins 2 prix historisés"),
):
    sort_field = sort.lstrip("-")
    sort_dir = -1 if sort.startswith("-") else 1
    query = {"price_history.1": {"$exists": True}} if with_history else {}
    projection = {"_id": 0, "content_hash": 0}
    if not with_history:
        projection["price_history"] = 0
    docs = list(
        db[collection]
        .find(query, projection)
        .sort(sort_field, sort_dir)
        .skip(offset)
        .limit(limit)
    )
    for d in docs:
        d["url"] = fix_url(d.get("url"))
    total = db[collection].count_documents(query)
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
    limit: int = Query(1000, ge=1, le=5000),
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
            "geo_type": 1, "geocoded_query": 1,
        })
        .limit(limit)
    )

    docs = sanitize_map_points(docs)
    return clean_doc({"total": len(docs), "data": docs})