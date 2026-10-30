import sys
import asyncio
from .mubawab_scraper import run_mubawab, run_mubawab_refresh
from .tayara_scraper import run_tayara
from .afariat_scraper import run_afariat
from .booking_scraper import scrape_booking
from .dar_tunisia_scraper import run_dar_tunisia
from .inside_airbnb_loader import load_inside_airbnb
from .osm_collector import collect_osm_poi
from .change_detector import detect_removed_listings, get_new_listings_today, get_price_changes_today
from .scheduler import run_scheduler


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m scrapers.main mubawab      → Scraper Mubawab maintenant")
        print("  python -m scrapers.main mubawab_refresh → Re-visiter les annonces Mubawab sans prix")
        print("  python -m scrapers.main tayara       → Scraper Tayara maintenant")
        print("  python -m scrapers.main afariat      → Scraper Afariat maintenant")
        print("  python -m scrapers.main booking      → Scraper Booking maintenant")
        print("  python -m scrapers.main dar_tunisia  → Scraper Dar Tunisia maintenant")
        print("  python -m scrapers.main airbnb       → Charger Inside Airbnb maintenant")
        print("  python -m scrapers.main osm          → Collecter POI OpenStreetMap")
        print("  python -m scrapers.main all          → Tout lancer une fois")
        print("  python -m scrapers.main --scheduler  → Démarrer le scheduler automatique")
        print("  python -m scrapers.main rapport      → Rapport nouvelles annonces aujourd'hui")
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "mubawab":
        cities = None
        if len(sys.argv) > 2:
            cities = [c.strip() for c in sys.argv[2].split(",") if c.strip()]
        run_mubawab(cities=cities)

    elif cmd == "mubawab_refresh":
        run_mubawab_refresh()

    elif cmd == "tayara":
        print("[TAYARA] Scraper recrit en Scrapy")
        run_tayara()

    elif cmd == "afariat":
        run_afariat()

    elif cmd == "booking":
        asyncio.run(scrape_booking())

    elif cmd == "dar_tunisia":
        print("[DAR TUNISIA] Site indisponible (domaine mort) — scraper désactivé")

    elif cmd == "airbnb":
        print("[AIRBNB] Tunisie plus disponible dans Inside Airbnb — scraper désactivé")

    elif cmd == "osm":
        collect_osm_poi()

    elif cmd == "all":
        print("[ALL] Lancement séquentiel de tous les scrapers...")
        collect_osm_poi()
        run_mubawab()
        run_tayara()
        run_afariat()
        asyncio.run(scrape_booking())
        detect_removed_listings()
        print("[ALL] Terminé. (Dar Tunisia et Airbnb désactivés — sources indisponibles)")

    elif cmd == "--scheduler":
        run_scheduler()

    elif cmd == "rapport":
        nouvelles   = get_new_listings_today()
        changements = get_price_changes_today()
        print("\n=== RAPPORT AUJOURD'HUI ===")
        for k, v in nouvelles.items():
            print(f"Nouvelles [{k}] : {len(v)}")
            for a in v[:3]:
                print(f"  - {a.get('titre','?')[:50]} — {a.get('prix','?')} TND")
        for k, v in changements.items():
            print(f"Prix changés [{k}] : {len(v)}")

    else:
        print(f"Commande inconnue : {cmd}")


if __name__ == "__main__":
    main()
