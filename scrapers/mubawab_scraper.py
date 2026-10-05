import re
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

# Pages "all Tunisia" (no pagination possible: JSF-driven, premier écran ~35 annonces)
SC_CATEGORIES = [
    ("vente",   "appartements-a-vendre"),
    ("location", "appartements-a-louer"),
    ("estival", "appartements-vacational"),
]

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
        [f"https://www.mubawab.tn/fr/sc/{slug}" for _, slug in SC_CATEGORIES]
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

    def __init__(self, start_urls=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = get_db()
        if start_urls:
            self.start_urls = list(start_urls)

    def parse(self, response):
        annonce_links = response.css("a[href*='/fr/a/'], a[href*='/fr/pa/']::attr(href)").getall()
        annonce_links = list(set(annonce_links))
        print(f"[MUBAWAB] Page {response.status} {response.url} -> {len(annonce_links)} annonces")

        ville_from_url = None
        if "/fr/sc/" in response.url:
            slug = response.url.split("/fr/sc/")[-1]
        elif "/fr/st/" in response.url:
            ville_from_url = response.url.split("/fr/st/")[-1].split("/")[0]
            slug = response.url.split("/fr/st/")[-1].split("/")[-1]
        else:
            slug = ""
        type_offre = _type_offre_from_slug(slug)

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

        prix_raw = (
            response.css("span.priceTag::text").get() or
            response.css("div.priceTag::text").get() or
            response.css("[class*='price']::text").get() or
            ""
        )
        if not prix_raw or "consulter" in prix_raw.lower():
            all_text = " ".join(response.css("*::text").getall())
            match = re.search(r"(\d{1,3}(?:[\s.,]\d{3})+)\s*(?:TND|DT|دينار|Dinar)", all_text)
            if not match:
                match = re.search(r"(\d{4,6})\s*(?:TND|DT|دينار|Dinar)", all_text)
            if not match:
                match = re.search(r"(\d{3})\s*(?:TND|DT|دينار|Dinar)", all_text)
            prix_raw = match.group(0) if match else None

        prix = clean_prix(prix_raw)

        surface_raw = (
            response.css("[class*='surface']::text").get() or
            response.css("[class*='size']::text").get() or
            ""
        )
        surface = clean_surface(surface_raw)
        if not surface:
            all_text = " ".join(response.css("*::text").getall())
            match = re.search(r"(\d+)\s*m²", all_text)
            surface_raw = match.group(0) if match else None
            surface = clean_surface(surface_raw)

        all_text = " ".join(response.css("*::text").getall())

        pieces_match   = re.search(r"(\d+)\s*[Pp]ièces?", all_text)
        chambres_match = re.search(r"(\d+)\s*[Cc]hambres?", all_text)
        sdb_match      = re.search(r"(\d+)\s*[Ss]alles?\s*de\s*bains?", all_text)
        etage_match    = re.search(r"(\d+)[eèème]+\s*étage", all_text)

        nb_pieces   = clean_int(pieces_match.group(1) if pieces_match else None)
        nb_chambres = clean_int(chambres_match.group(1) if chambres_match else None)
        nb_sdb      = clean_int(sdb_match.group(1) if sdb_match else None)
        etage       = clean_int(etage_match.group(1) if etage_match else None)

        localisation_raw = (
            response.css("span[class*='location']::text").get() or
            response.css("span[class*='city']::text").get() or
            response.css("div[class*='address']::text").get() or
            ""
        ).strip()

        parts = [p.strip() for p in localisation_raw.split(",")]
        quartier    = parts[0] if len(parts) > 0 else None
        ville       = parts[1] if len(parts) > 1 else parts[0] if parts else None
        gouvernorat = parts[2] if len(parts) > 2 else ville

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
    urls = [f"https://www.mubawab.tn/fr/sc/{slug}" for _, slug in SC_CATEGORIES]
    if cities:
        cities = [c.strip() for c in cities if c.strip()]
    else:
        cities = CITIES
    urls += [f"https://www.mubawab.tn/fr/st/{city}/{slug}" for city in cities for slug in ST_SLUGS]
    return urls


def _page_urls(urls, max_pages=4):
    expanded = []
    for url in urls:
        expanded.append(url)
        if "/fr/st/" in url:
            for page in range(2, max_pages + 1):
                expanded.append(f"{url}?p={page}")
    return expanded


def run_mubawab(cities=None):
    process = CrawlerProcess()
    process.crawl(MubawabSpider, start_urls=_page_urls(_build_start_urls(cities), max_pages=5))
    process.start()