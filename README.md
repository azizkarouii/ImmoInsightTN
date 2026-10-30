# ImmoInsight TN

Analyse du marché immobilier tunisien (vente, location classique, location estivale) : collecte
automatique des annonces, pipeline ETL, modèles de prix, alertes et tableau de bord web.

```
Scrapers (Tayara, Mubawab, Booking) ──► MongoDB raw_* ──► ETL ──► MongoDB clean_*
        ▲ scheduler                                              │
        └──────────── vérification des retraits                  ▼
                                    Modèles M1–M4, opportunités ──► API FastAPI ──► Angular
```

## Prérequis

- Python 3.13 (paquets de `requirements.txt`) et `playwright install chromium` (Booking)
- MongoDB 7+ en local (`mongodb://localhost:27017`, base `immoinsight`)
- Node.js 18+ pour le frontend

```bash
py -3.13 -m pip install -r requirements.txt
py -3.13 -m playwright install chromium
cd frontend && npm install
```

Configuration : copier `.env.example` en `.env` (`MONGO_URI`, `MONGO_DB`, `GROQ_API_KEY` pour l'assistant).

## Lancer l'application

```bash
py -3.13 -m uvicorn api.main:app --port 8000      # API  → http://localhost:8000/docs
cd frontend && npx ng serve                         # UI   → http://localhost:4200
```

## Collecte automatique

```bash
py -3.13 -m scrapers.main --scheduler   # à laisser tourner (processus longue durée)
py -3.13 -m scrapers.main planning      # planning + dernières exécutions
py -3.13 -m scrapers.main job etl       # lancer un job maintenant (journalisé)
```

| Tâche | Fréquence (Africa/Tunis) |
|---|---|
| Tayara — nouvelles annonces (s'arrête aux annonces déjà connues) | tous les jours 02:00 |
| Tayara — passage complet (détecte les changements de prix) | dimanche 01:00 |
| Mubawab — 3 pages par catégorie (le site limite le débit) | lundi et jeudi 03:00 |
| Booking — appartements, maisons, villas de 24 villes | mardi et vendredi 04:00 |
| Vérification des retraits (re-visite des annonces non revues depuis 14 j) | tous les jours 06:00 |
| Pipeline ETL (+ fiabilité M4, opportunités) | tous les jours 06:45 |
| Ré-entraînement M1 / M2 / M3 | dimanche 09:00 |
| Rapport d'alertes | tous les jours 09:30 |

Chaque tâche s'exécute dans un sous-processus avec un délai maximal, est journalisée dans la
collection `scheduler_logs` (visible dans l'onglet Alertes), et une tâche manquée pendant que la
machine était éteinte est rattrapée dans les 6 h.

## Commandes utiles

```bash
py -3.13 -m scrapers.main                 # liste des commandes de collecte
py -3.13 -m etl.pipeline                  # nettoyage → dédup → géocodage → features → M4 → opportunités
py -3.13 -m models.train_all              # ré-entraîner M1, M2, M3
py -3.13 -m pytest tests                  # tests (les tests API nécessitent MongoDB)
```

## Assistant (chatbot)

Widget flottant présent sur toutes les pages : répond en français (ou dans la langue de la question) **uniquement à
partir des données de la plateforme** — statistiques de prix, recherche d'annonces, estimations M1/M2/M3, rentabilité,
alertes, état de la collecte. Le LLM (Groq) appelle des outils en lecture seule ; il n'écrit jamais de requête.

```bash
cp .env.example .env          # puis renseigner GROQ_API_KEY
py -3.13 scripts/eval_chatbot.py   # évaluation sur 14 questions types (utilise le quota Groq)
```

Limites : 20 questions / 10 min par visiteur ; offre gratuite Groq ≈ 8 000 tokens/min par modèle (bascule automatique
sur un second modèle, cache des questions simples). Détails : `immoinsight_roadmap.md`, section 17.16.

## Modèles

| Modèle | Rôle | Erreur médiane (validation croisée) |
|---|---|---|
| M1 | Prix de vente (XGBoost + LightGBM, monotone en surface) | ~21 % |
| M2 | Loyer mensuel (LightGBM, zones encodées) | ~22 % |
| M3 | Prix par nuit estival (LightGBM sur les caractéristiques du logement) | ~29 % |
| M4 | Score de fiabilité des annonces (Isolation Forest) | — |

Un modèle n'est adopté que s'il bat sa référence naïve ; sinon l'API se replie sur des
références par zone. Détails et historique des choix : `immoinsight_roadmap.md`, section 17.
