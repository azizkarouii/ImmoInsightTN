import os
import json
import statistics
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "immoinsight")
MODEL_DIR = os.path.join(os.path.dirname(__file__), "artifacts")


def load_data():
    db = MongoClient(MONGO_URI)[MONGO_DB]
    docs = list(db["clean_location"].find({}))
    print(f"  [M2] Charge {len(docs)} annonces clean_location")
    return docs


def build_references(docs):
    refs = {"par_ville": {}, "par_type": {}, "global": [], "par_piece": []}
    for d in docs:
        prix, surface = d.get("prix"), d.get("surface")
        if not prix or not surface or surface <= 0:
            continue
        prix_m2 = prix / surface
        refs["global"].append(prix_m2)
        ville = d.get("ville") or "Inconnu"
        refs["par_ville"].setdefault(ville, []).append(prix_m2)
        type_bien = d.get("type_bien") or "appartement"
        refs["par_type"].setdefault(type_bien, []).append(prix_m2)
        if d.get("nb_pieces"):
            refs["par_piece"].append((prix, d["nb_pieces"]))
    for k in ["par_ville", "par_type"]:
        for zone, vals in refs[k].items():
            refs[k][zone] = statistics.median(vals)
    refs["prix_m2_mediane"] = statistics.median(refs["global"]) if refs["global"] else None
    refs["n"] = len(refs["global"])
    return refs


def run():
    print("\n" + "=" * 50)
    print("  M2 - LOYER CLASSIQUE (reference pricing)")
    print("=" * 50)

    docs = load_data()
    if not docs:
        print("  [M2] Aucune donnee location")
        return

    refs = build_references(docs)
    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(os.path.join(MODEL_DIR, "references.json"), "w", encoding="utf-8") as f:
        json.dump(refs, f, ensure_ascii=False, indent=2)

    print(f"  [M2] {refs['n']} echantillons avec surface")
    print(f"  [M2] Prix/m2 median global: {refs['prix_m2_mediane']:.1f} DT")
    for zone, val in sorted(refs["par_ville"].items()):
        print(f"  [M2]   {zone}: {val:.1f} DT/m2")
    print(f"  [M2] References sauvegardees dans {MODEL_DIR}")
    print("  [M2] Entrainement termine.\n")


if __name__ == "__main__":
    run()
