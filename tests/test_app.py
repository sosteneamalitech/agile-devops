"""Unit tests for the Agile DevOps API core authentication and projects."""

from __future__ import annotations

from typing import Any

import jwt
from fastapi import status
from fastapi.testclient import TestClient

from app.main import (
    JWT_ALGORITHM,
    JWT_SECRET,
    app,
    project_store,
    store,
)

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
    """Reset data stores before each test run."""
    store.reset()
    project_store.reset()


def test_successful_registration_returns_201_and_no_password() -> None:
    """Ensure valid user registration yields 201 and conceals passwords."""
    response = client.post("/users", json=VALID_USER)

    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    assert payload["id"] == 1
    assert payload["name"] == "Ada Lovelace"
    assert payload["email"] == "ada@example.com"
    assert "password" not in response.text
    assert store.snapshot()[0].password != "secret1"
    assert store.snapshot()[0].password


def test_validation_error_returns_400() -> None:
    """Ensure invalid structures drop down to validation status codes."""
    response = client.post("/users", json=INVALID_USER)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_duplicate_email_returns_409() -> None:
    """Ensure registering an existing email yields a 409 conflict."""
    first = client.post("/users", json=VALID_USER)
    second = client.post("/users", json=VALID_USER)

    assert first.status_code == status.HTTP_201_CREATED
    assert second.status_code == status.HTTP_409_CONFLICT


def test_stored_and_returned_users_never_expose_password() -> None:
    """Verify user listings never leak cleartext or hashed credentials."""
    response = client.post("/users", json=VALID_USER)
    assert response.status_code == status.HTTP_201_CREATED

    users = client.get("/users")
    assert users.status_code == status.HTTP_200_OK
    assert "password" not in users.text
    assert "secret1" not in users.text


def test_successful_login_returns_token() -> None:
    """Verify valid credentials return a properly encoded JWT token."""
    register = client.post("/users", json=VALID_USER)
    assert register.status_code == status.HTTP_201_CREATED

    response = client.post("/login", json=VALID_LOGIN)

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["user_id"] == 1
    assert isinstance(payload["token"], str)
    assert payload["token"]

    decoded: dict[str, Any] = jwt.decode(
        payload["token"], JWT_SECRET, algorithms=[JWT_ALGORITHM],
    )
    assert decoded["user_id"] == 1
    assert "password" not in response.text


def test_invalid_login_credentials_return_401() -> None:
    """Verify incorrect passwords strictly reject access with a 401."""
    register = client.post("/users", json=VALID_USER)
    assert register.status_code == status.HTTP_201_CREATED

    response = client.post(
        "/login", json={"email": "ada@example.com", "password": "wrongpass"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_login_validation_error_returns_400() -> None:
    """Verify malformed login payloads drop out immediately with a 400."""
    register = client.post("/users", json=VALID_USER)
    assert register.status_code == status.HTTP_201_CREATED

    response = client.post("/login", json=INVALID_LOGIN)

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_login_never_exposes_password_in_response() -> None:
    """Verify string sweeps of token payloads don't contain passwords."""
    register = client.post("/users", json=VALID_USER)
    assert register.status_code == status.HTTP_201_CREATED

    response = client.post("/login", json=VALID_LOGIN)

    assert response.status_code == status.HTTP_200_OK
    assert "secret1" not in response.text


def test_successful_project_creation_returns_201_and_details() -> None:
    """Verify authorized users can generate valid software projects."""
    register = client.post("/users", json=VALID_USER)
    assert register.status_code == status.HTTP_201_CREATED

    login = client.post("/login", json=VALID_LOGIN)
    assert login.status_code == status.HTTP_200_OK
    token = login.json()["token"]

    response = client.post(
        "/projects",
        json={
            "title": "Project Atlas",
            "description": "AI user story generator",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    assert payload["id"] == 1
    assert payload["title"] == "Project Atlas"
    assert payload["description"] == "AI user story generator"
    assert project_store.snapshot()[0].owner_id == 1


def test_project_validation_error_returns_400() -> None:
    """Verify empty project metadata yields bad request assertions."""
    register = client.post("/users", json=VALID_USER)
    assert register.status_code == status.HTTP_201_CREATED

    login = client.post("/login", json=VALID_LOGIN)
    assert login.status_code == status.HTTP_200_OK
    token = login.json()["token"]

    response = client.post(
        "/projects",
        json={"title": "", "description": "AI user story generator"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_project_creation_without_login_returns_401() -> None:
    """Verify anonymous tracking blocks baseline project submission."""
    response = client.post(
        "/projects",
        json={
            "title": "Project Atlas",
            "description": "AI user story generator",
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
def test_delete_project_success() -> None:
    """Verify owner can successfully delete their project (HTTP 204)."""
    register = client.post("/users", json=VALID_USER)
    assert register.status_code == status.HTTP_201_CREATED

    login = client.post("/login", json=VALID_LOGIN)
    assert login.status_code == status.HTTP_200_OK
    token = login.json()["token"]
    auth_header = {"Authorization": f"Bearer {token}"}

    proj_res = client.post(
        "/projects",
        json={"title": "Delete Me", "description": "Temp"},
        headers=auth_header,
    )
    project_id = proj_res.json()["id"]

    delete_res = client.delete(f"/projects/{project_id}", headers=auth_header)
    assert delete_res.status_code == status.HTTP_204_NO_CONTENT
    assert len(project_store.snapshot()) == 0


def test_delete_project_unauthorized_forbidden() -> None:
    """Verify a user cannot delete another user's project (HTTP 403)."""
    register1 = client.post("/users", json=VALID_USER)
    assert register1.status_code == status.HTTP_201_CREATED

    login1 = client.post("/login", json=VALID_LOGIN)
    assert login1.status_code == status.HTTP_200_OK
    token1 = login1.json()["token"]
    auth_header1 = {"Authorization": f"Bearer {token1}"}

    proj_res = client.post(
        "/projects",
        json={"title": "Secure Project", "description": "Keep"},
        headers=auth_header1,
    )
    project_id = proj_res.json()["id"]

    client.post(
        "/users",
        json={
            "name": "Attacker",
            "email": "attacker@example.com",
            "password": "password123",
        },
    )
    login2 = client.post(
        "/login",
        json={"email": "attacker@example.com", "password": "password123"},
    )
    token2 = login2.json()["token"]
    auth_header2 = {"Authorization": f"Bearer {token2}"}

    delete_res = client.delete(
        f"/projects/{project_id}", headers=auth_header2,
    )
    assert delete_res.status_code == status.HTTP_403_FORBIDDEN


def test_delete_project_not_found() -> None:
    """Verify attempting to delete a non-existent project yields HTTP 404."""
    register = client.post("/users", json=VALID_USER)
    assert register.status_code == status.HTTP_201_CREATED

    login = client.post("/login", json=VALID_LOGIN)
    assert login.status_code == status.HTTP_200_OK
    token = login.json()["token"]
    auth_header = {"Authorization": f"Bearer {token}"}

    response = client.delete("/projects/9999", headers=auth_header)
    assert response.status_code == status.HTTP_404_NOT_FOUND
