"""user_profile.chat_model(대화 모델 선택, S3-31)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-18 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("user_profile", schema=None) as batch_op:
        # NULL이면 서버 기본값(LLM_CHAT_MODEL)
        batch_op.add_column(sa.Column("chat_model", sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("user_profile", schema=None) as batch_op:
        batch_op.drop_column("chat_model")
