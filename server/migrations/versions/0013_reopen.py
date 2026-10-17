"""conversation_session.reopened_at, turn.greeting(끝난 대화 이어서 하기, S3-26)

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-18 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("conversation_session", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("turn", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("greeting", sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("turn", schema=None) as batch_op:
        batch_op.drop_column("greeting")
    with op.batch_alter_table("conversation_session", schema=None) as batch_op:
        batch_op.drop_column("reopened_at")
