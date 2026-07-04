"""FastAPI application for user stories generation using AI."""

from __future__ import annotations

import base64
import hashlib
import os
import time
from dataclasses import dataclass
from threading import Lock

import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, ValidationError


class RegisterRequest(BaseModel):
    """Request body for creating a new account."""

    name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=6)


class UserResponse(BaseModel):
    """Response payload returned for registered users."""

    id: int
    name: str
    email: EmailStr


class LoginRequest(BaseModel):
    """Request body for logging a user in."""

    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Response payload returned after successful login."""

    user_id: int
    token: str


class ProjectResponse(BaseModel):
    """Response payload returned after creating a project."""

    id: int
    title: str
    description: str


@dataclass(slots=True)
class Project:
    """Stored project record."""

    id: int
    title: str
    description: str
    owner_id: int


@dataclass(slots=True)
class User:
    """Stored user record with a hashed password."""

    id: int
    name: str
    email: str
    password: str


class UserStore:
    """Thread-safe in-memory user store."""

    def __init__(self) -> None:
        """Create an empty store."""
        self._users: list[User] = []
        self._next_id = 1
        self._lock = Lock()

    def all(self) -> list[UserResponse]:
        """Return every stored user without passwords."""
        with self._lock:
            return [
                UserResponse(id=user.id, name=user.name, email=user.email)
                for user in self._users
            ]

    def exists(self, email: str) -> bool:
        """Check whether a user already exists for the email address."""
        with self._lock:
            return any(user.email == email for user in self._users)

    def get_by_email(self, email: str) -> User | None:
        """Return the stored user matching the email address, if any."""
        with self._lock:
            for user in self._users:
                if user.email == email:
                    return user
            return None

    def get_by_id(self, user_id: int) -> User | None:
        """Return the stored user matching the id, if any."""
        with self._lock:
            for user in self._users:
                if user.id == user_id:
                    return user
            return None

    def add(self, name: str, email: str, password: str) -> User:
        """Store a new user and assign the next id."""
        with self._lock:
            user = User(id=self._next_id, name=name, email=email, password=password)
            self._next_id += 1
            self._users.append(user)
            return user

    def reset(self) -> None:
        """Clear all stored users."""
        with self._lock:
            self._users.clear()
            self._next_id = 1

    def snapshot(self) -> list[User]:
        """Return a copy of the stored users for tests."""
        with self._lock:
            return list(self._users)


class ProjectStore:
    """Thread-safe in-memory project store."""

    def __init__(self) -> None:
        """Create an empty store."""
        self._projects: list[Project] = []
        self._next_id = 1
        self._lock = Lock()

    def add(self, title: str, description: str, owner_id: int) -> Project:
        """Store a new project and assign the next id."""
        with self._lock:
            project = Project(
                id=self._next_id,
                title=title,
                description=description,
                owner_id=owner_id,
            )
            self._next_id += 1
            self._projects.append(project)
            return project

    def reset(self) -> None:
        """Clear all stored projects."""
        with self._lock:
            self._projects.clear()
            self._next_id = 1

    def snapshot(self) -> list[Project]:
        """Return a copy of the stored projects for tests."""
        with self._lock:
            return list(self._projects)


def hash_password(value: str) -> str:
    """Hash a password for storage."""
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


def create_auth_token(user: User) -> str:
    """Create a signed JWT that carries the user id and email."""
    payload = {"user_id": user.id, "email": user.email, "iat": int(time.time())}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_authenticated_user(request: Request) -> User:
    """Return the authenticated user for a bearer token request."""
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED) from exc

    user_id = payload.get("user_id")
    email = payload.get("email")
    if not isinstance(user_id, int) or not isinstance(email, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user = store.get_by_id(user_id)
    if user is None or user.email != email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return user


def parse_login_request(payload: object) -> LoginRequest:
    """Validate raw login payload data and coerce the email field."""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    email = payload.get("email")
    password = payload.get("password")

    if (
        not isinstance(email, str)
        or not isinstance(password, str)
        or not email.strip()
        or not password
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    try:
        email_adapter = TypeAdapter(EmailStr)
        validated_email = email_adapter.validate_python(email)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST) from exc

    return LoginRequest(email=validated_email, password=password)


def parse_project_request(payload: object) -> tuple[str, str]:
    """Validate raw project payload data."""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    title = payload.get("title")
    description = payload.get("description")

    if (
        not isinstance(title, str)
        or not isinstance(description, str)
        or not title.strip()
        or not description.strip()
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    return title.strip(), description.strip()


store = UserStore()
project_store = ProjectStore()
app = FastAPI(title="Agile DevOps API")


@app.get("/users", response_model=list[UserResponse])
def list_users() -> list[UserResponse]:
    """Return all registered users."""
    return store.all()


@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(request: RegisterRequest) -> UserResponse:
    """Create a new user account."""
    if store.exists(request.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)

    user = store.add(
        request.name,
        request.email,
        hash_password(request.password),
    )
    return UserResponse(id=user.id, name=user.name, email=user.email)


@app.post("/login", response_model=LoginResponse)
async def login(request: Request) -> LoginResponse:
    """Authenticate a user and return a token."""
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST) from exc

    login_request = parse_login_request(payload)
    user = store.get_by_email(login_request.email)

    if user is None or user.password != hash_password(login_request.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return LoginResponse(
        user_id=user.id,
        token=create_auth_token(user),
    )


@app.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(request: Request) -> ProjectResponse:
    """Create a new project for the authenticated user."""
    user = get_authenticated_user(request)

    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST) from exc

    title, description = parse_project_request(payload)
    project = project_store.add(title=title, description=description, owner_id=user.id)
    return ProjectResponse(
        id=project.id,
        title=project.title,
        description=project.description,
    )
