"""conversation_session.topics

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("conversation_session", schema=None) as batch_op:
        # 기존 행은 NULL(아직 분류 안 함)로 둔다. 새 대화는 앱이 빈 목록을 넣는다
        batch_op.add_column(sa.Column("topics", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("conversation_session", schema=None) as batch_op:
        batch_op.drop_column("topics")
