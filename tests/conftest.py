import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import numpy as np


def pytest_configure(config):
    config.addinivalue_line("markers", "mongo: tests requiring a local MongoDB")


@pytest.fixture
def mongo_available():
    """Skip si MongoDB local n'est pas joignable."""
    try:
        from pymongo import MongoClient
        from dotenv import load_dotenv
        load_dotenv()
        client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=1500)
        client.admin.command("ping")
        return True
    except Exception:
        return False
