"""Interfaces the services depend on. Adapters live in app/repositories and app/integrations."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.activity import Activity, ActivityType
from app.domain.pagination import Cursor
from app.domain.profile import Profile
from app.domain.social import Connection, Follow, Report
from app.domain.sync import CustomExerciseRecord, RoutineRecord, SessionRecord
from app.domain.visibility import FollowStatus, Visibility


class ProfileRepository(Protocol):
    async def get(self, user_id: UUID) -> Profile | None: ...
    async def get_by_username(self, username: str) -> Profile | None: ...
    async def get_many(self, user_ids: Collection[UUID]) -> dict[UUID, Profile]: ...
    async def insert_if_absent(self, profile: Profile) -> bool:
        """False when the id or the username already exists."""
        ...

    async def update(self, profile: Profile) -> None:
        """Raises Conflict('username.taken') if another profile has the username."""
        ...

    async def delete(self, user_id: UUID) -> None: ...
    async def search(self, query: str, viewer_id: UUID, limit: int) -> list[Profile]:
        """Matches username or display name, skipping users blocked either way."""
        ...

    async def counts(self, user_id: UUID) -> tuple[int, int]:
        """Active followers and active following."""
        ...


class FollowRepository(Protocol):
    async def get(self, follower_id: UUID, followee_id: UUID) -> Follow | None: ...
    async def save(self, follow: Follow) -> None: ...
    async def delete(self, follower_id: UUID, followee_id: UUID) -> bool: ...
    async def accept_all_pending(self, followee_id: UUID) -> list[UUID]:
        """Accepts every request to the user; returns the new followers."""
        ...

    async def followers(
        self, user_id: UUID, status: FollowStatus, cursor: Cursor | None, limit: int
    ) -> list[Connection]: ...
    async def following(self, user_id: UUID, cursor: Cursor | None, limit: int) -> list[Connection]: ...


class BlockRepository(Protocol):
    async def add(self, blocker_id: UUID, blocked_id: UUID) -> None: ...
    async def remove(self, blocker_id: UUID, blocked_id: UUID) -> None: ...
    async def between(self, a: UUID, b: UUID) -> bool:
        """True if either user blocked the other."""
        ...

    async def blocked_by(self, blocker_id: UUID) -> list[Profile]: ...


class ReportRepository(Protocol):
    async def add(self, report: Report) -> None: ...


class RoutineRepository(Protocol):
    async def get(self, routine_id: UUID) -> RoutineRecord | None: ...
    async def get_many(self, routine_ids: Collection[UUID]) -> dict[UUID, RoutineRecord]: ...
    async def save(self, routine: RoutineRecord) -> RoutineRecord:
        """Inserts or replaces it and gives it a new change_seq."""
        ...

    async def changed_since(self, owner_id: UUID, seq: int, limit: int) -> list[RoutineRecord]: ...


class SessionRepository(Protocol):
    async def get(self, session_id: UUID) -> SessionRecord | None: ...
    async def get_many(self, session_ids: Collection[UUID]) -> dict[UUID, SessionRecord]: ...
    async def save(self, session: SessionRecord) -> SessionRecord: ...
    async def changed_since(self, user_id: UUID, seq: int, limit: int) -> list[SessionRecord]: ...


class ExerciseRepository(Protocol):
    async def get(self, exercise_id: UUID) -> CustomExerciseRecord | None: ...
    async def get_many(self, exercise_ids: Collection[UUID]) -> dict[UUID, CustomExerciseRecord]: ...
    async def save(self, exercise: CustomExerciseRecord) -> CustomExerciseRecord: ...
    async def changed_since(self, owner_id: UUID, seq: int, limit: int) -> list[CustomExerciseRecord]: ...


class FeaturedRoutineRepository(Protocol):
    async def ids_of(self, user_id: UUID) -> list[UUID]: ...
    async def replace(self, user_id: UUID, routine_ids: Sequence[UUID]) -> None: ...
    async def remove(self, routine_id: UUID) -> None: ...


class ActivityRepository(Protocol):
    async def upsert(self, activity: Activity) -> None:
        """Creates it, or only updates the visibility if the user already has one for that ref."""
        ...

    async def delete_for(self, user_id: UUID, type_: ActivityType, ref_id: UUID) -> None: ...
    async def by_user(
        self, user_id: UUID, levels: Collection[Visibility], cursor: Cursor | None, limit: int
    ) -> list[Activity]: ...
    async def feed(self, viewer_id: UUID, cursor: Cursor | None, limit: int) -> list[Activity]:
        """Followers / public activities of the users the viewer actively follows."""
        ...


class UnitOfWork(Protocol):
    profiles: ProfileRepository
    follows: FollowRepository
    blocks: BlockRepository
    reports: ReportRepository
    routines: RoutineRepository
    sessions: SessionRepository
    exercises: ExerciseRepository
    featured: FeaturedRoutineRepository
    activities: ActivityRepository

    async def commit(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SignedUpload:
    upload_url: str
    token: str
    expires_at: datetime


class AvatarStorage(Protocol):
    def public_url(self, path: str) -> str: ...
    async def create_upload_url(self, path: str) -> SignedUpload: ...
    async def delete(self, paths: Sequence[str]) -> None: ...
    async def list_paths(self, prefix: str) -> list[str]:
        """Paths of the objects under `prefix/`."""
        ...


class IdentityAdmin(Protocol):
    async def delete_user(self, user_id: UUID) -> None:
        """Removes the login; succeeds if it is already gone."""
        ...


class UpstreamError(Exception):
    """Supabase (Auth or Storage) failed or could not be reached."""
