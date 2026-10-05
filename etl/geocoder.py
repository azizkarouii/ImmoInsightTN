import time
import requests
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv
import os

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "immoinsight")

def get_db():
    return MongoClient(MONGO_URI)[MONGO_DB]

PHOTON_URL = "https://photon.komoot.io/api"
PHOTON_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0"}
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "ImmoInsightTN/1.0 (contact: you@example.com)"}

CACHE = {}
KNOWN_TUNISIAN_CITIES = [
    "Tunis", "Sousse", "Sfax", "Djerba", "Hammamet", "Nabeul", "Monastir",
    "Bizerte", "Kelibia", "La Marsa", "Ariana", "Mahdia", "Gabes", "Menzel Bourguiba",
    "Tabarka", "Sidi Bou Said", "Gammarth", "Korba", "Hergla", "Tozeur", "Kairouan"
]


def _extract_city_from_url(url):
    if not url:
        return None
    try:
        segments = url.split("/")
        for idx, part in enumerate(segments):
            if "fr/st/" in url and idx < len(segments) - 1:
                candidate = segments[idx + 1]
                if candidate and candidate not in {"fr", "st"}:
                    return candidate.replace("%C3%A9", "é").replace("-", " ").replace("%20", " ")
    except Exception:
        pass
    return None


def _infer_location_candidates(doc):
    candidates = []
    for field in [
        "adresse_brute",
        "gouvernorat",
        "ville",
        "quartier",
        "localisation",
        "nom",
        "description",
        "titre",
    ]:
        val = doc.get(field)
        if val and str(val).strip():
            candidates.append(str(val).strip())

    url_city = _extract_city_from_url(doc.get("url") or "")
    if url_city:
        candidates.insert(0, url_city)

    text = " ".join(candidates)
    city_hits = [city for city in KNOWN_TUNISIAN_CITIES if city.lower() in text.lower()]
    for city in city_hits:
        if city not in candidates:
            candidates.insert(0, city)

    if not candidates:
        return ["Tunisie"]

    seen = []
    ordered = []
    for item in candidates:
        cleaned = item.replace("/", " ").replace("_", " ").strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
            ordered.append(cleaned)
    return ordered


def _as_text(value):
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value).strip()
    return str(value).strip()


def build_geocode_queries(doc):
    doc = doc or {}
    adresse_brute = _as_text(doc.get("adresse_brute"))
    gouvernorat = _as_text(doc.get("gouvernorat"))
    ville = _as_text(doc.get("ville"))
    quartier = _as_text(doc.get("quartier"))
    inferred = _infer_location_candidates(doc)

    city_candidates = []
    seen = set()
    for candidate in [ville, quartier, *inferred, gouvernorat, adresse_brute]:
        clean = str(candidate).replace("/", " ").replace("_", " ").strip().strip(", ")
        if not clean or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        city_candidates.append(clean)

    queries = []
    seen_queries = set()

    def add_query(value):
        cleaned = str(value).strip().strip(", ")
        if cleaned and cleaned not in seen_queries:
            seen_queries.add(cleaned)
            queries.append(cleaned)

    for city in city_candidates:
        if city.lower() == "tunisie":
            continue
        if adresse_brute:
            add_query(f"{adresse_brute}, {city}, Tunisie")
        add_query(f"{city}, Tunisie")
        if gouvernorat and city.lower() != gouvernorat.lower():
            add_query(f"{city}, {gouvernorat}, Tunisie")

    if gouvernorat:
        add_query(f"{gouvernorat}, Tunisie")
        if adresse_brute:
            add_query(f"{adresse_brute}, {gouvernorat}, Tunisie")

    if ville:
        add_query(f"{ville}, Tunisie")
    if adresse_brute:
        add_query(f"{adresse_brute}, Tunisie")
    if adresse_brute and ville:
        add_query(f"{adresse_brute}, {ville}, Tunisie")
    if ville and gouvernorat:
        add_query(f"{ville}, {gouvernorat}, Tunisie")
    if gouvernorat and ville:
        add_query(f"{gouvernorat}, {ville}, Tunisie")

    for city in city_candidates:
        if city.lower() != "tunisie":
            add_query(city)

    add_query("Tunisie")
    return queries


def geocode_address(adresse_brute, gouvernorat, ville, doc=None):
    doc = doc or {}
    if doc:
        queries = build_geocode_queries(doc)
    else:
        location_inputs = [
            adresse_brute,
            gouvernorat,
            ville,
        ]
        meaningful = []
        for item in location_inputs:
            stripped = str(item).strip().strip(", ") if item is not None else ""
            if stripped and not stripped.isspace():
                meaningful.append(stripped)
        queries = []
        for item in [
            f"{adresse_brute}, {ville}, {gouvernorat}",
            f"{ville}, {gouvernorat}",
            f"{gouvernorat}",
            f"{ville}",
            f"{adresse_brute}",
            *meaningful,
        ]:
            stripped = item.strip(", ").strip()
            if stripped and not stripped.isspace():
                queries.append(stripped)

    for query in queries:
        if query in CACHE:
            return CACHE[query]
        params = {"q": query, "limit": 1, "lang": "fr", "bbox": "7.0,30.0,12.0,38.0"}
        try:
            r = requests.get(PHOTON_URL, params=params, headers=PHOTON_HEADERS, timeout=10)
            if r.status_code == 200:
                data = r.json()
                features = data.get("features", [])
                if features:
                    geom = features[0]["geometry"]
                    coords = geom["coordinates"]
                    result = {"lat": coords[1], "lon": coords[0], "geocoded_query": query, "provider": "photon"}
                    CACHE[query] = result
                    return result
            # If Photon is forbidden or fails, fall back to Nominatim below
        except Exception:
            pass

        # Nominatim fallback (safer when Photon blocks or returns no result)
        try:
            # Request several candidates and prefer the most specific (building/address) result
            nparams = {"q": query, "format": "json", "limit": 5, "addressdetails": 0}
            nr = requests.get(NOMINATIM_URL, params=nparams, headers=NOMINATIM_HEADERS, timeout=10)
            if nr.status_code == 200:
                ndata = nr.json()
                if isinstance(ndata, list) and ndata:
                    # Score candidates: prefer class/type indicating building/address
                    best = None
                    best_score = -1
                    for item in ndata:
                        try:
                            cls = item.get('class', '')
                            typ = item.get('type', '')
                            score = 0
                            if cls in ('building', 'place'):
                                score += 3
                            if typ in ('house', 'residential', 'apartments', 'address'):
                                score += 3
                            if typ in ('road', 'highway', 'street'):
                                score += 1
                            # prefer items with more precise display_name length
                            display = item.get('display_name', '') or ''
                            if ',' in display and len(display.split(',')) > 2:
                                score += 1
                            if score > best_score:
                                best_score = score
                                best = item
                        except Exception:
                            continue
                    if best is None:
                        best = ndata[0]
                    lat = float(best.get("lat"))
                    lon = float(best.get("lon"))
                    result = {"lat": lat, "lon": lon, "geocoded_query": query, "provider": "nominatim"}
                    CACHE[query] = result
                    return result
        except Exception:
            pass
    return None


def geocode_collection(clean_name, force=False):
    db = get_db()
    docs = list(db[clean_name].find({}) if force else db[clean_name].find({"lat": {"$exists": False}}))
    if not docs:
        docs = list(db[clean_name].find({}))

    if not docs:
        print(f"  [GEO] Aucune donnee dans {clean_name}")
        return

    total = len(docs)
    geocoded = 0

    for i, doc in enumerate(docs):
        if not force and doc.get("lat") is not None and doc.get("lon") is not None:
            geocoded += 1
            continue

        result = geocode_address(
            doc.get("adresse_brute", ""),
            doc.get("gouvernorat", ""),
            doc.get("ville", ""),
            doc=doc,
        )

        if result:
            db[clean_name].update_one(
                {"_id": doc["_id"]},
                {"$set": {"lat": result["lat"], "lon": result["lon"]}}
            )
            geocoded += 1
        else:
            db[clean_name].update_one(
                {"_id": doc["_id"]},
                {"$unset": {"lat": "", "lon": ""}}
            )

        if (i + 1) % 10 == 0:
            print(f"  [GEO] {clean_name}: {i+1}/{total} ({geocoded} geocodes)")

    print(f"  [GEO] {clean_name}: {total} total, {geocoded} geocodes")


def run():
    print("=" * 50)
    print("ETL - Etape 3: Geocodage Photon")
    print("=" * 50)

    for name in ["clean_vente", "clean_location", "clean_estival"]:
        geocode_collection(name, force=True)

    print("[GEO] Termine.\n")


if __name__ == "__main__":
    run()