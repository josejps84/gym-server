import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.errors import Invalid

USERNAME_MIN = 3
USERNAME_MAX = 30
DISPLAY_NAME_MAX = 50
BIO_MAX = 160

_USERNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._]*[a-z0-9])?$")


@dataclass(frozen=True, slots=True)
class Profile:
    id: UUID
    username: str
    display_name: str
    bio: str
    avatar_url: str | None
    is_private: bool
    created_at: datetime


def normalize_username(raw: str) -> str:
    """Usernames are case-insensitive: stored and compared in lowercase."""
    username = raw.strip().lower()
    if not USERNAME_MIN <= len(username) <= USERNAME_MAX:
        raise Invalid("username.length", f"Username must be {USERNAME_MIN}-{USERNAME_MAX} characters")
    if not _USERNAME_RE.match(username) or ".." in username:
        raise Invalid("username.format", "Use letters, digits, dots and underscores")
    return username


def normalize_display_name(raw: str) -> str:
    name = " ".join(raw.split())
    if len(name) > DISPLAY_NAME_MAX:
        raise Invalid("displayName.length", f"Display name is longer than {DISPLAY_NAME_MAX}")
    return name


def normalize_bio(raw: str) -> str:
    bio = raw.strip()
    if len(bio) > BIO_MAX:
        raise Invalid("bio.length", f"Bio is longer than {BIO_MAX}")
    return bio


def generated_username() -> str:
    """Placeholder given on the first login until the user picks one."""
    return f"user{secrets.randbelow(10**8):08d}"
