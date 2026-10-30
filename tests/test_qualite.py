"""Qualité des données : corrections, doublons, limitation de débit des scrapers."""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from etl import qualite


@pytest.fixture(autouse=True)
def rapport_vide():
    qualite.reinitialiser()
    yield
    qualite.reinitialiser()


class TestChambresDepuisTitre:
    @pytest.mark.parametrize("titre,attendu", [
        ("Appartement S+2 à La Marsa", 2), ("s + 3 vue mer", 3), ("Coquet S2 à Kantaoui", 2),
        ("Villa S+4 avec piscine", 4), ("Appartement haut standing", None), ("Bloc A, lot 25", None), (None, None),
    ])
    def test_extraction(self, titre, attendu):
        assert qualite.chambres_depuis_titre(titre) == attendu


class TestCorrections:
    def test_chambres_aberrantes(self):
        df = pd.DataFrame([
            {"titre": "Coquet S2 à Kantaoui", "nb_chambres": 20, "surface": 79, "prix": 250000},   # titre
            {"titre": "Villa à Hammamet", "nb_chambres": 240, "surface": 240, "prix": 900000},     # vidé
            {"titre": "Studio meublé", "nb_chambres": 54, "surface": 30, "prix": 800},
            {"titre": "Appartement S+3", "nb_chambres": None, "surface": 120, "prix": 300000},     # complété
            {"titre": "Appartement", "nb_chambres": 3, "surface": 110, "prix": 300000},            # inchangé
        ])
        out = qualite.corriger(df, "raw_vente")
        chambres = out["nb_chambres"].tolist()
        assert chambres[0] == 2 and pd.isna(chambres[1]) and pd.isna(chambres[2])
        assert chambres[3:] == [3, 3]
        r = qualite.rapport()["raw_vente"]
        assert r["chambres_aberrantes_corrigees"] == 3 and r["chambres_completees_depuis_titre"] == 1

    def test_surface_incoherente_videe_prix_garde(self):
        df = pd.DataFrame([
            {"titre": "S+1", "prix": 195000, "surface": 1000},   # 195 TND/m² : surface fausse
            {"titre": "S+2", "prix": 300000, "surface": 100},    # 3 000 TND/m² : ok
        ])
        out = qualite.corriger(df, "raw_vente")
        assert pd.isna(out["surface"].iloc[0]) and out["prix"].iloc[0] == 195000
        assert out["surface"].iloc[1] == 100
        assert qualite.rapport()["raw_vente"]["surfaces_incoherentes_videes"] == 1

    def test_estival_sans_controle_prix_m2(self):
        df = pd.DataFrame([{"titre": "Villa", "prix": 2000, "surface": 300, "nb_chambres": 4}])
        assert qualite.corriger(df, "raw_estival")["surface"].iloc[0] == 300


class TestDoublons:
    def test_cle_bien(self):
        a = {"prix": 350000, "surface": 120.0, "ville": "La Marsa", "nb_chambres": 3}
        b = {"prix": 350000.0, "surface": 120, "ville": "la marsa", "nb_chambres": 3.0}
        assert qualite.cle_bien(a) == qualite.cle_bien(b)
        assert qualite.cle_bien({"prix": 350000, "ville": "La Marsa"}) is None  # sans surface : pas de clé

    def test_meme_bien_deux_sources(self):
        from etl.deduplicator import _par_cle_bien

        docs = [
            {"_id": 1, "source": "tayara", "url": "t/1", "prix": 350000, "surface": 120, "ville": "La Marsa", "nb_chambres": 3},
            {"_id": 2, "source": "mubawab", "url": "m/1", "prix": 350000, "surface": 120, "ville": "La Marsa",
             "nb_chambres": 3, "description": "Bel appartement lumineux " * 10, "equipements": ["parking"]},
            {"_id": 3, "source": "tayara", "url": "t/2", "prix": 350000, "surface": 140, "ville": "La Marsa", "nb_chambres": 3},
        ]
        gardes, retires, fusions = _par_cle_bien(docs)
        assert retires == [1]                                   # la plus complète (mubawab) est gardée
        assert {d["_id"] for d in gardes} == {2, 3}
        maj = fusions[0]._doc["$set"]
        assert maj["sources"] == ["mubawab", "tayara"] and maj["doublons"][0]["url"] == "t/1"

    def test_texte_court_non_deduplique(self):
        from etl.deduplicator import _par_texte

        docs = [{"_id": i, "titre": "Appartement 1 Chambre", "description": "", "prix": 150} for i in range(3)]
        assert _par_texte(docs, 0.85) == []


class TestPauseSurLimite:
    def _middleware(self):
        from scrapers.middlewares import PauseSurLimiteMiddleware
        crawler = MagicMock()
        mw = PauseSurLimiteMiddleware(crawler)
        mw._pause = MagicMock()
        return mw

    def _reponse(self, status, headers=None):
        r = MagicMock(status=status)
        r.headers = headers or {}
        return r

    def test_429_pause_et_nouvelle_tentative(self):
        from scrapy import Request

        mw = self._middleware()
        req = Request("https://www.mubawab.tn/fr/a/1")
        out = mw.process_response(req, self._reponse(429))
        assert isinstance(out, Request) and out.meta["tentatives_limite"] == 1 and out.dont_filter
        mw._pause.assert_called_once_with(30)
        out2 = mw.process_response(out, self._reponse(429))
        mw._pause.assert_called_with(60)  # attente exponentielle
        assert out2.meta["tentatives_limite"] == 2

    def test_retry_after_respecte(self):
        from scrapy import Request

        mw = self._middleware()
        mw.process_response(Request("https://x.tn/a"), self._reponse(429, {"Retry-After": b"120"}))
        mw._pause.assert_called_once_with(120)

    def test_abandon_apres_tentatives_max(self):
        from scrapy import Request

        mw = self._middleware()
        req = Request("https://x.tn/a", meta={"tentatives_limite": mw.TENTATIVES_MAX})
        reponse = self._reponse(429)
        assert mw.process_response(req, reponse) is reponse
        assert mw.stats["abandons"] == 1

    def test_succes_reinitialise_le_backoff(self):
        from scrapy import Request

        mw = self._middleware()
        mw.process_response(Request("https://x.tn/a"), self._reponse(429))
        mw.process_response(Request("https://x.tn/b"), self._reponse(200))
        assert mw.limites_consecutives == 0


def test_adresse_booking():
    from scrapers.booking_scraper import parse_booking_card

    r = parse_booking_card({"address": "Yasmine Hammamet\nIndiquer sur la carte", "card": ""})
    assert r["adresse_brute"] == "Yasmine Hammamet"
