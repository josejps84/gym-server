"""Every profile is public for now: turn off private ones and accept the requests they had.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE profiles SET is_private = false WHERE is_private")
    op.execute("UPDATE follows SET status = 'active' WHERE status = 'pending'")


def downgrade() -> None:
    # Nothing to undo: which profiles were private is not kept.
    pass
