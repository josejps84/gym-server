"""Reactions (💪) to the activity in the feed.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "activity_reactions",
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activities.id"],
            name=op.f("fk_activity_reactions_activity_id_activities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["profiles.id"], name=op.f("fk_activity_reactions_user_id_profiles"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("activity_id", "user_id", name=op.f("pk_activity_reactions")),
    )
    op.create_index(op.f("ix_activity_reactions_user_id"), "activity_reactions", ["user_id"], unique=False)
    op.execute("ALTER TABLE activity_reactions ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index(op.f("ix_activity_reactions_user_id"), table_name="activity_reactions")
    op.drop_table("activity_reactions")
