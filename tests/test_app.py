from fastapi.testclient import TestClient

from app.main import app, store


client = TestClient(app)

VALID_USER = {
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "password": "secret1",
}

INVALID_USER = {"name": "Ada"}


def setup_function() -> None:
    store.reset()


def test_successful_registration_returns_201_and_no_password() -> None:
    response = client.post("/users", json=VALID_USER)

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == 1
    assert payload["name"] == "Ada Lovelace"
    assert payload["email"] == "ada@example.com"
    assert "password" not in response.text
    assert store.snapshot()[0].password != "secret1"
    assert store.snapshot()[0].password


def test_validation_error_returns_400() -> None:
    response = client.post("/users", json=INVALID_USER)

    assert response.status_code == 422


def test_duplicate_email_returns_409() -> None:
    first = client.post("/users", json=VALID_USER)
    second = client.post("/users", json=VALID_USER)

    assert first.status_code == 201
    assert second.status_code == 409


def test_stored_and_returned_users_never_expose_password() -> None:
    response = client.post("/users", json=VALID_USER)
    assert response.status_code == 201

    users = client.get("/users")
    assert users.status_code == 200
    assert "password" not in users.text
    assert "secret1" not in users.text
