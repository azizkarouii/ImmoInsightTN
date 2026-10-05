from fastapi import APIRouter, Query
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from .. import clean_doc

load_dotenv()
router = APIRouter()
db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[os.getenv("MONGO_DB", "immoinsight")]


@router.get("/{annonce_id}")
def fiabilite_annonce(annonce_id: str):
    from bson.objectid import ObjectId
    try:
        doc = db["clean_vente"].find_one({"_id": ObjectId(annonce_id)})
        if not doc:
            return {"statut": "erreur", "message": "Annonce non trouvee"}
        return {
            "statut": "succes",
            "fiabilite": doc.get("fiabilite"),
            "titre": doc.get("titre"),
            "prix": doc.get("prix"),
        }
    except Exception:
        return {"statut": "erreur", "message": "ID invalide"}


@router.get("/")
def liste_fiabilite(
    min_score: float = Query(0, ge=0, le=100),
    max_score: float = Query(100, ge=0, le=100),
    limit: int = Query(50, le=200),
):
    docs = list(
        db["clean_vente"]
        .find({"fiabilite": {"$gte": min_score, "$lte": max_score}},
              {"_id": 1, "titre": 1, "prix": 1, "fiabilite": 1, "source": 1, "url": 1})
        .sort("fiabilite", 1)
        .limit(limit)
    )
    for d in docs:
        d["_id"] = str(d["_id"])
    return clean_doc({"total": len(docs), "min_score": min_score, "max_score": max_score, "data": docs})


@router.get("/alertes")
def alertes_fiabilite(seuil: float = Query(30, le=100)):
    docs = list(
        db["clean_vente"]
        .find({"fiabilite": {"$lte": seuil}},
              {"_id": 1, "titre": 1, "prix": 1, "fiabilite": 1, "source": 1, "url": 1})
        .sort("fiabilite", 1)
        .limit(50)
    )
    for d in docs:
        d["_id"] = str(d["_id"])
    return clean_doc({"total": len(docs), "seuil": seuil, "data": docs})
