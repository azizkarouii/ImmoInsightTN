import asyncio
import random
from datetime import datetime, timedelta
from urllib.parse import urljoin
from .utils import get_db, clean_prix, upsert_annonce

async def scrape_booking():
    from playwright.async_api import async_playwright

    db = get_db()
    collection = db["raw_estival"]

    VILLES = [
        "Djerba", "Hammamet", "Sousse", "Monastir",
        "Nabeul", "Mahdia", "Tabarka", "La Marsa",
        "Tunis", "Sfax", "Bizerte", "Zarzis",
        "Kelibia", "Hergla", "Port El Kantaoui", "Gammarth",
        "Korba", "Mrezga", "Hammam Sousse", "Ain Draham",
        "Gabes", "Mahres", "Hammamet Sud", "Sidi Bou Said",
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
            viewport={"width": 1366, "height": 768},
            locale="fr-FR",
        )

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        page = await context.new_page()

        checkin = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        checkout = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
        # Booking affiche le prix TOTAL du séjour recherché, pas le prix par nuit
        nb_nuits = (datetime.strptime(checkout, '%Y-%m-%d') - datetime.strptime(checkin, '%Y-%m-%d')).days

        for ville in VILLES:
            print(f"[BOOKING] Scraping {ville}...")
            try:
                for page_offset in range(6):
                    url = (
                        f"https://www.booking.com/searchresults.fr.html"
                        f"?ss={ville}%2C+Tunisie"
                        f"&checkin={checkin}&checkout={checkout}"
                        f"&group_adults=2&no_rooms=1"
                        f"&nflt=entire_place%3D1"
                        f"&offset={page_offset * 25}"
                    )

                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(random.randint(2000, 4000))

                    proprietes = await page.query_selector_all("[data-testid='property-card']")
                    if not proprietes:
                        break

                    for prop in proprietes:
                        try:
                            nom_el   = await prop.query_selector("[data-testid='title']")
                            prix_el  = await prop.query_selector("[data-testid='price-and-discounted-price']")
                            score_el = await prop.query_selector("[data-testid='review-score']")
                            loc_el   = await prop.query_selector("[data-testid='address']")
                            lien_el  = await prop.query_selector("a[data-testid='title-link']")

                            nom   = await nom_el.inner_text()   if nom_el   else None
                            prix  = await prix_el.inner_text()  if prix_el  else None
                            score = await score_el.inner_text() if score_el else None
                            loc   = await loc_el.inner_text()   if loc_el   else None
                            lien  = await lien_el.get_attribute("href") if lien_el else None

                            prix_sejour = clean_prix(prix)
                            prix_num = round(prix_sejour / nb_nuits) if prix_sejour else None

                            item = {
                                "source":         "booking",
                                # href peut être relatif ou déjà absolu
                                "url":            urljoin("https://www.booking.com", lien) if lien else None,
                                "nom":            nom,
                                "ville":          ville,
                                "prix_nuit":      prix_num,
                                "prix_sejour":    prix_sejour,
                                "nb_nuits":       nb_nuits,
                                "score_avis":     score,
                                "localisation":   loc,
                                "type_offre":     "location_estivale",
                                "devise":         "TND",
                            }

                            if item["url"]:
                                upsert_annonce(collection, item, key_field="url")

                        except Exception:
                            continue

                    await asyncio.sleep(random.randint(2, 5))

            except Exception as e:
                print(f"[BOOKING] Erreur pour {ville}: {e}")
                continue

        await browser.close()