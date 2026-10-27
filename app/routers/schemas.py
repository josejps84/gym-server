"""Request and response bodies. JSON uses camelCase, like the app's TypeScript."""

from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from app.domain.activity import ActivityType
from app.domain.profile import Profile
from app.domain.social import Connection, ReportReason
from app.domain.sync import (
    TUTORIALS_MAX,
    CustomExerciseRecord,
    RoutineRecord,
    SessionRecord,
    TutorialEntries,
    TutorialEntry,
)
from app.domain.visibility import FollowStatus, Visibility

NAME_MAX = 100
ROUTINE_EXERCISES_MAX = 50


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class OpenApiModel(ApiModel):
    """Keeps fields the server doesn't know, so newer app versions don't lose data."""

    model_config = ConfigDict(extra="allow")


# --- Profiles ---------------------------------------------------------------------------------


class ProfileCard(ApiModel):
    id: UUID
    username: str
    display_name: str
    avatar_url: str | None

    @classmethod
    def of(cls, profile: Profile) -> "ProfileCard":
        return cls(
            id=profile.id,
            username=profile.username,
            display_name=profile.display_name,
            avatar_url=profile.avatar_url,
        )


class ConnectionOut(ProfileCard):
    since: datetime

    @classmethod
    def of_connection(cls, connection: Connection) -> "ConnectionOut":
        return cls(**ProfileCard.of(connection.profile).model_dump(), since=connection.since)


class MeOut(ApiModel):
    id: UUID
    username: str
    display_name: str
    bio: str
    avatar_url: str | None
    is_private: bool
    created_at: datetime
    followers_count: int
    following_count: int
    featured_routine_ids: list[UUID]


class ProfilePatchIn(ApiModel):
    username: str | None = None
    display_name: str | None = None
    bio: str | None = None
    # Every profile is public for now: no isPrivate here (the rest of the private-profile logic stays).
    # null removes the photo.
    avatar_url: str | None = None


class AvatarUploadIn(ApiModel):
    content_type: Literal["image/jpeg", "image/png", "image/webp"]


class AvatarUploadOut(ApiModel):
    """PUT the image to uploadUrl (or use supabase-js uploadToSignedUrl with the token), then
    PATCH /me with avatarUrl."""

    upload_url: str
    token: str
    avatar_url: str
    expires_at: datetime


class RelationshipOut(ApiModel):
    following: FollowStatus | None
    followed_by: bool


class PublicExerciseOut(ApiModel):
    id: UUID
    name: str
    primary_muscle: str
    equipment: str

    @classmethod
    def of(cls, exercise: CustomExerciseRecord) -> "PublicExerciseOut":
        return cls(
            id=exercise.id,
            name=exercise.name,
            primary_muscle=exercise.primary_muscle,
            equipment=exercise.equipment,
        )


# --- Routines, sessions, exercises (sync) -----------------------------------------------------


class RoutineExerciseIn(OpenApiModel):
    exercise_id: Annotated[str, Field(min_length=1, max_length=64)]
    target_sets: Annotated[int, Field(ge=1, le=20)]
    target_reps: Annotated[int, Field(ge=1, le=100)]
    rest_seconds: Annotated[int, Field(ge=0, le=900)]


class RoutineIn(ApiModel):
    name: Annotated[str, Field(min_length=1, max_length=NAME_MAX)]
    exercises: Annotated[list[RoutineExerciseIn], Field(max_length=ROUTINE_EXERCISES_MAX)]
    # The routine's other app fields (warm-up, cool-down, subtype, level...), kept as they come.
    data: dict[str, Any] = {}
    visibility: Visibility = Visibility.PRIVATE
    created_at: AwareDatetime
    updated_at: AwareDatetime
    deleted_at: AwareDatetime | None = None


class RoutineOut(ApiModel):
    id: UUID
    owner_id: UUID
    name: str
    exercises: list[dict[str, Any]]
    data: dict[str, Any]
    visibility: Visibility
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    @classmethod
    def of(cls, routine: RoutineRecord) -> "RoutineOut":
        return cls(
            id=routine.id,
            owner_id=routine.owner_id,
            name=routine.name,
            exercises=routine.exercises,
            data=routine.data,
            visibility=routine.visibility,
            created_at=routine.created_at,
            updated_at=routine.updated_at,
            deleted_at=routine.deleted_at,
        )


class SessionSummary(OpenApiModel):
    duration_seconds: Annotated[int, Field(ge=0)]
    volume_kg: Annotated[float, Field(ge=0)]
    sets: Annotated[int, Field(ge=0)]


class SessionIn(ApiModel):
    routine_id: Annotated[str | None, Field(max_length=64)] = None
    name: Annotated[str, Field(min_length=1, max_length=NAME_MAX)]
    started_at: AwareDatetime
    ended_at: AwareDatetime
    summary: SessionSummary
    # The whole session as the app stores it; only its owner gets it back.
    data: dict[str, Any] = {}
    visibility: Visibility = Visibility.PRIVATE
    updated_at: AwareDatetime
    deleted_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def ends_after_start(self) -> Self:
        if self.ended_at < self.started_at:
            raise ValueError("endedAt is before startedAt")
        return self


class SessionOut(ApiModel):
    id: UUID
    routine_id: str | None
    name: str
    started_at: datetime
    ended_at: datetime
    summary: dict[str, Any]
    data: dict[str, Any]
    visibility: Visibility
    updated_at: datetime
    deleted_at: datetime | None

    @classmethod
    def of(cls, session: SessionRecord) -> "SessionOut":
        return cls(
            id=session.id,
            routine_id=session.routine_id,
            name=session.name,
            started_at=session.started_at,
            ended_at=session.ended_at,
            summary=session.summary,
            data=session.data,
            visibility=session.visibility,
            updated_at=session.updated_at,
            deleted_at=session.deleted_at,
        )


class ExerciseIn(ApiModel):
    name: Annotated[str, Field(min_length=1, max_length=NAME_MAX)]
    primary_muscle: Annotated[str, Field(min_length=1, max_length=32)]
    equipment: Annotated[str, Field(min_length=1, max_length=32)]
    note: Annotated[str | None, Field(max_length=500)] = None
    updated_at: AwareDatetime
    deleted_at: AwareDatetime | None = None


class ExerciseOut(PublicExerciseOut):
    note: str | None
    updated_at: datetime
    deleted_at: datetime | None

    @classmethod
    def of(cls, exercise: CustomExerciseRecord) -> "ExerciseOut":
        return cls(
            **PublicExerciseOut.of(exercise).model_dump(),
            note=exercise.note,
            updated_at=exercise.updated_at,
            deleted_at=exercise.deleted_at,
        )


class ChangesOut(ApiModel):
    routines: list[RoutineOut]
    sessions: list[SessionOut]
    exercises: list[ExerciseOut]
    # Send it back as ?since= next time.
    cursor: str
    # True if there is more to download right away.
    has_more: bool


class FeaturedRoutinesIn(ApiModel):
    routine_ids: list[UUID]


class FeaturedRoutinesOut(ApiModel):
    routine_ids: list[UUID]


class RoutineDetailOut(ApiModel):
    routine: RoutineOut
    owner: ProfileCard
    exercises: list[PublicExerciseOut]


class CopiedRoutineOut(ApiModel):
    routine: RoutineOut
    exercises: list[ExerciseOut]


class PublicProfileOut(ProfileCard):
    bio: str
    is_private: bool
    followers_count: int
    following_count: int
    relationship: RelationshipOut
    content_visible: bool
    featured_routines: list[RoutineOut]
    exercises: list[PublicExerciseOut]


# --- Social -----------------------------------------------------------------------------------


class FollowOut(ApiModel):
    status: FollowStatus


class ReportIn(ApiModel):
    reason: ReportReason
    details: Annotated[str, Field(max_length=1000)] = ""


class WorkoutOut(ApiModel):
    session_id: UUID
    name: str
    routine_id: str | None
    started_at: datetime
    ended_at: datetime
    summary: dict[str, Any]


class SharedRoutineOut(ApiModel):
    id: UUID
    name: str
    exercise_count: int


class ActivityOut(ApiModel):
    id: UUID
    type: ActivityType
    created_at: datetime
    actor: ProfileCard
    workout: WorkoutOut | None = None
    routine: SharedRoutineOut | None = None
    user: ProfileCard | None = None


class UserList(ApiModel):
    items: list[ProfileCard]


class Paged[T](ApiModel):
    items: list[T]
    next_cursor: str | None


class Health(ApiModel):
    status: Literal["ok"]


# --- Tutorials --------------------------------------------------------------------------------

TutorialId = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")]


class TutorialEntryIn(ApiModel):
    done: bool
    changed_at: AwareDatetime


class TutorialsIn(ApiModel):
    entries: Annotated[dict[TutorialId, TutorialEntryIn], Field(max_length=TUTORIALS_MAX)]

    def to_entries(self) -> TutorialEntries:
        return {
            tutorial_id: TutorialEntry(done=entry.done, changed_at=entry.changed_at)
            for tutorial_id, entry in self.entries.items()
        }


class TutorialEntryOut(ApiModel):
    done: bool
    changed_at: datetime


class TutorialsOut(ApiModel):
    entries: dict[str, TutorialEntryOut]

    @classmethod
    def of(cls, entries: TutorialEntries) -> "TutorialsOut":
        return cls(
            entries={
                tutorial_id: TutorialEntryOut(done=entry.done, changed_at=entry.changed_at)
                for tutorial_id, entry in entries.items()
            }
        )
