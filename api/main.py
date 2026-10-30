from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import annonces, estimation, fiabilite, stats, alerte, roi, chat

app = FastAPI(
    title="ImmoInsight TN API",
    description="API de prediction immobiliere pour la Tunisie",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(annonces.router, prefix="/api/annonces", tags=["Annonces"])
app.include_router(estimation.router, prefix="/api", tags=["Estimation"])
app.include_router(fiabilite.router, prefix="/api/fiabilite", tags=["Fiabilite"])
app.include_router(stats.router, prefix="/api", tags=["Stats"])
app.include_router(alerte.router, prefix="/api/alertes", tags=["Alertes"])
app.include_router(roi.router, prefix="/api", tags=["ROI"])
app.include_router(chat.router, prefix="/api/chat", tags=["Assistant"])


@app.get("/")
def root():
    return {"message": "ImmoInsight TN API", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}