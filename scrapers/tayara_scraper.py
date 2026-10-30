import re
import json
import scrapy
from scrapy.crawler import CrawlerProcess
from .utils import get_db, clean_int, upsert_annonce
from .middlewares import REGLAGES_LIMITE

# Sous-catégories résidentielles ; chacune mélange ventes et locations : la
# transaction est lue dans l'annonce elle-même (adParams "Type de transaction").
# Les anciennes URLs /ads/c/Immobilier/Location/... redirigent vers une recherche
# "Immobilier" non filtrée.
CATEGORIES = {
    "appartements": "https://www.tayara.tn/listing/c/immobilier/appartements/",
    "maisons": "https://www.tayara.tn/listing/c/immobilier/maisons-et-villas/",
}
MAX_PAGES = {"appartements": 40, "maisons": 30}  # 30 annonces par page
PAGES_SANS_NOUVEAUTE = 2

# Catégories d'annonces résidentielles suivies (URL /item/<categorie>/...)
CATEGORIES_RESIDENTIELLES = {
    "appartements": "appartement",
    "maisons-et-villas": "villa",
}

TRANSACTIONS = {
    "à louer": ("location", "raw_location"),
    "a louer": ("location", "raw_location"),
    "à vendre": ("vente", "raw_vente"),
    "a vendre": ("vente", "raw_vente"),
}


def _title(text):
    return " ".join(w.capitalize() for w in str(text).replace("-", " ").split()) if text else None


def parse_tayara_ad(next_data, url):
    """Construit une annonce à partir du JSON __NEXT_DATA__ d'une page /item/.

    Retourne (item, nom_collection) ou (None, raison) si l'annonce est ignorée.
    """
    try:
        ad = next_data["props"]["pageProps"]["adDetails"]
    except (KeyError, TypeError):
        return None, "pas de adDetails"

    params = {p.get("label"): p.get("value") for p in ad.get("adParams") or [] if isinstance(p, dict)}
    transaction = (params.get("Type de transaction") or "").strip().lower()
    if transaction not in TRANSACTIONS:
        return None, f"transaction '{transaction}'"
    type_offre, collection = TRANSACTIONS[transaction]

    match = re.search(r"/item/([^/]+)/", url)
    categorie = match.group(1) if match else ""
    if categorie not in CATEGORIES_RESIDENTIELLES:
        return None, f"categorie '{categorie}'"

    location = ad.get("location") or {}
    prix = ad.get("price")
    item = {
        "source":      "tayara",
        "url":         url.split("?")[0],
        "titre":       (ad.get("title") or "").strip(),
        "type_offre":  type_offre,
        "type_bien":   CATEGORIES_RESIDENTIELLES[categorie],
        "prix":        int(prix) if isinstance(prix, (int, float)) and prix > 0 else None,
        "surface":     clean_int(params.get("Superficie")),
        "nb_chambres": clean_int(params.get("Chambres")),
        "nb_sdb":      clean_int(params.get("Salles de bains")),
        "gouvernorat": _title(location.get("governorate")),
        "ville":       _title(location.get("delegation")),
        "description": (ad.get("description") or "")[:3000],
        "date_publi":  ad.get("publishedOn"),
    }
    # S+n : n chambres + séjour
    if item["nb_chambres"] is not None:
        item["nb_pieces"] = item["nb_chambres"] + 1
    return item, collection


class TayaraSpider(scrapy.Spider):
    name = "tayara"
    allowed_domains = ["tayara.tn"]

    custom_settings = {
        "DOWNLOAD_DELAY": 1.5,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "ROBOTSTXT_OBEY": False,
        "LOG_LEVEL": "WARNING",
        "CONCURRENT_REQUESTS": 2,
        "COOKIES_ENABLED": False,
        "RETRY_TIMES": 2,
        **REGLAGES_LIMITE,
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            "Referer": "https://www.tayara.tn/",
        },
    }

    def __init__(self, categories=None, incremental=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = get_db()
        self.categories = categories or list(CATEGORIES)
        self.stats = {"new": 0, "updated": 0, "price_changed": 0, "ignorees": 0}
        # Mode incrémental : arrêt d'une catégorie après PAGES_SANS_NOUVEAUTE pages
        # ne contenant que des annonces déjà connues (les listes sont triées par date)
        self.incremental = incremental
        self.ids_connus = set()
        if incremental:
            for col in ["raw_vente", "raw_location"]:
                for doc in self.db[col].find({"source": "tayara"}, {"url": 1}):
                    self.ids_connus.add(doc["url"].rstrip("/").split("/")[-1])
        self.pages_sans_nouveaute = {}

    async def start(self):
        # Point d'entrée de Scrapy >= 2.13 (start_requests n'est plus appelé seul)
        for request in self.start_requests():
            yield request

    def start_requests(self):
        for name in self.categories:
            yield scrapy.Request(CATEGORIES[name], callback=self.parse,
                                 cb_kwargs={"page": 1, "max_pages": MAX_PAGES[name], "base": CATEGORIES[name]})

    def parse(self, response, page, max_pages, base):
        raw = response.css("script#__NEXT_DATA__::text").get()
        hits = []
        if raw:
            listing = json.loads(raw).get("props", {}).get("pageProps", {}).get("searchedListingsAction") or {}
            hits = listing.get("newHits") or []
        # Les annonces "premium" sont répétées sur chaque page : seules les newHits sont suivies
        ids = {h.get("id") for h in hits if h.get("id")}
        links = [l for l in dict.fromkeys(response.css("a[href*='/item/']::attr(href)").getall())
                 if any(i in l for i in ids)]
        print(f"[TAYARA] {base} page {page}: {len(links)} annonces")

        for link in links:
            yield response.follow(link, callback=self.parse_annonce)

        if self.incremental:
            nouveaux = ids - self.ids_connus
            self.pages_sans_nouveaute[base] = 0 if nouveaux else self.pages_sans_nouveaute.get(base, 0) + 1
            if self.pages_sans_nouveaute[base] >= PAGES_SANS_NOUVEAUTE:
                print(f"[TAYARA] {base} : {PAGES_SANS_NOUVEAUTE} pages sans nouvelle annonce, arret")
                return

        if hits and page < max_pages:
            yield scrapy.Request(f"{base}?page={page + 1}", callback=self.parse,
                                 cb_kwargs={"page": page + 1, "max_pages": max_pages, "base": base})

    def parse_annonce(self, response):
        raw = response.css("script#__NEXT_DATA__::text").get()
        if not raw:
            self.stats["ignorees"] += 1
            return
        item, collection = parse_tayara_ad(json.loads(raw), response.url)
        if item is None:
            self.stats["ignorees"] += 1
            return
        result = upsert_annonce(self.db[collection], item)
        self.stats[result] = self.stats.get(result, 0) + 1
        if result == "new":
            print(f"[TAYARA] Nouveau ({item['type_offre']}) : {item['titre'][:50]} — {item['prix']} TND")

    def closed(self, reason):
        print(f"[TAYARA] Termine ({reason}) : {self.stats}")


def run_tayara(categories=None, incremental=False):
    process = CrawlerProcess()
    process.crawl(TayaraSpider, categories=categories, incremental=incremental)
    process.start()
