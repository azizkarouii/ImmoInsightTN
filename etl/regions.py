"""Rattachement des annonces aux grandes régions de Tunisie (Grand Tunis, Cap Bon, Sahel…).

Le champ « gouvernorat » des annonces contient souvent une ville ou un quartier (Mubawab ne
fournit pas le gouvernorat) : on passe par une table ville/quartier -> gouvernorat, puis
gouvernorat -> région.
"""

import re
import unicodedata

REGIONS = {
    "Grand Tunis": ["tunis", "ariana", "ben arous", "manouba"],
    "Cap Bon": ["nabeul"],
    "Sahel": ["sousse", "monastir", "mahdia"],
    "Sfax": ["sfax"],
    "Nord-Est": ["bizerte", "zaghouan"],
    "Nord-Ouest": ["beja", "jendouba", "le kef", "siliana"],
    "Centre-Ouest": ["kairouan", "kasserine", "sidi bouzid"],
    "Sud-Est": ["medenine", "gabes", "tataouine"],
    "Sud-Ouest": ["gafsa", "tozeur", "kebili"],
}
ORDRE_REGIONS = list(REGIONS)

GOUVERNORAT_REGION = {g: r for r, gouvs in REGIONS.items() for g in gouvs}

# Villes, délégations et quartiers rencontrés dans les annonces -> gouvernorat
VILLES = {
    "tunis": [
        "la marsa", "marsa", "carthage", "jardins de carthage", "gammarth", "sidi bou said", "le kram", "kram",
        "la goulette", "le bardo", "bardo", "lac 1", "lac 2", "berges du lac", "el menzah", "menzah", "el manar",
        "manar", "mutuelleville", "alain savary", "bab souika", "bellevue", "centre urbain nord", "lafayette",
        "cite el khadra", "cite olympique", "el omrane", "el omrane superieur", "el ouardia", "ettahrir",
        "ezzouhour", "monfleury", "sidi hassine", "hrairia", "belvedere", "ain zaghouan", "ain zaghouen",
        "l aouina", "aouina", "medina", "khaznadar",
    ],
    "ariana": [
        "la soukra", "soukra", "route soukra", "route sokra", "raoued", "mnihla", "ettadhamen", "ghazela",
        "borj louzir", "chotrana", "riadh andalous", "ennasr", "cite ennasr", "kalaat andalous", "sidi thabet",
        "jardins el menzah", "dar fadhal", "ariana essoughra",
    ],
    "ben arous": [
        "el mourouj", "mourouj", "hammam lif", "hammam chott", "megrine", "rades", "ezzahra", "borj cedria",
        "bou mhel", "bou mhel bassatine", "boumhel", "nouvelle medina", "medina jedida", "fouchana", "mohamedia",
        "mornag",
    ],
    "manouba": ["la manouba", "denden", "douar hicher", "oued ellil", "jedaida", "djedeida", "ksar said"],
    "nabeul": [
        "hammamet", "yasmine hammamet", "mrezga", "kelibia", "klibia", "korba", "el haouaria", "haouaria",
        "beni khiar", "dar chaabane", "el maamoura", "maamoura", "menzel temime", "soliman", "hammam el ghezaz",
        "hammam ghezeze", "barraket essahel", "sidi daoud", "grombalia", "takelsa",
    ],
    "sousse": [
        "hammam sousse", "port el kantaoui", "kantaoui", "akouda", "chott meriem", "chatt mariem", "hergla",
        "sahloul", "kalaa kebira", "kalaa sghira", "zaouit ksibat thrayett", "m saken", "msaken", "khzema",
        "enfidha", "jawhara", "jaouhara",
    ],
    "monastir": ["ksar hellal", "zeramdine", "teboulba", "skanes", "jemmal", "moknine", "sahline"],
    "mahdia": ["ksour essef", "chebba", "salakta"],
    "sfax": [
        "kerkennah", "mahres", "sakiet eddaier", "sakiet ezzit", "el ain", "menzel chaker", "route gremda",
        "route el afrane", "route el ain", "route menzel chaker", "route manzel chaker", "route saltania",
        "route taniour", "route de l aeroport", "route mehdia", "thyna",
    ],
    "bizerte": ["ras jebel", "tinja", "ghar el melh", "menzel bourguiba", "el alia", "menzel jemil", "metline"],
    "jendouba": ["tabarka", "ain draham"],
    "medenine": ["mdenine", "djerba", "houmt souk", "midoun", "zarzis", "ajim"],
    "kebili": ["douz"],
}
VILLE_GOUVERNORAT = {v: g for g, villes in VILLES.items() for v in villes}
VILLE_GOUVERNORAT.update({g: g for g in GOUVERNORAT_REGION})
VILLE_GOUVERNORAT.update({"kef": "le kef", "la manouba": "manouba"})

# Mots entiers, les noms les plus longs d'abord : « ain zaghouan » (Tunis) avant « zaghouan »,
# « hammam sousse » avant « sousse »
_MOTIF = re.compile(r"\b(" + "|".join(re.escape(v) for v in sorted(VILLE_GOUVERNORAT, key=len, reverse=True)) + r")\b")


def normaliser(texte):
    if not isinstance(texte, str):
        return ""
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[-'’_/]", " ", t).split())


def gouvernorat_de(nom):
    """Gouvernorat (minuscules, sans accents) d'un nom de ville, quartier ou gouvernorat, sinon None."""
    t = normaliser(nom)
    if not t:
        return None
    if t in VILLE_GOUVERNORAT:
        return VILLE_GOUVERNORAT[t]
    m = _MOTIF.search(t)
    return VILLE_GOUVERNORAT[m.group(1)] if m else None


def region_de(doc):
    """Région d'une annonce : champ gouvernorat d'abord (plus fiable), puis ville."""
    for champ in ("gouvernorat", "ville"):
        g = gouvernorat_de(doc.get(champ))
        if g:
            return GOUVERNORAT_REGION[g]
    return None
