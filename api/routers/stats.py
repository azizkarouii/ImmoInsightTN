from fastapi import APIRouter
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from statistics import mean, median
from collections import Counter
import math
import os
from .. import clean_doc
from etl.regions import ORDRE_REGIONS, region_de

load_dotenv()
router = APIRouter()
db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[os.getenv("MONGO_DB", "immoinsight")]


def _collection_overview(col: str):
    docs = list(
        db[col].find(
            {},
            {
                "prix": 1,
                "lat": 1,
                "lon": 1,
                "source": 1,
                "quality_score": 1,
            },
        )
    )

    total = len(docs)
    prices = [float(d["prix"]) for d in docs if d.get("prix") is not None]
    geo = [d for d in docs if d.get("lat") is not None and d.get("lon") is not None]
    quality_scores = [float(d["quality_score"]) for d in docs if d.get("quality_score") is not None]
    sources = Counter(d.get("source") or "Inconnue" for d in docs)
    top_sources = [
        {"source": source, "count": count}
        for source, count in sources.most_common(4)
    ]

    price_summary = None
    if prices:
        prices_sorted = sorted(prices)
        price_summary = {
            "moyen": round(mean(prices), 2),
            "median": round(median(prices_sorted), 2),
            "min": round(min(prices_sorted), 2),
            "max": round(max(prices_sorted), 2),
        }

    return {
        "total": total,
        "couverture_gps_pct": round((len(geo) / total) * 100, 1) if total else 0,
        "qualite_moyenne": round(mean(quality_scores), 1) if quality_scores else None,
        "prix": price_summary,
        "top_sources": top_sources,
    }


@router.get("/stats")
def stats_globales():
    collections = {
        "vente": "clean_vente",
        "location": "clean_location",
        "estival": "clean_estival",
    }
    stats = {}
    overviews = {}
    for key, col in collections.items():
        overview = overviews[key] = _collection_overview(col)
        stats[key] = {
            "total": db[col].count_documents({}),
            # Dates stockées en texte ISO (UTC) : comparaison en texte
            "nouveaux_7j": db[col].count_documents({
                "first_seen": {"$gte": (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)).isoformat()}
            }),
            "avec_gps": db[col].count_documents({"lat": {"$ne": None}, "lon": {"$ne": None}}),
            "couverture_gps_pct": overview["couverture_gps_pct"],
            "qualite_moyenne": overview["qualite_moyenne"],
            "top_sources": overview["top_sources"],
        }

    # Prix moyen par type
    prix_moyen = {}
    for col in ["clean_vente", "clean_estival"]:
        pipeline = [
            {"$group": {"_id": None, "moyen": {"$avg": "$prix"}}}
        ]
        result = list(db[col].aggregate(pipeline))
        prix_moyen[col] = round(result[0]["moyen"], 2) if result else None

    prix_median = {
        "clean_vente": overviews["vente"]["prix"],
        "clean_location": overviews["location"]["prix"],
        "clean_estival": overviews["estival"]["prix"],
    }

    total_geo = sum(s["avec_gps"] for s in stats.values())
    total_annonces = sum(s["total"] for s in stats.values())

    # Sources distribution
    sources = {}
    for col in ["clean_vente", "clean_estival"]:
        pipeline = [
            {"$group": {"_id": "$source", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        sources[col] = {r["_id"]: r["count"] for r in db[col].aggregate(pipeline)}

    return clean_doc({
        "collections": stats,
        "prix_moyen": prix_moyen,
        "prix_median": prix_median,
        "sources": sources,
        "total_annonces": sum(s["total"] for s in stats.values()),
        "global_geo_coverage_pct": round((total_geo / total_annonces) * 100, 1) if total_annonces else 0,
    })


@router.get("/stats/prix_par_gouvernorat")
def prix_par_gouvernorat(
    collection: str = "clean_vente",
):
    pipeline = [
        {"$match": {"prix": {"$ne": None}, "gouvernorat": {"$nin": [None, ""]}}},
        {"$group": {
            "_id": "$gouvernorat",
            "prix_moyen": {"$avg": "$prix"},
            "prix_median": {"$median": {"input": "$prix", "method": "approximate"}},
            "prix_min": {"$min": "$prix"},
            "prix_max": {"$max": "$prix"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
    ]
    results = list(db[collection].aggregate(pipeline))
    return clean_doc({"collection": collection, "data": results})


@router.get("/stats/prix_par_ville")
def prix_par_ville(
    collection: str = "clean_estival",
):
    pipeline = [
        {"$match": {"prix": {"$ne": None}, "ville": {"$nin": [None, ""]}}},
        {"$group": {
            "_id": "$ville",
            "prix_moyen": {"$avg": "$prix"},
            "prix_median": {"$median": {"input": "$prix", "method": "approximate"}},
            "prix_min": {"$min": "$prix"},
            "prix_max": {"$max": "$prix"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
    ]
    results = list(db[collection].aggregate(pipeline))
    return clean_doc({"collection": collection, "data": results})


# ---------------------------------------------------------------------------
# Lecture approfondie du marché (page Statistiques)
# ---------------------------------------------------------------------------
SEGMENTS_MARCHE = {"vente": "clean_vente", "location": "clean_location", "estival": "clean_estival"}
# Bornes de plausibilité du prix au m² (erreurs de saisie : surface 1 000 m² pour un S+1, prix x1000...)
PRIX_M2_BORNES = {"vente": (200, 15000), "location": (2, 80)}
MIN_ZONE = 8  # annonces minimum pour afficher une zone
# Les 24 gouvernorats : le champ "gouvernorat" contient parfois une ville (Mubawab ne
# fournit pas le gouvernorat, le nettoyage y recopie la ville)
GOUVERNORATS = {
    "ariana", "beja", "ben arous", "bizerte", "gabes", "gafsa", "jendouba", "kairouan", "kasserine",
    "kebili", "le kef", "kef", "mahdia", "manouba", "la manouba", "medenine", "monastir", "nabeul", "sfax",
    "sidi bouzid", "siliana", "sousse", "tataouine", "tozeur", "tunis", "zaghouan",
}


def _gouvernorat(d):
    import unicodedata
    g = d.get("gouvernorat")
    if not isinstance(g, str):
        return None
    cle = " ".join(unicodedata.normalize("NFKD", g).encode("ascii", "ignore").decode().lower().replace("-", " ").split())
    return g.strip().title() if cle in GOUVERNORATS else None


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not math.isnan(v) and v > 0 else None


def _med(values):
    values = [v for v in values if v is not None]
    return round(median(values), 1) if values else None


def _par_groupe(docs, cle, valeur, min_n=MIN_ZONE, limite=None, tri_par="n"):
    groupes = {}
    for d in docs:
        k, v = cle(d), valeur(d)
        if k not in (None, "") and v is not None:
            groupes.setdefault(k, []).append(v)
    lignes = [{"cle": k, "n": len(v), "median": round(median(v), 1)} for k, v in groupes.items() if len(v) >= min_n]
    lignes.sort(key=lambda r: -r[tri_par])
    return lignes[:limite] if limite else lignes


def _chambres(d):
    n = d.get("nb_chambres")
    if not isinstance(n, (int, float)) or math.isnan(n) or n < 0 or n > 10:
        return None
    return "S+5 et +" if n >= 5 else f"S+{int(n)}"


@router.get("/stats/marche")
def stats_marche():
    champs = {"prix": 1, "surface": 1, "ville": 1, "gouvernorat": 1, "type_bien": 1, "categorie": 1,
              "nb_chambres": 1, "first_seen": 1, "opportunite": 1}
    docs = {seg: list(db[col].find({"prix": {"$gt": 0}}, champs)) for seg, col in SEGMENTS_MARCHE.items()}

    def prix_m2(seg):
        lo, hi = PRIX_M2_BORNES[seg]

        def f(d):
            p, s = _num(d.get("prix")), _num(d.get("surface"))
            v = p / s if p and s else None
            return v if v is not None and lo <= v <= hi else None
        return f

    prix = lambda d: _num(d.get("prix"))  # noqa: E731
    appartements = {seg: [d for d in docs[seg] if d.get("type_bien") == "appartement"] for seg in ("vente", "location")}

    # Histogramme du prix au m² (vente), tranches de 500 TND
    valeurs_m2 = [v for v in map(prix_m2("vente"), docs["vente"]) if v is not None]
    pas, plafond = 500, 6000
    histogramme = [{"tranche": f"{b:,}–{b + pas:,}".replace(",", " "), "n": sum(1 for v in valeurs_m2 if b <= v < b + pas)}
                   for b in range(0, plafond, pas)]
    histogramme.append({"tranche": f"{plafond:,} et +".replace(",", " "), "n": sum(1 for v in valeurs_m2 if v >= plafond)})

    # Rendement locatif brut par ville : appartements uniquement (même type de bien à
    # l'achat et à la location), loyer médian x 12 / prix médian
    vente_ville = {r["cle"]: r for r in _par_groupe(appartements["vente"], lambda d: d.get("ville"), prix, min_n=5)}
    loyer_ville = {r["cle"]: r for r in _par_groupe(appartements["location"], lambda d: d.get("ville"), prix, min_n=5)}
    rendements = sorted((
        {"ville": v, "prix_median": vente_ville[v]["median"], "loyer_median": loyer_ville[v]["median"],
         "n_vente": vente_ville[v]["n"], "n_location": loyer_ville[v]["n"],
         "rendement_brut_pct": round(loyer_ville[v]["median"] * 12 / vente_ville[v]["median"] * 100, 1)}
        for v in vente_ville.keys() & loyer_ville.keys()), key=lambda r: -r["rendement_brut_pct"])

    # Nouvelles annonces par jour (60 derniers jours)
    debut = (datetime.now(timezone.utc) - timedelta(days=59)).date()
    jours = [(debut + timedelta(days=i)).isoformat() for i in range(60)]
    activite = {j: {"date": j, "vente": 0, "location": 0, "estival": 0} for j in jours}
    for seg, liste in docs.items():
        for d in liste:
            j = (d.get("first_seen") or "")[:10]
            if j in activite:
                activite[j][seg] += 1

    def types(seg):
        champ = "categorie" if seg == "estival" else "type_bien"
        compte = Counter(d.get(champ) for d in docs[seg] if d.get(champ))
        return dict(compte)

    # Grandes régions : volumes par segment et médianes (au moins MIN_ZONE annonces)
    def mediane_region(liste, valeur):
        valeurs = [v for v in map(valeur, liste) if v is not None]
        return round(median(valeurs), 1) if len(valeurs) >= MIN_ZONE else None

    par_region = []
    for region in ORDRE_REGIONS:
        du_segment = {seg: [d for d in docs[seg] if region_de(d) == region] for seg in SEGMENTS_MARCHE}
        if not any(du_segment.values()):
            continue
        par_region.append({
            "region": region,
            **{f"n_{seg}": len(liste) for seg, liste in du_segment.items()},
            "prix_m2_vente": mediane_region(du_segment["vente"], prix_m2("vente")),
            "prix_vente": mediane_region(du_segment["vente"], prix),
            "loyer": mediane_region(du_segment["location"], prix),
            "prix_nuit": mediane_region(du_segment["estival"], prix),
        })

    loyer_m2_appart = _med(map(prix_m2("location"), appartements["location"]))
    prix_m2_appart = _med(map(prix_m2("vente"), appartements["vente"]))
    return clean_doc({
        "kpis": {
            "prix_m2_median_vente": _med(valeurs_m2),
            "loyer_m2_median": _med(map(prix_m2("location"), docs["location"])),
            "prix_nuit_median": _med(map(prix, docs["estival"])),
            "rendement_brut_median_pct": round(loyer_m2_appart * 12 / prix_m2_appart * 100, 1) if loyer_m2_appart and prix_m2_appart else None,
            "nb_villes": len({d.get("ville") for liste in docs.values() for d in liste if d.get("ville")}),
            "opportunites": sum(1 for seg in ("vente", "location") for d in docs[seg] if d.get("opportunite")),
        },
        "vente_prix_m2_par_gouvernorat": _par_groupe(docs["vente"], _gouvernorat, prix_m2("vente"), limite=12, tri_par="median"),
        "vente_histogramme_prix_m2": histogramme,
        "location_loyer_par_ville": _par_groupe(docs["location"], lambda d: d.get("ville"), prix, limite=12, tri_par="median"),
        "prix_par_chambres": {
            seg: sorted(_par_groupe(docs[seg], _chambres, prix, min_n=5), key=lambda r: r["cle"])
            for seg in SEGMENTS_MARCHE
        },
        "estival_par_type": _par_groupe(docs["estival"], lambda d: d.get("categorie"), prix, min_n=5, tri_par="median"),
        "types": {seg: types(seg) for seg in SEGMENTS_MARCHE},
        "rendement_par_ville": rendements[:12],
        "par_region": par_region,
        "activite_quotidienne": list(activite.values()),
        "note_rendement": "Appartements uniquement : loyer médian × 12 / prix de vente médian, villes avec au moins 5 annonces de chaque.",
    })


@router.get("/stats/qualite")
def stats_qualite():
    """Dernier rapport qualité de l'ETL (corrections, doublons, annonces écartées)."""
    rapport = db["qualite_rapports"].find_one({}, {"_id": 0}, sort=[("date", -1)])
    return clean_doc(rapport or {"date": None, "collections": {}})
