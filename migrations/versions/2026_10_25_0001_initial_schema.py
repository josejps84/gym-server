"""Initial schema: profiles, follows, blocks, reports, synced data, featured routines, activities.

Revision ID: 0001
Revises:
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = [
    "profiles",
    "follows",
    "blocks",
    "reports",
    "routines",
    "custom_exercises",
    "workout_sessions",
    "profile_featured_routines",
    "activities",
]
VISIBILITIES = "visibility IN ('private', 'followers', 'public')"
NOW = sa.text("now()")
CHANGE_SEQ = sa.text("nextval('sync_change_seq')")


def _profile_fk(column: str, table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([column], ["profiles.id"], name=f"fk_{table}_{column}_profiles", ondelete="CASCADE")


def upgrade() -> None:
    op.execute(sa.schema.CreateSequence(sa.Sequence("sync_change_seq")))

    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), server_default="", nullable=False),
        sa.Column("bio", sa.Text(), server_default="", nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("is_private", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_profiles"),
        sa.UniqueConstraint("username", name="uq_profiles_username"),
    )
    op.create_index(
        "ix_profiles_username_pattern", "profiles", ["username"], postgresql_ops={"username": "text_pattern_ops"}
    )

    op.create_table(
        "follows",
        sa.Column("follower_id", sa.Uuid(), nullable=False),
        sa.Column("followee_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint("status IN ('active', 'pending')", name="ck_follows_status"),
        sa.CheckConstraint("follower_id <> followee_id", name="ck_follows_not_self"),
        _profile_fk("follower_id", "follows"),
        _profile_fk("followee_id", "follows"),
        sa.PrimaryKeyConstraint("follower_id", "followee_id", name="pk_follows"),
    )
    op.create_index("ix_follows_followee_id_status", "follows", ["followee_id", "status"])

    op.create_table(
        "blocks",
        sa.Column("blocker_id", sa.Uuid(), nullable=False),
        sa.Column("blocked_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        _profile_fk("blocker_id", "blocks"),
        _profile_fk("blocked_id", "blocks"),
        sa.PrimaryKeyConstraint("blocker_id", "blocked_id", name="pk_blocks"),
    )
    op.create_index("ix_blocks_blocked_id", "blocks", ["blocked_id"])

    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reporter_id", sa.Uuid(), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        _profile_fk("reporter_id", "reports"),
        _profile_fk("target_user_id", "reports"),
        sa.PrimaryKeyConstraint("id", name="pk_reports"),
    )
    op.create_index("ix_reports_reporter_id", "reports", ["reporter_id"])
    op.create_index("ix_reports_target_user_id", "reports", ["target_user_id"])

    op.create_table(
        "routines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("exercises", postgresql.JSONB(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("visibility", sa.Text(), server_default="private", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_seq", sa.BigInteger(), server_default=CHANGE_SEQ, nullable=False),
        sa.CheckConstraint(VISIBILITIES, name="ck_routines_visibility"),
        _profile_fk("owner_id", "routines"),
        sa.PrimaryKeyConstraint("id", name="pk_routines"),
    )
    op.create_index("ix_routines_owner_id_change_seq", "routines", ["owner_id", "change_seq"])

    op.create_table(
        "custom_exercises",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("primary_muscle", sa.Text(), nullable=False),
        sa.Column("equipment", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_seq", sa.BigInteger(), server_default=CHANGE_SEQ, nullable=False),
        _profile_fk("owner_id", "custom_exercises"),
        sa.PrimaryKeyConstraint("id", name="pk_custom_exercises"),
    )
    op.create_index("ix_custom_exercises_owner_id_change_seq", "custom_exercises", ["owner_id", "change_seq"])

    op.create_table(
        "workout_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("routine_id", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("visibility", sa.Text(), server_default="private", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_seq", sa.BigInteger(), server_default=CHANGE_SEQ, nullable=False),
        sa.CheckConstraint(VISIBILITIES, name="ck_workout_sessions_visibility"),
        _profile_fk("user_id", "workout_sessions"),
        sa.PrimaryKeyConstraint("id", name="pk_workout_sessions"),
    )
    op.create_index("ix_workout_sessions_user_id_change_seq", "workout_sessions", ["user_id", "change_seq"])
    op.create_index(
        "ix_workout_sessions_user_id_started_at", "workout_sessions", ["user_id", sa.text("started_at DESC")]
    )

    op.create_table(
        "profile_featured_routines",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("routine_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        _profile_fk("user_id", "profile_featured_routines"),
        sa.ForeignKeyConstraint(
            ["routine_id"],
            ["routines.id"],
            name="fk_profile_featured_routines_routine_id_routines",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "routine_id", name="pk_profile_featured_routines"),
        sa.UniqueConstraint("user_id", "position", name="uq_profile_featured_routines_user_id_position"),
    )
    op.create_index("ix_profile_featured_routines_routine_id", "profile_featured_routines", ["routine_id"])

    op.create_table(
        "activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("ref_id", sa.Uuid(), nullable=False),
        sa.Column("visibility", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "type IN ('workout_completed', 'routine_shared', 'started_following')", name="ck_activities_type"
        ),
        sa.CheckConstraint(VISIBILITIES, name="ck_activities_visibility"),
        _profile_fk("user_id", "activities"),
        sa.PrimaryKeyConstraint("id", name="pk_activities"),
        sa.UniqueConstraint("user_id", "type", "ref_id", name="uq_activities_user_id_type_ref_id"),
    )
    op.create_index("ix_activities_ref_id", "activities", ["ref_id"])
    op.create_index(
        "ix_activities_user_id_created_at",
        "activities",
        ["user_id", sa.text("created_at DESC"), sa.text("id DESC")],
    )

    # Supabase publishes the public schema through its Data API with the anon key. With RLS on and
    # no policies, nobody can read these tables that way; the API connects as the owner and is unaffected.
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute(sa.schema.DropSequence(sa.Sequence("sync_change_seq")))
