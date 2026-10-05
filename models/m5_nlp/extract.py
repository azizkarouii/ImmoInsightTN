import os
import re
import json
import spacy
import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "immoinsight")

KEYWORDS = {
    "vue_mer": ["vue mer", "vue sur mer", "vue mer panoramique", "mer"],
    "renove": ["renove", "refait a neuf", "recemment renove", "neuf"],
    "proche_plage": ["proche plage", "a deux pas de la plage", "front de mer", "pres de la plage", "distance plage"],
    "calme": ["calme", "tranquille", "residentiel", "sans nuisance"],
    "lumineux": ["lumineux", "clair", "bien eclaire", "ensoleille"],
    "double_vitrage": ["double vitrage", "double vitrage"],
    "cuisine_equipee": ["cuisine equipee", "cuisine amenagee", "cuisine integree"],
    "chauffage": ["chauffage", "chauffage central", "radiateur"],
    "securite": ["securite", "securise", "alarme", "vigile", "gardien", "surveillance"],
    "meuble": ["meuble", "meuble", "tout meuble", "amenage"],
    "standing": ["standing", "haut standing", "luxe", "prestigieux", "grand standing"],
}


def load_nlp():
    try:
        return spacy.load("fr_core_news_md")
    except OSError:
        print("  [M5] Modele spaCy francais introuvable, telechargement...")
        os.system("python -m spacy download fr_core_news_md")
        return spacy.load("fr_core_news_md")


def extract_keywords(text, nlp):
    if not text or not isinstance(text, str):
        return {}
    doc = nlp(text.lower())
    results = {}
    for kw_name, patterns in KEYWORDS.items():
        found = False
        for pattern in patterns:
            if re.search(re.escape(pattern), text.lower()):
                found = True
                break
        results[kw_name] = int(found)

    # Standing classification based on keyword density
    standing_score = (
        results["standing"] * 3 + results["vue_mer"] * 2 +
        results["lumineux"] + results["cuisine_equipee"] +
        results["double_vitrage"] + results["chauffage"]
    )
    if standing_score >= 4:
        results["standing_class"] = "haut"
    elif standing_score >= 2:
        results["standing_class"] = "moyen"
    else:
        results["standing_class"] = "bas"

    return results


def run():
    print("\n" + "=" * 50)
    print("  M5 - NLP DESCRIPTIONS (spaCy)")
    print("=" * 50)

    nlp = load_nlp()
    db = MongoClient(MONGO_URI)[MONGO_DB]

    for coll in ["clean_vente", "clean_estival"]:
        docs = list(db[coll].find({}))
        if not docs:
            continue
        updated = 0
        for doc in docs:
            text = doc.get("description") or doc.get("nom") or doc.get("titre") or ""
            features = extract_keywords(text, nlp)
            if features:
                features["nlp_version"] = "1.0"
                db[coll].update_one(
                    {"_id": doc["_id"]},
                    {"$set": {f"nlp_{k}": v for k, v in features.items()}}
                )
                updated += 1
        print(f"  [M5] {coll}: {updated}/{len(docs)} annonces enrichies NLP")

    print("  [M5] NLP termine.\n")


if __name__ == "__main__":
    run()