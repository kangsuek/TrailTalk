"""user_profile.speaking_rate

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("user_profile", schema=None) as batch_op:
        # 말 속도(S3-18 설정 화면). NULL이면 캐릭터(페르소나 YAML) 기본값
        batch_op.add_column(sa.Column("speaking_rate", sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("user_profile", schema=None) as batch_op:
        batch_op.drop_column("speaking_rate")
