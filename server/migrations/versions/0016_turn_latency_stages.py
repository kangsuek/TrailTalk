"""turn_latency 세부 계측 컬럼(합성·도구·CLI 재기동·취소 대기)

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-20 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("open_llm_ms", sa.Integer()),
    ("cli_resumed", sa.Boolean()),
    ("cli_age_ms", sa.Integer()),
    ("first_queued_ms", sa.Integer()),
    ("first_synth_ms", sa.Integer()),
    ("synth_wait_ms", sa.Integer()),
    ("sentence_count", sa.Integer()),
    ("reply_chars", sa.Integer()),
    ("tool_count", sa.Integer()),
    ("search_used", sa.Boolean()),
    ("cli_abort", sa.String(length=16)),
    ("cancel_wait_ms", sa.Integer()),
    ("cancel_outcome", sa.String(length=16)),
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
