"""conversation_session.report, turn.sources

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-17 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("conversation_session", schema=None) as batch_op:
        batch_op.add_column(sa.Column("report", sa.JSON(), nullable=True))
    with op.batch_alter_table("turn", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sources", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("turn", schema=None) as batch_op:
        batch_op.drop_column("sources")
    with op.batch_alter_table("conversation_session", schema=None) as batch_op:
        batch_op.drop_column("report")
