# Image backend commune : API FastAPI et scheduler de collecte (scrapers, ETL, modèles)
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Africa/Tunis

# libgomp1 : requis par LightGBM / XGBoost
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgomp1 tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Versions verrouillées, wheels uniquement : aucun script setup.py exécuté à l'installation
COPY requirements.lock .
RUN pip install --only-binary :all: -r requirements.lock \
    # Chromium pour le scraper Booking (Playwright)
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Uniquement le code exécuté (modèles entraînés et data/ sont montés en volume)
COPY api ./api
COPY etl ./etl
COPY models ./models
COPY scrapers ./scrapers

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
