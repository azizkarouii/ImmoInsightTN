import re
import asyncio
from .utils import get_db, clean_prix, clean_surface, clean_int, upsert_annonce

async def scrape_afariat():
    from playwright.async_api import async_playwright

    db = get_db()

    CATEGORIES = [
        ("https://www.afariat.com/tn/immobilier/vente", "vente", "raw_vente"),
        ("https://www.afariat.com/tn/immobilier/location", "location", "raw_location"),
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        for base_url, type_offre, collection_name in CATEGORIES:
            collection = db[collection_name]
            print(f"[AFARIAT] Scraping {type_offre}...")

            try:
                await page.goto(base_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(3000)

                for page_num in range(1, 20):
                    links = await page.eval_on_selector_all(
                        "a[href*='/annonce/'], a[href*='/tn/']",
                        "els => els.map(e => e.href)"
                    )
                    links = [l for l in set(links) if '/annonce/' in l]

                    if not links:
                        print(f"[AFARIAT] Plus d'annonces à la page {page_num}")
                        break

                    for link in links:
                        try:
                            await page.goto(link, wait_until="networkidle", timeout=20000)
                            await page.wait_for_timeout(1500)

                            content = await page.inner_text("body")
                            titre = await page.title()

                            prix_match    = re.search(r"([\d\s]+)\s*(?:DT|TND)", content)
                            surface_match = re.search(r"(\d+)\s*m[²2]", content)
                            pieces_match  = re.search(r"(\d+)\s*[Pp]ièces?", content)

                            gouvernorat = ""
                            loc_match = re.search(r"(?:Gouvernorat|Région|Ville|Location)\s*:?\s*([^\n,]+)", content)
                            if loc_match:
                                gouvernorat = loc_match.group(1).strip()

                            item = {
                                "source":      "afariat",
                                "url":         link,
                                "titre":       titre[:200],
                                "type_offre":  type_offre,
                                "prix":        clean_prix(prix_match.group(0) if prix_match else None),
                                "surface":     clean_surface(surface_match.group(0) if surface_match else None),
                                "nb_pieces":   clean_int(pieces_match.group(1) if pieces_match else None),
                                "gouvernorat": gouvernorat,
                                "description": content[:2000],
                                "equipements": [eq for eq in ["parking","piscine","jardin","ascenseur","terrasse"]
                                               if eq in content.lower()],
                            }

                            upsert_annonce(collection, item)
                            print(f"[AFARIAT] Annonce : {titre[:50]}")

                        except Exception as e:
                            print(f"[AFARIAT] Erreur annonce: {e}")
                            continue

                    # Pagination: essayer de cliquer "suivant"
                    try:
                        next_btn = await page.query_selector("a.next, a[rel='next'], li.next a")
                        if next_btn:
                            await next_btn.click()
                            await page.wait_for_timeout(3000)
                        else:
                            break
                    except:
                        break

            except Exception as e:
                print(f"[AFARIAT] Erreur {type_offre}: {e}")
                continue

        await browser.close()


def run_afariat():
    asyncio.run(scrape_afariat())
