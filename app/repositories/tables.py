"""Database schema. Alembic migrations must keep matching it (tests/test_migrations.py checks)."""

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    Sequence,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

VISIBILITIES = "'private', 'followers', 'public'"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: DateTime(timezone=True), dict[str, Any]: JSONB}


# One counter for every synced table: /me/changes returns rows with a higher value than the cursor.
CHANGE_SEQ = Sequence("sync_change_seq", metadata=Base.metadata)


def _profile_fk() -> Any:
    return ForeignKey("profiles.id", ondelete="CASCADE")


class ProfileRow(Base):
    __tablename__ = "profiles"

    # Same id as the Supabase Auth user.
    id: Mapped[UUID] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text, server_default="")
    bio: Mapped[str] = mapped_column(Text, server_default="")
    avatar_url: Mapped[str | None] = mapped_column(Text)
    is_private: Mapped[bool] = mapped_column(server_default="false")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        # Prefix search (LIKE 'abc%') whatever the database collation.
        Index("ix_profiles_username_pattern", "username", postgresql_ops={"username": "text_pattern_ops"}),
    )


class FollowRow(Base):
    __tablename__ = "follows"

    follower_id: Mapped[UUID] = mapped_column(_profile_fk(), primary_key=True)
    followee_id: Mapped[UUID] = mapped_column(_profile_fk(), primary_key=True)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('active', 'pending')", name="status"),
        CheckConstraint("follower_id <> followee_id", name="not_self"),
        Index("ix_follows_followee_id_status", "followee_id", "status"),
    )


class BlockRow(Base):
    __tablename__ = "blocks"

    blocker_id: Mapped[UUID] = mapped_column(_profile_fk(), primary_key=True)
    blocked_id: Mapped[UUID] = mapped_column(_profile_fk(), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ReportRow(Base):
    __tablename__ = "reports"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    reporter_id: Mapped[UUID] = mapped_column(_profile_fk(), index=True)
    target_user_id: Mapped[UUID] = mapped_column(_profile_fk(), index=True)
    reason: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(Text, server_default="")
    # Reviewed by hand from the Supabase table editor: open -> resolved.
    status: Mapped[str] = mapped_column(Text, server_default="open")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RoutineRow(Base):
    __tablename__ = "routines"

    # UUID generated on the phone.
    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(_profile_fk())
    name: Mapped[str] = mapped_column(Text)
    exercises: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    # Remaining app fields (warm-up, cool-down, subtype, level...), opaque to the server.
    data: Mapped[dict[str, Any]]
    visibility: Mapped[str] = mapped_column(Text, server_default="private")
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None]
    change_seq: Mapped[int] = mapped_column(BigInteger, CHANGE_SEQ, server_default=CHANGE_SEQ.next_value())

    __table_args__ = (
        CheckConstraint(f"visibility IN ({VISIBILITIES})", name="visibility"),
        Index("ix_routines_owner_id_change_seq", "owner_id", "change_seq"),
    )


class CustomExerciseRow(Base):
    __tablename__ = "custom_exercises"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(_profile_fk())
    name: Mapped[str] = mapped_column(Text)
    primary_muscle: Mapped[str] = mapped_column(Text)
    equipment: Mapped[str] = mapped_column(Text)
    # Personal note: only the owner sees it.
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None]
    change_seq: Mapped[int] = mapped_column(BigInteger, CHANGE_SEQ, server_default=CHANGE_SEQ.next_value())

    __table_args__ = (Index("ix_custom_exercises_owner_id_change_seq", "owner_id", "change_seq"),)


class TutorialProgressRow(Base):
    __tablename__ = "tutorial_progress"

    user_id: Mapped[UUID] = mapped_column(_profile_fk(), primary_key=True)
    # {tutorialId: {"done": bool, "changedAt": ISO}}
    entries: Mapped[dict[str, Any]]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class WorkoutSessionRow(Base):
    __tablename__ = "workout_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(_profile_fk())
    # Not a foreign key: suggested routines ship with the app and are not uploaded.
    routine_id: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime]
    # Duration, volume, number of sets: what the feed shows.
    summary: Mapped[dict[str, Any]]
    # The whole session as the app stores it: only the owner reads it.
    data: Mapped[dict[str, Any]]
    visibility: Mapped[str] = mapped_column(Text, server_default="private")
    updated_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None]
    change_seq: Mapped[int] = mapped_column(BigInteger, CHANGE_SEQ, server_default=CHANGE_SEQ.next_value())

    __table_args__ = (
        CheckConstraint(f"visibility IN ({VISIBILITIES})", name="visibility"),
        Index("ix_workout_sessions_user_id_change_seq", "user_id", "change_seq"),
    )


class FeaturedRoutineRow(Base):
    __tablename__ = "profile_featured_routines"

    user_id: Mapped[UUID] = mapped_column(_profile_fk(), primary_key=True)
    routine_id: Mapped[UUID] = mapped_column(
        ForeignKey("routines.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int]

    __table_args__ = (UniqueConstraint("user_id", "position"),)


class ActivityRow(Base):
    __tablename__ = "activities"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(_profile_fk())
    type: Mapped[str] = mapped_column(Text)
    ref_id: Mapped[UUID]
    visibility: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint("type IN ('workout_completed', 'routine_shared', 'started_following')", name="type"),
        CheckConstraint(f"visibility IN ({VISIBILITIES})", name="visibility"),
        # One activity per thing: sharing a routine again updates the existing one.
        UniqueConstraint("user_id", "type", "ref_id"),
        Index("ix_activities_ref_id", "ref_id"),
    )


# Newest-first lists: a user's sessions, a user's activity and the feed.
Index(
    "ix_workout_sessions_user_id_started_at",
    WorkoutSessionRow.user_id,
    WorkoutSessionRow.started_at.desc(),
)
Index(
    "ix_activities_user_id_created_at",
    ActivityRow.user_id,
    ActivityRow.created_at.desc(),
    ActivityRow.id.desc(),
)
