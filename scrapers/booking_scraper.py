import re
import asyncio
import secrets
from datetime import datetime, timedelta
from urllib.parse import urljoin
from .utils import get_db, clean_prix, upsert_annonce

VILLES = [
    "Djerba", "Hammamet", "Sousse", "Monastir",
    "Nabeul", "Mahdia", "Tabarka", "La Marsa",
    "Tunis", "Sfax", "Bizerte", "Zarzis",
    "Kelibia", "Hergla", "Port El Kantaoui", "Gammarth",
    "Korba", "Mrezga", "Hammam Sousse", "Ain Draham",
    "Gabes", "Mahres", "Hammamet Sud", "Sidi Bou Said",
]

# Filtres Booking par type d'hébergement (le filtre "entire_place=1" utilisé
# auparavant est ignoré par Booking, qui renvoyait des chambres d'hôtel).
TYPES_HEBERGEMENT = {
    "appartement": "ht_id%3D201",
    "maison_vacances": "ht_id%3D220",
    "villa": "ht_id%3D213",
}
CARTES_PAR_PAGE = 25
CHAMPS_VOLATILS = ("prix_sejour", "prix_nuit", "nb_nuits", "checkin", "score_avis", "nb_avis",
                   "pension", "unite", "type_logement", "logement_entier", "nb_lits")
MAX_PAGES = 4

PENSIONS = [
    ("tout compris", "tout_compris"),
    ("pension complète", "pension_complete"),
    ("demi-pension", "demi_pension"),
    ("petit-déjeuner compris", "petit_dejeuner"),
]


# Délais aléatoires entre les pages (rythme de navigation humain)
_ALEA = secrets.SystemRandom()


def _nombre(texte):
    """'8,3' -> 8.3 ; '2.500' -> 2500 ; '1 160' -> 1160."""
    if texte is None:
        return None
    t = texte.replace(" ", " ").replace("\xa0", " ").strip()
    if re.fullmatch(r"\d{1,3}([ .]\d{3})+", t):
        return float(re.sub(r"[ .]", "", t))
    try:
        return float(t.replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def _compte(pattern, texte):
    match = re.search(pattern, texte or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


def nb_nuits_depuis(texte):
    """'1 semaine, 2 adultes' -> 7 ; '3 nuits, 2 adultes' -> 3."""
    texte = (texte or "").lower()
    semaines = _compte(r"(\d+)\s*semaines?", texte)
    nuits = _compte(r"(\d+)\s*nuits?", texte)
    total = (semaines or 0) * 7 + (nuits or 0)
    return total or None


def canonical_url(href):
    """URL de l'établissement sans paramètres de recherche (dates, label...),
    sinon chaque scraping crée de nouveaux documents."""
    if not href:
        return None
    return urljoin("https://www.booking.com", href).split("?")[0].split("#")[0]


def parse_booking_card(textes):
    """Extrait les caractéristiques d'une carte de résultats Booking.

    textes : {data-testid: texte} pour title, price-and-discounted-price,
    price-for-x-nights, recommended-units, review-score, et "card" (texte complet).
    """
    card = textes.get("card") or ""
    unite = textes.get("recommended-units") or ""
    lignes = [l.strip() for l in unite.split("\n") if l.strip()]

    prix_sejour = clean_prix(textes.get("price-and-discounted-price"))
    nb_nuits = nb_nuits_depuis(textes.get("price-for-x-nights"))

    # "Appartement entier • 1 chambre • 1 salon • 1 salle de bains • 85 m²"
    config = next((l for l in lignes if "•" in l), "")
    if config:
        type_logement = config.split("•")[0].strip()
    else:
        type_logement = lignes[0] if lignes else None
    surface = re.search(r"(?<!\d)(\d+(?:[.\s]\d+)*)\s*m²", config)

    # "5 lits (2 lits simples, ...)" ou "1 grand lit double"
    ligne_lits = next((l for l in lignes if "•" not in l and re.search(r"\blits?\b", l, re.IGNORECASE)), "")
    nb_lits = _compte(r"^(\d+)\s", ligne_lits) if ligne_lits else None

    score_txt = textes.get("review-score") or ""
    score = re.search(r"(?<!\d)(\d+,\d)", score_txt)
    nb_avis = re.search(r"(?<!\d)(\d+(?:[\s.]\d+)*)\s*(?:expériences vécues|commentaires|avis)", score_txt)

    centre = re.search(r"(?<![\d,])([\d,]+)\s*(km|m)\s+du centre", card)
    plage = re.search(r"À\s*([\d,]+)\s*(km|m)\s+de la plage", card)

    def km(match):
        if not match:
            return None
        valeur = _nombre(match.group(1))
        return round(valeur / 1000, 3) if match.group(2) == "m" else valeur

    pension = next((code for libelle, code in PENSIONS if libelle in unite.lower()), None)
    # Adresse affichée sur la carte ("Yasmine Hammamet", "Houmt Souk") : plus précise que
    # la ville recherchée, utilisée par le géocodeur
    adresse = (textes.get("address") or "").strip().removesuffix("Indiquer sur la carte").rstrip() or None
    front_de_mer = "front de mer" in card.lower()

    return {
        "nom":             (textes.get("title") or "").strip() or None,
        "adresse_brute":   adresse,
        "prix_sejour":     prix_sejour,
        "nb_nuits":        nb_nuits,
        "prix_nuit":       round(prix_sejour / nb_nuits) if prix_sejour and nb_nuits else None,
        "unite":           lignes[0] if lignes else None,
        "type_logement":   type_logement,
        "logement_entier": bool(re.search(r"\bentier|\bentière", config, re.IGNORECASE)),
        "nb_chambres":     _compte(r"(\d+)\s*chambres?", config),
        "nb_salons":       _compte(r"(\d+)\s*salons?", config),
        "nb_sdb":          _compte(r"(\d+)\s*salles? de bains?", config),
        "surface":         _nombre(surface.group(1)) if surface else None,
        "nb_lits":         nb_lits,
        "pension":         pension,
        "score_avis":      _nombre(score.group(1)) if score else None,
        "nb_avis":         int(_nombre(nb_avis.group(1)) or 0) if nb_avis else None,
        "dist_centre_km":  km(centre),
        "dist_plage_km":   0.0 if front_de_mer else km(plage),
        "front_de_mer":    front_de_mer,
    }


async def _textes_carte(carte):
    textes = {"card": await carte.inner_text()}
    for testid in ["title", "price-and-discounted-price", "price-for-x-nights",
                   "recommended-units", "review-score", "address"]:
        el = await carte.query_selector(f"[data-testid='{testid}']")
        textes[testid] = await el.inner_text() if el else None
    lien = await carte.query_selector("a[data-testid='title-link']")
    textes["href"] = await lien.get_attribute("href") if lien else None
    return textes


async def scrape_booking(villes=None):
    from playwright.async_api import async_playwright

    db = get_db()
    collection = db["raw_estival"]
    stats = {"new": 0, "updated": 0, "price_changed": 0}

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="fr-FR",
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        page = await context.new_page()

        checkin = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        checkout = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')

        for ville in villes or VILLES:
            for categorie, filtre in TYPES_HEBERGEMENT.items():
                vus = 0
                try:
                    for page_num in range(MAX_PAGES):
                        url = (
                            f"https://www.booking.com/searchresults.fr.html"
                            f"?ss={ville}%2C+Tunisie"
                            f"&checkin={checkin}&checkout={checkout}"
                            f"&group_adults=2&no_rooms=1"
                            f"&nflt={filtre}"
                            f"&offset={page_num * CARTES_PAR_PAGE}"
                        )
                        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        await page.wait_for_timeout(_ALEA.randint(3000, 5000))

                        # "Hammamet : 13 établissements trouvés" : au-delà, Booking
                        # complète la page avec des suggestions hors filtre
                        h1 = await page.query_selector("h1")
                        total = _compte(r"(\d[\d\s ]*)\s*établissements?", (await h1.inner_text()) if h1 else "")
                        cartes = await page.query_selector_all("[data-testid='property-card']")
                        if total is not None:
                            cartes = cartes[:max(0, total - page_num * CARTES_PAR_PAGE)]
                        if not cartes:
                            break

                        for carte in cartes:
                            try:
                                textes = await _textes_carte(carte)
                                url_logement = canonical_url(textes["href"])
                                if not url_logement:
                                    continue
                                item = {
                                    "source":     "booking",
                                    "url":        url_logement,
                                    "ville":      ville,
                                    "categorie":  categorie,
                                    "type_offre": "location_estivale",
                                    "devise":     "TND",
                                    "checkin":    checkin,
                                    **parse_booking_card(textes),
                                }
                                # "prix" alimente l'historique de prix (upsert_annonce)
                                item["prix"] = item["prix_nuit"]
                                result = upsert_annonce(collection, item, key_field="url",
                                                        refresh_fields=CHAMPS_VOLATILS)
                                stats[result] = stats.get(result, 0) + 1
                                vus += 1
                            except Exception as e:
                                print(f"[BOOKING] Carte ignoree ({ville}/{categorie}): {e}")

                        if total is not None and (page_num + 1) * CARTES_PAR_PAGE >= total:
                            break
                        await asyncio.sleep(_ALEA.randint(2, 5))

                except Exception as e:
                    print(f"[BOOKING] Erreur pour {ville}/{categorie}: {e}")
                print(f"[BOOKING] {ville} / {categorie}: {vus} logements")

        await browser.close()
    print(f"[BOOKING] Termine : {stats}")
