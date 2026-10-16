"""turn_latency

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-16 16:22:24.703107

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "turn_latency",
        sa.Column("turn_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("audio_bytes", sa.Integer(), nullable=True),
        sa.Column("upload_ms", sa.Integer(), nullable=True),
        sa.Column("stt_ms", sa.Integer(), nullable=True),
        sa.Column("first_token_ms", sa.Integer(), nullable=True),
        sa.Column("first_sentence_ms", sa.Integer(), nullable=True),
        sa.Column("done_ms", sa.Integer(), nullable=True),
        sa.Column("speech_to_request_ms", sa.Integer(), nullable=True),
        sa.Column("request_to_playback_ms", sa.Integer(), nullable=True),
        sa.Column("first_sound_notice", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["conversation_session.id"],
            name=op.f("fk_turn_latency_session_id_conversation_session"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("turn_id", name=op.f("pk_turn_latency")),
    )
    with op.batch_alter_table("turn_latency", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_turn_latency_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_turn_latency_session_id"), ["session_id"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("turn_latency", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_turn_latency_session_id"))
        batch_op.drop_index(batch_op.f("ix_turn_latency_created_at"))

    op.drop_table("turn_latency")
