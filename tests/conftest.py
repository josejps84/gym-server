"""Integration tests run against a real Postgres (docker compose up -d) through the HTTP API.

TEST_DATABASE_URL picks the database; it is wiped and migrated once per run.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.auth import TokenVerifier
from app.config import Settings
from app.container import Container
from app.main import create_app
from app.rate_limit import RateLimiter
from app.repositories.tables import Base
from app.services.ports import SignedUpload, UpstreamError

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://gym:gym@localhost:5433/gym_test")
ISSUER = "https://supabase.test/auth/v1"
STORAGE_PREFIX = "https://supabase.test/storage/v1/object/public/avatars/"
ROOT = Path(__file__).resolve().parent.parent

PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())


def make_token(user_id: UUID, *, name: str | None = None, **claims: Any) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "aud": "authenticated",
        "iss": ISSUER,
        "role": "authenticated",
        "exp": now + timedelta(hours=1),
        "iat": now,
        "email": f"{user_id.hex[:8]}@example.com",
        "user_metadata": {"full_name": name} if name else {},
        **claims,
    }
    return jwt.encode(payload, PRIVATE_KEY, algorithm="ES256", headers={"kid": "test"})


def verifier_for_tests() -> TokenVerifier:
    public_key = PRIVATE_KEY.public_key()
    return TokenVerifier(lambda _token: public_key, issuer=ISSUER, audience="authenticated")


@dataclass
class FakeStorage:
    uploads: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    objects: dict[str, list[str]] = field(default_factory=dict)

    stored: dict[str, tuple[bytes, str]] = field(default_factory=dict)

    def public_url(self, path: str) -> str:
        return STORAGE_PREFIX + path

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        self.stored[path] = (data, content_type)

    async def create_upload_url(self, path: str) -> SignedUpload:
        self.uploads.append(path)
        return SignedUpload(f"https://supabase.test/upload/{path}?token=t", "t", datetime.now(UTC))

    async def delete(self, paths: Sequence[str]) -> None:
        self.deleted.extend(paths)

    async def list_paths(self, prefix: str) -> list[str]:
        return self.objects.get(prefix, [])


@dataclass
class FakePhotos:
    """Serves `content_type` for every URL, or fails when `failing`."""

    fetched: list[str] = field(default_factory=list)
    content_type: str = "image/jpeg"
    failing: bool = False

    async def fetch(self, url: str) -> tuple[bytes, str]:
        if self.failing:
            raise UpstreamError("down")
        self.fetched.append(url)
        return b"photo", self.content_type


@dataclass
class FakeIdentity:
    deleted: list[UUID] = field(default_factory=list)

    async def delete_user(self, user_id: UUID) -> None:
        self.deleted.append(user_id)


@dataclass
class FakeMailer:
    """Keeps the emails, or fails when `failing`."""

    sent: list[tuple[str, str, str]] = field(default_factory=list)
    failing: bool = False

    async def send(self, to: str, subject: str, text: str) -> None:
        if self.failing:
            raise UpstreamError("down")
        self.sent.append((to, subject, text))


REPORTS_EMAIL = "mod@example.com"


def _migrate() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
    except (OSError, SQLAlchemyError) as error:
        pytest.fail(f"No test database at {TEST_DATABASE_URL} ({error}). Run: docker compose up -d")
    # Alembic's env.py runs its own event loop.
    await asyncio.to_thread(_migrate)
    yield engine
    await engine.dispose()


@pytest.fixture
async def clean_db(engine: AsyncEngine) -> None:
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def identity() -> FakeIdentity:
    return FakeIdentity()


@pytest.fixture
def photos() -> FakePhotos:
    return FakePhotos()


@pytest.fixture
def mailer() -> FakeMailer:
    return FakeMailer()


def build_test_container(
    engine: AsyncEngine,
    storage: FakeStorage,
    identity: FakeIdentity,
    rate_limit: int = 0,
    photos: FakePhotos | None = None,
    mailer: FakeMailer | None = None,
) -> Container:
    return Container(
        settings=Settings(
            database_url=TEST_DATABASE_URL, supabase_url="https://supabase.test", reports_email=REPORTS_EMAIL
        ),
        engine=engine,
        sessions=async_sessionmaker(engine, expire_on_commit=False),
        verifier=verifier_for_tests(),
        storage=storage,
        identity=identity,
        photos=photos or FakePhotos(),
        rate_limiter=RateLimiter(rate_limit),
        mailer=mailer or FakeMailer(),
    )


@pytest.fixture
async def client(
    engine: AsyncEngine,
    clean_db: None,
    storage: FakeStorage,
    identity: FakeIdentity,
    photos: FakePhotos,
    mailer: FakeMailer,
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(build_test_container(engine, storage, identity, photos=photos, mailer=mailer))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@dataclass
class User:
    """A logged-in user calling the API."""

    http: httpx.AsyncClient
    id: UUID
    username: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(self.id)}"}

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.http.get(url, headers=self.headers, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.http.post(url, headers=self.headers, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.http.put(url, headers=self.headers, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.http.patch(url, headers=self.headers, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.http.delete(url, headers=self.headers, **kwargs)


@pytest.fixture
def new_user(client: httpx.AsyncClient) -> Any:
    async def create(username: str) -> User:
        user = User(client, uuid4(), username)
        response = await user.patch("/me", json={"username": username})
        assert response.status_code == 200, response.text
        return user

    return create


def iso(moment: datetime) -> str:
    return moment.isoformat()


T0 = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


def routine_body(
    name: str = "Pierna",
    *,
    visibility: str = "private",
    updated_at: datetime = T0,
    exercise_ids: Sequence[str] = ("seed-squat",),
    deleted: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "exercises": [{"exerciseId": e, "targetSets": 3, "targetReps": 10, "restSeconds": 90} for e in exercise_ids],
        "data": {"type": "CUSTOM", "subtype": "GYM", "level": 2},
        "visibility": visibility,
        "createdAt": iso(T0),
        "updatedAt": iso(updated_at),
        "deletedAt": iso(updated_at) if deleted else None,
    }


def session_body(
    *, visibility: str = "private", ended_at: datetime = T0 + timedelta(hours=1), updated_at: datetime = T0
) -> dict[str, Any]:
    return {
        "routineId": "suggested-l2-gym-1",
        "name": "Pierna",
        "startedAt": iso(ended_at - timedelta(hours=1)),
        "endedAt": iso(ended_at),
        "summary": {"durationSeconds": 3600, "volumeKg": 5230.5, "sets": 18},
        "data": {"exercises": [{"exerciseId": "seed-squat", "sets": []}], "status": "finished"},
        "visibility": visibility,
        "updatedAt": iso(updated_at),
    }


def exercise_body(
    name: str = "Hip thrust en máquina", *, updated_at: datetime = T0, note: str | None = "Asiento 4"
) -> dict[str, Any]:
    return {
        "name": name,
        "primaryMuscle": "glutes",
        "equipment": "machine",
        "note": note,
        "updatedAt": iso(updated_at),
    }
