from fastapi import APIRouter, HTTPException, Query
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

router = APIRouter()


def _model_unavailable(model, exc):
    # Artefacts absents (dossiers artifacts/ non versionnés) : modèle à ré-entraîner
    return HTTPException(
        status_code=503,
        detail=f"Modele {model} indisponible ({exc}). Lancer: python -m models.{model}.train",
    )


@router.get("/vente/estimation")
def estimer_vente(
    surface: float = Query(..., gt=0, le=10000, description="Surface en m²"),
    nb_pieces: int = Query(None, ge=1, le=50),
    nb_chambres: int = Query(None, ge=0, le=50),
    gouvernorat: str = Query(None, description="Gouvernorat ou ville (ex: Tunis, La Marsa)"),
    type_bien: str = Query("appartement", pattern="^(appartement|villa|terrain)$"),
    has_parking: int = Query(0, ge=0, le=1),
    has_ascenseur: int = Query(0, ge=0, le=1),
    has_piscine: int = Query(0, ge=0, le=1),
):
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
    try:
        result = predict_one(annonce)
    except FileNotFoundError as e:
        raise _model_unavailable("m1_avm_vente", e)
    return {"statut": "succes", **result}


@router.get("/location/estimation")
def estimer_location(
    surface: float = Query(None, gt=0, le=10000, description="Surface en m²"),
    nb_pieces: int = Query(None, ge=1, le=50),
    nb_chambres: int = Query(None, ge=0, le=50),
    nb_sdb: int = Query(None, ge=0, le=20),
    ville: str = Query(None, description="Ville ou délégation (ex: La Marsa, Ennasr)"),
    gouvernorat: str = Query(None),
    type_bien: str = Query("appartement", pattern="^(appartement|villa)$"),
    meuble: bool = Query(None),
):
    from models.m2_loyer_classique.predict import predict_one
    annonce = {
        "surface": surface,
        "nb_pieces": nb_pieces,
        "nb_chambres": nb_chambres,
        "nb_sdb": nb_sdb,
        "ville": ville,
        "gouvernorat": gouvernorat,
        "type_bien": type_bien,
        "meuble": meuble,
    }
    try:
        result = predict_one(annonce)
    except FileNotFoundError as e:
        raise _model_unavailable("m2_loyer_classique", e)
    return {"statut": "succes", **result}


@router.get("/estival/estimation")
def estimer_estival(
    ville: str = Query(..., min_length=2, description="Ville balnéaire couverte (ex: Hammamet)"),
    categorie: str = Query(None, pattern="^(appartement|maison_vacances|villa)$"),
    nb_chambres: int = Query(None, ge=0, le=20),
    surface: float = Query(None, gt=0, le=5000),
    nb_lits: int = Query(None, ge=1, le=40),
    nb_sdb: int = Query(None, ge=0, le=20),
    front_de_mer: bool = Query(None),
    dist_plage_km: float = Query(None, ge=0, le=100),
):
    from models.m3_pricing_estival.predict import predict_one, VilleInconnue
    try:
        result = predict_one(ville, categorie=categorie, nb_chambres=nb_chambres, surface=surface,
                             nb_lits=nb_lits, nb_sdb=nb_sdb, front_de_mer=front_de_mer,
                             dist_plage_km=dist_plage_km)
    except VilleInconnue as e:
        raise HTTPException(status_code=422, detail=str(e))
    except FileNotFoundError as e:
        raise _model_unavailable("m3_pricing_estival", e)
    return {"statut": "succes", **result}


@router.get("/estival/villes")
def villes_estivales():
    from models.m3_pricing_estival.predict import villes_couvertes
    try:
        return {"villes": villes_couvertes()}
    except FileNotFoundError as e:
        raise _model_unavailable("m3_pricing_estival", e)


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
