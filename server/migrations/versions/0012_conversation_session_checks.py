"""conversation_session.checks(일지 '확인할 것', S3-24)

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-17 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("conversation_session", schema=None) as batch_op:
        batch_op.add_column(sa.Column("checks", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("conversation_session", schema=None) as batch_op:
        batch_op.drop_column("checks")
