"""Tests unitaires des fonctions pures de l'ETL."""

import numpy as np
import pytest

from etl.cleaner import clean_prix, clean_surface, normalize_type_bien, is_rental_title, clean_titre
from etl.deduplicator import text_to_minhash
from etl.feature_engineer import haversine
from etl.geocoder import _infer_location_candidates, _names_known_city, build_geocode_queries, extract_title_place, extract_url_location
from models.roi_score.calculator import compute_roi, score_roi, label_roi


class TestCleanPrix:
    def test_simple(self):
        assert clean_prix("588 000 TND") == 588000

    def test_espaces_insécables(self):
        assert clean_prix("588\u00a0000 TND") == 588000

    def test_virgule_separateur(self):
        assert clean_prix("1,500") == 1500

    def test_suffixe_k(self):
        assert clean_prix("350k") == 350000

    def test_suffixe_m(self):
        assert clean_prix("1.2m") == 1200000

    def test_consulter(self):
        assert clean_prix("Prix à consulter") is None

    def test_none_et_nan(self):
        assert clean_prix(None) is None
        assert clean_prix(np.nan) is None

    def test_concatenation_simple(self):
        assert clean_prix("18419000") == 18419000


class TestCleanSurface:
    def test_simple(self):
        assert clean_surface("120 m²") == 120

    def test_none(self):
        assert clean_surface(None) is None

    def test_nan(self):
        assert clean_surface(np.nan) is None

    def test_decimal(self):
        assert clean_surface("70,24 m²") == pytest.approx(70.24)

    def test_decimal_avec_point(self):
        assert clean_surface("118.5 m²") == pytest.approx(118.5)


class TestNormalizeTypeBien:
    def test_nan_titre(self):
        assert normalize_type_bien(np.nan, "appartement") == "appartement"

    def test_none_titre(self):
        assert normalize_type_bien(None, None) == "appartement"

    def test_titre_vide(self):
        assert normalize_type_bien("", "villa") == "villa"

    def test_villa_detectee(self):
        assert normalize_type_bien("Superbe villa moderne", None) == "villa"

    def test_terrain_detecte(self):
        assert normalize_type_bien("Terrain 1000 m²", None) == "terrain"

    def test_bureau_detecte(self):
        assert normalize_type_bien("Bureau à louer", None) == "bureau"

    def test_appartement_par_defaut(self):
        assert normalize_type_bien("Bel S2 à Tunis", None) == "appartement"


class TestRentalFilter:
    def test_rental_titles(self):
        assert is_rental_title("A Louer étage De Villa Au Début De Corniche Bizerte")
        assert is_rental_title("Villa haut standing à Louer – Lac 2 – Longue Durée")
        assert not is_rental_title("Appartement à vendre à La Marsa")
        assert not is_rental_title(None)

    def test_tayara_suffix(self):
        assert clean_titre("Maison S+2 en vente | Tayara") == "Maison S+2 en vente"
        assert clean_titre(float("nan")) is None


class TestMinHash:
    def test_textes_similaires(self):
        m1 = text_to_minhash("Appartement S2 neuf à la Soukra Chotrana 3")
        m2 = text_to_minhash("Appartement S2 neuf à la Soukra Chotrana 3")
        assert m1.jaccard(m2) > 0.9

    def test_textes_differents(self):
        m1 = text_to_minhash("Villa avec piscine à Hammamet")
        m2 = text_to_minhash("Studio meublé centre ville Tunis")
        assert m1.jaccard(m2) < 0.3

    def test_chaine_courte(self):
        m = text_to_minhash("ab")  # < 3 caractères -> pas de shingles
        assert m is not None


class TestHaversine:
    def test_distance_connue(self):
        # Tunis (36.8065, 10.1815) -> Sfax (34.7406, 10.7603) ~ 235 km
        d = haversine(36.8065, 10.1815, 34.7406, 10.7603)
        assert 200 < d < 280

    def test_zero(self):
        assert haversine(36.8, 10.18, 36.8, 10.18) == pytest.approx(0, abs=1e-6)


class TestGeocoderCandidates:
    def test_description_contains_city(self):
        doc = {
            "titre": "Appartement en vente à Zone Touristique",
            "description": "Découvrez cet appartement ... idéalement située dans la Zone Touristique de Mahdia, à quelques minutes de la plage.",
            "gouvernorat": "",
            "ville": "",
        }
        candidates = _infer_location_candidates(doc)
        assert "Mahdia" in candidates

    def test_build_geocode_queries_prefers_precise_city_then_country(self):
        doc = {
            "adresse_brute": "",
            "gouvernorat": "Sousse",
            "ville": "",
            "description": "Appartement à vendre à Hammamet près de la plage",
            "titre": "Villa en bord de mer",
        }
        queries = build_geocode_queries(doc)
        assert queries[0].startswith("Hammamet")
        assert "Tunisie" in queries[0]
        assert any("Sousse" in q for q in queries)


    def test_nan_fields_never_become_queries(self):
        # "nan, Tunisie" était résolu par Photon en un bâtiment de Nabeul
        doc = {"ville": float("nan"), "gouvernorat": "nan", "quartier": None, "adresse_brute": "None", "titre": "Maison S+2"}
        queries = build_geocode_queries(doc)
        assert not any("nan" in q.lower() or "none" in q.lower() for q in queries)

    def test_no_country_level_fallback(self):
        assert build_geocode_queries({"titre": "Duplex de luxe avec Jardin et Piscine"}) == []

    def test_tayara_url_location(self):
        loc = extract_url_location("https://www.tayara.tn/item/maisons-et-villas/bizerte/bizerte-nord/une-maison/6a57")
        assert loc == {"gouvernorat": "Bizerte", "delegation": "Bizerte Nord"}

    def test_known_city_in_place_takes_precedence(self):
        # Gouvernorat Tayara "Tunis" mais titre "à Hammam Sousse" : le lieu cité d'abord
        assert _names_known_city("Hammam Sousse, Tunisie")
        assert not _names_known_city("Hammam Sousse, Tunis, Tunisie")
        assert not _names_known_city("Zone Touristique, Tunisie")
        doc = {"url": "https://www.tayara.tn/item/appartements/tunis/tunis/a-louer/1", "titre": "Etage de villa à Hammam Sousse"}
        assert build_geocode_queries(doc)[0] == "Hammam Sousse, Tunisie"

    def test_title_place(self):
        assert extract_title_place("Appartement en vente à La Manouba. Surface de 68 m²") == "La Manouba"
        assert extract_title_place("Superbe appartement à vendre à El Omrane Supérieur. Surface totale 107 m²") == "El Omrane Supérieur"
        assert extract_title_place("Appartement S1 à vendre à El Menzah 9. Surface totale 73 m²") == "El Menzah 9"
        assert extract_title_place("A vendre grand S3 au 1er étage") is None
        assert extract_title_place("Fabuleux S2 à vendre au RDC") is None


class TestROI:
    def test_roi_classique(self):
        r = compute_roi(prix=300000, loyer_mensuel=1500)
        assert r["statut"] == "succes"
        assert r["rendement_brut_pct"] == pytest.approx(5.71, abs=0.1)
        assert r["cout_total_acquisition"] == 315000
        assert r["revenu_annuel_classique"] == 18000

    def test_roi_estival(self):
        r = compute_roi(prix=300000, prix_nuit=350, nuits_an=90)
        assert r["revenu_annuel_estival"] == 31500

    def test_roi_mixte(self):
        r = compute_roi(prix=300000, loyer_mensuel=1000, prix_nuit=300)
        assert r["revenu_annuel_total"] == 12000 + 27000

    def test_prix_invalide(self):
        r = compute_roi(prix=0)
        assert r["statut"] == "erreur"

    def test_score_roi(self):
        assert score_roi(8.0, True, True) == 100
        assert score_roi(4.0, True, False) == 50 + 25
        assert score_roi(0, False, False) == 0

    def test_label_roi(self):
        assert label_roi(9) == "excellent"
        assert label_roi(7) == "bon"
        assert label_roi(5) == "moyen"
        assert label_roi(2) == "faible"
        assert label_roi(-1) == "deficitaire"
