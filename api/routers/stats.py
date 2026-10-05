from fastapi import APIRouter
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timedelta
from statistics import mean, median
from collections import Counter
import os
from .. import clean_doc

load_dotenv()
router = APIRouter()
db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[os.getenv("MONGO_DB", "immoinsight")]


def _collection_overview(col: str):
    docs = list(
        db[col].find(
            {},
            {
                "prix": 1,
                "lat": 1,
                "lon": 1,
                "source": 1,
                "quality_score": 1,
            },
        )
    )

    total = len(docs)
    prices = [float(d["prix"]) for d in docs if d.get("prix") is not None]
    geo = [d for d in docs if d.get("lat") is not None and d.get("lon") is not None]
    quality_scores = [float(d["quality_score"]) for d in docs if d.get("quality_score") is not None]
    sources = Counter(d.get("source") or "Inconnue" for d in docs)
    top_sources = [
        {"source": source, "count": count}
        for source, count in sources.most_common(4)
    ]

    price_summary = None
    if prices:
        prices_sorted = sorted(prices)
        price_summary = {
            "moyen": round(mean(prices), 2),
            "median": round(median(prices_sorted), 2),
            "min": round(min(prices_sorted), 2),
            "max": round(max(prices_sorted), 2),
        }

    return {
        "total": total,
        "couverture_gps_pct": round((len(geo) / total) * 100, 1) if total else 0,
        "qualite_moyenne": round(mean(quality_scores), 1) if quality_scores else None,
        "prix": price_summary,
        "top_sources": top_sources,
    }


@router.get("/stats")
def stats_globales():
    collections = {
        "vente": "clean_vente",
        "location": "clean_location",
        "estival": "clean_estival",
    }
    stats = {}
    for key, col in collections.items():
        overview = _collection_overview(col)
        stats[key] = {
            "total": db[col].count_documents({}),
            "nouveaux_7j": db[col].count_documents({
                "scraped_at": {"$gte": datetime.now() - timedelta(days=7)}
            }),
            "avec_gps": db[col].count_documents({"lat": {"$ne": None}, "lon": {"$ne": None}}),
            "couverture_gps_pct": overview["couverture_gps_pct"],
            "qualite_moyenne": overview["qualite_moyenne"],
            "top_sources": overview["top_sources"],
        }

    # Prix moyen par type
    prix_moyen = {}
    for col in ["clean_vente", "clean_estival"]:
        pipeline = [
            {"$group": {"_id": None, "moyen": {"$avg": "$prix"}}}
        ]
        result = list(db[col].aggregate(pipeline))
        prix_moyen[col] = round(result[0]["moyen"], 2) if result else None

    prix_median = {
        col: _collection_overview(col)["prix"]
        for col in ["clean_vente", "clean_estival"]
    }

    total_geo = sum(s["avec_gps"] for s in stats.values())
    total_annonces = sum(s["total"] for s in stats.values())

    # Sources distribution
    sources = {}
    for col in ["clean_vente", "clean_estival"]:
        pipeline = [
            {"$group": {"_id": "$source", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        sources[col] = {r["_id"]: r["count"] for r in db[col].aggregate(pipeline)}

    return clean_doc({
        "collections": stats,
        "prix_moyen": prix_moyen,
        "prix_median": prix_median,
        "sources": sources,
        "total_annonces": sum(s["total"] for s in stats.values()),
        "global_geo_coverage_pct": round((total_geo / total_annonces) * 100, 1) if total_annonces else 0,
    })


@router.get("/stats/prix_par_gouvernorat")
def prix_par_gouvernorat(
    collection: str = "clean_vente",
):
    pipeline = [
        {"$match": {"prix": {"$ne": None}, "gouvernorat": {"$ne": None}}},
        {"$group": {
            "_id": "$gouvernorat",
            "prix_moyen": {"$avg": "$prix"},
            "prix_min": {"$min": "$prix"},
            "prix_max": {"$max": "$prix"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
    ]
    results = list(db[collection].aggregate(pipeline))
    return clean_doc({"collection": collection, "data": results})


@router.get("/stats/prix_par_ville")
def prix_par_ville(
    collection: str = "clean_estival",
):
    pipeline = [
        {"$match": {"prix": {"$ne": None}, "ville": {"$ne": None}}},
        {"$group": {
            "_id": "$ville",
            "prix_moyen": {"$avg": "$prix"},
            "prix_min": {"$min": "$prix"},
            "prix_max": {"$max": "$prix"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
    ]
    results = list(db[collection].aggregate(pipeline))
    return clean_doc({"collection": collection, "data": results})
