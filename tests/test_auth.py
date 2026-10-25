from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.auth import InvalidToken
from app.main import create_app
from tests.conftest import (
    FakeIdentity,
    FakeStorage,
    build_test_container,
    make_token,
    verifier_for_tests,
)


def test_valid_token_gives_the_user() -> None:
    user_id = uuid4()
    user = verifier_for_tests().verify(make_token(user_id, name="José Piñeros"))
    assert user.id == user_id
    assert user.name == "José Piñeros"


@pytest.mark.parametrize(
    "claims",
    [
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"aud": "anon"},
        {"iss": "https://evil.test/auth/v1"},
        {"role": "anon"},
        {"sub": "not-a-uuid"},
    ],
)
def test_rejects_bad_claims(claims: dict[str, Any]) -> None:
    with pytest.raises(InvalidToken):
        verifier_for_tests().verify(make_token(uuid4(), **claims))


def test_rejects_other_signers_and_symmetric_tokens() -> None:
    other = jwt.encode({"sub": str(uuid4())}, ec.generate_private_key(ec.SECP256R1()), algorithm="ES256")
    hs256 = jwt.encode({"sub": str(uuid4())}, "a-shared-secret-that-is-long-enough!", algorithm="HS256")
    for token in (other, hs256, "garbage"):
        with pytest.raises(InvalidToken):
            verifier_for_tests().verify(token)


async def test_api_needs_a_token(client: httpx.AsyncClient) -> None:
    assert (await client.get("/me")).status_code == 401
    bad = await client.get("/me", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401
    assert bad.headers["www-authenticate"] == "Bearer"


async def test_health_needs_no_token(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_rate_limit_per_user(engine: object, clean_db: None) -> None:
    app = create_app(build_test_container(engine, FakeStorage(), FakeIdentity(), rate_limit=2))  # type: ignore[arg-type]
    headers = {"Authorization": f"Bearer {make_token(uuid4())}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        assert (await http.get("/me", headers=headers)).status_code == 200
        assert (await http.get("/me", headers=headers)).status_code == 200
        limited = await http.get("/me", headers=headers)
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) > 0
        other = {"Authorization": f"Bearer {make_token(uuid4())}"}
        assert (await http.get("/me", headers=other)).status_code == 200


async def test_rejects_big_bodies(client: httpx.AsyncClient) -> None:
    response = await client.put(
        f"/me/routines/{uuid4()}",
        content=b"{" + b" " * 1_000_001 + b"}",
        headers={"Authorization": f"Bearer {make_token(uuid4())}", "Content-Type": "application/json"},
    )
    assert response.status_code == 413
