from fastapi import APIRouter, Query
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
from .. import clean_doc

load_dotenv()
router = APIRouter()
db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[os.getenv("MONGO_DB", "immoinsight")]


@router.get("/prix")
def alertes_prix(
    collection: str = Query("clean_vente", pattern="^(clean_vente|clean_location|clean_estival)$"),
    jours: int = 7,
):
    cutoff = datetime.now() - timedelta(days=jours)
    docs = list(
        db[collection]
        .find({"price_history": {"$ne": None}, "scraped_at": {"$gte": cutoff}},
              {"_id": 0, "titre": 1, "url": 1, "prix": 1, "price_history": 1, "source": 1})
        .sort("scraped_at", -1)
        .limit(50)
    )
    for d in docs:
        if d.get("price_history"):
            d["price_history"] = [
                h for h in d["price_history"]
                if datetime.fromisoformat(h.get("date", "")) >= cutoff
            ]
    return clean_doc({"collection": collection, "jours": jours, "count": len(docs), "data": docs})


@router.get("/nouvelles")
def alertes_nouvelles(
    collection: str = Query("clean_vente", pattern="^(clean_vente|clean_location|clean_estival)$"),
    jours: int = 3,
):
    cutoff = datetime.now() - timedelta(days=jours)
    docs = list(
        db[collection]
        .find({"is_new": True, "scraped_at": {"$gte": cutoff}},
              {"_id": 0, "titre": 1, "url": 1, "prix": 1, "source": 1, "scraped_at": 1, "type_bien": 1})
        .sort("scraped_at", -1)
        .limit(50)
    )
    return clean_doc({"collection": collection, "jours": jours, "count": len(docs), "data": docs})


@router.get("/supprimees")
def alertes_supprimees(
    collection: str = Query("clean_vente", pattern="^(clean_vente|clean_location|clean_estival)$"),
    jours: int = 7,
):
    cutoff = datetime.now() - timedelta(days=jours)
    docs = list(
        db[collection]
        .find({"status": "supprime", "scraped_at": {"$gte": cutoff}},
              {"_id": 0, "titre": 1, "url": 1, "source": 1, "scraped_at": 1})
        .sort("scraped_at", -1)
        .limit(50)
    )
    return clean_doc({"collection": collection, "jours": jours, "count": len(docs), "data": docs})