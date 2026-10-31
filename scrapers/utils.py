import os
import re
import hashlib
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "immoinsight")

def get_db():
    client = MongoClient(MONGO_URI)
    return client[MONGO_DB]

def clean_prix(val):
    if not val:
        return None
    val = str(val).lower().strip()
    if "consulter" in val or "prix" in val:
        return None
    val = re.sub(r"[^\d]", "", val)
    return int(val) if val else None

def clean_surface(val):
    if not val:
        return None
    nums = re.sub(r"[^\d]", "", str(val))
    return int(nums) if nums else None

def clean_int(val):
    if not val:
        return None
    nums = re.sub(r"[^\d]", "", str(val))
    return int(nums) if nums else None

ENTIER = re.compile(r"\d+")
NOMBRE_GROUPE = re.compile(r"\d+(?:[.\s]\d+)*")   # "1 160", "2.500"
NOMBRE_VIRGULE = re.compile(r"\d+(?:,\d+)*")      # "1,2"


def nombre_suivi_de(texte, suite, nombre=ENTIER, espaces=True):
    r"""Premier nombre de `texte` suivi de `suite` (regex compilée, testée par match).

    Remplace re.search(r"(\d+)\s*suite", texte) en temps linéaire : une recherche qui
    commence par \d+ réessaie chaque position d'une longue suite de chiffres. Ici les
    nombres sont parcourus une seule fois (finditer) et la suite est ancrée juste après.
    Retourne (nombre, match de la suite) ou None.
    """
    texte = texte or ""
    for m in nombre.finditer(texte):
        i = m.end()
        while espaces and i < len(texte) and texte[i].isspace():
            i += 1
        apres = suite.match(texte, i)
        if apres:
            return m.group(), apres
    return None


def compute_hash(item: dict) -> str:
    content = f"{item.get('titre','')}{item.get('prix','')}{item.get('surface','')}{item.get('description','')}{item.get('ville','')}{item.get('gouvernorat','')}{item.get('type_bien','')}"
    return hashlib.md5(content.encode("utf-8")).hexdigest()

def upsert_annonce(collection, item: dict, key_field="url", refresh_fields=()):
    """Insère ou met à jour une annonce.

    refresh_fields : champs volatils réécrits à chaque passage (note, nb d'avis...).
    Les autres champs ne sont écrits que s'ils manquaient dans le document existant.
    """
    existing = collection.find_one({key_field: item[key_field]})
    new_hash = compute_hash(item)
    item["content_hash"] = new_hash
    item["scraped_at"]   = datetime.utcnow().isoformat()

    if not existing:
        item["is_new"]       = True
        item["first_seen"]   = datetime.utcnow().isoformat()
        item["status"]       = "actif"
        item["price_history"] = [{"prix": item.get("prix"), "date": item["scraped_at"]}]
        collection.insert_one(item)
        return "new"

    updates = {"is_new": False, "content_hash": new_hash, "scraped_at": item["scraped_at"]}

    # Backfill de la ville si manquante (listing /fr/st/{ville}/...)
    if not existing.get("ville") and item.get("ville"):
        updates["ville"] = item["ville"]
    if not existing.get("gouvernorat") and item.get("gouvernorat"):
        updates["gouvernorat"] = item["gouvernorat"]
    if not existing.get("surface") and item.get("surface"):
        updates["surface"] = item["surface"]
    if not existing.get("description") and item.get("description"):
        updates["description"] = item["description"]
    if not existing.get("equipements") and item.get("equipements"):
        updates["equipements"] = item["equipements"]
    if not existing.get("photos_urls") and item.get("photos_urls"):
        updates["photos_urls"] = item["photos_urls"]
    if not existing.get("type_bien") and item.get("type_bien"):
        updates["type_bien"] = item["type_bien"]
    if not existing.get("type_offre") and item.get("type_offre"):
        updates["type_offre"] = item["type_offre"]

    # Nouveaux champs ajoutés aux scrapers (chambres, lits, pension...) : complétés
    # sur les annonces déjà connues
    for field, value in item.items():
        if field in updates or field in (key_field, "prix", "content_hash", "scraped_at"):
            continue
        if value in (None, "", []):
            continue
        if field in refresh_fields or existing.get(field) in (None, "", []):
            updates[field] = value

    if existing.get("prix") != item.get("prix") and item.get("prix"):
        updates["prix"] = item["prix"]
        collection.update_one(
            {key_field: item[key_field]},
            {"$push": {"price_history": {"prix": item["prix"], "date": item["scraped_at"]}},
             "$set": updates}
        )
        return "price_changed"

    # Enregistrer des snapshots plus riches quand de nouvelles infos apparaissent.
    snapshot = {}
    for field in ["description", "equipements", "photos_urls", "surface", "ville", "gouvernorat", "type_bien", "type_offre"]:
        if item.get(field) and item.get(field) != existing.get(field):
            snapshot[field] = item.get(field)
    if snapshot:
        updates["last_snapshot"] = {**snapshot, "date": item["scraped_at"]}

    collection.update_one({key_field: item[key_field]}, {"$set": updates})
    return "updated"
