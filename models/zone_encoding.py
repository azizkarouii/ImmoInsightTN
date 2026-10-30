"""Encodage des zones (ville / délégation / gouvernorat) par leur niveau de prix.

Avec quelques dizaines d'annonces par zone, un one-hot surapprend et ne gère pas
les zones inconnues. On encode plutôt chaque zone par la moyenne de la cible
(log du prix au m² ou du prix par nuit), lissée vers la moyenne globale :

    encodage = (n * moyenne_zone + k * moyenne_globale) / (n + k)

Une zone vue une seule fois reste proche de la moyenne globale ; une zone
inconnue reçoit la moyenne globale.
"""
import unicodedata

import numpy as np
import pandas as pd


def norm_zone(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace("-", " ").split())


class ZoneEncoder:
    def __init__(self, smoothing=5.0):
        self.smoothing = smoothing
        self.global_mean = None
        self.table = {}

    def fit(self, zones, target):
        zones = pd.Series([norm_zone(z) for z in zones])
        target = pd.Series(np.asarray(target, dtype=float))
        self.global_mean = float(target.mean())
        stats = target.groupby(zones.values).agg(["mean", "count"])
        stats = stats[stats.index != ""]
        k = self.smoothing
        self.table = {
            zone: float((row["count"] * row["mean"] + k * self.global_mean) / (row["count"] + k))
            for zone, row in stats.iterrows()
        }
        return self

    def known(self, zone):
        return norm_zone(zone) in self.table

    def transform(self, zones):
        return np.array([self.table.get(norm_zone(z), self.global_mean) for z in zones], dtype=float)

    def to_dict(self):
        return {"smoothing": self.smoothing, "global_mean": self.global_mean, "table": self.table}

    @classmethod
    def from_dict(cls, data):
        enc = cls(data.get("smoothing", 5.0))
        enc.global_mean = data["global_mean"]
        enc.table = data["table"]
        return enc
