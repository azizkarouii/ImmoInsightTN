"""Contrôles de qualité des annonces et rapport par passage de l'ETL.

Principe : corriger ou vider un champ manifestement faux plutôt que supprimer
l'annonce (un loyer correct avec une surface aberrante reste une donnée utile).
Chaque correction est comptée dans un rapport enregistré dans `qualite_rapports`.
"""
import re
import unicodedata
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# Prix au m² plausibles : en dehors, c'est la surface qui est le plus souvent fausse
# (1 000 m² pour un S+1, surface du terrain au lieu de l'habitable...)
PRIX_M2_BORNES = {"vente": (200, 15000), "location": (2, 80)}
CHAMBRES_MAX = 10
M2_MIN_PAR_CHAMBRE = 9

# "S+2", "S + 3", "s2", "S+1 bis" -> nombre de chambres (convention tunisienne)
_S_PLUS = re.compile(r"(?<![a-z0-9])s\s*\+?\s*(\d)(?![0-9])", re.IGNORECASE)

_rapport = {}


def segment_de(collection_name):
    for seg in ("estival", "vente", "location"):
        if seg in collection_name:
            return seg
    return None


def norm(texte):
    if texte is None or (isinstance(texte, float) and np.isnan(texte)):
        return ""
    texte = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode()
    return " ".join(texte.lower().replace("-", " ").split())


def chambres_depuis_titre(titre):
    if not isinstance(titre, str):
        return None
    m = _S_PLUS.search(titre)
    return int(m.group(1)) if m else None


def compter(collection, cle, n=1):
    if n:
        _rapport.setdefault(collection, {}).setdefault(cle, 0)
        _rapport[collection][cle] += int(n)


def _nombre(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def corriger(df, collection_name):
    """Corrige les champs incohérents d'un DataFrame d'annonces (avant les filtres)."""
    seg = segment_de(collection_name)
    if df.empty or seg is None:
        return df
    df = df.copy()

    if "nb_chambres" in df.columns or "titre" in df.columns:
        if "nb_chambres" not in df.columns:
            df["nb_chambres"] = None
        titres = df["titre"] if "titre" in df.columns else pd.Series([None] * len(df), index=df.index)
        surfaces = df["surface"] if "surface" in df.columns else pd.Series([None] * len(df), index=df.index)
        completees = corrigees = 0
        valeurs = []
        for nb, titre, surface in zip(df["nb_chambres"], titres, surfaces):
            nb, surface = _nombre(nb), _nombre(surface)
            depuis_titre = chambres_depuis_titre(titre)
            aberrant = nb is not None and (nb > CHAMBRES_MAX or (surface and nb >= 1 and surface / nb < M2_MIN_PAR_CHAMBRE))
            if aberrant:
                corrigees += 1
                nb = depuis_titre
            elif nb is None and depuis_titre is not None:
                completees += 1
                nb = depuis_titre
            valeurs.append(nb)
        df["nb_chambres"] = valeurs
        compter(collection_name, "chambres_aberrantes_corrigees", corrigees)
        compter(collection_name, "chambres_completees_depuis_titre", completees)

    if "nb_pieces" in df.columns:
        pieces = pd.to_numeric(df["nb_pieces"], errors="coerce")
        aberrants = pieces > CHAMBRES_MAX + 5
        compter(collection_name, "pieces_aberrantes_videes", aberrants.sum())
        df.loc[aberrants, "nb_pieces"] = None

    if seg in PRIX_M2_BORNES and {"prix", "surface"} <= set(df.columns):
        lo, hi = PRIX_M2_BORNES[seg]
        prix = pd.to_numeric(df["prix"], errors="coerce")
        surface = pd.to_numeric(df["surface"], errors="coerce")
        prix_m2 = prix / surface
        incoherent = surface.notna() & (surface > 0) & ((prix_m2 < lo) | (prix_m2 > hi))
        compter(collection_name, "surfaces_incoherentes_videes", incoherent.sum())
        df.loc[incoherent, "surface"] = None
    return df


def cle_bien(doc):
    """Clé d'identité d'un bien : même prix, surface, ville et nombre de chambres.
    Un même bien est souvent publié sur Tayara et Mubawab avec des titres différents."""
    prix, surface = _nombre(doc.get("prix")), _nombre(doc.get("surface"))
    ville = norm(doc.get("ville"))
    if not (prix and surface and ville):
        return None
    chambres = _nombre(doc.get("nb_chambres"))
    return (round(prix), round(surface), ville, int(chambres) if chambres is not None else -1)


def richesse(doc):
    """Annonce la plus complète d'un groupe de doublons (gardée)."""
    remplis = sum(1 for v in doc.values() if v not in (None, "", [], {}) and not (isinstance(v, float) and np.isnan(v)))
    return remplis + min(len(str(doc.get("description") or "")), 2000) / 1000


def reinitialiser():
    _rapport.clear()


def rapport():
    return {k: dict(v) for k, v in _rapport.items()}


def sauvegarder_rapport(db, volumes):
    """Enregistre le rapport du passage avec les volumes brut/propre par collection."""
    document = {
        "date": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "collections": {
            # compteurs du nettoyage (raw_*) et de la déduplication (clean_*)
            nom: {**volumes.get(nom, {}), **_rapport.get(nom.replace("clean_", "raw_"), {}), **_rapport.get(nom, {})}
            for nom in ["clean_vente", "clean_location", "clean_estival"]
        },
    }
    db["qualite_rapports"].insert_one(document)
    return document
