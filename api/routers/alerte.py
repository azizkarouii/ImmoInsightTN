from fastapi import APIRouter, Query
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import os
import re
from .. import clean_doc
from .annonces import fix_url

load_dotenv()
router = APIRouter()
db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[os.getenv("MONGO_DB", "immoinsight")]

COLLECTIONS = "^(clean_vente|clean_location|clean_estival)$"
RAW = {"clean_vente": "raw_vente", "clean_location": "raw_location", "clean_estival": "raw_estival"}
CHAMPS = {
    "_id": 0, "titre": 1, "nom": 1, "url": 1, "prix": 1, "surface": 1, "ville": 1, "gouvernorat": 1,
    "type_bien": 1, "source": 1, "first_seen": 1, "scraped_at": 1, "nb_chambres": 1,
    "prix_estime": 1, "ecart_estimation_pct": 1, "opportunite": 1, "fiabilite": 1,
}


def cutoff_iso(jours):
    """Les dates sont stockées en texte ISO (UTC) par les scrapers : la comparaison
    doit se faire en texte (comparer à un datetime ne renvoyait jamais rien)."""
    return (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=jours)).isoformat()


def _prix_valides(history):
    return [h for h in history or [] if isinstance(h, dict) and isinstance(h.get("prix"), (int, float)) and h["prix"] > 0]


def variation_prix(history, depuis):
    """Dernier changement de prix survenu après `depuis` : (ancien, nouveau, date) ou None."""
    points = _prix_valides(history)
    for i in range(len(points) - 1, 0, -1):
        if points[i]["prix"] != points[i - 1]["prix"]:
            if str(points[i].get("date", "")) >= depuis:
                return points[i - 1]["prix"], points[i]["prix"], points[i].get("date")
            return None
    return None


# Colonnes triables du tableau des nouvelles annonces -> champs Mongo
TRIS_NOUVELLES = {
    "publiee": ["first_seen"],
    "lieu": ["ville", "gouvernorat"],
    "surface": ["surface"],
    "prix": ["prix"],
    "estimation": ["ecart_estimation_pct"],
}


def _recherche(q):
    """Recherche plein texte simple (titre, nom, ville, gouvernorat, quartier) ; chaque mot doit apparaître."""
    mots = [m for m in re.split(r"\s+", (q or "").strip()) if m][:6]
    champs = ["titre", "nom", "ville", "gouvernorat", "quartier"]
    return [{"$or": [{c: {"$regex": re.escape(m), "$options": "i"}} for c in champs]} for m in mots]


def _nouvelles(collection, jours, limit=50, q=None, tri="publiee", ordre="desc"):
    conditions = [{"first_seen": {"$gte": cutoff_iso(jours)}}, *_recherche(q)]
    query = {"$and": conditions}
    total = db[collection].count_documents(query)
    champs = TRIS_NOUVELLES.get(tri, TRIS_NOUVELLES["publiee"])
    sens = 1 if ordre == "asc" else -1
    # Valeurs manquantes toujours en fin de liste, quel que soit le sens du tri
    pipeline = [
        {"$match": query},
        {"$addFields": {"_vide": {"$cond": [{"$in": [{"$ifNull": [f"${champs[0]}", ""]}, ["", None]]}, 1, 0]}}},
        {"$sort": {"_vide": 1, **{c: sens for c in champs}, "_id": 1}},
        {"$limit": limit},
        {"$project": CHAMPS},  # projection par inclusion : _vide est retiré
    ]
    docs = list(db[collection].aggregate(pipeline, collation={"locale": "fr", "strength": 1}))
    return total, docs


def _changements_prix(collection, jours, sens="tous"):
    depuis = cutoff_iso(jours)
    rows = []
    for d in db[collection].find({"price_history.1": {"$exists": True}, "scraped_at": {"$gte": depuis}},
                                 {**CHAMPS, "price_history": 1}):
        v = variation_prix(d.pop("price_history", None), depuis)
        if not v:
            continue
        ancien, nouveau, date = v
        pct = round((nouveau - ancien) / ancien * 100, 1)
        # Écarts > x5 : erreurs de saisie / de scraping, pas une variation de prix
        if abs(pct) >= 400 or pct <= -80:
            continue
        if (sens == "baisse" and pct >= 0) or (sens == "hausse" and pct <= 0):
            continue
        rows.append({**d, "ancien_prix": ancien, "nouveau_prix": nouveau, "variation_pct": pct, "date_changement": date})
    rows.sort(key=lambda r: r["variation_pct"])
    return rows


def _retirees(collection, jours, limit=50):
    raw = RAW[collection]
    query = {"status": "supprime", "supprime_le": {"$gte": cutoff_iso(jours)}}
    total = db[raw].count_documents(query)
    docs = list(db[raw].find(query, {**CHAMPS, "supprime_le": 1}).sort("supprime_le", -1).limit(limit))
    return total, docs


def seuil_opportunite(collection):
    meta = db["meta"].find_one({"_id": "opportunites"}) or {}
    return meta.get(collection)


def _opportunites(collection, limit=50):
    query = {"opportunite": True}
    total = db[collection].count_documents(query)
    docs = list(db[collection].find(query, CHAMPS).sort("ecart_estimation_pct", 1).limit(limit))
    return total, docs


def _urls(docs):
    for d in docs:
        d["url"] = fix_url(d.get("url"))
        # Booking stocke le nom du logement dans "nom"
        d["titre"] = d.get("titre") or d.pop("nom", None)
        d.pop("nom", None)
    return docs


@router.get("/nouvelles")
def alertes_nouvelles(
    collection: str = Query("clean_vente", pattern=COLLECTIONS),
    jours: int = Query(3, ge=1, le=90),
    limit: int = Query(50, ge=1, le=200),
    q: str = Query(None, max_length=100, description="Mots recherchés dans le titre ou le lieu"),
    tri: str = Query("publiee", pattern="^(publiee|lieu|surface|prix|estimation)$"),
    ordre: str = Query("desc", pattern="^(asc|desc)$"),
):
    total, docs = _nouvelles(collection, jours, limit, q, tri, ordre)
    return clean_doc({"collection": collection, "jours": jours, "q": q, "tri": tri, "ordre": ordre,
                      "count": total, "data": _urls(docs)})


@router.get("/prix")
def alertes_prix(
    collection: str = Query("clean_vente", pattern=COLLECTIONS),
    jours: int = Query(7, ge=1, le=90),
    sens: str = Query("tous", pattern="^(tous|baisse|hausse)$"),
    limit: int = Query(50, ge=1, le=200),
):
    rows = _changements_prix(collection, jours, sens)
    return clean_doc({"collection": collection, "jours": jours, "count": len(rows), "data": _urls(rows[:limit])})


@router.get("/supprimees")
def alertes_supprimees(
    collection: str = Query("clean_vente", pattern=COLLECTIONS),
    jours: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=200),
):
    total, docs = _retirees(collection, jours, limit)
    return clean_doc({"collection": collection, "jours": jours, "count": total, "data": _urls(docs)})


@router.get("/opportunites")
def alertes_opportunites(
    collection: str = Query("clean_vente", pattern="^(clean_vente|clean_location)$"),
    limit: int = Query(50, ge=1, le=200),
):
    """Annonces affichées nettement sous l'estimation du modèle (estimation hors échantillon)."""
    total, docs = _opportunites(collection, limit)
    return clean_doc({"collection": collection, "seuil_pct": seuil_opportunite(collection), "count": total, "data": _urls(docs)})


@router.get("/resume")
def alertes_resume(jours: int = Query(7, ge=1, le=90)):
    """Compteurs par type d'alerte et par collection (badges du tableau de bord)."""
    resume = {}
    for collection in ["clean_vente", "clean_location", "clean_estival"]:
        variations = _changements_prix(collection, jours)
        resume[collection] = {
            "nouvelles": _nouvelles(collection, jours, 1)[0],
            "baisses_prix": sum(1 for r in variations if r["variation_pct"] < 0),
            "hausses_prix": sum(1 for r in variations if r["variation_pct"] > 0),
            "retirees": _retirees(collection, jours, 1)[0],
            "opportunites": _opportunites(collection, 1)[0] if collection != "clean_estival" else 0,
        }
    return {
        "jours": jours,
        "collections": resume,
        "fiabilite_faible": db["clean_vente"].count_documents({"fiabilite": {"$lte": 30}}),
    }


@router.get("/scheduler")
def statut_scheduler():
    """Planning des collectes automatiques et dernières exécutions."""
    from scrapers.scheduler import planning
    return clean_doc({"jobs": planning(db)})
