# 🏠 ImmoInsight TN — Roadmap Complète du Projet

> Document de référence complet : tout ce qu'il faut faire, dans l'ordre, avec explications détaillées.  
> Couverture : **Vente · Location classique · Location estivale**  
> Stack : Python · Scrapy · Playwright · MongoDB · Pandas · XGBoost · LSTM · FastAPI · Angular

---

## Table des Matières

1. [Setup Environnement](#1-setup-environnement)
2. [Architecture Globale](#2-architecture-globale)
3. [Collecte de Données — Scraping](#3-collecte-de-données--scraping)
4. [Data Lake — MongoDB](#4-data-lake--mongodb)
5. [Pipeline ETL](#5-pipeline-etl)
6. [Feature Engineering](#6-feature-engineering)
7. [Modèle M1 — AVM Vente](#7-modèle-m1--avm-vente)
8. [Modèle M2 — Estimation Loyer Classique](#8-modèle-m2--estimation-loyer-classique)
9. [Modèle M3 — Pricing Estival Dynamique](#9-modèle-m3--pricing-estival-dynamique)
10. [Modèle M4 — Détection de Fraude](#10-modèle-m4--détection-de-fraude)
11. [Modèle M5 — NLP Descriptions](#11-modèle-m5--nlp-descriptions)
12. [Score ROI Investissement](#12-score-roi-investissement)
13. [Dashboard Web — FastAPI + Angular](#13-dashboard-web--fastapi--angular)
14. [Déploiement](#14-déploiement)
15. [Rapport CRISP-DM](#15-rapport-crisp-dm)
16. [Planning Sprints](#16-planning-sprints)
17. [Annexe : État des lieux et écarts](#17-annexe--état-des-lieux-et-écarts)

---

## 1. Setup Environnement

### 1.1 Prérequis système

```bash
# Python 3.10+
python --version

# Node.js 18+ (pour Angular)
node --version

# MongoDB Community 7.x
mongod --version

# Git
git --version
```

### 1.2 Structure du projet

```
immoinsight-tn/
│
├── scrapers/                  # Tous les scrapers
│   ├── mubawab/
│   ├── tayara/
│   ├── afariat/
│   ├── booking/
│   ├── dar_tunisia/
│   └── inside_airbnb/
│
├── etl/                       # Pipeline ETL
│   ├── cleaner.py
│   ├── deduplicator.py
│   ├── geocoder.py
│   └── feature_engineer.py
│
├── models/                    # Tous les modèles ML
│   ├── m1_avm_vente/
│   ├── m2_loyer_classique/
│   ├── m3_pricing_estival/
│   ├── m4_fraude/
│   ├── m5_nlp/
│   └── roi_score/
│
├── api/                       # Backend FastAPI
│   ├── main.py
│   ├── routers/
│   └── schemas/
│
├── frontend/                  # Angular app
│
├── notebooks/                 # Exploration, EDA
│
├── data/                      # Données locales (échantillons)
│
├── docker-compose.yml
├── requirements.txt
└── README.md
```

### 1.3 Environnement virtuel Python

```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

pip install scrapy playwright pymongo pandas \
    scikit-learn xgboost lightgbm shap \
    prophet tensorflow keras \
    fastapi uvicorn geopandas \
    transformers sentence-transformers \
    apscheduler datasketch requests \
    python-dotenv tqdm
```

### 1.4 Variables d'environnement

Créer un fichier `.env` à la racine :

```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB=immoinsight
OSM_NOMINATIM_URL=https://nominatim.openstreetmap.org
OSM_OVERPASS_URL=https://overpass-api.de/api/interpreter
BOOKING_USER_AGENT=Mozilla/5.0 (...)
LOG_LEVEL=INFO
```

---

## 2. Architecture Globale

```
┌─────────────────────────────────────────────────────────┐
│                   COUCHE COLLECTE                       │
│  Scrapy (crawl statique)  +  Playwright (JS dynamique)  │
│  APScheduler (tâches planifiées hebdomadaires)          │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│               DATA LAKE — MongoDB                       │
│  raw_vente  |  raw_location  |  raw_estival             │
│  geo_poi    |  price_history |  scheduler_logs          │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│               PIPELINE ETL (Pandas)                     │
│  Nettoyage → Déduplication → Géocodage → Enrichissement │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│               COUCHE MODÈLES ML/DL                      │
│  M1: AVM Vente          M2: Loyer classique             │
│  M3: Pricing estival    M4: Détection fraude            │
│  M5: NLP descriptions   ROI: Score investissement       │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│           DASHBOARD — FastAPI + Angular                 │
│  Carte Leaflet  |  Estimateur  |  Score ROI  |  Alertes │
└─────────────────────────────────────────────────────────┘
```

**Flux de données résumé :**
- Les scrapers tournent en tâches planifiées et alimentent MongoDB (collections `raw_*`)
- L'ETL lit depuis les `raw_*`, nettoie et écrit dans les collections `clean_*`
- Les modèles ML lisent les `clean_*` pour l'entraînement et l'inférence
- Le backend FastAPI expose les inférences via une API REST
- Angular consomme l'API et affiche les résultats

---

## 3. Collecte de Données — Scraping

### 3.1 Vue d'ensemble des sources

| Source | Segment | Méthode | Fréquence |
|--------|---------|---------|-----------|
| Mubawab.tn | Vente + Location | Scrapy | Hebdomadaire |
| Tayara.tn | Vente + Location | Scrapy + Playwright | Hebdomadaire |
| Afariat.com | Vente | Scrapy | Hebdomadaire |
| Tecnocasa TN | Vente | Requests + BS4 | Hebdomadaire |
| Facebook Marketplace | Vente + Location | Playwright | Hebdomadaire |
| Booking.com | Estival | Playwright | Quotidien |
| Dar Tunisia | Estival | Scrapy | Quotidien |
| Inside Airbnb | Estival | Download direct CSV | Mensuel |
| OpenStreetMap | Enrichissement | API Overpass | Une fois |
| INS / BCT | Macro | PDF scraping (pdfplumber) | Mensuel |

---

### 3.2 Scraper Mubawab (Scrapy)

Mubawab est la plus grande plateforme immobilière tunisienne. Les annonces sont en HTML statique, donc Scrapy suffit.

**Champs à extraire par annonce :**

```python
# scrapers/mubawab/items.py
import scrapy

class MubawabItem(scrapy.Item):
    source        = scrapy.Field()   # "mubawab"
    url           = scrapy.Field()   # URL originale
    titre         = scrapy.Field()   # Titre de l'annonce
    type_bien     = scrapy.Field()   # appartement / villa / terrain...
    type_offre    = scrapy.Field()   # vente / location
    prix          = scrapy.Field()   # int (DT)
    surface       = scrapy.Field()   # m²
    nb_pieces     = scrapy.Field()
    nb_chambres   = scrapy.Field()
    nb_sdb        = scrapy.Field()
    etage         = scrapy.Field()
    gouvernorat   = scrapy.Field()
    ville         = scrapy.Field()
    quartier      = scrapy.Field()
    adresse_brute = scrapy.Field()
    description   = scrapy.Field()
    equipements   = scrapy.Field()   # liste
    photos_urls   = scrapy.Field()   # liste
    date_publi    = scrapy.Field()
    scraped_at    = scrapy.Field()   # datetime.utcnow()
```

**Spider principal :**

```python
# scrapers/mubawab/spiders/mubawab_spider.py
import scrapy
from datetime import datetime
from ..items import MubawabItem

class MubawabSpider(scrapy.Spider):
    name = "mubawab"
    allowed_domains = ["mubawab.tn"]

    # Points d'entrée : vente et location
    start_urls = [
        "https://www.mubawab.tn/fr/sc/immobilier-a-vendre",
        "https://www.mubawab.tn/fr/sc/appartements-a-louer",
        "https://www.mubawab.tn/fr/sc/maisons-villas-a-louer",
    ]

    def parse(self, response):
        # Extraire les liens des annonces de la page listing
        for link in response.css("a.listingBlock::attr(href)").getall():
            yield response.follow(link, callback=self.parse_annonce)

        # Pagination : suivre le lien "page suivante"
        next_page = response.css("a.nextPage::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

    def parse_annonce(self, response):
        item = MubawabItem()
        item["source"]        = "mubawab"
        item["url"]           = response.url
        item["scraped_at"]    = datetime.utcnow().isoformat()

        # Les sélecteurs CSS sont à ajuster selon le HTML réel
        item["titre"]         = response.css("h1.listingTitle::text").get("").strip()
        item["prix"]          = self._parse_prix(response.css("span.priceTag::text").get(""))
        item["surface"]       = self._parse_number(response.css("span.surface::text").get(""))
        item["gouvernorat"]   = response.css("span.gouvernorat::text").get("").strip()
        item["description"]   = " ".join(response.css("div.listingDescription *::text").getall())
        item["equipements"]   = response.css("ul.amenities li::text").getall()
        item["photos_urls"]   = response.css("div.gallery img::attr(src)").getall()

        yield item

    def _parse_prix(self, text):
        # Nettoyer "250 000 DT" → 250000
        import re
        nums = re.sub(r"[^\d]", "", text)
        return int(nums) if nums else None

    def _parse_number(self, text):
        import re
        nums = re.sub(r"[^\d]", "", text)
        return int(nums) if nums else None
```

**Pipeline MongoDB pour Scrapy :**

```python
# scrapers/mubawab/pipelines.py
from pymongo import MongoClient
from datetime import datetime

class MongoDBPipeline:
    def open_spider(self, spider):
        self.client = MongoClient("mongodb://localhost:27017")
        self.db = self.client["immoinsight"]

    def close_spider(self, spider):
        self.client.close()

    def process_item(self, item, spider):
        collection = self.db["raw_vente"] if item.get("type_offre") == "vente" \
                     else self.db["raw_location"]
        # Éviter les doublons par URL
        collection.update_one(
            {"url": item["url"]},
            {"$set": dict(item)},
            upsert=True
        )
        return item
```

---

### 3.3 Scraper Tayara (Playwright — site JS)

Tayara charge les annonces en JavaScript, donc Scrapy seul ne suffit pas. On utilise Playwright pour rendre le JS avant d'extraire.

```python
# scrapers/tayara/playwright_scraper.py
import asyncio
from playwright.async_api import async_playwright
from pymongo import MongoClient
from datetime import datetime

async def scrape_tayara_page(page_url: str, db):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Simuler un vrai navigateur
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        await page.goto(page_url, wait_until="networkidle")

        # Attendre que les annonces soient chargées
        await page.wait_for_selector("div.listing-card", timeout=10000)

        annonces = await page.query_selector_all("div.listing-card")

        for annonce in annonces:
            titre  = await annonce.query_selector("h2.title")
            prix   = await annonce.query_selector("span.price")
            lieu   = await annonce.query_selector("span.location")
            lien   = await annonce.query_selector("a")

            item = {
                "source":     "tayara",
                "titre":      await titre.inner_text() if titre else None,
                "prix":       await prix.inner_text() if prix else None,
                "lieu":       await lieu.inner_text() if lieu else None,
                "url":        await lien.get_attribute("href") if lien else None,
                "scraped_at": datetime.utcnow().isoformat()
            }

            db["raw_vente"].update_one(
                {"url": item["url"]},
                {"$set": item},
                upsert=True
            )

        await browser.close()

async def main():
    client = MongoClient("mongodb://localhost:27017")
    db = client["immoinsight"]

    base_url = "https://www.tayara.tn/ads/c/Immobilier/"
    for page_num in range(1, 50):  # 50 pages max
        url = f"{base_url}?page={page_num}"
        await scrape_tayara_page(url, db)
        await asyncio.sleep(2)  # Respecter le serveur

asyncio.run(main())
```

---

### 3.4 Scraper Inside Airbnb (données publiques estivales)

Inside Airbnb publie des dumps CSV mensuels pour les villes tunisiennes. C'est légal et direct.

```python
# scrapers/inside_airbnb/downloader.py
import requests
import pandas as pd
from pymongo import MongoClient
from datetime import datetime

# URLs des données publiques Inside Airbnb pour la Tunisie
AIRBNB_DATASETS = {
    "tunis":    "http://data.insideairbnb.com/tunisia/tunis/tunis/listings.csv.gz",
    "djerba":   "http://data.insideairbnb.com/tunisia/djerba/djerba/listings.csv.gz",
    "sousse":   "http://data.insideairbnb.com/tunisia/sousse/sousse/listings.csv.gz",
    "hammamet": "http://data.insideairbnb.com/tunisia/hammamet/hammamet/listings.csv.gz",
}

def load_airbnb_to_mongo(city: str, url: str, db):
    print(f"Téléchargement Inside Airbnb — {city}...")
    df = pd.read_csv(url, compression="gz")

    # Colonnes utiles
    colonnes = [
        "id", "name", "description", "latitude", "longitude",
        "property_type", "room_type", "accommodates", "bedrooms",
        "bathrooms", "price", "minimum_nights", "number_of_reviews",
        "review_scores_rating", "availability_365", "neighbourhood_cleansed"
    ]
    df = df[[c for c in colonnes if c in df.columns]]
    df["source"]   = "inside_airbnb"
    df["city"]     = city
    df["loaded_at"] = datetime.utcnow().isoformat()

    records = df.to_dict("records")
    for record in records:
        db["raw_estival"].update_one(
            {"id": record["id"], "city": city},
            {"$set": record},
            upsert=True
        )
    print(f"  → {len(records)} annonces insérées pour {city}")

if __name__ == "__main__":
    client = MongoClient("mongodb://localhost:27017")
    db = client["immoinsight"]
    for city, url in AIRBNB_DATASETS.items():
        load_airbnb_to_mongo(city, url, db)
```

---

### 3.5 Collecte POI OpenStreetMap

Les POI (Points of Interest) géographiques enrichissent les features de chaque bien : distance à la plage, hôpital, école, transport...

```python
# etl/osm_collector.py
import requests
import json
from pymongo import MongoClient

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Types de POI à collecter avec leur tag OSM
POI_TYPES = {
    "ecoles":     '[amenity~"school|university|college"]',
    "hopitaux":   '[amenity~"hospital|clinic|pharmacy"]',
    "plages":     '[natural="beach"]',
    "transports": '[highway="bus_stop"][railway~"station|halt"]',
    "commerces":  '[shop~"supermarket|mall|market"]',
}

def fetch_poi_tunisie(poi_tag: str, poi_name: str, db):
    """
    Récupère tous les POI d'un type donné sur tout le territoire tunisien
    via l'API Overpass (OpenStreetMap).
    """
    query = f"""
    [out:json][timeout:60];
    area["name:fr"="Tunisie"]->.searchArea;
    (
      node{poi_tag}(area.searchArea);
      way{poi_tag}(area.searchArea);
    );
    out center;
    """
    response = requests.post(OVERPASS_URL, data={"data": query})
    data = response.json()

    pois = []
    for element in data.get("elements", []):
        lat = element.get("lat") or element.get("center", {}).get("lat")
        lon = element.get("lon") or element.get("center", {}).get("lon")
        if lat and lon:
            pois.append({
                "type": poi_name,
                "lat": lat,
                "lon": lon,
                "name": element.get("tags", {}).get("name", ""),
                "tags": element.get("tags", {}),
            })

    db["geo_poi"].insert_many(pois)
    print(f"  → {len(pois)} POI de type '{poi_name}' collectés")

if __name__ == "__main__":
    client = MongoClient("mongodb://localhost:27017")
    db = client["immoinsight"]
    db["geo_poi"].create_index([("lat", 1), ("lon", 1)])
    for name, tag in POI_TYPES.items():
        fetch_poi_tunisie(tag, name, db)
```

---

### 3.6 Scheduler automatique (APScheduler)

Pour que la collecte soit continue et automatisée :

```python
# scrapers/scheduler.py
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import subprocess

scheduler = BlockingScheduler()

@scheduler.scheduled_job(CronTrigger(day_of_week="mon", hour=2))
def job_vente_location():
    """Lance les scrapers vente + location chaque lundi à 2h du matin"""
    print("Lancement scraping vente/location...")
    subprocess.run(["scrapy", "crawl", "mubawab"], cwd="scrapers/mubawab")
    subprocess.run(["python", "scrapers/tayara/playwright_scraper.py"])

@scheduler.scheduled_job(CronTrigger(hour=6))
def job_estival():
    """Lance le scraping estival tous les jours à 6h"""
    print("Lancement scraping estival...")
    subprocess.run(["python", "scrapers/booking/playwright_scraper.py"])

@scheduler.scheduled_job(CronTrigger(day=1, hour=3))
def job_airbnb():
    """Télécharge les données Inside Airbnb le 1er de chaque mois"""
    subprocess.run(["python", "scrapers/inside_airbnb/downloader.py"])

if __name__ == "__main__":
    print("Scheduler démarré.")
    scheduler.start()
```

---

## 4. Data Lake — MongoDB

### 4.1 Collections et schémas

MongoDB stocke les données brutes sans schéma fixe, mais voici la structure cible pour chaque collection :

**`raw_vente`** — Annonces de vente
```json
{
  "_id": ObjectId,
  "source": "mubawab",
  "url": "https://...",
  "titre": "Appartement S+2 à Lac 2",
  "type_bien": "appartement",
  "type_offre": "vente",
  "prix": 285000,
  "surface": 110,
  "nb_pieces": 3,
  "nb_chambres": 2,
  "nb_sdb": 1,
  "etage": 3,
  "gouvernorat": "Tunis",
  "ville": "Tunis",
  "quartier": "Lac 2",
  "adresse_brute": "...",
  "description": "...",
  "equipements": ["ascenseur", "parking", "gardien"],
  "photos_urls": ["https://..."],
  "date_publi": "2025-06-01",
  "scraped_at": "2025-06-07T02:30:00Z"
}
```

**`raw_estival`** — Annonces location estivale
```json
{
  "_id": ObjectId,
  "source": "inside_airbnb",
  "city": "djerba",
  "id": "12345678",
  "name": "Villa avec piscine vue mer",
  "property_type": "Villa",
  "room_type": "Entire home",
  "accommodates": 8,
  "bedrooms": 4,
  "price": "$150.00",
  "latitude": 33.876,
  "longitude": 10.857,
  "review_scores_rating": 4.8,
  "availability_365": 180,
  "loaded_at": "2025-06-01T03:00:00Z"
}
```

### 4.2 Index MongoDB essentiels

```javascript
// À exécuter dans mongosh
use immoinsight

// Index géospatiaux pour les requêtes de proximité
db.raw_vente.createIndex({ "gouvernorat": 1, "ville": 1 })
db.raw_vente.createIndex({ "prix": 1 })
db.raw_vente.createIndex({ "url": 1 }, { unique: true })
db.raw_estival.createIndex({ "latitude": 1, "longitude": 1 })
db.geo_poi.createIndex({ "lat": 1, "lon": 1 })

// Index 2dsphere pour requêtes géospatiales avancées (après géocodage)
db.clean_vente.createIndex({ "location": "2dsphere" })
```

---

## 5. Pipeline ETL

### 5.1 Vue d'ensemble

L'ETL transforme les données brutes (`raw_*`) en données propres (`clean_*`) prêtes pour les modèles.

```
raw_vente / raw_location / raw_estival
         ↓
    [Nettoyage]          → Normaliser prix, surface, types
         ↓
    [Déduplication]      → Supprimer les annonces identiques cross-sources
         ↓
    [Géocodage]          → Adresse brute → (lat, lon)
         ↓
    [Enrichissement POI] → Calculer distances aux points d'intérêt
         ↓
clean_vente / clean_location / clean_estival
```

### 5.2 Nettoyage

```python
# etl/cleaner.py
import pandas as pd
import re
from pymongo import MongoClient

def clean_prix(val):
    """Normalise les prix : '285 000 DT', '285000', '285K' → 285000"""
    if val is None:
        return None
    val = str(val).lower()
    val = re.sub(r"[^\d.,k]", "", val)
    if "k" in val:
        return int(float(val.replace("k", "")) * 1000)
    val = re.sub(r"[,.](?=\d{3})", "", val)  # séparateurs milliers
    nums = re.sub(r"[^\d]", "", val)
    return int(nums) if nums else None

def clean_surface(val):
    """Normalise les surfaces : '110 m²', '110m2' → 110"""
    if val is None:
        return None
    nums = re.sub(r"[^\d]", "", str(val))
    return int(nums) if nums else None

def clean_collection(collection_name: str, db):
    raw = list(db[collection_name].find({}))
    df = pd.DataFrame(raw)

    df["prix"]    = df["prix"].apply(clean_prix)
    df["surface"] = df["surface"].apply(clean_surface)

    # Supprimer les lignes sans prix ni surface
    df = df.dropna(subset=["prix"])

    # Filtres outliers grossiers
    if "vente" in collection_name:
        df = df[(df["prix"] > 10_000) & (df["prix"] < 5_000_000)]
    if "surface" in df.columns:
        df = df[(df["surface"].isna()) | (df["surface"] < 2000)]

    # Normaliser type_bien
    type_map = {
        "appt": "appartement", "appartment": "appartement",
        "villa": "villa", "maison": "villa",
        "terrain": "terrain", "fond": "local_commercial"
    }
    if "type_bien" in df.columns:
        df["type_bien"] = df["type_bien"].str.lower().map(
            lambda x: next((v for k, v in type_map.items() if k in str(x)), x)
        )

    return df
```

### 5.3 Déduplication par MinHash LSH

Des mêmes annonces apparaissent sur plusieurs plateformes. MinHash permet de détecter les quasi-doublons efficacement même sur des centaines de milliers de lignes.

```python
# etl/deduplicator.py
from datasketch import MinHash, MinHashLSH

def text_to_minhash(text: str, num_perm=128) -> MinHash:
    """Convertit un texte en signature MinHash (bag of shingles)."""
    m = MinHash(num_perm=num_perm)
    # Shingles de 3 caractères
    shingles = {text[i:i+3] for i in range(len(text) - 2)}
    for shingle in shingles:
        m.update(shingle.encode("utf8"))
    return m

def deduplicate(df, text_col="description", threshold=0.85):
    """
    Retourne un DataFrame sans quasi-doublons.
    threshold : similarité Jaccard au-dessus de laquelle deux annonces sont considérées doublons.
    """
    lsh = MinHashLSH(threshold=threshold, num_perm=128)
    minhashes = {}

    to_remove = set()
    for idx, row in df.iterrows():
        text = str(row.get(text_col, "")) + str(row.get("titre", ""))
        if len(text) < 20:
            continue
        m = text_to_minhash(text)
        key = str(idx)

        # Chercher les voisins proches déjà indexés
        result = lsh.query(m)
        if result:
            # C'est un doublon — on garde le premier inséré
            to_remove.add(idx)
        else:
            lsh.insert(key, m)
            minhashes[idx] = m

    print(f"  → {len(to_remove)} doublons détectés et supprimés")
    return df.drop(index=list(to_remove))
```

### 5.4 Géocodage

Convertit les adresses textuelles en coordonnées GPS via Nominatim (OpenStreetMap, gratuit).

```python
# etl/geocoder.py
import requests
import time

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

def geocode_address(adresse: str, gouvernorat: str = "", ville: str = "") -> dict:
    """
    Retourne {"lat": float, "lon": float} ou None.
    Stratégie en cascade : adresse complète → ville + gouvernorat → gouvernorat seul.
    """
    queries = [
        f"{adresse}, {ville}, {gouvernorat}, Tunisie",
        f"{ville}, {gouvernorat}, Tunisie",
        f"{gouvernorat}, Tunisie",
    ]

    for query in queries:
        if not query.strip(", Tunisie"):
            continue
        params = {
            "q": query,
            "format": "json",
            "countrycodes": "tn",
            "limit": 1
        }
        headers = {"User-Agent": "ImmoInsightTN/1.0"}
        try:
            r = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=5)
            results = r.json()
            if results:
                return {
                    "lat": float(results[0]["lat"]),
                    "lon": float(results[0]["lon"])
                }
        except Exception:
            pass
        time.sleep(1)  # Respecter le rate limit Nominatim (1 req/s)

    return None

def geocode_dataframe(df):
    """Ajoute les colonnes 'lat' et 'lon' à un DataFrame."""
    coords = df.apply(
        lambda row: geocode_address(
            row.get("adresse_brute", ""),
            row.get("gouvernorat", ""),
            row.get("ville", "")
        ),
        axis=1
    )
    df["lat"] = coords.apply(lambda x: x["lat"] if x else None)
    df["lon"] = coords.apply(lambda x: x["lon"] if x else None)
    return df
```

---

## 6. Feature Engineering

### 6.1 Calcul des distances aux POI

Après géocodage, on calcule pour chaque bien la distance aux POI les plus proches. C'est une feature très prédictive pour les modèles de prix.

```python
# etl/feature_engineer.py
import numpy as np
from scipy.spatial import cKDTree

def haversine(lat1, lon1, lat2, lon2):
    """Distance en km entre deux points GPS."""
    R = 6371
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlam/2)**2
    return R * 2 * np.arcsin(np.sqrt(a))

def add_poi_distances(df, poi_df, poi_type: str, radius_km=5.0):
    """
    Ajoute une colonne f'dist_{poi_type}_km' avec la distance
    au POI le plus proche de ce type.
    """
    poi_subset = poi_df[poi_df["type"] == poi_type][["lat", "lon"]].dropna()

    if poi_subset.empty or df[["lat", "lon"]].dropna().empty:
        df[f"dist_{poi_type}_km"] = None
        return df

    # KD-Tree sur les coordonnées POI pour recherche rapide du plus proche
    tree = cKDTree(poi_subset[["lat", "lon"]].values)

    def dist_to_nearest(row):
        if pd.isna(row["lat"]) or pd.isna(row["lon"]):
            return None
        _, idx = tree.query([row["lat"], row["lon"]])
        poi_lat = poi_subset.iloc[idx]["lat"]
        poi_lon = poi_subset.iloc[idx]["lon"]
        return haversine(row["lat"], row["lon"], poi_lat, poi_lon)

    df[f"dist_{poi_type}_km"] = df.apply(dist_to_nearest, axis=1)
    return df

def engineer_features(df, poi_df):
    """Applique tout le feature engineering sur le DataFrame propre."""

    # 1. Distances POI
    for poi_type in ["plages", "ecoles", "hopitaux", "transports", "commerces"]:
        df = add_poi_distances(df, poi_df, poi_type)

    # 2. Prix au m² (target dérivée utile pour la détection de fraude)
    df["prix_m2"] = df["prix"] / df["surface"].replace(0, np.nan)

    # 3. Indicateurs binaires
    df["has_parking"]   = df["equipements"].apply(lambda x: int("parking" in str(x).lower()))
    df["has_ascenseur"] = df["equipements"].apply(lambda x: int("ascenseur" in str(x).lower()))
    df["has_piscine"]   = df["equipements"].apply(lambda x: int("piscine" in str(x).lower()))
    df["has_gardien"]   = df["equipements"].apply(lambda x: int("gardien" in str(x).lower()))

    # 4. Encodage gouvernorat (fréquence encoding)
    freq = df["gouvernorat"].value_counts(normalize=True)
    df["gouvernorat_freq"] = df["gouvernorat"].map(freq)

    return df
```

---

## 7. Modèle M1 — AVM Vente

### 7.1 Objectif
Estimer le prix de vente d'un bien immobilier tunisien à partir de ses caractéristiques. C'est le cœur du projet : un **Automated Valuation Model (AVM)**.

### 7.2 Features utilisées

```python
FEATURES_VENTE = [
    # Caractéristiques physiques
    "surface", "nb_pieces", "nb_chambres", "nb_sdb", "etage",
    # Équipements (binaires)
    "has_parking", "has_ascenseur", "has_piscine", "has_gardien",
    # Localisation encodée
    "gouvernorat_freq",
    # Distances POI
    "dist_plages_km", "dist_ecoles_km", "dist_hopitaux_km",
    "dist_transports_km", "dist_commerces_km",
    # Type de bien (one-hot)
    "type_appartement", "type_villa", "type_terrain",
]

TARGET = "prix"
```

### 7.3 Entraînement avec stacking XGBoost + LightGBM

```python
# models/m1_avm_vente/train.py
import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
from sklearn.model_selection import KFold
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, r2_score
import shap
import joblib

def train_avm(df: pd.DataFrame):
    df = df.dropna(subset=["prix", "surface"])
    X = pd.get_dummies(df[FEATURES_VENTE + ["type_bien"]], columns=["type_bien"])
    y = df["prix"]

    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    oof_xgb  = np.zeros(len(X))
    oof_lgbm = np.zeros(len(X))

    xgb_params = {
        "n_estimators": 800, "max_depth": 7,
        "learning_rate": 0.05, "subsample": 0.8,
        "colsample_bytree": 0.8, "reg_alpha": 0.1,
        "random_state": 42
    }
    lgbm_params = {
        "n_estimators": 800, "max_depth": 7,
        "learning_rate": 0.05, "subsample": 0.8,
        "colsample_bytree": 0.8, "random_state": 42
    }

    for fold, (train_idx, val_idx) in enumerate(kf.split(X)):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

        # XGBoost
        model_xgb = xgb.XGBRegressor(**xgb_params)
        model_xgb.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                      early_stopping_rounds=50, verbose=False)
        oof_xgb[val_idx] = model_xgb.predict(X_val)

        # LightGBM
        model_lgbm = lgb.LGBMRegressor(**lgbm_params)
        model_lgbm.fit(X_tr, y_tr,
                       eval_set=[(X_val, y_val)],
                       callbacks=[lgb.early_stopping(50, verbose=False)])
        oof_lgbm[val_idx] = model_lgbm.predict(X_val)

    # Meta-modèle (stacking) : Ridge sur les prédictions OOF
    meta_X = np.column_stack([oof_xgb, oof_lgbm])
    meta_model = Ridge()
    meta_model.fit(meta_X, y)

    mae = mean_absolute_error(y, meta_model.predict(meta_X))
    r2  = r2_score(y, meta_model.predict(meta_X))
    print(f"AVM — MAE: {mae:.0f} DT | R²: {r2:.4f}")

    # Interprétabilité SHAP sur XGBoost
    explainer   = shap.TreeExplainer(model_xgb)
    shap_values = explainer.shap_values(X)
    shap.summary_plot(shap_values, X, show=False)

    # Sauvegarde
    joblib.dump(model_xgb,   "models/m1_avm_vente/xgb_model.pkl")
    joblib.dump(model_lgbm,  "models/m1_avm_vente/lgbm_model.pkl")
    joblib.dump(meta_model,  "models/m1_avm_vente/meta_model.pkl")
    joblib.dump(list(X.columns), "models/m1_avm_vente/feature_names.pkl")

    return model_xgb, model_lgbm, meta_model
```

### 7.4 Inférence (prédiction d'un nouveau bien)

```python
def predict_prix(bien: dict) -> dict:
    """
    Prédit le prix d'un bien et retourne une explication SHAP.
    bien : dict avec les features du bien
    """
    model_xgb  = joblib.load("models/m1_avm_vente/xgb_model.pkl")
    model_lgbm = joblib.load("models/m1_avm_vente/lgbm_model.pkl")
    meta_model = joblib.load("models/m1_avm_vente/meta_model.pkl")
    feature_names = joblib.load("models/m1_avm_vente/feature_names.pkl")

    X = pd.DataFrame([bien]).reindex(columns=feature_names, fill_value=0)

    pred_xgb  = model_xgb.predict(X)[0]
    pred_lgbm = model_lgbm.predict(X)[0]
    pred_meta = meta_model.predict([[pred_xgb, pred_lgbm]])[0]

    # SHAP pour expliquer la prédiction
    explainer   = shap.TreeExplainer(model_xgb)
    shap_values = explainer.shap_values(X)
    top_features = sorted(
        zip(feature_names, shap_values[0]),
        key=lambda x: abs(x[1]), reverse=True
    )[:5]

    return {
        "prix_estime": round(pred_meta),
        "intervalle_bas":  round(pred_meta * 0.90),
        "intervalle_haut": round(pred_meta * 1.10),
        "top_features_shap": [{"feature": f, "impact": round(v)} for f, v in top_features]
    }
```

---

## 8. Modèle M2 — Estimation Loyer Classique

### 8.1 Objectif
Estimer le loyer mensuel juste d'un bien en location longue durée. Même architecture que M1 mais avec des features adaptées à la location.

### 8.2 Différences clés avec M1

```python
# Features supplémentaires pour la location
FEATURES_LOCATION = FEATURES_VENTE + [
    "meuble",          # bien meublé ou non (impacte fortement le loyer)
    "charges_incluses" # charges comprises dans le loyer
]
TARGET_LOCATION = "loyer_mensuel"

# Le prix/m² en location varie selon le gouvernorat
# → utiliser une régression hédonique par zone géographique
# → segmenter le modèle par gouvernorat si suffisamment de données
```

### 8.3 Régression hédonique par zone

```python
# models/m2_loyer_classique/train.py
from sklearn.ensemble import RandomForestRegressor

def train_loyer(df: pd.DataFrame):
    df = df.dropna(subset=["loyer_mensuel", "surface"])

    # Filtrer outliers
    df = df[(df["loyer_mensuel"] > 100) & (df["loyer_mensuel"] < 10000)]

    X = pd.get_dummies(df[FEATURES_LOCATION + ["type_bien", "gouvernorat"]],
                       columns=["type_bien", "gouvernorat"])
    y = df["loyer_mensuel"]

    model = RandomForestRegressor(
        n_estimators=500, max_depth=12,
        min_samples_leaf=5, random_state=42, n_jobs=-1
    )
    model.fit(X, y)

    # Métriques
    from sklearn.model_selection import cross_val_score
    scores = cross_val_score(model, X, y, cv=5, scoring="neg_mean_absolute_error")
    print(f"Loyer MAE moyen (CV5): {-scores.mean():.0f} DT/mois")

    joblib.dump(model, "models/m2_loyer_classique/rf_model.pkl")
    return model
```

---

## 9. Modèle M3 — Pricing Estival Dynamique

### 9.1 Objectif
Prédire le prix optimal par nuit d'un bien en location estivale, en tenant compte de la saisonnalité, de la zone, du type de bien et du taux d'occupation.

### 9.2 Préparation des données temporelles

```python
# models/m3_pricing_estival/prepare.py
import pandas as pd
import numpy as np

def prepare_timeseries(df_estival: pd.DataFrame) -> pd.DataFrame:
    """
    Crée des séries temporelles prix/nuit par ville et type de bien.
    Utilise les données Inside Airbnb enrichies.
    """
    # Nettoyer le prix Airbnb "$150.00" → 150.0
    df_estival["prix_nuit"] = (
        df_estival["price"]
        .str.replace(r"[$,]", "", regex=True)
        .astype(float)
    )

    # Ajouter des features temporelles
    df_estival["mois"]    = pd.to_datetime(df_estival["loaded_at"]).dt.month
    df_estival["saison"]  = df_estival["mois"].map({
        12: "hiver", 1: "hiver", 2: "hiver",
        3: "printemps", 4: "printemps", 5: "printemps",
        6: "ete", 7: "ete", 8: "ete",
        9: "automne", 10: "automne", 11: "automne"
    })
    df_estival["haute_saison"] = (df_estival["mois"].isin([6, 7, 8])).astype(int)

    return df_estival
```

### 9.3 Modèle Prophet (saisonnalité)

```python
# models/m3_pricing_estival/prophet_model.py
from prophet import Prophet
import pandas as pd

def train_prophet_per_city(df: pd.DataFrame, city: str):
    """
    Entraîne un modèle Prophet pour prédire le prix moyen/nuit
    pour une ville donnée.
    """
    df_city = df[df["city"] == city].copy()
    df_city["ds"] = pd.to_datetime(df_city["loaded_at"])
    df_city["y"]  = df_city["prix_nuit"]

    # Agréger par semaine
    df_weekly = df_city.set_index("ds").resample("W")["y"].mean().reset_index()
    df_weekly.columns = ["ds", "y"]
    df_weekly = df_weekly.dropna()

    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        seasonality_mode="multiplicative"  # Saisonnalité multiplicative (été = x2)
    )
    # Ajouter une saisonnalité estivale tunisienne personnalisée
    model.add_seasonality(name="ete_tunisien", period=365.25, fourier_order=8)
    model.fit(df_weekly)

    # Prédire les 12 prochains mois
    future = model.make_future_dataframe(periods=52, freq="W")
    forecast = model.predict(future)

    forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].to_csv(
        f"models/m3_pricing_estival/forecast_{city}.csv", index=False
    )
    return model, forecast
```

### 9.4 LSTM pour la prédiction du taux d'occupation

```python
# models/m3_pricing_estival/lstm_model.py
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout

def build_lstm(seq_len=12, n_features=5):
    model = Sequential([
        LSTM(64, input_shape=(seq_len, n_features), return_sequences=True),
        Dropout(0.2),
        LSTM(32),
        Dropout(0.2),
        Dense(1, activation="sigmoid")  # taux d'occupation [0, 1]
    ])
    model.compile(optimizer="adam", loss="mse", metrics=["mae"])
    return model

def create_sequences(data: np.ndarray, seq_len=12):
    X, y = [], []
    for i in range(len(data) - seq_len):
        X.append(data[i:i+seq_len])
        y.append(data[i+seq_len, 0])  # target = taux d'occupation
    return np.array(X), np.array(y)
```

---

## 10. Modèle M4 — Détection de Fraude

### 10.1 Objectif
Identifier automatiquement les annonces suspectes : prix anormalement bas/haut, descriptions copiées, biens inexistants.

### 10.2 Isolation Forest

```python
# models/m4_fraude/isolation_forest.py
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import numpy as np

FRAUD_FEATURES = [
    "prix_m2",              # Prix au m² (principal signal)
    "prix",
    "surface",
    "gouvernorat_freq",     # Rareté de la zone
    "dist_transports_km",
]

def train_isolation_forest(df: pd.DataFrame):
    X = df[FRAUD_FEATURES].dropna()
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=200,
        contamination=0.05,  # On suppose 5% d'annonces frauduleuses
        random_state=42
    )
    model.fit(X_scaled)

    # Score d'anomalie : plus négatif = plus suspect
    scores = model.score_samples(X_scaled)
    # Normaliser en score fiabilité 0-100 (100 = très fiable)
    fiabilite = (scores - scores.min()) / (scores.max() - scores.min()) * 100

    joblib.dump(model,  "models/m4_fraude/iso_forest.pkl")
    joblib.dump(scaler, "models/m4_fraude/scaler.pkl")
    return model, fiabilite
```

### 10.3 Autoencoder pour anomalies complexes

```python
# models/m4_fraude/autoencoder.py
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense

def build_autoencoder(input_dim: int):
    """
    Autoencoder : encode puis décode les features.
    Une erreur de reconstruction élevée = annonce anormale.
    """
    inputs  = Input(shape=(input_dim,))
    encoded = Dense(16, activation="relu")(inputs)
    encoded = Dense(8,  activation="relu")(encoded)
    decoded = Dense(16, activation="relu")(encoded)
    decoded = Dense(input_dim, activation="linear")(decoded)

    autoencoder = Model(inputs, decoded)
    autoencoder.compile(optimizer="adam", loss="mse")
    return autoencoder

def get_reconstruction_error(model, X_scaled):
    X_pred = model.predict(X_scaled)
    errors = np.mean((X_scaled - X_pred)**2, axis=1)
    return errors

def combined_fraud_score(iso_score, ae_error):
    """Combine les deux scores en un seul score de fiabilité [0, 100]."""
    norm_iso = (iso_score - iso_score.min()) / (iso_score.max() - iso_score.min())
    norm_ae  = 1 - (ae_error - ae_error.min()) / (ae_error.max() - ae_error.min())
    combined = (norm_iso * 0.6 + norm_ae * 0.4) * 100
    return combined
```

---

## 11. Modèle M5 — NLP Descriptions

### 11.1 Objectif
Extraire des features cachées des descriptions textuelles (vue mer, rénové, standing, proche école...) et les utiliser pour améliorer les modèles de prix.

### 11.2 Extraction d'entités avec spaCy

```python
# models/m5_nlp/entity_extractor.py
import spacy

# Charger le modèle français
nlp = spacy.load("fr_core_news_md")

# Dictionnaire de features à détecter
FEATURES_KEYWORDS = {
    "vue_mer":        ["vue mer", "vue sur mer", "face à la mer"],
    "renove":         ["rénové", "refait", "neuf", "neuve", "récent"],
    "standing":       ["standing", "luxe", "haut standing", "prestige"],
    "proche_plage":   ["proche plage", "à 100m de la plage", "bord de mer"],
    "calme":          ["calme", "tranquille", "résidentiel"],
    "lumineux":       ["lumineux", "lumineux", "bien exposé"],
    "double_vitrage": ["double vitrage", "isolation"],
}

def extract_nlp_features(description: str) -> dict:
    """Retourne un dict de features binaires extraites de la description."""
    desc_lower = description.lower()
    features = {}
    for feature, keywords in FEATURES_KEYWORDS.items():
        features[feature] = int(any(kw in desc_lower for kw in keywords))
    return features
```

### 11.3 Fine-tuning CamemBERT pour classification de qualité

```python
# models/m5_nlp/camembert_finetune.py
from transformers import CamembertTokenizer, CamembertForSequenceClassification
import torch

def load_camembert():
    tokenizer = CamembertTokenizer.from_pretrained("camembert-base")
    model = CamembertForSequenceClassification.from_pretrained(
        "camembert-base", num_labels=3  # bas / moyen / haut standing
    )
    return tokenizer, model

def predict_standing(description: str, tokenizer, model) -> str:
    inputs = tokenizer(
        description, return_tensors="pt",
        max_length=512, truncation=True, padding=True
    )
    with torch.no_grad():
        outputs = model(**inputs)
    pred = torch.argmax(outputs.logits, dim=1).item()
    return ["bas", "moyen", "haut"][pred]
```

---

## 12. Score ROI Investissement

### 12.1 Objectif
La contribution originale du projet : estimer la rentabilité d'un bien en croisant les trois modèles (vente, location classique, location estivale).

### 12.2 Formule de calcul

```python
# models/roi_score/calculator.py

def compute_roi(
    prix_achat: float,          # M1 ou prix réel
    loyer_mensuel: float,       # M2
    prix_nuit_estival: float,   # M3
    nuits_estivales: int = 90,  # hypothèse : 3 mois d'été
    taux_occupation: float = 0.70,
    frais_annuels_pct: float = 0.02,  # 2% du prix en frais gestion
    horizon_ans: int = 10
) -> dict:
    """
    Calcule le rendement brut et le ROI sur n années.

    Stratégie mixte : 9 mois de location classique + 3 mois de location estivale.
    """
    # Revenus annuels
    revenus_classique = loyer_mensuel * 9  # 9 mois hors été
    revenus_estival   = prix_nuit_estival * nuits_estivales * taux_occupation
    revenus_totaux    = revenus_classique + revenus_estival

    # Frais annuels
    frais = prix_achat * frais_annuels_pct

    # Rendement brut annuel
    rendement_brut = (revenus_totaux / prix_achat) * 100

    # Revenu net annuel
    revenu_net = revenus_totaux - frais

    # ROI cumulé sur l'horizon
    roi_cumule = (revenu_net * horizon_ans / prix_achat) * 100

    # Score normalisé 0-100
    # Référence : rendement brut 5% = score 50, 10% = score 100
    score_roi = min(100, (rendement_brut / 10) * 100)

    return {
        "revenus_annuels_estimes": round(revenus_totaux),
        "revenus_classique":       round(revenus_classique),
        "revenus_estival":         round(revenus_estival),
        "rendement_brut_pct":      round(rendement_brut, 2),
        "revenu_net_annuel":       round(revenu_net),
        f"roi_{horizon_ans}ans_pct": round(roi_cumule, 1),
        "score_roi":               round(score_roi),
        "exemple": (
            f"Achat {prix_achat:,.0f} DT → "
            f"{revenus_totaux:,.0f} DT/an → "
            f"ROI {horizon_ans} ans : {roi_cumule:.1f}%"
        )
    }
```

---

## 13. Dashboard Web — FastAPI + Angular

### 13.1 Backend FastAPI

```python
# api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import estimation, fraude, roi, tendances

app = FastAPI(title="ImmoInsight TN API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(estimation.router, prefix="/api/estimation", tags=["Estimation"])
app.include_router(fraude.router,     prefix="/api/fraude",     tags=["Fraude"])
app.include_router(roi.router,        prefix="/api/roi",        tags=["ROI"])
app.include_router(tendances.router,  prefix="/api/tendances",  tags=["Tendances"])
```

**Exemple d'endpoint estimation :**

```python
# api/routers/estimation.py
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class BienInput(BaseModel):
    surface: float
    nb_pieces: int
    nb_chambres: int
    gouvernorat: str
    ville: str
    type_bien: str
    has_parking: int = 0
    has_ascenseur: int = 0
    has_piscine: int = 0
    lat: float = None
    lon: float = None

@router.post("/vente")
def estimer_vente(bien: BienInput):
    from models.m1_avm_vente.train import predict_prix
    result = predict_prix(bien.dict())
    return result

@router.post("/loyer")
def estimer_loyer(bien: BienInput):
    from models.m2_loyer_classique.train import predict_loyer
    result = predict_loyer(bien.dict())
    return result
```

### 13.2 Frontend Angular — Structure

```
frontend/src/app/
├── pages/
│   ├── carte/               # Carte Leaflet interactive
│   ├── estimateur/          # Formulaire estimation prix
│   ├── score-roi/           # Calculateur ROI investissement
│   ├── fiabilite/           # Vérificateur annonce
│   └── tendances/           # Graphes temporels par zone
├── services/
│   ├── estimation.service.ts
│   ├── map.service.ts
│   └── tendances.service.ts
└── shared/
    ├── components/
    └── models/
```

### 13.3 Intégration Leaflet.js dans Angular

```typescript
// pages/carte/carte.component.ts
import { Component, OnInit } from '@angular/core';
import * as L from 'leaflet';

@Component({
  selector: 'app-carte',
  template: '<div id="map" style="height: 600px;"></div>'
})
export class CarteComponent implements OnInit {
  private map!: L.Map;

  ngOnInit(): void {
    this.map = L.map('map').setView([33.89, 9.53], 7); // Centre Tunisie

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors'
    }).addTo(this.map);

    this.loadHeatmap();
  }

  loadHeatmap(): void {
    // Charger les données de prix/m² depuis l'API FastAPI
    fetch('http://localhost:8000/api/tendances/heatmap')
      .then(r => r.json())
      .then(data => {
        data.zones.forEach((zone: any) => {
          L.circle([zone.lat, zone.lon], {
            radius: zone.rayon_m,
            color: this.getPriceColor(zone.prix_m2_median),
            fillOpacity: 0.5
          }).bindPopup(`
            <b>${zone.quartier}</b><br>
            Prix médian/m² : ${zone.prix_m2_median} DT<br>
            Nb annonces : ${zone.nb_annonces}
          `).addTo(this.map);
        });
      });
  }

  getPriceColor(prix_m2: number): string {
    if (prix_m2 < 1500) return '#00ff00';
    if (prix_m2 < 2500) return '#ffff00';
    if (prix_m2 < 4000) return '#ff8800';
    return '#ff0000';
  }
}
```

---

## 14. Déploiement

### 14.1 Docker Compose

```yaml
# docker-compose.yml
version: "3.9"

services:
  mongodb:
    image: mongo:7
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db

  api:
    build: ./api
    ports:
      - "8000:8000"
    environment:
      - MONGO_URI=mongodb://mongodb:27017
    depends_on:
      - mongodb
    command: uvicorn main:app --host 0.0.0.0 --port 8000

  scheduler:
    build: ./scrapers
    depends_on:
      - mongodb
    command: python scheduler.py

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - api

volumes:
  mongo_data:
```

### 14.2 Déploiement gratuit (Railway / Render)

```bash
# Railway
npm install -g @railway/cli
railway login
railway init
railway up

# Ou Render (via render.yaml)
# FastAPI → Web Service Python
# MongoDB → MongoDB Atlas (gratuit 512MB)
# Angular → Static Site
```

---

## 15. Rapport CRISP-DM

Le rapport final doit suivre les 6 phases CRISP-DM :

| Phase | Contenu |
|-------|---------|
| **1. Compréhension métier** | Problématique immobilière tunisienne, objectifs du projet, critères de succès (MAE < 15%) |
| **2. Compréhension données** | EDA : distributions de prix, corrélations, couverture géographique, qualité par source |
| **3. Préparation données** | Pipeline ETL, déduplication, géocodage, feature engineering — choix justifiés |
| **4. Modélisation** | Description de chaque modèle (M1→M5 + ROI), hyperparamètres, validation croisée |
| **5. Évaluation** | Métriques (MAE, RMSE, R², AUC fraude), comparaison baseline, interprétation SHAP |
| **6. Déploiement** | Architecture dashboard, démo, limites, perspectives (extension MENA, article) |

---

## 16. Planning Sprints

### Sprint 1 — S1-S2 : Infrastructure & Collecte
- [x] Setup environnement Python + MongoDB + Scrapy
- [x] Scraper Mubawab (vente + location + estivale — 25 gouvernorats × 3 catégories)
- [x] Scraper Tayara (réécrit en Scrapy au lieu de Playwright)
- [x] Downloader Inside Airbnb (désactivé — Tunisie supprimée)
- [x] Collecte POI OpenStreetMap (Nominatim au lieu d'Overpass)
- [x] Scheduler APScheduler
- [x] Scraper Booking (16 villes — non planifié initialement)
- [ ] Scraper Tecnocasa, Facebook, INS/BCT (abandonnés)
- **Objectif :** ~500 annonces en base (vs 60k planifié, dû aux blocages)

### Sprint 2 — S3-S4 : ETL & Modèles de base
- [x] Pipeline nettoyage + normalisation (cleaner.py, 136 lignes)
- [x] Déduplication MinHash LSH (15 doublons éliminés)
- [x] Géocodage via Photon API (pas Nominatim — évite rate-limit 429)
- [x] Feature engineering (8 POI au lieu de 5, 9 amenities au lieu de 4)
- [x] Entraînement M1 (AVM vente — XGBoost+LightGBM stacking, R²~0.09)
- [x] ~~Entraînement M2 (loyer classique)~~ — FAIT Juillet 2026 (4 échantillons clean_location, modèle par référence prix/m²/zone)
- [ ] ~~Interprétabilité SHAP~~ — NON FAIT (trop peu d'échantillons)
- **Objectif :** AVM fonctionnel (77 échantillons), MAE non mesurable formellement

### Sprint 3 — S5-S6 : Modèles avancés
- [x] Modèle M3 (pricing estival) — XGBoost (pas Prophet/LSTM, pas de données temporelles)
- [x] Modèle M4 (fraude) — Isolation Forest 3 features (pas d'autoencoder)
- [x] Modèle M5 (NLP) — spaCy + règles (pas CamemBERT, pas de GPU)
- [ ] ~~Score ROI investissement~~ — NON FAIT (dossier vide)
- **Objectif :** 4 modèles sur 5 fonctionnels (M2 et ROI en suspens)

### Sprint 4 — S7-S8 : Dashboard & Rapport
- [x] Backend FastAPI (21 routes, 5 routeurs — dépasse les 5 planifiées)
- [x] Frontend Angular (4 composants standalone — structure différente)
- [x] Intégration Leaflet.js marqueurs (pas heatmap)
- [ ] ~~Docker Compose~~ — NON FAIT
- [ ] ~~Déploiement Railway/Render~~ — NON FAIT
- [ ] Rédaction rapport final (présent document + rapport LaTeX)
- [ ] Soutenance
- **Objectif :** Plateforme fonctionnelle en local, rapport final produit

---

---

## 17. Annexe : État des lieux et écarts (réel vs. planifié)

> Documentation de tout ce qui a été **réellement implémenté**, avec les écarts par rapport à la roadmap initiale.  
> Date de mise à jour : Juillet 2026

---

### 17.1 Structure réelle du projet

```
immoinsight-tn/
│
├── scrapers/                   # Fichiers plats (pas de sous-dossiers)
│   ├── __init__.py
│   ├── main.py                 # CLI orchestrateur (python -m scrapers.main [name])
│   ├── utils.py                # get_db(), clean_prix(), clean_surface(), upsert_annonce()
│   ├── mubawab_scraper.py      # Scrapy, 25 gouvernorats × 3 catégories, pagination 20 pages
│   ├── tayara_scraper.py       # Scrapy (réécrit, était Playwright auparavant)
│   ├── afariat_scraper.py      # Playwright, toujours bloqué (Cloudflare 522)
│   ├── booking_scraper.py      # Playwright, 16 villes, 3 pages chacune
│   ├── dar_tunisia_scraper.py  # Désactivé — domaine mort
│   ├── inside_airbnb_loader.py # Désactivé — Tunisie retirée d'Inside Airbnb
│   ├── osm_collector.py        # Nominatim API (pas Overpass), 14 villes, 8 catégories POI
│   ├── change_detector.py      # Détection des annonces supprimées, nouvelles, changements de prix
│   └── scheduler.py            # APScheduler, timezone Africa/Tunis, jobs planifiés
│
├── etl/
│   ├── cleaner.py              # 136 lignes : normalize_type_bien(), residential filter, save_clean()
│   ├── deduplicator.py         # 67 lignes : MinHash LSH + déduplication URL
│   ├── geocoder.py             # 98 lignes : Photon API (pas Nominatim), bbox Tunisie, cache mémoire
│   ├── feature_engineer.py     # 129 lignes : 8 POI, 9 amenities, KD-tree en radians
│   └── pipeline.py             # 46 lignes : orchestrateur Cleaner→Dedup→Geocoder→Features
│
├── models/
│   ├── __init__.py
│   ├── m1_avm_vente/
│   │   ├── train.py            # XGBoost + LightGBM stacking, 77 échantillons
│   │   ├── predict.py          # predict_one() + run() batch, pas de SHAP
│   │   └── artifacts/          # xgb.pkl, lgb.pkl, meta.pkl, features.json, metrics.json
│   ├── m2_loyer_classique/     # DOSSIER VIDE — non implémenté
│   ├── m3_pricing_estival/
│   │   ├── train.py            # XGBoost (pas Prophet/LSTM), 193 échantillons
│   │   ├── predict.py
│   │   └── artifacts/          # model.pkl, scaler.pkl
│   ├── m4_fraude/
│   │   ├── train.py            # Isolation Forest, 3 features (pas 5, pas d'autoencoder)
│   │   ├── predict.py          # save_fiabilite() écrit dans MongoDB
│   │   └── artifacts/          # isolation_forest.pkl, scaler.pkl
│   ├── m5_nlp/
│   │   └── extract.py          # spaCy, 11 catégories (pas 7), scoring règle (pas CamemBERT)
│   └── roi_score/              # DOSSIER VIDE — non implémenté
│
├── api/
│   ├── __init__.py             # clean_doc() helper pour NaN→null
│   ├── main.py                 # FastAPI, CORS "*", 5 routeurs
│   └── routers/
│       ├── annonces.py         # GET /api/annonces/, /annonces/carte, /annonces/recentes
│       ├── estimation.py       # GET /api/vente/estimation, /estival/estimation, /vente/prix_m2/moyen
│       ├── stats.py            # GET /api/stats (global, prix_par_gouvernorat, prix_par_ville)
│       ├── fiabilite.py        # GET /api/fiabilite/ (per-annonce, list, alertes)
│       └── alerte.py           # GET /api/alertes/ (prix, nouvelles, supprimees)
│
├── frontend/
│   └── src/
│       └── app/
│           ├── app.component.ts         # Header + 4 onglets (Carte/Stats/Estimation/Alertes)
│           ├── app.config.ts            # provideRouter, provideHttpClient
│           ├── map.component.ts         # Leaflet, 400 marqueurs, popups, couleurs par type
│           ├── stats.component.ts       # Cartes stats, prix moyens, répartition sources
│           ├── estimation.component.ts  # Formulaire 8 champs, intervalle confiance 90%
│           ├── alerts.component.ts      # 3 tabs (Nouvelles/Prix/Fiabilité)
│           ├── api.service.ts           # Client HTTP pour tous les endpoints
│           └── styles.scss              # Système de design complet (280 lignes)
│
├── immoinsight_roadmap.md      # Ce document
├── requirements.txt
└── README.md                   # À créer
```

---

### 17.2 Écarts par section

| Section | Planifié | Réel | Décision |
|---------|----------|------|----------|
| **3.1 Sources de données** | Tecnocasa, Facebook, INS/BCT | Non implémentés | Périmètre réduit (non essentiel) |
| **3.2 Mubawab** | Scrapy items/pipelines/spiders | Fichier plat unique, regex | Simplification |
| **3.3 Tayara** | Playwright | Scrapy (réécrit pour contourner blocage) | Changement d'approche |
| **3.5 Booking** | — | 16 villes, 3 pages | Extension non prévue |
| **3.7 OpenStreetMap** | Overpass API, `etl/osm_collector.py` | Nominatim API, `scrapers/osm_collector.py` | Changement de fournisseur |
| **5.3 Géocodage** | Nominatim 1s/req | Photon API (pas de rate-limit) | Blocage Nominatim (429) |
| **5.4 Feature Engineering** | 5 POI, 4 amenities | 8 POI, 9 amenities | Enrichissement |
| **6. ETL** | Pas d'orchestrateur | `pipeline.py` créé | Ajout non planifié |
| **7. M1 AVM** | SHAP, early_stopping, 15 features | Pas de SHAP, 10 features | Données insuffisantes (77 samples) |
| **8. M2 Loyer** | Référence prix/m² par zone | **IMPLÉMENTÉ** (Juillet 2026) | 4 échantillons clean_location |
| **9. M3 Estival** | Prophet + LSTM, time series | XGBoost, features statiques | Données non temporelles |
| **10. M4 Fraude** | 5 features + Autoencoder | 3 features, Isolation Forest seul | Simplicité |
| **11. M5 NLP** | CamemBERT | spaCy + règles | Temps d'entraînement GPU |
| **12. ROI** | Calculator | **NON IMPLÉMENTÉ** (dossier vide) | Données insuffisantes |
| **13. API** | 4 routers, POST/Pydantic | 5 routers, GET/query params | 21 routes vs 5 planifiées |
| **13. Frontend** | 5 pages, heatmap | 4 composants standalone, markers | Approche différente |
| **14. Déploiement** | Docker Compose, Railway | **NON IMPLÉMENTÉ** | Non prioritaire |

---

### 17.3 Services externes utilisés

| Service | Usage | Statut |
|---------|-------|--------|
| Photon API (`photon.komoot.io/api`) | Géocodage adresses → lat/lon | ✅ Fonctionnel (96-100%) |
| Nominatim API | Collecte POI OSM | ✅ Fonctionnel (via `osm_collector.py`) |
| spaCy `fr_core_news_md` | Extraction keywords NLP | ✅ Modèle chargé |
| MongoDB 7.x | Stockage local | ✅ `immoinsight` DB |
| FastAPI / Uvicorn | Serveur API | ✅ Port 8000 |
| Angular 17 | Frontend SPA | ✅ Build OK (385 kB) |

### 17.4 Statistiques finales de la base

| Collection | Documents | Notes |
|-----------|-----------|-------|
| `raw_vente` | 327 | Mubawab (76) + Tayara (251) |
| `clean_vente` | 60 | Après nettoyage + dédup + filtre résidentiel |
| `raw_location` | 6 | Locations réelles (prix 1150-5500 DT) |
| `clean_location` | 4 | Après nettoyage + dédup |
| `raw_estival` | 195 | Booking (193) + Mubawab (2) |
| `clean_estival` | 186 | Après dédup |
| `geodata_poi` | ~2400 | 14 villes, 8 catégories |

### 17.5 Fichiers non planifiés (créés en cours de route)

| Fichier | Rôle |
|---------|------|
| `scrapers/__init__.py` | Package Python |
| `scrapers/main.py` | CLI `python -m scrapers.main [scraper]` |
| `scrapers/utils.py` | `upsert_annonce()`, helpers nettoyage |
| `scrapers/change_detector.py` | Détection delta (nouvelles/supprimées/prix) |
| `etl/pipeline.py` | Orchestrateur 4 étapes |
| `models/__init__.py` | Package Python |
| `models/roi_score/calculator.py` | Score ROI investisseur + top_zones |
| `api/__init__.py` | `clean_doc()` helper |
| `api/routers/annonces.py` | Routes annonces |
| `api/routers/stats.py` | Routes statistiques |
| `api/routers/alerte.py` | Routes alertes |
| `api/routers/fiabilite.py` | Routes fiabilité |
| `api/routers/roi.py` | Routes ROI (calculer, top_zones) |
| `frontend/src/app/app.config.ts` | Config Angular standalone |
| `frontend/src/app/api.service.ts` | Service HTTP Angular |
| `tests/conftest.py` | Fixtures pytest (skip si pas de MongoDB) |
| `tests/test_etl.py` | 29 tests unitaires (cleaner, dedup, haversine, ROI) |
| `tests/test_api.py` | 14 tests API (TestClient + MongoDB) |

### 17.6 Mise à jour Juillet 2026 — Refonte du scraper Mubawab

Mubawab a **changé sa structure d'URL** (`/fr/cc/{cat}/{gov}` → 404) :

| Avant | Après |
|-------|-------|
| `/fr/cc/immobilier-a-vendre/tunis` | `/fr/sc/appartements-a-vendre` (all Tunisia) |
| 78 start_urls (25 gouvernorats × 3 cat) | `/fr/st/{ville}/{categorie}` (13 villes × 9 sous-catégories) |
| Pagination `?p=N` (20 pages) | Pagination JSF par AJAX POST — **supprimée** (1er écran ~35 annonces) |

Améliorations :
- **Classification `type_offre` par URL de listing** (meta Scrapy) au lieu de mots-clés dans l'URL de détail (bug : les annonces `vend-appartement` finissaient en `raw_location`).
- Regex prix améliorée : `(\d{1,3}(?:[\s.,]\d{3})+)\s*(?:TND|DT)` + fallback 3 chiffres.
- `run_mubawab(cities=[...])` permet de scraper par lots de villes.
- Bug scheduler corrigé (`scrape_tayara` → `run_tayara`).

### 17.7 Mise à jour Juillet 2026 — Bug critique ETL corrigé

**Bug** : 2 annonces mubawab estivales (avec champ `prix`) introduisaient une colonne `prix` dans le DataFrame `raw_estival`, détournant la branche de normalisation (`clean_prix` au lieu de `prix_nuit`) → **193 annonces Booking perdues** (clean_estival 195→2).

**Fix** (`etl/cleaner.py`) :
- Décision par nom de collection (`"estival" in collection_name`) et non par présence de colonnes.
- Fusion `prix_nuit` + `prix` pour l'estival.
- `normalize_type_bien` gère `NaN`/`None` (crash potentiel masqué).
- Fallback `nom`→`titre` (Booking) et `ville`→`gouvernorat`.

**Résultat après fix** : clean_vente 60, clean_location 4, clean_estival 186.

### 17.8 Mise à jour Juillet 2026 — ROI investisseur

- `models/roi_score/calculator.py` : `compute_roi()` (frais 5%, taxe 0.5%, revenus classique + estival, rendement net, temps de retour, score 0-100, label), `top_zones()` (meilleures zones par rendement).
- API : `GET /api/roi/calculer` + `GET /api/roi/top_zones` → **23 routes** au total.
- Frontend : section « Calcul ROI investisseur » dans l'onglet Estimation.

### 17.9 Mise à jour Juillet 2026 — Dashboard enrichi

- **Carte** : toggle `Marqueurs` / `🔥 Heatmap prix` (plugin `leaflet.heat`, intensité = prix/m², gradient bleu→rouge, légende).
- **Stats** : 4 graphiques Chart.js (`chart.js@4.5`) :
  - Barres : prix moyen par gouvernorat (vente)
  - Barres : prix/nuit par ville (estival)
  - Doughnut : sources des annonces
  - Courbes : évolution des prix par annonce (`price_history`)
- Bundle : 607 kB initial (budget warning relevé à 700 kB).

### 17.11 Mise à jour Juillet 2026 — M2 Loyer + scraping final

- **Scraping Mubawab complété** (toutes les 13 villes) : backfill ille depuis l'URL /fr/st/{ville}/ via meta Scrapy + backfill surface dans upsert_annonce (nouvelle extraction regex (\d+)\s*m²).
- **État final des données** : raw_vente 337 (mubawab 86 / tayara 251), raw_location 6 (surfaces 30/44/140/260 m²), raw_estival 195 ; clean_vente 66, clean_location 4, clean_estival 186.
- **M2 Loyer implémenté** (models/m2_loyer_classique/) : modèle par référence — prix/m² médian par ville mesuré + références marché Tunisie (12 refs manuelles) + détection de quartier dans le titre (el manar, chotrana, marsa...) + fallback par type de bien et par pièce.
- **Endpoint** : GET /api/location/estimation (surface, ville, type_bien, nb_pieces) → loyer estimé ±15 %, prix/m² de référence.
- **Frontend** : carte « Estimation de loyer mensuel (M2) » dans l'onglet Estimation.
- **Tests** : +2 tests API (45 au total) — précision modèle 2/4 <20 % (écarts = résidences meublées premium, limite des 4 échantillons).

### 17.10 Mise à jour Juillet 2026 — Tests pytest

- **43 tests** (29 ETL + 14 API), `python -m pytest tests` → tout vert en ~2.6s.
- Tests API skippés si MongoDB local indisponible (fixture `mongo_available`).
- Dépendances ajoutées : `pytest`, `pytest-cov`, `httpx`.

### 17.12 Mise à jour Octobre 2026 — Correction carte, ETL et dashboard

**Carte (cause racine : géocodage)** — 66 annonces vente sur 13 positions seulement :
- Les champs vides stockés en `NaN` produisaient la requête « nan, Tunisie », résolue par Photon en un bâtiment de **Nabeul** (25 annonces Tayara de Bizerte/Sousse/Ariana empilées à Nabeul).
- Le repli final « Tunisie » plaçait 10 annonces au **centroïde du pays** (désert de Kébili).
- `etl/geocoder.py` : localisation déduite de l'URL Tayara (`/item/<cat>/<gouvernorat>/<délégation>/`) et du titre (« à La Manouba »), plus de requête pays, contrôle de distance (40 km) par rapport à la ville/gouvernorat, cache persistant `data/geocode_cache.json`, throttling 1 req/s, Nominatim en secours (User-Agent conforme). Backfill `gouvernorat`/`ville` (83/104 renseignés vs ~20).
- API `/annonces/carte` : coordonnées renvoyées telles quelles (suppression du jitter appliqué deux fois, backend + front), champs `geo_type`/`geocoded_query`.
- Front : clustering `leaflet.markercluster` (spiderfy au zoom max), heatmap normalisée par percentiles (prix/m² vente, prix/nuit estival), popups échappées (XSS), mention « position approximative », requêtes annulées au changement de collection, légende positionnée sur la carte.

**Données** : `clean_*` étaient périmées avec des **prix et surfaces ×10** (ex. 480 000 → 4 800 000). Pipeline ETL relancé : clean_vente 104 (97 géolocalisées, 42 positions distinctes), clean_location 4, clean_estival 182. Le cleaner retire les locations publiées en rubrique vente (« à louer ») et le suffixe « | Tayara » ; `NaN` → `null` à l'écriture. URLs Booking doublées (`https://www.booking.comhttps://...`) corrigées (scraper + base).

**API / modèles** : `/api/fiabilite/alertes` était capturé par `/{annonce_id}` (ordre des routes) ; `/api/vente/estimation` plantait (dtype `object`) et ignorait `type_bien`. M1 réentraîné sur `log1p(prix)` : MAE 1 036 k → 228 k DT, plus de prédictions négatives.

**Dashboard** : l'onglet Statistiques faisait planter le navigateur (getter `collections` recréé à chaque détection → boucle avec le resize Chart.js) ; un seul des 4 graphiques survivait (destruction globale) ; historique des prix toujours vide (`price_history` exclu → paramètre `with_history`). NG0100 sur la carte corrigé.

**Tests** : 57 (dont géocodage, filtre locations, sanitation carte, URLs).

### 17.13 Mise à jour Octobre 2026 — Audit et correction des modèles de prédiction

Évaluation par validation croisée contre une référence naïve, puis corrections :

| Modèle | Problème constaté | Correction | Résultat (CV) |
|---|---|---|---|
| **Données estivales** | Booking affiche le prix **total d'un séjour de 7 nuits**, stocké comme prix/nuit (médiane « 1 904 DT/nuit ») | Scraper : `prix_nuit = prix_sejour / nb_nuits` (+ `prix_sejour`, `nb_nuits`) ; migration de `raw_estival` | Médiane réaliste : 280 DT/nuit |
| **M3 estival** | Ville sans effet (toutes à 2 843 DT), ville inconnue/minuscules → erreur technique, `dist_plages` ignoré, pire que la médiane par ville | Remplacé par une **référence par ville** (médiane, intervalle P25–P75) : XGBoost/Ridge ne battent pas la médiane (distances identiques par ville, score d'avis non corrélé, capacité non scrapée). Villes normalisées + alias, `GET /api/estival/villes` | Erreur médiane 49 % (dispersion intrinsèque) |
| **M1 vente** | Gouvernorat ignoré, distances POI vides à la prédiction, prix non monotone en surface, intervalle ±10 % fictif, surfaces aberrantes (1 m², 2 935 m²) | Profils géographiques par zone (`zone_profiles.json`), arbres régularisés + contrainte monotone sur la surface, intervalle 80 % empirique, surfaces hors [15, 2000] m² ignorées au nettoyage | Erreur médiane ≈ 28 % vs 37,5 % (médiane naïve) |
| **M2 loyer** | Ville inconnue plus chère que La Marsa (référence tirée d'un studio à 50 DT/m²), « Tunisie » reconnu comme « Tunis », loyer négatif | Références mesurées seulement si ≥ 10 annonces, repli sur la médiane marché, correspondance sur mots entiers, champ `source_reference` | — (4 annonces seulement) |
| **M4 fiabilité** | Plus exécuté (alertes fiabilité vides), scores associés aux annonces par position, prédiction unitaire incohérente | Mise à jour par `_id`, médianes/normalisation d'entraînement réutilisées, **ajouté au pipeline ETL** (étape 5) | 104 annonces scorées |
| **API** | Erreurs renvoyées en HTTP 200 `{"statut": "erreur"}`, surfaces ≤ 0 acceptées | Validation (`surface > 0`, `prix > 0`...), erreurs 422 / 503, messages affichés dans le front | — |

Corrigé aussi : regex du géocodeur (`_names_known_city`) qui ne reconnaissait jamais une ville connue. **Tests** : 66.

*Document maintenu par Mohamed Aziz Karoui — ImmoInsight TN — 2025 — Mise à jour Juillet 2026*
