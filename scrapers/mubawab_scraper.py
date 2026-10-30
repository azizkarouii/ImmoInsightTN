import re
import json
from urllib.parse import unquote

import scrapy
from scrapy.crawler import CrawlerProcess
from .utils import get_db, clean_prix, clean_surface, clean_int, upsert_annonce

GOUVERNORATS = [
    "tunis", "ariana", "ben-arous", "manouba",
    "nabeul", "hammamet", "sousse", "monastir", "mahdia",
    "sfax", "bizerte", "beja", "jendouba", "le-kef", "siliana",
    "kairouan", "kasserine", "sidi-bouzid",
    "gabes", "medenine", "djerba", "tataouine", "gafsa", "tozeur", "kebili",
]

# Pages "toute la Tunisie" : (type, slug, nombre de pages). Pagination ":p:N",
# 32 annonces par page (~4 800 appartements à louer, ~5 000 à vendre).
SC_CATEGORIES = [
    ("location", "appartements-a-louer", 25),
    ("location", "villas-et-maisons-de-luxe-a-louer", 12),
    ("location", "maisons-a-louer", 6),
    ("vente",   "appartements-a-vendre", 10),
    ("vente",   "villas-et-maisons-de-luxe-a-vendre", 5),
    ("estival", "appartements-vacational", 1),
]
PAGES_PAR_SLUG = {slug: pages for _, slug, pages in SC_CATEGORIES}
PAGE_RE = re.compile(r":p:(\d+)$")

# Pages par ville — sous-catégories découvertes depuis la homepage
ST_SLUGS = [
    "appartements-a-vendre", "villas-et-maisons-de-luxe-a-vendre", "maisons-a-vendre",
    "terrains-a-vendre", "duplex-et-lofts-a-vendre", "locaux-commerciaux-et-bureaux-a-vendre",
    "appartements-a-louer", "villas-et-maisons-de-luxe-a-louer", "maisons-a-louer",
    "appartements-vacational", "villas-et-maisons-de-luxe-vacational", "maisons-vacational",
]

CITIES = [
    "ariana", "carthage", "djerba", "hammam-sousse", "hammamet", "k%C3%A9libia",
    "la-marsa", "la-soukra", "nabeul", "raoued", "sfax", "sousse", "tunis",
    "bizerte", "monastir", "mahdia", "gabes", "medenine", "kairouan",
    "gammarth", "chott-meriem", "el-mourouj", "ben-arous", "manouba", "sfax-ville",
]


def parse_json_ld(scripts):
    """Prix et caractéristiques depuis le JSON-LD RealEstateListing d'une annonce."""
    for raw in scripts:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict) or data.get("@type") != "RealEstateListing":
            continue
        offre = data.get("offers") or {}
        bien = data.get("itemOffered") or {}
        surface = (bien.get("floorSize") or {}).get("value")

        def entier(value):
            return int(value) if isinstance(value, (int, float)) and value > 0 else None

        return {
            "prix": entier(offre.get("price")),
            "surface": entier(surface),
            "nb_pieces": entier(bien.get("numberOfRooms")),
            "nb_chambres": entier(bien.get("numberOfBedrooms")),
            "nb_sdb": entier(bien.get("numberOfBathroomsTotal")),
            "ville": (bien.get("address") or {}).get("addressLocality"),
        }
    return {}


def _type_offre_from_slug(slug: str) -> str:
    if "vacational" in slug:
        return "location_estivale"
    if "a-louer" in slug:
        return "location"
    return "vente"


class MubawabSpider(scrapy.Spider):
    name = "mubawab"
    allowed_domains = ["mubawab.tn"]

    start_urls = (
        [f"https://www.mubawab.tn/fr/sc/{slug}" for _, slug, _ in SC_CATEGORIES]
        + [f"https://www.mubawab.tn/fr/st/{city}/{slug}" for city in CITIES for slug in ST_SLUGS]
    )

    custom_settings = {
        "DOWNLOAD_DELAY": 1.5,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "ROBOTSTXT_OBEY": False,
        "LOG_LEVEL": "WARNING",
        "CONCURRENT_REQUESTS": 2,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 1.0,
        "AUTOTHROTTLE_MAX_DELAY": 8.0,
        "COOKIES_ENABLED": False,
    }

    def __init__(self, start_urls=None, annonces=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = get_db()
        if start_urls:
            self.start_urls = list(start_urls)
        # Mode rafraîchissement : [(url_annonce, type_offre)] visitées directement
        self.annonces = annonces or []

    async def start(self):
        if self.annonces:
            for url, type_offre in self.annonces:
                yield scrapy.Request(url, callback=self.parse_annonce,
                                     meta={"type_offre": type_offre, "ville_from_url": None})
            return
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse)

    def parse(self, response):
        # ::attr(href) sur chaque sélecteur : sans lui, le premier renvoyait la balise <a>
        # entière, enregistrée comme URL d'annonce ("/fr/st/tunis/<a href=...")
        annonce_links = response.css("a[href*='/fr/a/']::attr(href), a[href*='/fr/pa/']::attr(href)").getall()
        annonce_links = list(dict.fromkeys(annonce_links))
        print(f"[MUBAWAB] Page {response.status} {response.url} -> {len(annonce_links)} annonces")

        url = PAGE_RE.sub("", response.url)
        match = PAGE_RE.search(response.url)
        page = int(match.group(1)) if match else 1

        ville_from_url = None
        if "/fr/sc/" in url:
            slug = url.split("/fr/sc/")[-1]
        elif "/fr/st/" in url:
            ville_from_url = url.split("/fr/st/")[-1].split("/")[0]
            slug = url.split("/fr/st/")[-1].split("/")[-1]
        else:
            slug = ""
        type_offre = _type_offre_from_slug(slug)

        if "/fr/sc/" in url and annonce_links and page < PAGES_PAR_SLUG.get(slug, 1):
            yield response.follow(f"{url}:p:{page + 1}", callback=self.parse)

        for link in annonce_links:
            yield response.follow(
                link,
                callback=self.parse_annonce,
                meta={"type_offre": type_offre, "ville_from_url": ville_from_url},
            )

    @staticmethod
    def _type_offre_fallback(url: str, titre: str):
        t = (titre or "").lower()
        if any(k in url for k in ["a-vendre", "-vendre", "la-vente", "vend-", "vente-", "achat-"]):
            return "vente"
        if any(k in url for k in ["vacances", "estival", "location-vacances"]):
            return "location_estivale"
        if any(k in t for k in ["vend ", "vends ", "a vendre", "à vendre", "a la vente", "à la vente", "achat ", "acheter "]):
            return "vente"
        if any(k in t for k in ["louer", "a louer", "à louer", "location"]):
            return "location"
        return "location"

    def parse_annonce(self, response):
        url = response.url
        titre = (
            response.css("h1::text").get("") or
            response.css("h1 *::text").get("")
        ).strip()

        type_offre = response.meta.get("type_offre") or self._type_offre_fallback(url, titre)
        collection = self.db[{
            "vente": "raw_vente",
            "location": "raw_location",
            "location_estivale": "raw_estival",
        }[type_offre]]

        all_text = " ".join(response.css("*::text").getall())

        # Source principale : données structurées JSON-LD (RealEstateListing).
        # Repli : bloc principal ("6 500 TND", "180m²", "4 Pièces"...). Plus de
        # recherche de prix dans tout le texte : elle captait d'autres nombres
        # (prix x1000 sur les pages /fr/pa/).
        ld = parse_json_ld(response.css("script[type='application/ld+json']::text").getall())

        prix = ld.get("prix")
        if prix is None:
            prix = clean_prix(response.css(".mainInfoProp h3.orangeTit bdi::text").get())

        details = " | ".join(" ".join(t.split()) for t in response.css(".adDetailFeature ::text").getall() if t.strip())

        surface_match  = re.search(r"(\d+)\s*m²", details)
        pieces_match   = re.search(r"(\d+)\s*[Pp]ièces?", details)
        chambres_match = re.search(r"(\d+)\s*[Cc]hambres?", details)
        sdb_match      = re.search(r"(\d+)\s*[Ss]alles?\s*de\s*bains?", details)
        etage_match    = re.search(r"(\d+)[eèème]+\s*étage", all_text)

        surface     = ld.get("surface") or clean_surface(surface_match.group(1) if surface_match else None)
        nb_pieces   = ld.get("nb_pieces") or clean_int(pieces_match.group(1) if pieces_match else None)
        nb_chambres = ld.get("nb_chambres") or clean_int(chambres_match.group(1) if chambres_match else None)
        nb_sdb      = ld.get("nb_sdb") or clean_int(sdb_match.group(1) if sdb_match else None)
        etage       = clean_int(etage_match.group(1) if etage_match else None)

        # "La Marsa Ville à La Marsa" : quartier à ville
        localisation_raw = " ".join(" ".join(response.css("h3.greyTit ::text").getall()).split())
        if " à " in localisation_raw:
            quartier, ville = [p.strip() for p in localisation_raw.split(" à ", 1)]
        else:
            quartier, ville = None, localisation_raw or None
        gouvernorat = None
        if not ville and ld.get("ville"):
            ville = ld["ville"]

        # Extract gouvernorat from URL path if not in text
        if not gouvernorat:
            path_parts = [p for p in response.url.split("/") if p.strip()]
            for p in reversed(path_parts):
                if p.lower() in GOUVERNORATS:
                    gouvernorat = p.capitalize()
                    break

        # Ville connue depuis l'URL de listing /fr/st/{ville}/...
        if not ville and response.meta.get("ville_from_url"):
            ville = unquote(response.meta["ville_from_url"]).replace("-", " ").title()

        type_bien = "appartement"
        titre_lower = titre.lower()
        if any(k in titre_lower for k in ["villa", "maison", "duplex", "bungalow"]):
            type_bien = "villa"
        elif "terrain" in titre_lower:
            type_bien = "terrain"
        elif "local" in titre_lower or "commercial" in titre_lower:
            type_bien = "local_commercial"
        elif "bureau" in titre_lower:
            type_bien = "bureau"

        # "Type de bien" déclaré dans les caractéristiques prime sur le titre
        # (un "duplex" est le plus souvent un appartement)
        features = [" ".join(t.split()) for t in response.css(".adMainFeatureContent ::text").getall() if t.strip()]
        if "Type de bien" in features[:-1]:
            declare = features[features.index("Type de bien") + 1].lower()
            for cle, valeur in [("appartement", "appartement"), ("duplex", "appartement"), ("studio", "appartement"),
                                ("villa", "villa"), ("maison", "villa"), ("terrain", "terrain"),
                                ("bureau", "bureau"), ("local", "local_commercial")]:
                if cle in declare:
                    type_bien = valeur
                    break

        equipements_keywords = [
            "ascenseur", "parking", "garage", "piscine", "jardin",
            "terrasse", "balcon", "gardien", "concierge", "meublé",
            "climatisation", "chauffage central", "double vitrage",
            "porte blindée", "cuisine équipée", "vue sur mer",
            "sécurité", "salon européen"
        ]
        equipements = [eq for eq in equipements_keywords if eq in all_text.lower()]

        description_parts = response.css("div[class*='desc'] *::text, div[class*='listing'] p::text").getall()
        description = " ".join(description_parts).strip()
        if not description:
            description = " ".join(response.css("p::text").getall()[:5]).strip()

        photos = response.css("img[src*='mubawab-media']::attr(src)").getall()

        item = {
            "source":       "mubawab",
            "url":          url,
            "titre":        titre,
            "type_offre":   type_offre,
            "type_bien":    type_bien,
            "prix":         prix,
            "surface":      surface,
            "nb_pieces":    nb_pieces,
            "nb_chambres":  nb_chambres,
            "nb_sdb":       nb_sdb,
            "etage":        etage,
            "gouvernorat":  gouvernorat,
            "ville":        ville,
            "quartier":     quartier,
            "adresse_brute":localisation_raw,
            "description":  description,
            "equipements":  equipements,
            "photos_urls":  photos[:10],
        }

        result = upsert_annonce(collection, item)
        if result == "new":
            print(f"[MUBAWAB] Nouveau : {titre[:50]} — {prix} TND")
        elif result == "price_changed":
            print(f"[MUBAWAB] Prix change : {titre[:50]}")


def _build_start_urls(cities=None):
    urls = [f"https://www.mubawab.tn/fr/sc/{slug}" for _, slug, _ in SC_CATEGORIES]
    if cities:
        cities = [c.strip() for c in cities if c.strip()]
    else:
        cities = CITIES
    urls += [f"https://www.mubawab.tn/fr/st/{city}/{slug}" for city in cities for slug in ST_SLUGS]
    return urls


def run_mubawab(cities=None):
    process = CrawlerProcess()
    process.crawl(MubawabSpider, start_urls=_build_start_urls(cities))
    process.start()


def run_mubawab_refresh(limit=None):
    """Re-visite les annonces Mubawab sans prix (prix sur demande, ou prix
    aberrant annulé) avec le parseur actuel."""
    db = get_db()
    annonces = []
    for collection, type_offre in [("raw_vente", "vente"), ("raw_location", "location")]:
        for doc in db[collection].find({"source": "mubawab", "prix": None}, {"url": 1}):
            if "/fr/a/" in doc["url"] or "/fr/pa/" in doc["url"]:
                annonces.append((doc["url"], type_offre))
    annonces = annonces[:limit] if limit else annonces
    print(f"[MUBAWAB] Rafraichissement de {len(annonces)} annonces sans prix")
    process = CrawlerProcess()
    process.crawl(MubawabSpider, annonces=annonces)
    process.start()
