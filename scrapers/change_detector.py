from datetime import datetime, timedelta
from .utils import get_db

def detect_removed_listings():
    db  = get_db()
    now = datetime.utcnow()

    for col_name in ["raw_vente", "raw_location", "raw_estival"]:
        collection = db[col_name]
        seuil = (now - timedelta(days=14)).isoformat()

        anciennes = collection.find({
            "status": {"$ne": "supprimé"},
            "scraped_at": {"$lt": seuil}
        })

        count = 0
        for annonce in anciennes:
            collection.update_one(
                {"_id": annonce["_id"]},
                {"$set": {
                    "status":      "supprimé",
                    "supprime_le": now.isoformat(),
                }}
            )
            count += 1

        if count:
            print(f"[CDC] {count} annonces marquées 'supprimé' dans {col_name}")

def get_new_listings_today():
    db  = get_db()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    result = {}

    for col_name in ["raw_vente", "raw_location", "raw_estival"]:
        nouvelles = list(db[col_name].find({
            "is_new": True,
            "first_seen": {"$gte": today}
        }, {"_id": 0, "url": 1, "titre": 1, "prix": 1, "gouvernorat": 1}))
        result[col_name] = nouvelles

    return result

def get_price_changes_today():
    db    = get_db()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    result = {}

    for col_name in ["raw_vente", "raw_location"]:
        changements = list(db[col_name].find({
            "price_history.1": {"$exists": True},
            "scraped_at": {"$gte": today}
        }, {"_id": 0, "url": 1, "titre": 1, "price_history": 1}))
        result[col_name] = changements

    return result
