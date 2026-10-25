"""Verifies the Supabase Auth access token the app sends. The API never sees passwords."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt

from app.services.ports import UpstreamError

# Supabase's asymmetric JWT signing keys; the legacy shared secret (HS256) is not accepted.
ALGORITHMS = ["ES256", "RS256"]

KeyResolver = Callable[[str], Any]


class InvalidToken(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AuthUser:
    id: UUID
    email: str | None = None
    # Full name from Google / Apple, used as the first display name.
    name: str | None = None


def jwks_resolver(jwks_url: str) -> KeyResolver:
    """Fetches Supabase's public keys once and caches them (refetched when a new key id shows up)."""
    client = jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=3600, timeout=5)

    def resolve(token: str) -> Any:
        try:
            return client.get_signing_key_from_jwt(token).key
        except jwt.PyJWKClientConnectionError as error:
            raise UpstreamError("Supabase JWKS unreachable") from error

    return resolve


class TokenVerifier:
    def __init__(self, key_for: KeyResolver, *, issuer: str, audience: str) -> None:
        self._key_for = key_for
        self._issuer = issuer
        self._audience = audience

    def verify(self, token: str) -> AuthUser:
        """Blocking (it may fetch the keys): call it from a thread."""
        try:
            claims = jwt.decode(
                token,
                self._key_for(token),
                algorithms=ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
            # The anon key is a JWT too, but it has no user behind it.
            if claims.get("role") != "authenticated":
                raise InvalidToken("Not a user token")
            metadata = claims.get("user_metadata") or {}
            return AuthUser(
                id=UUID(claims["sub"]),
                email=claims.get("email"),
                name=metadata.get("full_name") or metadata.get("name"),
            )
        except (jwt.PyJWTError, ValueError) as error:
            raise InvalidToken(str(error)) from error
