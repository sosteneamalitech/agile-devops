from __future__ import annotations

import base64
import hashlib
import os
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
import jwt
from dotenv import load_dotenv
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, ValidationError


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=6)


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    user_id: int
    token: str


@dataclass(slots=True)
class User:
    id: int
    name: str
    email: str
    password: str


class UserStore:
    def __init__(self) -> None:
        self._users: list[User] = []
        self._next_id = 1
        self._lock = Lock()

    def all(self) -> list[UserResponse]:
        with self._lock:
            return [UserResponse(id=user.id, name=user.name, email=user.email) for user in self._users]

    def exists(self, email: str) -> bool:
        with self._lock:
            return any(user.email == email for user in self._users)

    def get_by_email(self, email: str) -> User | None:
        with self._lock:
            for user in self._users:
                if user.email == email:
                    return user
            return None

    def add(self, name: str, email: str, password: str) -> User:
        with self._lock:
            user = User(id=self._next_id, name=name, email=email, password=password)
            self._next_id += 1
            self._users.append(user)
            return user

    def reset(self) -> None:
        with self._lock:
            self._users.clear()
            self._next_id = 1

    def snapshot(self) -> list[User]:
        with self._lock:
            return list(self._users)


def hash_password(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


def create_auth_token(user: User) -> str:
    payload = {"user_id": user.id, "email": user.email, "iat": int(time.time())}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def parse_login_request(payload: Any) -> LoginRequest:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    email = payload.get("email")
    password = payload.get("password")

    if not isinstance(email, str) or not isinstance(password, str) or not email.strip() or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    try:
        validated_email = TypeAdapter(EmailStr).validate_python(email)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST) from exc

    return LoginRequest(email=validated_email, password=password)


store = UserStore()
app = FastAPI(title="Agile DevOps API")


@app.get("/users", response_model=list[UserResponse])
def list_users() -> list[UserResponse]:
    return store.all()


@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(request: RegisterRequest) -> UserResponse:
    if store.exists(request.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)

    user = store.add(request.name, request.email, hash_password(request.password))
    return UserResponse(id=user.id, name=user.name, email=user.email)


@app.post("/login", response_model=LoginResponse)
async def login(request: Request) -> LoginResponse:
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST) from exc

    login_request = parse_login_request(payload)
    user = store.get_by_email(login_request.email)

    if user is None or user.password != hash_password(login_request.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return LoginResponse(user_id=user.id, token=create_auth_token(user))
