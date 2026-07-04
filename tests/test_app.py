import jwt
from fastapi.testclient import TestClient

from app.main import JWT_ALGORITHM, JWT_SECRET, app, project_store, store

client = TestClient(app)

VALID_USER = {
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "password": "secret1",
}

INVALID_USER = {"name": "Ada"}
VALID_LOGIN = {"email": "ada@example.com", "password": "secret1"}
INVALID_LOGIN = {"email": "ada@example.com"}


def setup_function() -> None:
    store.reset()
    project_store.reset()


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


def test_successful_login_returns_token() -> None:
    register = client.post("/users", json=VALID_USER)
    assert register.status_code == 201

    response = client.post("/login", json=VALID_LOGIN)

    assert response.status_code == 200
    payload = response.json()
    assert payload["user_id"] == 1
    assert isinstance(payload["token"], str)
    assert payload["token"]
    assert jwt.decode(payload["token"], JWT_SECRET, algorithms=[JWT_ALGORITHM])["user_id"] == 1
    assert "password" not in response.text


def test_invalid_login_credentials_return_401() -> None:
    register = client.post("/users", json=VALID_USER)
    assert register.status_code == 201

    response = client.post("/login", json={"email": "ada@example.com", "password": "wrongpass"})

    assert response.status_code == 401


def test_login_validation_error_returns_400() -> None:
    register = client.post("/users", json=VALID_USER)
    assert register.status_code == 201

    response = client.post("/login", json=INVALID_LOGIN)

    assert response.status_code == 400


def test_login_never_exposes_password_in_response() -> None:
    register = client.post("/users", json=VALID_USER)
    assert register.status_code == 201

    response = client.post("/login", json=VALID_LOGIN)

    assert response.status_code == 200
    assert "secret1" not in response.text


def test_successful_project_creation_returns_201_and_details() -> None:
    register = client.post("/users", json=VALID_USER)
    assert register.status_code == 201

    login = client.post("/login", json=VALID_LOGIN)
    assert login.status_code == 200
    token = login.json()["token"]

    response = client.post(
        "/projects",
        json={"title": "Project Atlas", "description": "AI user story generator"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == 1
    assert payload["title"] == "Project Atlas"
    assert payload["description"] == "AI user story generator"
    assert project_store.snapshot()[0].owner_id == 1


def test_project_validation_error_returns_400() -> None:
    register = client.post("/users", json=VALID_USER)
    assert register.status_code == 201

    login = client.post("/login", json=VALID_LOGIN)
    assert login.status_code == 200
    token = login.json()["token"]

    response = client.post(
        "/projects",
        json={"title": "", "description": "AI user story generator"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400


def test_project_creation_without_login_returns_401() -> None:
    response = client.post(
        "/projects",
        json={"title": "Project Atlas", "description": "AI user story generator"},
    )

    assert response.status_code == 401
