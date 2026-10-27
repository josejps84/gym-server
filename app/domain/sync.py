"""Copies of the user's own data (routines, sessions, custom exercises) uploaded from the phone.

The phone is the source of truth for this data: every record keeps the phone's UUID, and the
newest `updated_at` wins. Deletions are tombstones (`deleted_at`) so they reach other devices.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any
from uuid import UUID

from app.domain.visibility import Visibility

JsonObject = dict[str, Any]

# Routines shown on a profile.
FEATURED_MAX = 10


@dataclass(frozen=True, slots=True)
class RoutineRecord:
    id: UUID
    owner_id: UUID
    name: str
    exercises: list[JsonObject]
    data: JsonObject
    visibility: Visibility
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    change_seq: int = 0

    @property
    def is_shared(self) -> bool:
        return self.deleted_at is None and self.visibility != Visibility.PRIVATE


@dataclass(frozen=True, slots=True)
class SessionRecord:
    id: UUID
    user_id: UUID
    routine_id: str | None
    name: str
    started_at: datetime
    ended_at: datetime
    summary: JsonObject
    data: JsonObject
    visibility: Visibility
    updated_at: datetime
    deleted_at: datetime | None = None
    change_seq: int = 0

    @property
    def is_shared(self) -> bool:
        return self.deleted_at is None and self.visibility != Visibility.PRIVATE


@dataclass(frozen=True, slots=True)
class CustomExerciseRecord:
    id: UUID
    owner_id: UUID
    name: str
    primary_muscle: str
    equipment: str
    note: str | None
    updated_at: datetime
    deleted_at: datetime | None = None
    change_seq: int = 0


@dataclass(frozen=True, slots=True)
class Changes:
    """What changed after a cursor, for another device of the same user."""

    routines: list[RoutineRecord] = field(default_factory=list)
    sessions: list[SessionRecord] = field(default_factory=list)
    exercises: list[CustomExerciseRecord] = field(default_factory=list)
    cursor: int = 0
    has_more: bool = False


def should_replace(stored_updated_at: datetime | None, incoming_updated_at: datetime) -> bool:
    """Last writer wins; resending the same version is a no-op, so uploads are idempotent."""
    return stored_updated_at is None or incoming_updated_at > stored_updated_at


def exercise_ids(exercises: list[JsonObject]) -> list[str]:
    """Exercise ids a routine uses, in order and without repeats."""
    seen: dict[str, None] = {}
    for exercise in exercises:
        exercise_id = exercise.get("exerciseId")
        if isinstance(exercise_id, str):
            seen.setdefault(exercise_id, None)
    return list(seen)


def remap_exercises(exercises: list[JsonObject], new_ids: dict[str, str]) -> list[JsonObject]:
    """Points a copied routine at the copies of the owner's custom exercises."""
    return [
        {**exercise, "exerciseId": new_ids.get(exercise["exerciseId"], exercise["exerciseId"])}
        for exercise in exercises
    ]


def copy_routine(
    source: RoutineRecord, *, new_id: UUID, owner_id: UUID, now: datetime, new_exercise_ids: dict[str, str]
) -> RoutineRecord:
    return replace(
        source,
        id=new_id,
        owner_id=owner_id,
        exercises=remap_exercises(source.exercises, new_exercise_ids),
        visibility=Visibility.PRIVATE,
        created_at=now,
        updated_at=now,
        deleted_at=None,
        change_seq=0,
    )


@dataclass(frozen=True, slots=True)
class TutorialEntry:
    """Whether the user has seen one of the app's tutorials, and when that last changed."""

    done: bool
    changed_at: datetime


# Tutorial id -> entry. Ids are the app's: unknown ones are kept, for newer app versions.
TutorialEntries = dict[str, TutorialEntry]

TUTORIALS_MAX = 50


def merge_tutorials(stored: TutorialEntries, incoming: TutorialEntries) -> TutorialEntries:
    """Entry by entry, the latest change wins: a tutorial seen on one device and another replayed on
    a second device both survive. Same timestamp keeps the stored one, so uploads are idempotent."""
    merged = dict(stored)
    for tutorial_id, entry in incoming.items():
        current = merged.get(tutorial_id)
        if current is None or entry.changed_at > current.changed_at:
            merged[tutorial_id] = entry
    return merged
