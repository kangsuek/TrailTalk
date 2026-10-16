"""conversation_session.title_edited

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-17 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("conversation_session", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("title_edited", sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("conversation_session", schema=None) as batch_op:
        batch_op.drop_column("title_edited")
