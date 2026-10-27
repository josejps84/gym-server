"""Which app tutorials each user has seen, shared by their devices.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tutorial_progress",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("entries", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["profiles.id"], name=op.f("fk_tutorial_progress_user_id_profiles"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_tutorial_progress")),
    )
    op.execute("ALTER TABLE tutorial_progress ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("tutorial_progress")
