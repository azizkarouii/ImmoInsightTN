import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests

from .utils import get_db

COLLECTIONS = ["raw_vente", "raw_location", "raw_estival"]
STATUT_RETIRE = "supprime"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def statut_en_ligne(url, session=None):
    """'en_ligne', 'retiree' ou 'inconnu' (limitation de débit, erreur réseau...)."""
    session = session or requests
    try:
        r = session.get(url, headers=HEADERS, timeout=20, allow_redirects=False)
    except requests.RequestException:
        return "inconnu"
    if r.status_code in (404, 410):
        return "retiree"
    if r.status_code in (301, 302, 303, 307, 308):
        cible = urlparse(r.headers.get("Location", ""))
        source = urlparse(url)
        # Redirection vers une autre page que l'annonce (liste, accueil, recherche)
        meme_annonce = cible.path.rstrip("/").split("/")[-1:] == source.path.rstrip("/").split("/")[-1:]
        return "en_ligne" if meme_annonce else "retiree"
    if r.status_code == 200:
        # Tayara répond 200 avec une page vide quand l'annonce n'existe plus
        if "tayara.tn/item/" in url and '"adDetails":{' not in r.text and '"adDetails": {' not in r.text:
            return "retiree"
        return "en_ligne"
    return "inconnu"


def verifier_retraits(jours=14, max_par_source=150, pause_s=1.5):
    """Vérifie les annonces non revues par les scrapers depuis `jours` jours.

    Une annonce absente des pages parcourues n'est pas forcément retirée (les
    scrapers ne visitent que les pages récentes) : on re-visite son URL.
    """
    db = get_db()
    now = _now()
    seuil = (now - timedelta(days=jours)).isoformat()
    deja_verifie = (now - timedelta(days=3)).isoformat()
    session = requests.Session()
    stats = {"retiree": 0, "en_ligne": 0, "inconnu": 0}

    for col_name in COLLECTIONS:
        col = db[col_name]
        par_source = {}
        candidats = col.find({
            "status": {"$ne": STATUT_RETIRE},
            "scraped_at": {"$lt": seuil},
            "$or": [{"verifie_le": {"$exists": False}}, {"verifie_le": {"$lt": deja_verifie}}],
        }, {"url": 1, "source": 1}).sort("scraped_at", 1)

        sources_bloquees = set()
        for doc in candidats:
            source = doc.get("source") or "?"
            if source in sources_bloquees or par_source.get(source, 0) >= max_par_source:
                continue
            par_source[source] = par_source.get(source, 0) + 1
            statut = statut_en_ligne(doc["url"], session)
            stats[statut] += 1
            maj = {"verifie_le": now.isoformat()}
            if statut == "retiree":
                maj.update({"status": STATUT_RETIRE, "supprime_le": now.isoformat()})
            elif statut == "inconnu":
                # Probablement limité par le site : on arrête cette source pour ce passage
                sources_bloquees.add(source)
            col.update_one({"_id": doc["_id"]}, {"$set": maj})
            time.sleep(pause_s)

    print(f"[CDC] Verification des retraits : {stats}")
    return stats


def migrer_statuts():
    """Ancienne valeur accentuée 'supprimé' (jamais trouvée par l'API qui cherche 'supprime')."""
    db = get_db()
    for col_name in COLLECTIONS:
        db[col_name].update_many({"status": "supprimé"}, {"$set": {"status": STATUT_RETIRE}})


def rapport_quotidien():
    """Résumé des alertes des dernières 24 h, archivé dans `alert_reports`."""
    from api.routers.alerte import alertes_resume

    resume = alertes_resume(jours=1)
    db = get_db()
    db["alert_reports"].insert_one({"date": _now().isoformat(), **resume})
    print(f"[RAPPORT] {_now():%d/%m/%Y %H:%M}")
    for collection, compteurs in resume["collections"].items():
        print(f"  {collection:15} " + "  ".join(f"{k}={v}" for k, v in compteurs.items()))
    print(f"  fiabilite faible (clean_vente) = {resume['fiabilite_faible']}")
    return resume


# Compatibilité avec l'ancien nom
def detect_removed_listings():
    return verifier_retraits()
