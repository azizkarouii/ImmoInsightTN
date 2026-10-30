from datasketch import MinHash, MinHashLSH
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv
import os

from etl import qualite

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB", "immoinsight")

# Texte trop court (titre seul) : deux annonces différentes se ressemblent vite
DESCRIPTION_MIN_MINHASH = 80

def get_db():
    return MongoClient(MONGO_URI)[MONGO_DB]

def text_to_minhash(text, num_perm=128):
    m = MinHash(num_perm=num_perm)
    shingles = {text[i:i+3] for i in range(len(text) - 2)}
    for shingle in shingles:
        m.update(shingle.encode("utf-8"))
    return m


def _par_url(docs):
    """Une annonce par URL (la plus récemment scrapée)."""
    gardes, retires = {}, []
    for doc in sorted(docs, key=lambda d: str(d.get("scraped_at") or ""), reverse=True):
        url = doc.get("url") or str(doc["_id"])
        if url in gardes:
            retires.append(doc["_id"])
        else:
            gardes[url] = doc
    return list(gardes.values()), retires


def _par_cle_bien(docs):
    """Même bien publié plusieurs fois (souvent sur Tayara ET Mubawab, titres différents) :
    on garde l'annonce la plus complète et on mémorise les autres liens."""
    groupes, sans_cle = {}, []
    for doc in docs:
        cle = qualite.cle_bien(doc)
        (groupes.setdefault(cle, []) if cle else sans_cle).append(doc)
    gardes, retires, fusions = list(sans_cle), [], []
    for groupe in groupes.values():
        groupe.sort(key=qualite.richesse, reverse=True)
        principal, autres = groupe[0], groupe[1:]
        gardes.append(principal)
        if autres:
            retires.extend(d["_id"] for d in autres)
            doublons = [{"source": d.get("source"), "url": d.get("url")} for d in autres]
            fusions.append(UpdateOne({"_id": principal["_id"]}, {"$set": {
                "doublons": doublons,
                "sources": sorted({principal.get("source"), *(d.get("source") for d in autres)} - {None}),
            }}))
    return gardes, retires, fusions


def _par_texte(docs, threshold):
    """Quasi-doublons de texte (même description reprise par plusieurs annonceurs)."""
    lsh = MinHashLSH(threshold=threshold, num_perm=128)
    retires = []
    for doc in docs:
        description = str(doc.get("description") or "")
        if len(description) < DESCRIPTION_MIN_MINHASH:
            continue
        text = f"{doc.get('titre','')} {description} {doc.get('prix','')} {doc.get('gouvernorat','')}"
        m = text_to_minhash(text)
        if lsh.query(m):
            retires.append(doc["_id"])
        else:
            lsh.insert(str(doc["_id"]), m)
    return retires


def deduplicate_collection(clean_name, threshold=0.85):
    db = get_db()
    docs = list(db[clean_name].find({}))
    if not docs:
        print(f"  [DEDUP] Aucune donnée dans {clean_name}")
        return

    docs, retires_url = _par_url(docs)
    retires_bien, retires_texte, fusions = [], [], []
    # Estival : l'URL Booking identifie le logement ; la similarité de texte sur des noms
    # courts ("Résidence X") fusionnait des logements différents
    if "estival" not in clean_name:
        docs, retires_bien, fusions = _par_cle_bien(docs)
        retires_texte = _par_texte(docs, threshold)

    to_remove = retires_url + retires_bien + retires_texte
    if to_remove:
        db[clean_name].delete_many({"_id": {"$in": to_remove}})
    if fusions:
        db[clean_name].bulk_write(fusions)
    qualite.compter(clean_name, "doublons_url_retires", len(retires_url))
    qualite.compter(clean_name, "doublons_meme_bien_retires", len(retires_bien))
    qualite.compter(clean_name, "doublons_texte_retires", len(retires_texte))

    remaining = db[clean_name].count_documents({})
    print(f"  [DEDUP] {clean_name}: {remaining + len(to_remove)} -> {remaining} "
          f"(URL {len(retires_url)}, meme bien {len(retires_bien)}, texte {len(retires_texte)})")

def run():
    print("=" * 50)
    print("ETL - Etape 2: Deduplication")
    print("=" * 50)

    for name in ["clean_vente", "clean_location", "clean_estival"]:
        deduplicate_collection(name)

    print("[DEDUP] Terminé.\n")

if __name__ == "__main__":
    run()
