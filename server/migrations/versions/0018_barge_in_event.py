"""barge_in_event 테이블(끼어들기 기록, V2-M0-05)

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-20 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "barge_in_event",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("turn_id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("probe_to_confirm_ms", sa.Integer(), nullable=True),
        sa.Column("stop_ms", sa.Integer(), nullable=True),
        sa.Column("played_ratio", sa.Float(), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("next_turn_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("barge_in_event", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_barge_in_event_occurred_at"), ["occurred_at"])
        batch_op.create_index(batch_op.f("ix_barge_in_event_session_id"), ["session_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("barge_in_event")
