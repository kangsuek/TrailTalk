"""S3-22 롤백: conversation_session.report, turn.sources 제거

0009를 지우지 않고 되돌리는 마이그레이션을 더한다(이미 0009까지 올린 DB도 이어서 올라가게).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-17 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("turn", schema=None) as batch_op:
        batch_op.drop_column("sources")
    with op.batch_alter_table("conversation_session", schema=None) as batch_op:
        batch_op.drop_column("report")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("conversation_session", schema=None) as batch_op:
        batch_op.add_column(sa.Column("report", sa.JSON(), nullable=True))
    with op.batch_alter_table("turn", schema=None) as batch_op:
        batch_op.add_column(sa.Column("sources", sa.JSON(), nullable=True))
