import os
import tempfile
import warnings

import pytest

warnings.filterwarnings("ignore")
_tmp = tempfile.mkdtemp(prefix="gmsun_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DATA_DIR"] = f"{_tmp}/data"
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-test-secret-key"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    r = client.post("/api/auth/login-json", json={"email": "admin@gmsun.local", "password": "admin1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}
