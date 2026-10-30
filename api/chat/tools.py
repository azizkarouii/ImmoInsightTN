"""Outils du chatbot : fonctions en lecture seule sur MongoDB et les modèles.

Le LLM ne fait que choisir un outil et remplir ses paramètres ; il n'écrit jamais
de requête Mongo. Chaque appel est validé contre le schéma JSON de l'outil
avant exécution, et les résultats sont compacts (champs utiles, textes tronqués).
"""
import json
import os
import re
import statistics
from datetime import datetime, timedelta, timezone

from jsonschema import Draft7Validator
from pymongo import MongoClient
from pymongo.collation import Collation
from dotenv import load_dotenv

load_dotenv()
db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[os.getenv("MONGO_DB", "immoinsight")]

SEGMENTS = {
    "vente": {"collection": "clean_vente", "unite": "TND"},
    "location": {"collection": "clean_location", "unite": "TND/mois"},
    "estival": {"collection": "clean_estival", "unite": "TND/nuit"},
}
# Égalité insensible à la casse et aux accents ("la marsa" == "La Marsa")
COLLATION_FR = Collation(locale="fr", strength=1)
MAX_ANNONCES = 10
MAX_TITRE = 100
MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models")


class ErreurOutil(ValueError):
    """Erreur renvoyée au modèle (paramètre invalide, donnée absente) pour qu'il se corrige."""


# ----------------------------------------------------------------------------
# Utilitaires
# ----------------------------------------------------------------------------
def _texte(value, longueur=MAX_TITRE):
    """Texte scrapé (non fiable) : caractères de contrôle retirés, longueur bornée."""
    if not isinstance(value, str):
        return None
    value = re.sub(r"[\x00-\x1f\x7f]+", " ", value).strip()
    return value[:longueur] + ("…" if len(value) > longueur else "")


def _arrondi(value, chiffres=0):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return int(round(value)) if chiffres == 0 else round(value, chiffres)


def _compact(d):
    return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def _percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    k = (len(values) - 1) * q
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    return values[f] + (values[c] - values[f]) * (k - f)


def _zone(ville=None, gouvernorat=None):
    """Filtre de localisation : la "ville" peut être une ville, une délégation, un
    quartier ou un gouvernorat (les annonces ne sont pas homogènes)."""
    conditions = []
    if ville:
        conditions.append({"$or": [{"ville": ville}, {"gouvernorat": ville}, {"quartier": ville}]})
    if gouvernorat:
        conditions.append({"gouvernorat": gouvernorat})
    return conditions


def _find(collection, query, projection=None, sort=None, limit=0):
    cursor = db[collection].find(query, projection).collation(COLLATION_FR)
    if sort:
        cursor = cursor.sort(sort)
    if limit:
        cursor = cursor.limit(limit)
    return list(cursor)


def _compte(collection, query):
    return db[collection].count_documents(query, collation=COLLATION_FR)


def _resoudre_zone(collection, base, ville, gouvernorat):
    """Égalité exacte (casse/accents ignorés), puis « contient » (ex. "Ennasr" ->
    "Ennasr 2"), puis la ville seule : les modèles ajoutent parfois un gouvernorat
    erroné (Ennasr est dans l'Ariana, pas à Tunis)."""
    query = {"$and": base + _zone(ville, gouvernorat)} if (base or ville or gouvernorat) else {}
    if not (ville or gouvernorat) or _compte(collection, query):
        return query, "exacte"

    def contient(champ_valeur):
        return {"$regex": re.escape(champ_valeur), "$options": "i"}

    regex_ville = {"$or": [{"ville": contient(ville)}, {"gouvernorat": contient(ville)}, {"quartier": contient(ville)}]} if ville else None
    conditions = base + ([regex_ville] if regex_ville else []) + ([{"gouvernorat": contient(gouvernorat)}] if gouvernorat else [])
    query = {"$and": conditions}
    if _compte(collection, query) or not (ville and gouvernorat):
        return query, "approchante"

    for sans_gouv in ({"$and": base + _zone(ville)}, {"$and": base + [regex_ville]}):
        if _compte(collection, sans_gouv):
            return sans_gouv, f"ville seule (aucune annonce pour {ville} dans le gouvernorat {gouvernorat})"
    return query, "approchante"


def _annonce(doc, unite):
    surface = doc.get("surface")
    prix = doc.get("prix")
    return _compact({
        "titre": _texte(doc.get("titre") or doc.get("nom")),
        "prix": _arrondi(prix),
        "unite": unite,
        "surface_m2": _arrondi(surface),
        "prix_m2": _arrondi(prix / surface) if prix and surface else None,
        "chambres": _arrondi(doc.get("nb_chambres")),
        "type": doc.get("type_bien") or doc.get("categorie"),
        "ville": doc.get("ville"),
        "gouvernorat": doc.get("gouvernorat"),
        "publiee_le": (doc.get("first_seen") or "")[:10] or None,
        "source": doc.get("source"),
        "url": doc.get("url"),
        "ecart_estimation_pct": doc.get("ecart_estimation_pct"),
    })


def _filtres_bien(type_bien=None, chambres_min=None, prix_min=None, prix_max=None,
                  surface_min=None, surface_max=None):
    conditions = []
    if type_bien:
        conditions.append({"$or": [{"type_bien": type_bien}, {"categorie": type_bien}]})
    if chambres_min is not None:
        conditions.append({"nb_chambres": {"$gte": chambres_min}})
    prix = {k: v for k, v in [("$gte", prix_min), ("$lte", prix_max)] if v is not None}
    if prix:
        conditions.append({"prix": prix})
    surface = {k: v for k, v in [("$gte", surface_min), ("$lte", surface_max)] if v is not None}
    if surface:
        conditions.append({"surface": surface})
    return conditions


def _derniere_mise_a_jour():
    log = db["scheduler_logs"].find_one({"job": "etl", "statut": "succes"}, sort=[("fin", -1)])
    return (log or {}).get("fin", "")[:16] or None


# ----------------------------------------------------------------------------
# Outils
# ----------------------------------------------------------------------------
def rechercher_annonces(segment, ville=None, gouvernorat=None, type_bien=None, chambres_min=None,
                        prix_min=None, prix_max=None, surface_min=None, surface_max=None,
                        tri="recentes", limite=5):
    seg = SEGMENTS[segment]
    base = _filtres_bien(type_bien, chambres_min, prix_min, prix_max, surface_min, surface_max)
    query, correspondance = _resoudre_zone(seg["collection"], base, ville, gouvernorat)
    tris = {"recentes": [("first_seen", -1)], "prix_croissant": [("prix", 1)], "prix_decroissant": [("prix", -1)],
            "surface_decroissante": [("surface", -1)], "meilleure_affaire": [("ecart_estimation_pct", 1)]}
    if tri == "meilleure_affaire":
        query = {"$and": [query, {"ecart_estimation_pct": {"$gte": -70}}]} if query else {"ecart_estimation_pct": {"$gte": -70}}
    total = db[seg["collection"]].count_documents(query, collation=COLLATION_FR)
    docs = _find(seg["collection"], query, sort=tris[tri], limit=min(limite, MAX_ANNONCES))
    return _compact({
        "segment": segment,
        "criteres": _compact({"zone": ville or gouvernorat or "toute la Tunisie", "type_bien": type_bien or "tous types",
                              "chambres_min": chambres_min, "prix_min": prix_min, "prix_max": prix_max,
                              "surface_min": surface_min, "surface_max": surface_max, "tri": tri}),
        "total_correspondant": total,
        "affichees": len(docs),
        "correspondance_zone": correspondance if (ville or gouvernorat) else None,
        "annonces": [_annonce(d, seg["unite"]) for d in docs],
    })


def statistiques_marche(segment, ville=None, gouvernorat=None, type_bien=None, chambres_min=None,
                        grouper_par=None):
    seg = SEGMENTS[segment]
    base = _filtres_bien(type_bien, chambres_min)
    query, correspondance = _resoudre_zone(seg["collection"], base, ville, gouvernorat)

    if grouper_par:
        pipeline = ([{"$match": query}] if query else []) + [
            {"$match": {"prix": {"$gt": 0}, grouper_par: {"$nin": [None, ""]}}},
            {"$group": {"_id": f"${grouper_par}", "n": {"$sum": 1},
                        "prix_median": {"$median": {"input": "$prix", "method": "approximate"}}}},
            {"$match": {"n": {"$gte": 3}}},
            {"$sort": {"n": -1}}, {"$limit": 15},
        ]
        zones = list(db[seg["collection"]].aggregate(pipeline, collation=COLLATION_FR))
        return {"segment": segment, "unite": seg["unite"], "groupe_par": grouper_par,
                "zones": [{"zone": z["_id"], "nb_annonces": z["n"], "prix_median": _arrondi(z["prix_median"])} for z in zones],
                "note": "zones avec au moins 3 annonces, triées par nombre d'annonces",
                "donnees_a_jour_au": _derniere_mise_a_jour()}

    criteres = _compact({"zone": ville or gouvernorat or "toute la Tunisie", "type_bien": type_bien or "tous types",
                         "chambres_min": chambres_min})
    docs = _find(seg["collection"], query, {"prix": 1, "surface": 1, "first_seen": 1})
    prix = [d["prix"] for d in docs if isinstance(d.get("prix"), (int, float)) and d["prix"] > 0]
    if not prix:
        return {"segment": segment, "nb_annonces": 0,
                "message": "Aucune annonce correspondante dans la base pour ces critères."}
    prix_m2 = [d["prix"] / d["surface"] for d in docs
               if isinstance(d.get("prix"), (int, float)) and isinstance(d.get("surface"), (int, float)) and d["surface"] > 0]
    surfaces = [d["surface"] for d in docs if isinstance(d.get("surface"), (int, float)) and d["surface"] > 0]
    dates = sorted(d["first_seen"][:10] for d in docs if d.get("first_seen"))
    return _compact({
        "segment": segment,
        "unite": seg["unite"],
        "criteres": criteres,
        "correspondance_zone": correspondance if (ville or gouvernorat) else None,
        "nb_annonces": len(prix),
        "prix_median": _arrondi(statistics.median(prix)),
        "prix_quartile_bas": _arrondi(_percentile(prix, 0.25)),
        "prix_quartile_haut": _arrondi(_percentile(prix, 0.75)),
        "prix_min": _arrondi(min(prix)),
        "prix_max": _arrondi(max(prix)),
        "prix_m2_median": _arrondi(statistics.median(prix_m2)) if len(prix_m2) >= 3 else None,
        "surface_mediane_m2": _arrondi(statistics.median(surfaces)) if len(surfaces) >= 3 else None,
        "annonces_publiees_entre": f"{dates[0]} et {dates[-1]}" if dates else None,
        "fiabilite": "faible (moins de 10 annonces)" if len(prix) < 10 else None,
        "donnees_a_jour_au": _derniere_mise_a_jour(),
    })


def _erreur_typique(chemin, cle):
    try:
        with open(os.path.join(MODELS_DIR, chemin)) as f:
            metrics = json.load(f)
    except (OSError, ValueError):
        return None
    for part in cle.split("."):
        metrics = (metrics or {}).get(part) if isinstance(metrics, dict) else None
    return metrics


def estimer_prix(segment, ville=None, gouvernorat=None, surface=None, type_bien=None, chambres=None,
                 salles_de_bain=None, meuble=None, parking=None, ascenseur=None, piscine=None,
                 lits=None, front_de_mer=None):
    zone = ville or gouvernorat
    if segment == "vente":
        if not surface:
            raise ErreurOutil("La surface (m²) est obligatoire pour estimer un prix de vente : demande-la à l'utilisateur.")
        from models.m1_avm_vente.predict import predict_one
        r = predict_one({
            "surface": surface, "gouvernorat": zone,
            "type_bien": type_bien if type_bien in ("appartement", "villa", "terrain") else "appartement",
            "nb_chambres": chambres, "nb_pieces": chambres + 1 if chambres is not None else None,
            "nb_sdb": salles_de_bain, "has_parking": int(bool(parking)), "has_ascenseur": int(bool(ascenseur)),
            "has_piscine": int(bool(piscine)),
        })
        erreur = _erreur_typique("m1_avm_vente/artifacts/metrics.json", "erreur_mediane_pct")
        zone_reconnue = r.get("zone_reconnue")
    elif segment == "location":
        from models.m2_loyer_classique.predict import predict_one
        r = predict_one({"surface": surface, "ville": ville, "gouvernorat": gouvernorat,
                         "type_bien": type_bien if type_bien in ("appartement", "villa") else "appartement",
                         "nb_chambres": chambres, "nb_sdb": salles_de_bain, "meuble": meuble})
        erreur = _erreur_typique("m2_loyer_classique/artifacts/metrics.json", "cv.modele.erreur_mediane_pct")
        zone_reconnue = r.get("zone_reconnue")
        r["prix_estime"] = r.pop("loyer_estime")
    else:
        if not zone:
            raise ErreurOutil("La ville est obligatoire pour une estimation estivale.")
        from models.m3_pricing_estival.predict import predict_one, VilleInconnue
        categorie = {"villa": "villa", "maison": "maison_vacances", "maison_vacances": "maison_vacances"}.get(type_bien or "", "appartement" if type_bien else None)
        try:
            r = predict_one(zone, categorie=categorie, nb_chambres=chambres, surface=surface, nb_lits=lits,
                            nb_sdb=salles_de_bain, front_de_mer=front_de_mer)
        except VilleInconnue as e:
            raise ErreurOutil(str(e))
        r["prix_estime"] = r.pop("prix_nuit_estime")
        erreur = _erreur_typique("m3_pricing_estival/artifacts/metrics.json", "cv.modele.erreur_mediane_pct")
        zone_reconnue = r.get("ville")

    return _compact({
        "segment": segment,
        "unite": SEGMENTS[segment]["unite"],
        "prix_estime": _arrondi(r["prix_estime"]),
        "fourchette_basse": _arrondi(r.get("intervalle_bas")),
        "fourchette_haute": _arrondi(r.get("intervalle_haut")),
        "zone_reconnue": zone_reconnue,
        "zone_non_reconnue": bool(zone and not zone_reconnue),
        "modele": r.get("modele") or "M1-vente",
        "erreur_mediane_typique_pct": erreur,
        "avertissement": "Estimation statistique indicative, pas une expertise.",
    })


def alertes_marche(type_alerte, segment="vente", jours=7, limite=5):
    from api.routers.alerte import _nouvelles, _changements_prix, _opportunites, _retirees, seuil_opportunite

    seg = SEGMENTS[segment]
    collection = seg["collection"]
    limite = min(limite, MAX_ANNONCES)
    if type_alerte == "nouvelles":
        total, docs = _nouvelles(collection, jours, limite)
        lignes = [_annonce(d, seg["unite"]) for d in docs]
    elif type_alerte == "variations_prix":
        rows = _changements_prix(collection, jours)
        total = len(rows)
        lignes = [_compact({**_annonce(r, seg["unite"]), "ancien_prix": r["ancien_prix"], "nouveau_prix": r["nouveau_prix"],
                            "variation_pct": r["variation_pct"], "date_changement": (r.get("date_changement") or "")[:10]})
                  for r in rows[:limite]]
    elif type_alerte == "opportunites":
        if segment == "estival":
            raise ErreurOutil("Les opportunités ne sont calculées que pour la vente et la location.")
        total, docs = _opportunites(collection, limite)
        lignes = [_compact({**_annonce(d, seg["unite"]), "prix_estime_modele": _arrondi(d.get("prix_estime"))}) for d in docs]
    else:
        total, docs = _retirees(collection, jours, limite)
        lignes = [_compact({**_annonce(d, seg["unite"]), "retiree_le": (d.get("supprime_le") or "")[:10]}) for d in docs]

    return _compact({
        "type_alerte": type_alerte,
        "segment": segment,
        "periode_jours": jours if type_alerte != "opportunites" else None,
        "total": total,
        "seuil_opportunite_pct": seuil_opportunite(collection) if type_alerte == "opportunites" else None,
        "annonces": lignes,
    })


def etat_plateforme():
    from scrapers.scheduler import planning
    from models.m3_pricing_estival.predict import villes_couvertes

    jobs = planning(db)
    try:
        villes_estivales = villes_couvertes()
    except FileNotFoundError:
        villes_estivales = []
    return {
        "annonces": {nom: db[s["collection"]].count_documents({}) for nom, s in SEGMENTS.items()},
        "sources": ["Tayara", "Mubawab", "Booking (estival)"],
        "donnees_a_jour_au": _derniere_mise_a_jour(),
        "villes_estivales_couvertes": villes_estivales,
        "collectes": [_compact({
            "tache": j["label"], "frequence": j["frequence"],
            "prochaine": (j["prochaine_execution"] or "")[:16],
            "derniere": ((j["derniere_execution"] or {}).get("debut") or "")[:16],
            "statut_derniere": (j["derniere_execution"] or {}).get("statut"),
        }) for j in jobs],
    }


def calculer_rentabilite(prix_achat, loyer_mensuel=None, prix_nuit=None, nuits_par_an=90):
    from models.roi_score.calculator import compute_roi

    if not loyer_mensuel and not prix_nuit:
        raise ErreurOutil("Il faut un loyer mensuel ou un prix par nuit (utilise estimer_prix si l'utilisateur ne le connaît pas).")
    r = compute_roi(prix_achat, loyer_mensuel=loyer_mensuel, prix_nuit=prix_nuit, nuits_an=nuits_par_an)
    return _compact({k: r.get(k) for k in [
        "prix", "cout_total_acquisition", "revenu_annuel_total", "rendement_brut_pct", "rendement_net_pct",
        "temps_retour_annees", "score_roi", "label_roi"]} | {"unite": "TND", "hypotheses": "frais d'acquisition 5 %, charges et taxe incluses dans le rendement net"})


# ----------------------------------------------------------------------------
# Schémas exposés au LLM
# ----------------------------------------------------------------------------
_SEGMENT = {"type": "string", "enum": list(SEGMENTS),
            "description": "vente (prix total), location (loyer mensuel) ou estival (prix par nuit)"}
_VILLE = {"type": "string", "description": "Ville, délégation ou quartier (ex : La Marsa, Ennasr, Hammamet)"}
_GOUV = {"type": "string", "description": "Gouvernorat (ex : Tunis, Ariana, Nabeul, Sousse). "
                                          "À renseigner seulement si l'utilisateur l'indique."}
_TYPE = {"type": "string", "enum": ["appartement", "villa", "maison_vacances"],
         "description": "Type de bien (maison_vacances : estival uniquement)"}


def _schema(proprietes, requis=()):
    return {"type": "object", "properties": proprietes, "required": list(requis), "additionalProperties": False}


OUTILS = {
    "rechercher_annonces": {
        "fonction": rechercher_annonces,
        "description": "Recherche des annonces dans la base selon des critères (zone, type, prix, surface, chambres). "
                       "Renvoie le nombre total correspondant et quelques annonces avec leur lien.",
        "parametres": _schema({
            "segment": _SEGMENT, "ville": _VILLE, "gouvernorat": _GOUV, "type_bien": _TYPE,
            "chambres_min": {"type": "integer", "minimum": 0, "maximum": 20},
            "prix_min": {"type": "number", "minimum": 0}, "prix_max": {"type": "number", "minimum": 0},
            "surface_min": {"type": "number", "minimum": 0}, "surface_max": {"type": "number", "minimum": 0},
            "tri": {"type": "string", "enum": ["recentes", "prix_croissant", "prix_decroissant", "surface_decroissante", "meilleure_affaire"]},
            "limite": {"type": "integer", "minimum": 1, "maximum": MAX_ANNONCES},
        }, ["segment"]),
    },
    "statistiques_marche": {
        "fonction": statistiques_marche,
        "description": "Statistiques de prix observées dans les annonces (médiane, quartiles, prix au m², nombre d'annonces) "
                       "pour une zone, ou classement des zones avec grouper_par.",
        "parametres": _schema({
            "segment": _SEGMENT, "ville": _VILLE, "gouvernorat": _GOUV, "type_bien": _TYPE,
            "chambres_min": {"type": "integer", "minimum": 0, "maximum": 20},
            "grouper_par": {"type": "string", "enum": ["ville", "gouvernorat"],
                            "description": "Pour comparer les zones entre elles"},
        }, ["segment"]),
    },
    "estimer_prix": {
        "fonction": estimer_prix,
        "description": "Estime le prix d'un bien avec les modèles de la plateforme : prix de vente (surface obligatoire), "
                       "loyer mensuel ou prix par nuit estival (ville obligatoire). Renvoie une fourchette et l'erreur typique.",
        "parametres": _schema({
            "segment": _SEGMENT, "ville": _VILLE, "gouvernorat": _GOUV,
            "surface": {"type": "number", "exclusiveMinimum": 0, "maximum": 10000},
            "type_bien": _TYPE,
            "chambres": {"type": "integer", "minimum": 0, "maximum": 20},
            "salles_de_bain": {"type": "integer", "minimum": 0, "maximum": 20},
            "meuble": {"type": "boolean"}, "parking": {"type": "boolean"}, "ascenseur": {"type": "boolean"},
            "piscine": {"type": "boolean"},
            "lits": {"type": "integer", "minimum": 1, "maximum": 40, "description": "estival uniquement"},
            "front_de_mer": {"type": "boolean", "description": "estival uniquement"},
        }, ["segment"]),
    },
    "alertes_marche": {
        "fonction": alertes_marche,
        "description": "Alertes de la plateforme : nouvelles annonces, variations de prix, opportunités "
                       "(prix nettement sous l'estimation des modèles) ou annonces retirées.",
        "parametres": _schema({
            "type_alerte": {"type": "string", "enum": ["nouvelles", "variations_prix", "opportunites", "retirees"]},
            "segment": _SEGMENT,
            "jours": {"type": "integer", "minimum": 1, "maximum": 90, "description": "période en jours (défaut 7)"},
            "limite": {"type": "integer", "minimum": 1, "maximum": MAX_ANNONCES},
        }, ["type_alerte"]),
    },
    "etat_plateforme": {
        "fonction": etat_plateforme,
        "description": "Informations sur la plateforme : nombre d'annonces, sources, date de mise à jour des données, "
                       "planning des collectes, villes couvertes en location estivale.",
        "parametres": _schema({}),
    },
    "calculer_rentabilite": {
        "fonction": calculer_rentabilite,
        "description": "Calcule la rentabilité locative d'un achat (rendements brut et net, temps de retour, score) "
                       "à partir d'un prix d'achat et d'un loyer mensuel et/ou d'un prix par nuit.",
        "parametres": _schema({
            "prix_achat": {"type": "number", "exclusiveMinimum": 0},
            "loyer_mensuel": {"type": "number", "minimum": 0},
            "prix_nuit": {"type": "number", "minimum": 0},
            "nuits_par_an": {"type": "integer", "minimum": 1, "maximum": 365},
        }, ["prix_achat"]),
    },
}
_VALIDATEURS = {nom: Draft7Validator(o["parametres"]) for nom, o in OUTILS.items()}


def definitions():
    """Définitions au format « function calling » (compatible OpenAI / Groq)."""
    return [{"type": "function", "function": {"name": nom, "description": o["description"], "parameters": o["parametres"]}}
            for nom, o in OUTILS.items()]


def executer(nom, arguments):
    """Valide et exécute un appel d'outil. Renvoie un dict sérialisable ; les erreurs
    sont renvoyées au modèle sous la forme {"erreur": ...} pour qu'il se corrige."""
    if nom not in OUTILS:
        return {"erreur": f"Outil inconnu : {nom}. Outils disponibles : {', '.join(OUTILS)}."}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments or "{}")
        except ValueError:
            return {"erreur": "Arguments JSON invalides."}
    if not isinstance(arguments, dict):
        return {"erreur": "Les arguments doivent être un objet JSON."}
    # Les modèles envoient parfois null pour un paramètre facultatif
    arguments = {k: v for k, v in arguments.items() if v is not None}
    erreurs = sorted(_VALIDATEURS[nom].iter_errors(arguments), key=lambda e: list(e.path))
    if erreurs:
        return {"erreur": "Paramètres invalides : " + "; ".join(
            f"{'.'.join(map(str, e.path)) or 'arguments'} : {e.message}" for e in erreurs[:3])}
    try:
        return OUTILS[nom]["fonction"](**arguments)
    except ErreurOutil as e:
        return {"erreur": str(e)}
