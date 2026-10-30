"""Collecte automatique : scrapers, vérification des retraits, ETL, ré-entraînement, rapport.

Chaque job tourne dans un sous-processus (`python -m ...`) :
- Scrapy ne peut démarrer son reactor Twisted qu'une fois par processus : dans un
  scheduler longue durée, le 2e job Scrapy échouait (ReactorNotRestartable) ;
- un job qui plante ou se bloque n'emporte pas le scheduler (timeout par job).
Chaque exécution est journalisée dans la collection Mongo `scheduler_logs`.

Démarrage : python -m scrapers.main --scheduler
Un job à la demande : python -m scrapers.main job <id>
"""
import os
import sys
import time
import threading
import subprocess
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .utils import get_db

TIMEZONE = "Africa/Tunis"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Les scrapers d'Afariat (Cloudflare), Dar Tunisia (domaine mort) et Inside Airbnb
# (Tunisie retirée) ne sont plus planifiés : ils échouaient à chaque exécution.
JOBS = [
    {
        "id": "tayara_incremental",
        "label": "Tayara — nouvelles annonces",
        "description": "Pages récentes jusqu'à 2 pages sans nouvelle annonce (vente + location)",
        "cron": {"hour": 2, "minute": 0},
        "jours": "Tous les jours à 02:00",
        "commande": ["-m", "scrapers.main", "tayara", "--incremental"],
        "timeout_min": 90,
        "collecte": True,
    },
    {
        "id": "tayara_complet",
        "label": "Tayara — passage complet",
        "description": "Toutes les pages configurées : détecte les changements de prix",
        "cron": {"day_of_week": "sun", "hour": 1, "minute": 0},
        "jours": "Dimanche à 01:00",
        "commande": ["-m", "scrapers.main", "tayara"],
        "timeout_min": 180,
        "collecte": True,
    },
    {
        "id": "mubawab",
        "label": "Mubawab — pages récentes",
        "description": "3 premières pages par catégorie (le site limite le débit, erreurs 429)",
        "cron": {"day_of_week": "mon,thu", "hour": 3, "minute": 0},
        "jours": "Lundi et jeudi à 03:00",
        "commande": ["-m", "scrapers.main", "mubawab", "--rapide"],
        "timeout_min": 90,
        "collecte": True,
    },
    {
        "id": "mubawab_refresh",
        "label": "Mubawab — annonces sans prix",
        "description": "Re-visite les annonces sans prix (prix sur demande, erreur de lecture précédente)",
        "cron": {"day_of_week": "sat", "hour": 3, "minute": 0},
        "jours": "Samedi à 03:00",
        "commande": ["-m", "scrapers.main", "mubawab_refresh"],
        "timeout_min": 60,
        "collecte": True,
    },
    {
        "id": "booking",
        "label": "Booking — locations estivales",
        "description": "Appartements, maisons de vacances et villas de 24 villes (prix pour J+7)",
        "cron": {"day_of_week": "tue,fri", "hour": 4, "minute": 0},
        "jours": "Mardi et vendredi à 04:00",
        "commande": ["-m", "scrapers.main", "booking"],
        "timeout_min": 120,
        "collecte": True,
    },
    {
        "id": "retraits",
        "label": "Vérification des retraits",
        "description": "Re-visite les annonces non revues depuis 14 jours ; 404 / redirection = retirée",
        "cron": {"hour": 6, "minute": 0},
        "jours": "Tous les jours à 06:00",
        "commande": ["-m", "scrapers.main", "retraits"],
        "timeout_min": 30,
        "collecte": True,
    },
    {
        "id": "etl",
        "label": "Pipeline ETL",
        "description": "Nettoyage, déduplication, géocodage, features, fiabilité (M4), opportunités",
        "cron": {"hour": 6, "minute": 45},
        "jours": "Tous les jours à 06:45",
        "commande": ["-m", "etl.pipeline"],
        "timeout_min": 120,
        "attend_collectes": True,
    },
    {
        "id": "entrainement",
        "label": "Ré-entraînement des modèles",
        "description": "M1 vente, M2 loyer, M3 estival, puis recalcul des opportunités",
        "cron": {"day_of_week": "sun", "hour": 9, "minute": 0},
        "jours": "Dimanche à 09:00",
        "commande": ["-m", "models.train_all"],
        "timeout_min": 60,
        "attend_collectes": True,
    },
    {
        "id": "rapport",
        "label": "Rapport d'alertes",
        "description": "Nouvelles annonces, baisses de prix, retraits et opportunités du jour",
        "cron": {"hour": 9, "minute": 30},
        "jours": "Tous les jours à 09:30",
        "commande": ["-m", "scrapers.main", "rapport"],
        "timeout_min": 10,
    },
]
JOBS_PAR_ID = {job["id"]: job for job in JOBS}

_collectes_en_cours = set()
_verrou = threading.Lock()


def _maintenant():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def run_job(job_id, db=None):
    """Exécute un job dans un sous-processus et journalise le résultat."""
    job = JOBS_PAR_ID[job_id]
    db = db if db is not None else get_db()

    if job.get("attend_collectes"):
        # L'ETL ne doit pas lire des collections brutes en cours d'écriture
        debut_attente = time.time()
        while _collectes_en_cours and time.time() - debut_attente < 3 * 3600:
            time.sleep(30)

    log = {"job": job_id, "label": job["label"], "debut": _maintenant(), "statut": "en_cours"}
    log_id = db["scheduler_logs"].insert_one(log).inserted_id
    if job.get("collecte"):
        with _verrou:
            _collectes_en_cours.add(job_id)

    print(f"[SCHEDULER] {log['debut']} — {job['label']}", flush=True)
    debut = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, *job["commande"]],
            cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=job["timeout_min"] * 60,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        statut = "succes" if proc.returncode == 0 else "echec"
        sortie = (proc.stdout or "") + (proc.stderr or "" if proc.returncode else "")
    except subprocess.TimeoutExpired as e:
        statut, sortie = "timeout", (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
    finally:
        if job.get("collecte"):
            with _verrou:
                _collectes_en_cours.discard(job_id)

    lignes = [l for l in sortie.splitlines() if l.strip()]
    db["scheduler_logs"].update_one({"_id": log_id}, {"$set": {
        "fin": _maintenant(),
        "duree_s": round(time.time() - debut, 1),
        "statut": statut,
        "resume": [l for l in lignes if "Termine" in l or "BILAN" in l or "[RAPPORT]" in l][-5:],
        "sortie": lignes[-40:],
    }})
    print(f"[SCHEDULER] {job['label']} : {statut} ({round(time.time() - debut)} s)", flush=True)
    return statut


def planning(db):
    """Planning (prochaine exécution) et dernière exécution de chaque job."""
    now = datetime.now(timezone.utc)
    resultat = []
    for job in JOBS:
        trigger = CronTrigger(timezone=TIMEZONE, **job["cron"])
        prochaine = trigger.get_next_fire_time(None, now)
        derniere = db["scheduler_logs"].find_one({"job": job["id"]}, {"_id": 0, "sortie": 0}, sort=[("debut", -1)])
        resultat.append({
            "id": job["id"],
            "label": job["label"],
            "description": job["description"],
            "frequence": job["jours"],
            "prochaine_execution": prochaine.isoformat() if prochaine else None,
            "derniere_execution": derniere,
        })
    return resultat


def run_scheduler():
    scheduler = BlockingScheduler(
        timezone=TIMEZONE,
        # Machine éteinte ou en veille à l'heure prévue : le job est rattrapé au
        # réveil (dans les 6 h) au lieu d'être abandonné ; une seule exécution à la fois
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 6 * 3600},
    )
    for job in JOBS:
        scheduler.add_job(run_job, CronTrigger(timezone=TIMEZONE, **job["cron"]),
                          args=[job["id"]], id=job["id"], name=job["label"])

    print("=" * 60)
    print("ImmoInsight TN — Scheduler démarré (fuseau Africa/Tunis)")
    for job in JOBS:
        print(f"  {job['jours']:28} {job['label']}")
    print("=" * 60, flush=True)
    scheduler.start()
