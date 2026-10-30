"""Tests des fonctions d'extraction des scrapers (textes réels relevés en Octobre 2026)."""
import pytest

from scrapers.booking_scraper import canonical_url, nb_nuits_depuis, parse_booking_card
from scrapers.tayara_scraper import parse_tayara_ad


class TestBookingCard:
    APPARTEMENT = {
        "title": "Résidence Les Jasmins",
        "price-and-discounted-price": "TND 2 385",
        "price-for-x-nights": "1 semaine, 2 adultes",
        "recommended-units": (
            "Appartement 1 Chambre\n"
            "Appartement entier • 1 chambre • 1 salon • 1 salle de bains • 85 m²\n"
            "5 lits (2 lits simples, 1 lit double, 2 canapés-lits)\n"
            "Annulation gratuite"
        ),
        "review-score": "Avec une note de 8,3\n8,3\nTrès bien\n2 660 expériences vécues",
        "card": "Résidence Les Jasmins\nHammamet\n4,9 km du centre\nFront de mer\n",
    }

    def test_appartement_entier(self):
        r = parse_booking_card(self.APPARTEMENT)
        assert r["prix_sejour"] == 2385
        assert r["nb_nuits"] == 7
        assert r["prix_nuit"] == 341
        assert r["logement_entier"] is True
        assert r["type_logement"] == "Appartement entier"
        assert (r["nb_chambres"], r["nb_salons"], r["nb_sdb"], r["surface"], r["nb_lits"]) == (1, 1, 1, 85, 5)
        assert r["score_avis"] == 8.3
        assert r["nb_avis"] == 2660
        assert r["dist_centre_km"] == 4.9
        assert r["front_de_mer"] is True and r["dist_plage_km"] == 0.0

    def test_chambre_hotel_tout_compris(self):
        r = parse_booking_card({
            "price-and-discounted-price": "TND 818",
            "price-for-x-nights": "1 semaine, 2 adultes",
            "recommended-units": "Chambre Double Standard\nTypes de lits : 1 lit double ou 2 lits simples\nTout compris",
            "card": "400 m du centre\nÀ 150 m de la plage",
        })
        assert r["logement_entier"] is False
        assert r["pension"] == "tout_compris"
        assert r["dist_centre_km"] == 0.4
        assert r["dist_plage_km"] == 0.15

    def test_grande_surface_separateur_milliers(self):
        r = parse_booking_card({"recommended-units": "Maison de vacances entière • 7 chambres • 3 salons • 2.500 m²\n9 lits (...)"})
        assert r["surface"] == 2500
        assert r["nb_chambres"] == 7

    @pytest.mark.parametrize("texte,nuits", [("1 semaine, 2 adultes", 7), ("3 nuits, 2 adultes", 3), ("1 nuit", 1), (None, None)])
    def test_nb_nuits(self, texte, nuits):
        assert nb_nuits_depuis(texte) == nuits

    def test_url_sans_parametres_de_recherche(self):
        href = "https://www.booking.com/hotel/tn/dar-el-bhar.fr.html?aid=304142&checkin=2026-07-25&checkout=2026-08-01"
        assert canonical_url(href) == "https://www.booking.com/hotel/tn/dar-el-bhar.fr.html"
        assert canonical_url("/hotel/tn/x.fr.html?label=y") == "https://www.booking.com/hotel/tn/x.fr.html"


class TestTayaraAd:
    @staticmethod
    def next_data(transaction="À Louer", price=1600):
        return {"props": {"pageProps": {"adDetails": {
            "title": "appartement S2 à Ain Zaghouan nord",
            "price": price,
            "description": "Bel appartement",
            "location": {"governorate": "Tunis", "delegation": "Ain Zaghouan Nord"},
            "adParams": [
                {"label": "Type de transaction", "value": transaction},
                {"label": "Superficie", "value": "117"},
                {"label": "Salles de bains", "value": "1"},
                {"label": "Chambres", "value": "2"},
            ],
        }}}}

    URL = "https://www.tayara.tn/item/appartements/tunis/ain-zaghouan-nord/appartement-s2/6a9efdca62d7349f5f069347/"

    def test_location(self):
        item, collection = parse_tayara_ad(self.next_data(), self.URL)
        assert collection == "raw_location"
        assert item["type_offre"] == "location"
        assert (item["prix"], item["surface"], item["nb_chambres"], item["nb_pieces"]) == (1600, 117, 2, 3)
        assert (item["gouvernorat"], item["ville"]) == ("Tunis", "Ain Zaghouan Nord")
        assert item["type_bien"] == "appartement"

    def test_vente(self):
        _, collection = parse_tayara_ad(self.next_data("À Vendre", 550000), self.URL)
        assert collection == "raw_vente"

    def test_categorie_non_residentielle_ignoree(self):
        item, raison = parse_tayara_ad(self.next_data(), "https://www.tayara.tn/item/bureaux-et-plateaux/tunis/x/y/1/")
        assert item is None and "categorie" in raison

    def test_sans_transaction_ignoree(self):
        item, _ = parse_tayara_ad(self.next_data(transaction=""), self.URL)
        assert item is None


class TestMubawabJsonLd:
    def test_annonce(self):
        import json
        from scrapers.mubawab_scraper import parse_json_ld

        ld = json.dumps({
            "@type": "RealEstateListing",
            "offers": {"@type": "Offer", "price": 6500.0, "priceCurrency": "TND"},
            "itemOffered": {
                "@type": "Apartment",
                "address": {"addressLocality": "La Marsa"},
                "numberOfRooms": 4, "numberOfBedrooms": 3, "numberOfBathroomsTotal": 3,
                "floorSize": {"value": 180, "unitCode": "MTR"},
            },
        })
        r = parse_json_ld(['{"@type": "Organization"}', "pas du json", ld])
        assert r == {"prix": 6500, "surface": 180, "nb_pieces": 4, "nb_chambres": 3, "nb_sdb": 3, "ville": "La Marsa"}

    def test_prix_sur_demande(self):
        import json
        from scrapers.mubawab_scraper import parse_json_ld

        r = parse_json_ld([json.dumps({"@type": "RealEstateListing", "offers": {"price": 0}})])
        assert r["prix"] is None
