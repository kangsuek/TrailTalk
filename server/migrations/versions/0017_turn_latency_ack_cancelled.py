"""turn_latency 맞장구 시각(ack_ms)과 직전에 취소된 턴(cancelled_turn_id)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-20 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("ack_ms", sa.Integer()),
    ("cancelled_turn_id", sa.String(length=36)),
)


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("turn_latency", schema=None) as batch_op:
        # 모두 NULL 허용: 이전 행은 값이 없다
        for name, type_ in _COLUMNS:
            batch_op.add_column(sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("turn_latency", schema=None) as batch_op:
        for name, _ in reversed(_COLUMNS):
            batch_op.drop_column(name)
