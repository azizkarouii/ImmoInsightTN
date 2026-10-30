import hashlib
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()
db = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))[os.getenv("MONGO_DB", "immoinsight")]

# Ouvert à tous les visiteurs : limite par adresse IP pour protéger le quota du fournisseur
LIMITE_REQUETES = int(os.getenv("CHAT_LIMITE_REQUETES", "20"))
FENETRE_S = int(os.getenv("CHAT_FENETRE_S", "600"))
_requetes = defaultdict(deque)
_verrou = threading.Lock()

# Questions sans historique (ex. suggestions cliquées) : réponse réutilisée 15 min,
# pour économiser le quota du fournisseur (offre gratuite limitée par minute)
CACHE_TTL_S = 900
CACHE_MAX = 200
_cache = {}

SUGGESTIONS = [
    "Quel est le loyer médian d'un S+2 à La Marsa ?",
    "Combien vaut un appartement de 120 m² à Ennasr ?",
    "Quelles villes sont les moins chères à l'achat ?",
    "Prix d'une villa à Djerba en été pour 3 chambres ?",
    "Quelles opportunités à la vente cette semaine ?",
    "Quand les données ont-elles été mises à jour ?",
]


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=2000)


class DemandeChat(BaseModel):
    messages: list[Message] = Field(..., min_length=1, max_length=30)


# Derrière le reverse proxy nginx (Docker), toutes les requêtes viennent de l'IP du proxy :
# l'IP du visiteur est lue dans X-Real-IP, seulement si TRUST_PROXY=1 (sinon un client
# appelant l'API directement pourrait falsifier l'en-tête pour contourner la limite)
TRUST_PROXY = os.getenv("TRUST_PROXY", "0") == "1"


def _client_id(request: Request):
    ip = request.client.host if request.client else "inconnu"
    if TRUST_PROXY:
        ip = request.headers.get("x-real-ip") or ip
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _verifier_quota(client_id):
    maintenant = time.time()
    with _verrou:
        file = _requetes[client_id]
        while file and maintenant - file[0] > FENETRE_S:
            file.popleft()
        if len(file) >= LIMITE_REQUETES:
            attente = int(FENETRE_S - (maintenant - file[0])) + 1
            raise HTTPException(429, detail=f"Trop de questions en peu de temps. Réessayez dans {max(1, attente // 60)} min.",
                                headers={"Retry-After": str(attente)})
        file.append(maintenant)


def _cle_cache(messages):
    if len(messages) != 1:
        return None
    return " ".join(messages[0].content.lower().split()).rstrip(" ?!.")


def _depuis_cache(cle):
    entree = _cache.get(cle) if cle else None
    if entree and time.time() - entree[0] < CACHE_TTL_S:
        return entree[1]
    return None


def _mettre_en_cache(cle, reponse):
    if not cle:
        return
    if len(_cache) >= CACHE_MAX:
        _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
    _cache[cle] = (time.time(), reponse)


def _journaliser(client_id, question, resultat=None, erreur=None):
    """Journal des échanges (sans adresse IP en clair) pour suivre qualité et consommation."""
    try:
        db["chat_logs"].insert_one({
            "date": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "client": client_id,
            "question": question[:500],
            "reponse": (resultat or {}).get("reponse", "")[:2000],
            "outils": (resultat or {}).get("outils", []),
            "modele": (resultat or {}).get("modele"),
            "tokens": (resultat or {}).get("tokens"),
            "duree_ms": (resultat or {}).get("duree_ms"),
            "erreur": erreur,
            "cache": bool((resultat or {}).get("cache")),
        })
    except Exception:
        pass  # la journalisation ne doit jamais faire échouer la réponse


@router.post("")
def chat(demande: DemandeChat, request: Request):
    from api.chat.agent import repondre
    from api.chat.llm import LLMIndisponible

    if demande.messages[-1].role != "user":
        raise HTTPException(422, detail="Le dernier message doit être une question de l'utilisateur.")
    client_id = _client_id(request)
    _verifier_quota(client_id)
    question = demande.messages[-1].content
    cle = _cle_cache(demande.messages)
    en_cache = _depuis_cache(cle)
    if en_cache:
        _journaliser(client_id, question, {**en_cache, "cache": True})
        return en_cache
    try:
        resultat = repondre([m.model_dump() for m in demande.messages])
    except LLMIndisponible as e:
        _journaliser(client_id, question, erreur=str(e))
        if e.quota:
            raise HTTPException(429, detail="L'assistant est très sollicité, réessayez dans quelques instants.")
        raise HTTPException(503, detail="L'assistant est momentanément indisponible.")
    _journaliser(client_id, question, resultat)
    reponse = {k: resultat[k] for k in ["reponse", "sources"]}
    # Pas de mise en cache d'une réponse produite après une erreur d'outil
    if not any(o.get("erreur") for o in resultat["outils"]):
        _mettre_en_cache(cle, reponse)
    return reponse


@router.get("/suggestions")
def suggestions():
    return {"suggestions": SUGGESTIONS}
