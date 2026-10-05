import re
import scrapy
from scrapy.crawler import CrawlerProcess
from .utils import get_db, clean_prix, clean_surface, clean_int, upsert_annonce

class DarTunisiaSpider(scrapy.Spider):
    name = "dar_tunisia"
    allowed_domains = ["dar-tunisia.com", "vacances-tunisie.com"]

    start_urls = [
        "https://www.dar-tunisia.com/locations-saisonnieres",
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 2,
        "USER_AGENT": "Mozilla/5.0 (compatible)",
        "LOG_LEVEL": "WARNING",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = get_db()

    def parse(self, response):
        links = response.css("a[href*='/location/']::attr(href), a[href*='/villa/']::attr(href)").getall()
        for link in links:
            yield response.follow(link, callback=self.parse_annonce)

        next_page = response.css("a.next::attr(href), a[rel='next']::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

    def parse_annonce(self, response):
        collection = self.db["raw_estival"]
        all_text   = " ".join(response.css("*::text").getall())

        titre       = response.css("h1::text").get("").strip()
        prix_match  = re.search(r"([\d\s]+)\s*(?:TND|DT|€|EUR)\s*(?:/\s*nuit|par nuit)?", all_text)
        surface_match = re.search(r"(\d+)\s*m²", all_text)
        cap_match   = re.search(r"(\d+)\s*(?:personnes?|voyageurs?|adultes?)", all_text)

        ville = (
            response.css("span[class*='ville']::text").get() or
            response.css("span[class*='location']::text").get() or
            ""
        ).strip()

        item = {
            "source":      "dar_tunisia",
            "url":         response.url,
            "titre":       titre,
            "ville":       ville,
            "prix_nuit":   clean_prix(prix_match.group(0) if prix_match else None),
            "surface":     clean_surface(surface_match.group(0) if surface_match else None),
            "capacite":    clean_int(cap_match.group(1) if cap_match else None),
            "type_offre":  "location_estivale",
            "description": " ".join(response.css("div[class*='desc'] *::text").getall()),
        }

        upsert_annonce(collection, item)


def run_dar_tunisia():
    process = CrawlerProcess()
    process.crawl(DarTunisiaSpider)
    process.start()
