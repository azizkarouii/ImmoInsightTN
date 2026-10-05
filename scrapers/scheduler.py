import asyncio
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from .mubawab_scraper import run_mubawab
from .afariat_scraper import run_afariat
from .tayara_scraper import run_tayara
from .booking_scraper import scrape_booking
from .dar_tunisia_scraper import run_dar_tunisia
from .inside_airbnb_loader import load_inside_airbnb
from .change_detector import detect_removed_listings, get_new_listings_today, get_price_changes_today

def run_scheduler():
    scheduler = BlockingScheduler(timezone="Africa/Tunis")

    @scheduler.scheduled_job(CronTrigger(day_of_week="mon,thu", hour=2, minute=0))
    def job_mubawab():
        print(f"\n{'='*50}")
        print(f"[SCHEDULER] {datetime.now()} — Lancement Mubawab")
        run_mubawab()
        detect_removed_listings()

    @scheduler.scheduled_job(CronTrigger(day_of_week="tue", hour=3, minute=0))
    def job_afariat():
        print(f"[SCHEDULER] {datetime.now()} — Lancement Afariat")
        run_afariat()

    @scheduler.scheduled_job(CronTrigger(day_of_week="wed", hour=2, minute=0))
    def job_tayara():
        print(f"[SCHEDULER] {datetime.now()} — Lancement Tayara")
        run_tayara()

    @scheduler.scheduled_job(CronTrigger(hour=6, minute=0))
    def job_booking():
        print(f"[SCHEDULER] {datetime.now()} — Lancement Booking")
        asyncio.run(scrape_booking())

    @scheduler.scheduled_job(CronTrigger(day_of_week="fri", hour=4, minute=0))
    def job_dar_tunisia():
        print(f"[SCHEDULER] {datetime.now()} — Lancement Dar Tunisia")
        run_dar_tunisia()

    @scheduler.scheduled_job(CronTrigger(day=1, hour=5, minute=0))
    def job_airbnb():
        print(f"[SCHEDULER] {datetime.now()} — Chargement Inside Airbnb")
        load_inside_airbnb()

    @scheduler.scheduled_job(CronTrigger(hour=8, minute=0))
    def job_rapport():
        nouvelles   = get_new_listings_today()
        changements = get_price_changes_today()
        total_new     = sum(len(v) for v in nouvelles.values())
        total_changes = sum(len(v) for v in changements.values())
        print(f"\n[RAPPORT] {datetime.now().strftime('%d/%m/%Y')}")
        print(f"  Nouvelles annonces : {total_new}")
        print(f"  Changements de prix : {total_changes}")

    print("="*50)
    print("ImmoInsight TN — Scheduler démarré")
    print("Planning :")
    print("  Mubawab    → Lundi + Jeudi  02:00")
    print("  Afariat    → Mardi          03:00")
    print("  Tayara     → Mercredi       02:00")
    print("  Booking    → Tous les jours 06:00")
    print("  Dar Tunisia→ Vendredi       04:00")
    print("  Airbnb     → 1er du mois    05:00")
    print("  Rapport    → Tous les jours 08:00")
    print("="*50)

    scheduler.start()
