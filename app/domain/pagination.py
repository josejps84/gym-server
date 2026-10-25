import base64
import binascii
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.errors import Invalid

PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class Cursor:
    """Keyset position: the (created_at, id) of the last item already returned, newest first."""

    created_at: datetime
    id: UUID

    def encode(self) -> str:
        raw = f"{self.created_at.isoformat()}|{self.id}".encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def decode(token: str) -> "Cursor":
        try:
            raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
            created_at, id_ = raw.split("|")
            return Cursor(datetime.fromisoformat(created_at), UUID(id_))
        except (binascii.Error, UnicodeDecodeError, ValueError) as error:
            raise Invalid("cursor.invalid", "Invalid cursor") from error


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: list[T]
    next_cursor: str | None


def page_of[T](items: list[T], limit: int, cursor_of: Callable[[T], Cursor]) -> Page[T]:
    """`items` was fetched with limit + 1 rows: the extra one only says there is a next page."""
    if len(items) <= limit:
        return Page(items, None)
    kept = items[:limit]
    return Page(kept, cursor_of(kept[-1]).encode())
