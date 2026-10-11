import pytest
from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATA_DIR": str(tmp_path), "START_WORKER": False})


@pytest.fixture
def client(app):
    client = app.test_client()
    client.get("/setup")
    with client.session_transaction() as session:
        token = session["csrf"]
    response = client.post("/setup", data={"username": "tester", "password": "test-password-123", "csrf_token": token})
    assert response.status_code == 302
    return client


@pytest.fixture
def headers(client):
    with client.session_transaction() as session:
        return {"X-CSRF-Token": session["csrf"]}

