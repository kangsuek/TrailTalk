"""user_profile.email(대화 내용을 보낼 이메일 주소)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-19 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("user_profile", schema=None) as batch_op:
        # NULL이면 설정하지 않은 것(send_email 도구가 보내지 않는다)
        batch_op.add_column(sa.Column("email", sa.String(length=254), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("user_profile", schema=None) as batch_op:
        batch_op.drop_column("email")
