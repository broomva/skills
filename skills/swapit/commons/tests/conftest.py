import importlib
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")  # commons tests require `pip install -r requirements.txt`

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SWAPIT_COMMONS_DB", str(tmp_path / "commons.db"))
    from app import main

    importlib.reload(main)  # rebind the module-level Store to the temp DB
    from fastapi.testclient import TestClient

    return TestClient(main.app)
