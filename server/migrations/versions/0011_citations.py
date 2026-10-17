"""일지 인용(S3-23): turn.sources, conversation_session.summary_cites·citations, note.cites

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-17 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("turn", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sources", sa.JSON(), nullable=True))
    with op.batch_alter_table("conversation_session", schema=None) as batch_op:
        batch_op.add_column(sa.Column("summary_cites", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("citations", sa.JSON(), nullable=True))
    with op.batch_alter_table("note", schema=None) as batch_op:
        batch_op.add_column(sa.Column("cites", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("note", schema=None) as batch_op:
        batch_op.drop_column("cites")
    with op.batch_alter_table("conversation_session", schema=None) as batch_op:
        batch_op.drop_column("citations")
        batch_op.drop_column("summary_cites")
    with op.batch_alter_table("turn", schema=None) as batch_op:
        batch_op.drop_column("sources")
