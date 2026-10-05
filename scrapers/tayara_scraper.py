import re
import scrapy
from scrapy.crawler import CrawlerProcess
from .utils import get_db, clean_prix, clean_surface, clean_int, upsert_annonce

CATEGORIES = {
    "vente":   "https://www.tayara.tn/ads/c/Immobilier/Vente/",
    "location": "https://www.tayara.tn/ads/c/Immobilier/Location/",
    "vente_appartements": "https://www.tayara.tn/ads/c/Immobilier/Vente/Appartements/",
    "vente_maisons": "https://www.tayara.tn/ads/c/Immobilier/Vente/Maisons-Villas/",
    "vente_terrains": "https://www.tayara.tn/ads/c/Immobilier/Vente/Terrains/",
    "location_appartements": "https://www.tayara.tn/ads/c/Immobilier/Location/Appartements/",
    "location_maisons": "https://www.tayara.tn/ads/c/Immobilier/Location/Maisons-Villas/",
}


class TayaraSpider(scrapy.Spider):
    name = "tayara"
    allowed_domains = ["tayara.tn"]

    start_urls = list(CATEGORIES.values())

    custom_settings = {
        "DOWNLOAD_DELAY": 1.5,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "ROBOTSTXT_OBEY": False,
        "LOG_LEVEL": "WARNING",
        "CONCURRENT_REQUESTS": 2,
        "COOKIES_ENABLED": False,
        "RETRY_TIMES": 2,
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.tayara.tn/",
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = get_db()

    def parse(self, response):
        url = response.url
        if "Vente" in url:
            type_offre = "vente"
            collection = self.db["raw_vente"]
        else:
            type_offre = "location"
            collection = self.db["raw_location"]

        # Extract listing links
        links = response.css("a[href*='/item/']::attr(href)").getall()
        links = list(set(links))
        print(f"[TAYARA] Page {response.url}: {len(links)} annonces")

        for link in links:
            yield response.follow(link, callback=self.parse_annonce,
                                  cb_kwargs={"type_offre": type_offre, "collection": collection})

        # Paginate
        current_page = 1
        page_match = re.search(r"page=(\d+)", url)
        if page_match:
            current_page = int(page_match.group(1))

        if current_page < 30 and links:
            next_url = re.sub(r"page=\d+", f"page={current_page+1}", url) if "page=" in url else f"{url}?page={current_page+1}"
            yield response.follow(next_url, callback=self.parse)

    def parse_annonce(self, response, type_offre, collection):
        titre = response.css("title::text").get("").replace(" - Tayara", "").strip()
        body = " ".join(response.css("body *::text").getall())

        prix_match     = re.search(r"([\d\s]+)\s*(?:TND|DT|Dinar)", body)
        surface_match  = re.search(r"(\d+)\s*m²", body)
        pieces_match   = re.search(r"(\d+)\s*[Pp]ièces?", body)
        chambres_match = re.search(r"(\d+)\s*[Cc]hambres?", body)
        loc_match      = re.search(r"(?:Gouvernorat|Region|Ville)\s*:?\s*([^\n,]+)", body)

        prix = clean_prix(prix_match.group(0) if prix_match else None)
        surface = clean_surface(surface_match.group(0) if surface_match else None)
        nb_pieces = clean_int(pieces_match.group(1) if pieces_match else None)
        nb_chambres = clean_int(chambres_match.group(1) if chambres_match else None)
        gouvernorat = loc_match.group(1).strip() if loc_match else None

        # Determine type_bien from titre
        type_bien = "appartement"
        t = titre.lower()
        if any(k in t for k in ["villa", "maison", "duplex", "bungalow"]):
            type_bien = "villa"
        elif "terrain" in t:
            type_bien = "terrain"
        elif "local" in t or "commercial" in t:
            type_bien = "local_commercial"
        elif "bureau" in t:
            type_bien = "bureau"

        item = {
            "source":      "tayara",
            "url":         response.url,
            "titre":       titre,
            "type_offre":  type_offre,
            "type_bien":   type_bien,
            "prix":        prix,
            "surface":     surface,
            "nb_pieces":   nb_pieces,
            "nb_chambres": nb_chambres,
            "gouvernorat": gouvernorat,
            "description": body[:2000],
        }

        result = upsert_annonce(collection, item)
        if result == "new":
            print(f"[TAYARA] Nouveau : {titre[:50]} — {prix} TND")


def run_tayara():
    process = CrawlerProcess()
    process.crawl(TayaraSpider)
    process.start()