from datasketch import MinHash, MinHashLSH
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv
import os

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "immoinsight")

def get_db():
    return MongoClient(MONGO_URI)[MONGO_DB]

def text_to_minhash(text, num_perm=128):
    m = MinHash(num_perm=num_perm)
    shingles = {text[i:i+3] for i in range(len(text) - 2)}
    for shingle in shingles:
        m.update(shingle.encode("utf-8"))
    return m

def deduplicate_collection(clean_name, threshold=0.85):
    db = get_db()
    docs = list(db[clean_name].find({}))
    if not docs:
        print(f"  [DEDUP] Aucune donnée dans {clean_name}")
        return

    lsh = MinHashLSH(threshold=threshold, num_perm=128)
    seen_urls = set()
    to_remove = []

    for doc in docs:
        url = doc.get("url", "")
        if url and url in seen_urls:
            to_remove.append(doc["_id"])
            continue
        if url:
            seen_urls.add(url)

        text = f"{doc.get('titre','')} {doc.get('description','')} {doc.get('prix','')} {doc.get('gouvernorat','')}"
        if len(text) < 20:
            continue

        m = text_to_minhash(text)
        result = lsh.query(m)
        if result:
            to_remove.append(doc["_id"])
        else:
            lsh.insert(str(doc["_id"]), m)

    if to_remove:
        db[clean_name].delete_many({"_id": {"$in": to_remove}})

    remaining = db[clean_name].count_documents({})
    print(f"  [DEDUP] {clean_name}: {len(docs)} -> {remaining} (supprime {len(to_remove)})")

def run():
    print("=" * 50)
    print("ETL - Etape 2: Deduplication MinHash")
    print("=" * 50)

    for name in ["clean_vente", "clean_location", "clean_estival"]:
        deduplicate_collection(name)

    print("[DEDUP] Terminé.\n")

if __name__ == "__main__":
    run()