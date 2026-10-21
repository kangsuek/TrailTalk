"""attachment.pages 컬럼(PDF 첨부 쪽수)

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-22 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("attachment", schema=None) as batch_op:
        batch_op.add_column(sa.Column("pages", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("attachment", schema=None) as batch_op:
        batch_op.drop_column("pages")
