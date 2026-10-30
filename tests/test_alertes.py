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


class TestRechercheEtTri:
    def test_tri_prix_croissant_puis_decroissant(self, client):
        asc = client.get("/api/alertes/nouvelles", params={"jours": 90, "tri": "prix", "ordre": "asc", "limit": 20}).json()["data"]
        desc = client.get("/api/alertes/nouvelles", params={"jours": 90, "tri": "prix", "ordre": "desc", "limit": 20}).json()["data"]
        prix_asc = [d["prix"] for d in asc if d.get("prix")]
        prix_desc = [d["prix"] for d in desc if d.get("prix")]
        assert prix_asc == sorted(prix_asc) and prix_desc == sorted(prix_desc, reverse=True)
        assert prix_asc[0] < prix_desc[0]

    def test_valeurs_manquantes_en_fin_de_liste(self, client):
        for ordre in ("asc", "desc"):
            data = client.get("/api/alertes/nouvelles", params={"jours": 90, "tri": "surface", "ordre": ordre, "limit": 200}).json()["data"]
            surfaces = [d.get("surface") for d in data]
            premiers_vides = next((i for i, s in enumerate(surfaces) if s is None), len(surfaces))
            assert all(s is None for s in surfaces[premiers_vides:])

    def test_recherche_tous_les_mots(self, client):
        j = client.get("/api/alertes/nouvelles", params={"jours": 90, "q": "villa marsa", "limit": 50}).json()
        assert j["count"] >= 1
        for d in j["data"]:
            texte = " ".join(str(d.get(k) or "") for k in ("titre", "ville", "gouvernorat")).lower()
            assert "villa" in texte or "marsa" in texte

    def test_recherche_sans_resultat_et_caracteres_speciaux(self, client):
        assert client.get("/api/alertes/nouvelles", params={"jours": 90, "q": "zzzqqq"}).json()["count"] == 0
        assert client.get("/api/alertes/nouvelles", params={"jours": 90, "q": ".*(["}).status_code == 200

    def test_tri_invalide(self, client):
        assert client.get("/api/alertes/nouvelles", params={"tri": "titre"}).status_code == 422


class TestStatsMarche:
    def test_structure(self, client):
        j = client.get("/api/stats/marche").json()
        for cle in ["kpis", "vente_prix_m2_par_gouvernorat", "vente_histogramme_prix_m2", "location_loyer_par_ville",
                    "prix_par_chambres", "estival_par_type", "types", "rendement_par_ville", "activite_quotidienne"]:
            assert cle in j
        assert len(j["activite_quotidienne"]) == 60

    def test_gouvernorats_officiels_uniquement(self, client):
        from api.routers.stats import GOUVERNORATS
        for z in client.get("/api/stats/marche").json()["vente_prix_m2_par_gouvernorat"]:
            assert z["cle"].lower() in GOUVERNORATS and z["n"] >= 8

    def test_rendement_coherent(self, client):
        for r in client.get("/api/stats/marche").json()["rendement_par_ville"]:
            assert r["rendement_brut_pct"] == round(r["loyer_median"] * 12 / r["prix_median"] * 100, 1)
            assert r["n_vente"] >= 5 and r["n_location"] >= 5
