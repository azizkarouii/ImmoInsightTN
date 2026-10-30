"""Accès au LLM — seul module dépendant du fournisseur (Groq).

Pour changer de fournisseur (Mistral, Anthropic...), il suffit de réimplémenter
`ClientLLM.completer` : le reste du chatbot ne manipule que `ReponseLLM`.
"""
import os
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

# Chaque modèle Groq a son propre quota (offre gratuite : ~8 000 tokens/min et
# 1 000 requêtes/jour par modèle) : quand le premier est saturé, on bascule sur le
# suivant au lieu d'attendre (les tentatives automatiques du SDK ajoutaient 15 s).
MODELES_PAR_DEFAUT = "openai/gpt-oss-120b,qwen/qwen3.8-27b"


class LLMIndisponible(RuntimeError):
    """Clé absente, quota dépassé ou service injoignable."""

    def __init__(self, message, quota=False):
        super().__init__(message)
        self.quota = quota


@dataclass
class AppelOutil:
    id: str
    nom: str
    arguments: str  # JSON brut, validé par api.chat.tools.executer


@dataclass
class ReponseLLM:
    texte: str
    appels: list = field(default_factory=list)
    tokens_entree: int = 0
    tokens_sortie: int = 0
    modele: str = ""


class ClientLLM:
    def __init__(self, modeles=None):
        from groq import Groq

        if not os.getenv("GROQ_API_KEY"):
            raise LLMIndisponible("GROQ_API_KEY absente du fichier .env")
        self.modeles = modeles or [m.strip() for m in os.getenv("GROQ_MODELS", MODELES_PAR_DEFAUT).split(",") if m.strip()]
        self.modele = self.modeles[0]
        self._client = Groq(timeout=30, max_retries=0)
        self._satures = {}  # modèle -> instant jusqu'auquel l'éviter

    def completer(self, messages, outils=None):
        import groq

        params = {
            "messages": messages,
            # Réponses factuelles : peu de variabilité
            "temperature": 0.2,
            "max_completion_tokens": 1500,
        }
        if outils:
            params.update(tools=outils, tool_choice="auto")

        maintenant = time.time()
        candidats = [m for m in self.modeles if self._satures.get(m, 0) <= maintenant] or self.modeles
        derniere_erreur = None
        for modele in candidats:
            for tentative in range(2):
                try:
                    r = self._client.chat.completions.create(model=modele, **params)
                except groq.RateLimitError as e:
                    self._satures[modele] = time.time() + 60
                    derniere_erreur = LLMIndisponible("Quota du fournisseur atteint", quota=True)
                    break  # modèle suivant
                except (groq.InternalServerError, groq.APIConnectionError, groq.APITimeoutError) as e:
                    derniere_erreur = LLMIndisponible("Fournisseur injoignable")
                    if tentative == 0:
                        time.sleep(1)
                        continue
                    break
                except groq.APIStatusError as e:
                    # 400 "tool_use_failed" : le modèle a produit un appel d'outil mal formé ;
                    # on laisse sa chance au modèle suivant
                    if e.status_code == 400 and "tool_use_failed" in str(e):
                        derniere_erreur = LLMIndisponible("Appel d'outil mal formé par le modèle")
                        break
                    raise LLMIndisponible(f"Erreur du fournisseur ({e.status_code})") from e

                self.modele = modele
                message = r.choices[0].message
                return ReponseLLM(
                    texte=message.content or "",
                    appels=[AppelOutil(tc.id, tc.function.name, tc.function.arguments or "{}") for tc in (message.tool_calls or [])],
                    tokens_entree=getattr(r.usage, "prompt_tokens", 0) or 0,
                    tokens_sortie=getattr(r.usage, "completion_tokens", 0) or 0,
                    modele=modele,
                )
        raise derniere_erreur or LLMIndisponible("Aucun modèle disponible")


_client_partage = None


def obtenir_client():
    """Client partagé entre les requêtes (mémorise les modèles saturés)."""
    global _client_partage
    if _client_partage is None:
        _client_partage = ClientLLM()
    return _client_partage
