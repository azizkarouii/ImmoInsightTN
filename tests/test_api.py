"""Tests de l'API FastAPI — nécessitent MongoDB local (skippés sinon)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

pytestmark = pytest.mark.mongo


class TestRoot:
    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["message"] == "ImmoInsight TN API"

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestAnnonces:
    def test_liste(self, client):
        r = client.get("/api/annonces/", params={"collection": "clean_vente", "limit": 5})
        assert r.status_code == 200
        data = r.json()
        assert "data" in data
        assert len(data["data"]) <= 5

    def test_sanitize_map_points_filters_without_moving_points(self):
        from api.routers.annonces import sanitize_map_points

        docs = [
            {"lat": 36.8, "lon": 10.18},
            {"lat": 36.8, "lon": 10.18},
            {"lat": "35.8", "lon": "10.6"},
            {"lat": None, "lon": 10.0},
            {"lat": float("nan"), "lon": 10.0},
            {"lat": 45.0, "lon": 2.0},
        ]

        cleaned = sanitize_map_points(docs)

        assert [(d["lat"], d["lon"]) for d in cleaned] == [(36.8, 10.18), (36.8, 10.18), (35.8, 10.6)]

    def test_fix_url_removes_doubled_booking_prefix(self):
        from api.routers.annonces import fix_url

        assert fix_url("https://www.booking.comhttps://www.booking.com/hotel/tn/x.html") ==             "https://www.booking.com/hotel/tn/x.html"
        assert fix_url("https://www.tayara.tn/item/a?next=https://x.tn") == "https://www.tayara.tn/item/a?next=https://x.tn"

    def test_carte(self, client):
        r = client.get("/api/annonces/carte", params={"collection": "clean_vente"})
        assert r.status_code == 200
        for item in r.json()["data"]:
            assert "lat" in item and "lon" in item

    def test_recentes(self, client):
        r = client.get("/api/annonces/recentes")
        assert r.status_code == 200


class TestStats:
    def test_globales(self, client):
        r = client.get("/api/stats")
        assert r.status_code == 200
        j = r.json()
        assert "collections" in j
        assert "total_annonces" in j

    def test_par_gouvernorat(self, client):
        r = client.get("/api/stats/prix_par_gouvernorat", params={"collection": "clean_vente"})
        assert r.status_code == 200
        for item in r.json()["data"]:
            assert "prix_moyen" in item

    def test_par_ville(self, client):
        r = client.get("/api/stats/prix_par_ville", params={"collection": "clean_estival"})
        assert r.status_code == 200


class TestEstimation:
    def test_location(self, client):
        r = client.get(
            "/api/location/estimation",
            params={"surface": 90, "ville": "La Marsa"},
        )
        assert r.status_code == 200
        j = r.json()
        assert j["statut"] == "succes"
        assert "loyer_estime" in j
        assert "prix_m2_reference" in j
        assert j["intervalle_bas"] <= j["loyer_estime"] <= j["intervalle_haut"]

    def test_location_sans_surface(self, client):
        r = client.get(
            "/api/location/estimation",
            params={"nb_pieces": 3, "ville": "Tunis"},
        )
        assert r.status_code == 200
        j = r.json()
        assert j["statut"] == "succes"
        assert j["loyer_estime"] > 0


    def test_location_surface_invalide(self, client):
        r = client.get("/api/location/estimation", params={"surface": -10, "ville": "Tunis"})
        assert r.status_code == 422

    def test_location_ville_inconnue_pas_plus_chere_que_la_marsa(self, client):
        inconnue = client.get("/api/location/estimation", params={"surface": 90, "ville": "Kasserine"}).json()
        marsa = client.get("/api/location/estimation", params={"surface": 90, "ville": "La Marsa"}).json()
        assert inconnue["loyer_estime"] < marsa["loyer_estime"]

    def test_vente_surface_invalide(self, client):
        assert client.get("/api/vente/estimation", params={"surface": 0}).status_code == 422

    def test_vente_prix_croissant_avec_surface(self, client):
        prix = [
            client.get("/api/vente/estimation", params={"surface": s, "gouvernorat": "Tunis"}).json()["prix_estime"]
            for s in [50, 100, 200, 400]
        ]
        assert prix == sorted(prix)
        assert all(p > 0 for p in prix)

    def test_vente_zone_utilisee(self, client):
        j = client.get("/api/vente/estimation", params={"surface": 100, "gouvernorat": "Sousse"}).json()
        assert j["zone_reconnue"] == "sousse"
        assert j["intervalle_bas"] < j["prix_estime"] < j["intervalle_haut"]

    def test_estival_par_ville(self, client):
        villes = client.get("/api/estival/villes").json()["villes"]
        assert "Hammamet" in villes
        prix = {v: client.get("/api/estival/estimation", params={"ville": v}).json()["prix_nuit_estime"] for v in villes}
        assert len(set(prix.values())) > 1  # la ville influence le prix
        assert all(30 < p < 2000 for p in prix.values())  # prix par nuit, pas par séjour

    def test_estival_ville_insensible_casse(self, client):
        a = client.get("/api/estival/estimation", params={"ville": "hammamet"}).json()
        b = client.get("/api/estival/estimation", params={"ville": "Hammamet"}).json()
        assert a["prix_nuit_estime"] == b["prix_nuit_estime"]

    def test_estival_ville_inconnue(self, client):
        r = client.get("/api/estival/estimation", params={"ville": "Kairouan"})
        assert r.status_code == 422
        assert "Hammamet" in r.json()["detail"]


    def test_location_loyer_croissant_avec_surface(self, client):
        loyers = [
            client.get("/api/location/estimation", params={"surface": s, "ville": "La Marsa", "nb_chambres": 2}).json()["loyer_estime"]
            for s in [50, 90, 150, 250]
        ]
        assert loyers == sorted(loyers)

    def test_location_type_invalide(self, client):
        assert client.get("/api/location/estimation", params={"surface": 90, "type_bien": "terrain"}).status_code == 422

    def test_estival_caracteristiques(self, client):
        base = {"ville": "Hammamet", "categorie": "appartement", "surface": 90, "nb_lits": 4}
        prix = [
            client.get("/api/estival/estimation", params={**base, "nb_chambres": n}).json()["prix_nuit_estime"]
            for n in [1, 2, 3]
        ]
        assert prix == sorted(prix)
        j = client.get("/api/estival/estimation", params={**base, "nb_chambres": 2}).json()
        assert j["intervalle_bas"] < j["prix_nuit_estime"] < j["intervalle_haut"]

    def test_estival_parametre_invalide(self, client):
        r = client.get("/api/estival/estimation", params={"ville": "Hammamet", "categorie": "chateau"})
        assert r.status_code == 422


class TestROI:
    def test_calculer(self, client):
        r = client.get("/api/roi/calculer", params={"prix": 300000, "loyer_mensuel": 1500})
        assert r.status_code == 200
        j = r.json()
        assert j["statut"] == "succes"
        assert "score_roi" in j

    def test_calculer_prix_invalide(self, client):
        r = client.get("/api/roi/calculer", params={"prix": -5})
        assert r.status_code == 422

    def test_top_zones(self, client):
        r = client.get("/api/roi/top_zones", params={"limit": 3})
        assert r.status_code == 200
        data = r.json()["data"]
        assert "data" in r.json()
        assert all(item.get("zone_label") for item in data)
        assert all(any(char.isalpha() for char in item["zone_label"]) for item in data)


class TestFiabilite:
    def test_liste(self, client):
        r = client.get("/api/fiabilite/")
        assert r.status_code == 200


class TestAlertes:
    def test_nouvelles(self, client):
        r = client.get("/api/alertes/nouvelles")
        assert r.status_code == 200

    def test_prix(self, client):
        r = client.get("/api/alertes/prix")
        assert r.status_code == 200
