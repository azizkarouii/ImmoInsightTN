import sys
import asyncio

USAGE = """Usage :
  python -m scrapers.main tayara [--incremental]  → Tayara (--incremental : s'arrête aux annonces déjà connues)
  python -m scrapers.main mubawab [--rapide]      → Mubawab (--rapide : 3 pages par catégorie)
  python -m scrapers.main mubawab_refresh         → Re-visiter les annonces Mubawab sans prix
  python -m scrapers.main booking                 → Booking (locations estivales)
  python -m scrapers.main osm                     → Collecter les POI OpenStreetMap
  python -m scrapers.main retraits                → Vérifier les annonces non revues depuis 14 jours
  python -m scrapers.main rapport                 → Rapport d'alertes du jour
  python -m scrapers.main all                     → Collecte complète puis ETL (sous-processus)
  python -m scrapers.main --scheduler             → Démarrer la collecte automatique
  python -m scrapers.main planning                → Afficher le planning et les dernières exécutions
  python -m scrapers.main job <id>                → Lancer un job planifié maintenant (journalisé)

Sources désactivées : afariat (Cloudflare), dar_tunisia (domaine mort), airbnb (Tunisie retirée)."""


def main():
    args = sys.argv[1:]
    if not args:
        print(USAGE)
        sys.exit(0)

    cmd = args[0].lower()
    flags = {a.lower() for a in args[1:]}

    if cmd == "mubawab":
        cities = [a for a in args[1:] if not a.startswith("--")]
        from .mubawab_scraper import run_mubawab
        run_mubawab(cities=cities[0].split(",") if cities else None, rapide="--rapide" in flags)

    elif cmd == "mubawab_refresh":
        from .mubawab_scraper import run_mubawab_refresh
        run_mubawab_refresh()

    elif cmd == "tayara":
        from .tayara_scraper import run_tayara
        run_tayara(incremental="--incremental" in flags)

    elif cmd == "booking":
        from .booking_scraper import scrape_booking
        asyncio.run(scrape_booking())

    elif cmd == "osm":
        from .osm_collector import collect_osm_poi
        collect_osm_poi()

    elif cmd == "retraits":
        from .change_detector import migrer_statuts, verifier_retraits
        migrer_statuts()
        verifier_retraits()

    elif cmd == "rapport":
        from .change_detector import rapport_quotidien
        rapport_quotidien()

    elif cmd == "all":
        # Chaque étape dans un sous-processus : Scrapy ne redémarre pas dans le même processus
        from .scheduler import run_job
        for job_id in ["tayara_complet", "mubawab", "booking", "retraits", "etl", "rapport"]:
            run_job(job_id)

    elif cmd == "--scheduler":
        from .scheduler import run_scheduler
        run_scheduler()

    elif cmd == "planning":
        from .scheduler import planning
        from .utils import get_db
        for job in planning(get_db()):
            derniere = job["derniere_execution"] or {}
            print(f"  {job['frequence']:28} {job['label']:34} prochaine: {job['prochaine_execution'][:16]}"
                  f"  derniere: {derniere.get('debut', '—')[:16]} {derniere.get('statut', '')}")

    elif cmd == "job" and len(args) > 1:
        from .scheduler import run_job, JOBS_PAR_ID
        if args[1] not in JOBS_PAR_ID:
            print(f"Job inconnu : {args[1]}. Jobs : {', '.join(JOBS_PAR_ID)}")
            sys.exit(1)
        sys.exit(0 if run_job(args[1]) == "succes" else 1)

    elif cmd in ("afariat", "dar_tunisia", "airbnb"):
        print(f"[{cmd.upper()}] Source indisponible — scraper désactivé")

    else:
        print(f"Commande inconnue : {cmd}\n")
        print(USAGE)
        sys.exit(1)


if __name__ == "__main__":
    main()
