"""Alertes, détection des retraits et scheduler."""
from unittest.mock import MagicMock

import pytest

from etl.cleaner import clean_price_history
from scrapers.change_detector import statut_en_ligne
from scrapers.scheduler import JOBS, planning


class TestVariationPrix:
    def test_dernier_changement_dans_la_periode(self):
        from api.routers.alerte import variation_prix

        history = [
            {"prix": 300000, "date": "2026-09-01T10:00:00"},
            {"prix": 300000, "date": "2026-10-01T10:00:00"},
            {"prix": 270000, "date": "2026-10-20T10:00:00"},
        ]
        assert variation_prix(history, "2026-10-15") == (300000, 270000, "2026-10-20T10:00:00")
        # Changement antérieur à la période : pas d'alerte
        assert variation_prix(history, "2026-10-25") is None

    def test_points_invalides_ignores(self):
        from api.routers.alerte import variation_prix

        history = [{"prix": None, "date": "2026-10-01"}, {"prix": 250000, "date": "2026-10-20"}]
        assert variation_prix(history, "2026-10-01") is None


class TestHistoriquePrix:
    def test_retire_prix_aberrants_et_repetitions(self):
        history = [
            {"prix": None, "date": "a"},
            {"prix": 320000, "date": "b"},
            {"prix": 320000, "date": "c"},
            {"prix": 320000000, "date": "d"},  # prix x1000 (erreur de scraping)
            {"prix": 300000, "date": "e"},
        ]
        assert clean_price_history(history, 10_000, 5_000_000) == [
            {"prix": 320000, "date": "b"}, {"prix": 300000, "date": "e"},
        ]

    def test_entree_invalide(self):
        assert clean_price_history("[{'prix': 1}]", 0, 10) == []


def _reponse(status, location=None, text=""):
    r = MagicMock(status_code=status, text=text)
    r.headers = {"Location": location} if location else {}
    return r


class TestStatutEnLigne:
    URL = "https://www.tayara.tn/item/appartements/tunis/tunis/s2/6a5bd6e24956ba003a43a04c/"

    @pytest.mark.parametrize("reponse,attendu", [
        (_reponse(404), "retiree"),
        (_reponse(410), "retiree"),
        (_reponse(302, "/ads/c/immobilier/appartements/"), "retiree"),
        (_reponse(301, "/item/appartements/tunis/tunis/s2/6a5bd6e24956ba003a43a04c/"), "en_ligne"),
        (_reponse(200, text='{"props":{"pageProps":{"adDetails":{"title":"S2"}}}}'), "en_ligne"),
        (_reponse(200, text="<html>page vide</html>"), "retiree"),
        (_reponse(429), "inconnu"),
        (_reponse(503), "inconnu"),
    ])
    def test_statuts(self, reponse, attendu):
        session = MagicMock()
        session.get.return_value = reponse
        assert statut_en_ligne(self.URL, session) == attendu


class TestScheduler:
    def test_jobs_valides(self):
        ids = [j["id"] for j in JOBS]
        assert len(ids) == len(set(ids))
        for job in JOBS:
            assert job["commande"][0] == "-m"
            assert job["timeout_min"] > 0

    def test_planning(self):
        db = MagicMock()
        db.__getitem__.return_value.find_one.return_value = None
        jobs = planning(db)
        assert len(jobs) == len(JOBS)
        assert all(j["prochaine_execution"] for j in jobs)
        assert all(j["derniere_execution"] is None for j in jobs)


class TestEndpointsAlertes:
    def test_resume(self, client):
        r = client.get("/api/alertes/resume", params={"jours": 7})
        assert r.status_code == 200
        j = r.json()
        assert set(j["collections"]) == {"clean_vente", "clean_location", "clean_estival"}
        assert set(j["collections"]["clean_vente"]) == {"nouvelles", "baisses_prix", "hausses_prix", "retirees", "opportunites"}
        assert isinstance(j["fiabilite_faible"], int)

    def test_nouvelles_triees_par_date(self, client):
        data = client.get("/api/alertes/nouvelles", params={"jours": 90, "limit": 20}).json()["data"]
        dates = [d["first_seen"] for d in data]
        assert dates == sorted(dates, reverse=True)

    def test_prix_variations_coherentes(self, client):
        for r in client.get("/api/alertes/prix", params={"jours": 90}).json()["data"]:
            assert r["ancien_prix"] != r["nouveau_prix"]
            attendu = round((r["nouveau_prix"] - r["ancien_prix"]) / r["ancien_prix"] * 100, 1)
            assert r["variation_pct"] == attendu

    def test_opportunites_sous_le_seuil(self, client):
        j = client.get("/api/alertes/opportunites").json()
        for r in j["data"]:
            assert r["ecart_estimation_pct"] <= j["seuil_pct"]

    def test_scheduler(self, client):
        jobs = client.get("/api/alertes/scheduler").json()["jobs"]
        assert {j["id"] for j in jobs} == {j["id"] for j in JOBS}

    def test_periode_invalide(self, client):
        assert client.get("/api/alertes/nouvelles", params={"jours": 0}).status_code == 422
