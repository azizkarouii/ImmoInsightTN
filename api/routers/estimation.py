from fastapi import APIRouter, Query
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

router = APIRouter()


@router.get("/vente/estimation")
def estimer_vente(
    surface: float = Query(...),
    nb_pieces: int = Query(None),
    nb_chambres: int = Query(None),
    gouvernorat: str = Query(None),
    type_bien: str = Query("appartement", pattern="^(appartement|villa|terrain)$"),
    has_parking: int = Query(0),
    has_ascenseur: int = Query(0),
    has_piscine: int = Query(0),
):
    try:
        from models.m1_avm_vente.predict import predict_one
        annonce = {
            "surface": surface,
            "nb_pieces": nb_pieces,
            "nb_chambres": nb_chambres,
            "gouvernorat": gouvernorat,
            "type_bien": type_bien,
            "has_parking": has_parking,
            "has_ascenseur": has_ascenseur,
            "has_piscine": has_piscine,
        }
        result = predict_one(annonce)
        return {"statut": "succes", **result}
    except Exception as e:
        return {"statut": "erreur", "message": str(e)}


@router.get("/location/estimation")
def estimer_location(
    surface: float = Query(None),
    nb_pieces: int = Query(None),
    nb_chambres: int = Query(None),
    ville: str = Query(None),
    type_bien: str = Query("appartement", pattern="^(appartement|villa|terrain)$"),
):
    try:
        from models.m2_loyer_classique.predict import predict_one
        annonce = {
            "surface": surface,
            "nb_pieces": nb_pieces,
            "nb_chambres": nb_chambres,
            "ville": ville,
            "type_bien": type_bien,
        }
        result = predict_one(annonce)
        return {"statut": "succes", **result}
    except Exception as e:
        return {"statut": "erreur", "message": str(e)}


@router.get("/estival/estimation")
def estimer_estival(
    ville: str = Query(...),
    score_avis: float = Query(None),
    dist_plages: float = Query(None),
):
    try:
        from models.m3_pricing_estival.predict import predict_one
        result = predict_one(ville, score_avis, dist_plages)
        return {"statut": "succes", **result}
    except Exception as e:
        return {"statut": "erreur", "message": str(e)}


@router.get("/vente/prix_m2/moyen")
def prix_m2_moyen(
    gouvernorat: str = Query(None),
    type_bien: str = Query(None),
):
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv()
    db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[os.getenv("MONGO_DB", "immoinsight")]

    match = {}
    if gouvernorat:
        match["gouvernorat"] = gouvernorat
    if type_bien:
        match["type_bien"] = type_bien

    pipeline = [
        {"$match": {"prix_m2": {"$ne": None}, **match}},
        {"$group": {
            "_id": "$gouvernorat",
            "prix_m2_moyen": {"$avg": "$prix_m2"},
            "count": {"$sum": 1},
            "prix_m2_min": {"$min": "$prix_m2"},
            "prix_m2_max": {"$max": "$prix_m2"},
        }},
        {"$sort": {"count": -1}},
    ]
    results = list(db["clean_vente"].aggregate(pipeline))
    return {"data": results}
