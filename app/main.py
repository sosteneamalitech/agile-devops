from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from threading import Lock

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    password: str = Field(min_length=6)


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr


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
