import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import numpy as np


def pytest_configure(config):
    config.addinivalue_line("markers", "mongo: tests requiring a local MongoDB")


@pytest.fixture(scope="session")
def mongo_available():
    """MongoDB local joignable ? (testé une seule fois par session : sans base, comme
    en CI, chaque test réessayait la connexion et la suite prenait près de 2 minutes)"""
    try:
        from pymongo import MongoClient
        from dotenv import load_dotenv
        load_dotenv()
        client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=1500)
        client.admin.command("ping")
        return True
    except Exception:
        return False


@pytest.fixture
def client(mongo_available):
    """Client de test de l'API (tests ignorés sans MongoDB local)."""
    if not mongo_available:
        pytest.skip("MongoDB local indisponible")
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)
