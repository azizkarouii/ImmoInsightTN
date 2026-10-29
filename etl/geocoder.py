import json
import math
import re
import time
from urllib.parse import unquote
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
# Nominatim refuse (403) les User-Agent génériques ou de contact factice
NOMINATIM_HEADERS = {"User-Agent": "ImmoInsightTN/1.0 (projet academique; geocodage annonces immobilieres)"}

# Bbox Tunisie (lat_min, lat_max, lon_min, lon_max)
TN_BBOX = (30.0, 38.0, 7.0, 12.0)

# Cache persistant : évite de re-solliciter Photon/Nominatim (rate-limit) à chaque run
CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "geocode_cache.json")
MIN_REQUEST_INTERVAL_S = 1.1
_last_request_at = 0.0


def _load_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_cache():
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(CACHE, f, ensure_ascii=False, indent=1)


def _throttle():
    global _last_request_at
    wait = MIN_REQUEST_INTERVAL_S - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


CACHE = _load_cache()
KNOWN_TUNISIAN_CITIES = [
    "Tunis", "Sousse", "Sfax", "Djerba", "Hammamet", "Nabeul", "Monastir",
    "Bizerte", "Kelibia", "La Marsa", "Ariana", "Mahdia", "Gabes", "Menzel Bourguiba",
    "Tabarka", "Sidi Bou Said", "Gammarth", "Korba", "Hergla", "Tozeur", "Kairouan",
    "La Manouba", "Ben Arous", "La Soukra", "Raoued", "Ennasr", "Lac 2", "Lac 1",
    "El Menzah", "El Aouina", "Carthage", "Megrine", "Rades", "Sahloul",
]

# Valeurs « vides » rencontrées dans Mongo (NaN pandas sérialisé, None stringifié...).
# Sans ce filtre, la requête "nan, Tunisie" est envoyée à Photon qui la résout
# en un bâtiment de Nabeul : toutes les annonces sans ville y étaient empilées.
_MISSING_VALUES = {"", "nan", "none", "null", "undefined"}

# Types Photon/Nominatim trop vagues pour positionner un bien.
_COARSE_TYPES = {"country", "state"}

_TITLE_PLACE_RE = re.compile(r"(?:^|\s)(?:à|au|aux)\s+([^.,;:|()\[\]!?]+)", re.IGNORECASE)
_TITLE_PLACE_SPLIT = re.compile(r"\s+(?:à|au|aux)\s+", re.IGNORECASE)
_TITLE_PLACE_STOP = re.compile(
    r"\s+(?:surface|avec|de\s+\d|\d+\s*(?:m|chambre|pi)|pour|prix|proche|près|pres|vue|meubl|neuf|[-–])",
    re.IGNORECASE,
)
_TITLE_PLACE_SKIP = {
    "vendre", "louer", "partir", "saisir", "proximité", "proximite", "rdc", "étage",
    "etage", "côté", "cote", "la vente", "la location", "deux", "quelques", "découvrir",
    "decouvrir", "l'achat",
}

# Distance max (km) entre un résultat et le centre de sa ville/gouvernorat déclaré.
# Photon fait du matching flou : "Mdina, Tunis" renvoyait un bâtiment près de Bizerte.
MAX_CONTEXT_DISTANCE_KM = 40


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in _MISSING_VALUES else text


def _slug_to_label(slug):
    return unquote(slug).replace("-", " ").replace("_", " ").strip().title()


def _extract_city_from_url(url):
    if not url or "fr/st/" not in url:
        return None
    match = re.search(r"/fr/st/([^/?#]+)", url)
    return _slug_to_label(match.group(1)) if match else None


def extract_url_location(url):
    """Tayara encode la localisation dans l'URL : /item/<categorie>/<gouvernorat>/<delegation>/<slug>/<id>."""
    url = _as_text(url)
    result = {}
    match = re.search(r"tayara\.tn/item/[^/]+/([^/]+)/([^/]+)/", url)
    if match:
        result["gouvernorat"] = _slug_to_label(match.group(1))
        result["delegation"] = _slug_to_label(match.group(2))
    city = _extract_city_from_url(url)
    if city:
        result["ville"] = city
    return result


def extract_title_place(titre):
    """'Appartement en vente à La Manouba. Surface de 68 m²' -> 'La Manouba'."""
    titre = re.sub(r"\s*[|]\s*Tayara\s*$", "", _as_text(titre), flags=re.IGNORECASE)
    for match in _TITLE_PLACE_RE.finditer(titre):
        # "à vendre à El Omrane" : on garde le segment après le dernier "à"
        segment = _TITLE_PLACE_SPLIT.split(match.group(1))[-1]
        place = _TITLE_PLACE_STOP.split(segment, maxsplit=1)[0].strip(" -–'’")
        words = place.split()
        if not words or len(place) < 3 or len(words) > 5 or place[0].isdigit():
            continue
        lowered = place.lower()
        if lowered in _TITLE_PLACE_SKIP or words[0].lower() in _TITLE_PLACE_SKIP or "étage" in lowered:
            continue
        return place
    return None


def location_hints(doc):
    """Localisation la plus précise déductible d'une annonce (champs, URL, titre)."""
    doc = doc or {}
    from_url = extract_url_location(doc.get("url"))
    titre = _as_text(doc.get("titre")) or _as_text(doc.get("nom"))
    text = " ".join(_as_text(doc.get(f)) for f in ["titre", "nom", "description"]).lower()
    known_city = next((c for c in KNOWN_TUNISIAN_CITIES if re.search(rf"\b{re.escape(c.lower())}\b", text)), None)
    return {
        "adresse": _as_text(doc.get("adresse_brute")),
        "quartier": _as_text(doc.get("quartier")),
        "titre_lieu": extract_title_place(titre),
        "delegation": from_url.get("delegation"),
        "ville": _as_text(doc.get("ville")) or from_url.get("ville") or _as_text(doc.get("localisation")),
        "gouvernorat": _as_text(doc.get("gouvernorat")) or from_url.get("gouvernorat"),
        "ville_connue": known_city,
    }


def _infer_location_candidates(doc):
    hints = location_hints(doc)
    candidates = []
    for value in hints.values():
        if value and value not in candidates:
            candidates.append(value)
    return candidates


def build_geocode_queries(doc):
    """Requêtes ordonnées de la plus précise à la plus large.

    On ne descend jamais jusqu'à « Tunisie » seule : un bien placé au centroïde du
    pays (désert de Kébili) est pire qu'un bien non géolocalisé.
    """
    hints = location_hints(doc)
    gouv = hints["gouvernorat"]
    # Contexte servant à désambiguïser un lieu-dit ("Zone Touristique" -> Mahdia)
    context = gouv or hints["ville"] or hints["ville_connue"]
    queries = []
    seen = set()

    def add_query(*parts):
        cleaned = [p for p in parts if p]
        if not cleaned:
            return
        query = ", ".join(cleaned + ["Tunisie"])
        if query.lower() not in seen:
            seen.add(query.lower())
            queries.append(query)

    for place in [hints["adresse"], hints["quartier"], hints["titre_lieu"], hints["delegation"]]:
        if not place:
            continue
        if _names_known_city(place):
            add_query(place)
        if context and place.lower() != context.lower():
            add_query(place, context)
        add_query(place)

    for place in [hints["ville"], hints["ville_connue"], gouv]:
        add_query(place)

    return queries


def _in_tunisia(lat, lon):
    lat_min, lat_max, lon_min, lon_max = TN_BBOX
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


# Après plusieurs échecs réseau consécutifs, Photon est ignoré pour le reste du run
PHOTON_MAX_FAILURES = 3
_photon_failures = 0


def _query_photon(query):
    global _photon_failures
    if _photon_failures >= PHOTON_MAX_FAILURES:
        raise RuntimeError("Photon desactive pour ce run")
    try:
        result = _photon_request(query)
    except requests.RequestException:
        _photon_failures += 1
        raise
    _photon_failures = 0
    return result


def _photon_request(query):
    params = {"q": query, "limit": 1, "lang": "fr", "bbox": "7.0,30.0,12.0,38.0"}
    r = requests.get(PHOTON_URL, params=params, headers=PHOTON_HEADERS, timeout=6)
    r.raise_for_status()
    features = r.json().get("features", [])
    if not features:
        return None
    props = features[0].get("properties", {})
    if props.get("type") in _COARSE_TYPES or (props.get("countrycode") or "TN").upper() != "TN":
        return None
    lon, lat = features[0]["geometry"]["coordinates"][:2]
    return {"lat": float(lat), "lon": float(lon), "provider": "photon", "geo_type": props.get("type")}


def _query_nominatim(query):
    # Request several candidates and prefer the most specific (building/address) result
    nparams = {"q": query, "format": "json", "limit": 5, "addressdetails": 0, "countrycodes": "tn"}
    nr = requests.get(NOMINATIM_URL, params=nparams, headers=NOMINATIM_HEADERS, timeout=10)
    nr.raise_for_status()
    ndata = nr.json()
    if not isinstance(ndata, list):
        return None
    best, best_score = None, -1
    for item in ndata:
        if item.get("addresstype") in _COARSE_TYPES:
            continue
        cls = item.get("class", "")
        typ = item.get("type", "")
        score = 0
        if cls in ("building", "place"):
            score += 3
        if typ in ("house", "residential", "apartments", "address"):
            score += 3
        if typ in ("road", "highway", "street"):
            score += 1
        display = item.get("display_name", "") or ""
        if len(display.split(",")) > 2:
            score += 1
        if score > best_score:
            best_score, best = score, item
    if best is None:
        return None
    return {"lat": float(best["lat"]), "lon": float(best["lon"]), "provider": "nominatim", "geo_type": best.get("type")}


def geocode_address(adresse_brute, gouvernorat, ville, doc=None):
    doc = dict(doc or {})
    doc.setdefault("adresse_brute", adresse_brute)
    doc.setdefault("gouvernorat", gouvernorat)
    doc.setdefault("ville", ville)
    queries = build_geocode_queries(doc)

    hints = location_hints(doc)
    context = hints["gouvernorat"] or hints["ville"] or hints["ville_connue"]
    context_query = f"{context}, Tunisie" if context else None
    anchor = _resolve(context_query) if context_query else None

    for query in queries:
        result = _resolve(query)
        if not result:
            continue
        if anchor and query != context_query and not _names_known_city(query):
            if _distance_km(result, anchor) > MAX_CONTEXT_DISTANCE_KM:
                continue
        return {**result, "geocoded_query": query}
    return None


def _names_known_city(query):
    """'Hammam Sousse, Tunis, Tunisie' : le lieu cité (Sousse) prime sur le gouvernorat
    choisi par l'annonceur, souvent approximatif sur Tayara."""
    parts = [p.strip() for p in query.split(",")]
    if parts[-1].lower() == "tunisie":
        parts = parts[:-1]
    if len(parts) != 1:
        return False
    place = parts[0].lower()
    return any(re.search(rf"\b{re.escape(c.lower())}\b", place) for c in KNOWN_TUNISIAN_CITIES)


def _distance_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [a["lat"], a["lon"], b["lat"], b["lon"]])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _resolve(query, retries=3):
    """Géocode une requête. Seules les réponses valides (résultat ou « aucun résultat »)
    sont mises en cache : une erreur réseau / 429 ne doit pas empoisonner le cache."""
    if query in CACHE:
        return CACHE[query]
    for attempt in range(retries):
        answered = False
        for provider in (_query_photon, _query_nominatim):
            try:
                _throttle()
                result = provider(query)
            except Exception:
                continue
            answered = True
            if result and _in_tunisia(result["lat"], result["lon"]):
                CACHE[query] = result
                return result
        if answered:
            CACHE[query] = None
            return None
        time.sleep(2 * (attempt + 1))
    return None


def geocode_collection(clean_name, force=False):
    db = get_db()
    docs = list(db[clean_name].find({}) if force else db[clean_name].find({"lat": {"$exists": False}}))

    if not docs:
        print(f"  [GEO] Aucune donnee a geocoder dans {clean_name}")
        return

    total = len(docs)
    geocoded = 0

    for i, doc in enumerate(docs):
        # Compléter gouvernorat / ville quand ils ne sont déductibles que de l'URL
        hints = location_hints(doc)
        backfill = {}
        if not _as_text(doc.get("gouvernorat")) and hints["gouvernorat"]:
            backfill["gouvernorat"] = hints["gouvernorat"]
        if not _as_text(doc.get("ville")) and (hints["delegation"] or hints["ville"]):
            backfill["ville"] = hints["delegation"] or hints["ville"]

        result = geocode_address(
            doc.get("adresse_brute", ""),
            doc.get("gouvernorat", ""),
            doc.get("ville", ""),
            doc=doc,
        )

        if result:
            db[clean_name].update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    **backfill,
                    "lat": result["lat"],
                    "lon": result["lon"],
                    "geocoded_query": result["geocoded_query"],
                    "geo_type": result.get("geo_type"),
                }}
            )
            geocoded += 1
        else:
            db[clean_name].update_one(
                {"_id": doc["_id"]},
                {"$set": backfill, "$unset": {"lat": "", "lon": "", "geocoded_query": "", "geo_type": ""}}
                if backfill else
                {"$unset": {"lat": "", "lon": "", "geocoded_query": "", "geo_type": ""}}
            )

        if (i + 1) % 10 == 0:
            print(f"  [GEO] {clean_name}: {i+1}/{total} ({geocoded} geocodes)")

    save_cache()
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
