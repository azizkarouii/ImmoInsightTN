"""Rattachement des villes et quartiers aux grandes régions (sans base de données)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from etl.regions import ORDRE_REGIONS, gouvernorat_de, region_de


@pytest.mark.parametrize("nom, region", [
    ("Tunis", "Grand Tunis"), ("La Marsa", "Grand Tunis"), ("El Menzah 9", "Grand Tunis"),
    ("Ain Zaghouan Nord", "Grand Tunis"),      # quartier de Tunis, pas le gouvernorat de Zaghouan
    ("Hammamet Sud", "Cap Bon"), ("Kélibia", "Cap Bon"), ("Klibia", "Cap Bon"), ("Dar Châabane", "Cap Bon"),
    ("Hammam Sousse", "Sahel"), ("Sousse Jaouhara", "Sahel"), ("Zéramdine", "Sahel"), ("Mahdia", "Sahel"),
    ("Route Gremda", "Sfax"), ("Kerkennah", "Sfax"),
    ("Ras Jebel", "Nord-Est"), ("Tabarka", "Nord-Ouest"), ("Béja", "Nord-Ouest"),
    ("Djerba Midoun", "Sud-Est"), ("Médenine", "Sud-Est"), ("Gafsa Sud", "Sud-Ouest"), ("Kairouan Ville", "Centre-Ouest"),
])
def test_region_par_ville(nom, region):
    assert region_de({"ville": nom}) == region


def test_gouvernorat_prioritaire_sur_ville():
    # Une « Route Tunis » à Sfax : le gouvernorat renseigné l'emporte
    assert region_de({"gouvernorat": "Sfax", "ville": "Route Tunis"}) == "Sfax"


def test_inconnu():
    assert region_de({}) is None
    assert region_de({"ville": "Autres Villes"}) is None
    assert gouvernorat_de(None) is None


def test_ordre_regions():
    assert ORDRE_REGIONS[:3] == ["Grand Tunis", "Cap Bon", "Sahel"]
