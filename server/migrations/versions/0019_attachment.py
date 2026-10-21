"""attachment 테이블(파일 첨부, FR-22)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-21 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "attachment",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("turn_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("mime", sa.String(length=100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("thumb_path", sa.String(length=500), nullable=True),
        sa.Column("chars", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["turn_id"], ["turn.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("attachment", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_attachment_turn_id"), ["turn_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("attachment")
