"""FastAPI application for user stories generation using AI."""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import time
from dataclasses import dataclass
from threading import Lock

import crewai.llms.cache as _crewai_cache
import jwt
from crewai import LLM, Agent, Crew, Process, Task
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, ValidationError

_crewai_cache.mark_cache_breakpoint = lambda msg: msg
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agile_devops_api")

JWT_SECRET = os.getenv("JWT_SECRET", "change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
AI_API_KEY = os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
AI_MODEL = os.getenv("AI_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
AI_AGENT_MAX_ITERATIONS = int(os.getenv("AI_AGENT_MAX_ITERATIONS", "3"))

os_llm = LLM(
    model=AI_MODEL,
    temperature=0.2,
)
strategic_po = Agent(
    role="Strategic Product Owner",
    goal=(
        "Deconstruct vague project ideas into a comprehensive list of "
        "feature backlogs."
    ),
    backstory=(
        "You are a veteran Agile Product Manager. You look at a project from "
        "30,000 feet and map out every single user persona, epic, and required "
        "feature milestone. You ensure no core engineering requirements or "
        "edge-cases are missed."
    ),
    llm=os_llm,
    verbose=True,
)

scrum_writer = Agent(
    role="Scrum User Story Specialist",
    goal=(
        "Draft and validate flawless, Pydantic-compliant Scrum user stories "
        "and data structures."
    ),
    backstory=(
        "You convert feature lists into production-ready Agile backlogs. You "
        "format every story perfectly as 'As a... I want... So that...', "
        "attach strict Acceptance Criteria, estimate Fibonacci story points, "
        "and run strict checks to eliminate duplicate or missing features."
    ),
    llm=os_llm,
    verbose=True,
)
class HealthResponse(BaseModel):
    """Response payload for system health check status."""

    status: str

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


class UserStoryResponse(BaseModel):
    """Response payload returned for a generated user story."""

    title: str
    story: str
    acceptance_criteria: list[str]
    estimated_points: int | None


class GenerateUserStoriesResponse(BaseModel):
    """Response payload returned after generating project user stories."""

    project_id: int
    project_title: str
    user_stories: list[UserStoryResponse]
    is_complete: bool
    iterations: int
    titles: list[str]
    missing_titles: list[str]
    duplicate_titles: list[str]


@dataclass(slots=True)
class UserStoryAgentResult:
    """Result produced by the simple user story generation agent."""

    stories: list[UserStoryResponse]
    is_complete: bool
    iterations: int
    titles: list[str]
    missing_titles: list[str]
    duplicate_titles: list[str]


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
            user = User(
                id=self._next_id, name=name, email=email, password=password,
            )
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

    def get_for_owner(self, project_id: int, owner_id: int) -> Project | None:
        """Return the project if it exists and belongs to the owner."""
        with self._lock:
            for project in self._projects:
                if project.id == project_id and project.owner_id == owner_id:
                    return project
            return None

    def reset(self) -> None:
        """Clear all stored projects."""
        with self._lock:
            self._projects.clear()
            self._next_id = 1

    def snapshot(self) -> list[Project]:
        """Return a copy of the stored projects for tests."""
        with self._lock:
            return list(self._projects)
    def exists(self, project_id: int) -> bool:
        """Check whether a project exists by its id."""
        with self._lock:
            return any(project.id == project_id for project in self._projects)
    def delete(self, project_id: int) -> bool:
        """Permanently delete a project by its id.

        Return True if found and deleted, False otherwise.
        """
        with self._lock:
            for index, project in enumerate(self._projects):
                if project.id == project_id:
                    self._projects.pop(index)
                    return True
            return False

def hash_password(value: str) -> str:
    """Hash a password for storage."""
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from exc

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
@app.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
def health_check() -> HealthResponse:
    """Return the current operational status of the API application."""
    return HealthResponse(status="healthy")
@app.get("/users", response_model=list[UserResponse])
def list_users() -> list[UserResponse]:
    """Return all registered users."""
    return store.all()


@app.post(
    "/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED,
)
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
    project = project_store.add(
        title=title, description=description, owner_id=user.id,
    )
    return ProjectResponse(
        id=project.id,
        title=project.title,
        description=project.description,
    )


@app.post(
    "/projects/{project_id}/stories",
    response_model=GenerateUserStoriesResponse,
)
def generate_project_stories(
    project_id: int, request: Request,
) -> GenerateUserStoriesResponse:
    """Triggers CrewAI process to turn a saved project into structured agile stories."""
    user = get_authenticated_user(request)
    project = project_store.get_for_owner(
        project_id=project_id, owner_id=user.id,
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or you do not have permission to view it.",
        )

    scoping_task = Task(
        description=(
            f"Analyze this software project: Title: '{project.title}'. "
            f"Description: '{project.description}'. \n Identify all key "
            "user personas, core software epics, and draft a master backlog "
            "list of individual feature titles needed to make a complete "
            "Minimum Viable Product (MVP)."
        ),
        expected_output=(
            "A clean breakdown list detailing project scopes, personas, "
            "and feature titles."
        ),
        agent=strategic_po,
    )

    generation_task = Task(
        description=(
            "Take the master feature breakdown from the previous task and "
            "generate a complete Scrum backlog. \n 1. Map each feature into a "
            "full 'UserStoryResponse' block.\n 2. Ensure stories contain clear,"
            " realistic Given-When-Then Acceptance Criteria.\n 3. Assign an "
            "estimated Fibonacci story point (1, 2, 3, 5, 8, 13).\n 4. Force-"
            f"inject the current metadata: project_id must be exactly "
            f"{project.id}, and project_title must be exactly "
            f"'{project.title}'.\n 5. Populate 'titles', 'missing_titles', and "
            "'duplicate_titles' during self-audit. Set iterations to 1."
        ),
        expected_output=(
            "A fully populated JSON structure matching the "
            "GenerateUserStoriesResponse schema."
        ),
        agent=scrum_writer,
        output_json=GenerateUserStoriesResponse,
    )

    scrum_crew = Crew(
        agents=[strategic_po, scrum_writer],
        tasks=[scoping_task, generation_task],
        process=Process.sequential,
    )

    try:
        crew_result = scrum_crew.kickoff()
    except ValidationError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"The AI model failed to produce matching structural data: "
                f"{val_err}"
            ),
        ) from val_err
    except RuntimeError as run_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Story generation engine encountered a runtime error: "
                f"{run_err!s}"
            ),
        ) from run_err
    else:
        validated_payload: GenerateUserStoriesResponse = crew_result.pydantic
        return validated_payload
@app.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, request: Request) -> None:
    """Permanently delete a project belonging to the authenticated owner."""
    user = get_authenticated_user(request)

    if not project_store.exists(project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    project = project_store.get_for_owner(
        project_id=project_id, owner_id=user.id,
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this project.",
        )

    project_store.delete(project_id)
