"""서버 DB 모델 (설계서 4.5).

ID는 UUID 문자열, 시각은 UTC다. 열거값은 SQLite에서도 CHECK 제약으로 막는다.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, new_id, utcnow


class SessionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class ConversationMode(StrEnum):
    """대화 방식. 프롬프트의 상황 블록이 달라진다(CLI 복구 때 같은 프롬프트를 다시 만든다)."""

    TEXT = "text"
    VOICE = "voice"


class ExtractStatus(StrEnum):
    """세션 종료 추출(일지 정리) 상태. 끝나지 않은 세션은 None이다."""

    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class TurnRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class NoteKind(StrEnum):
    IDEA = "idea"
    TODO = "todo"
    MEMO = "memo"


def _enum(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=16,
        values_callable=lambda members: [m.value for m in members],
    )


class ConversationSession(Base):
    __tablename__ = "conversation_session"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[SessionStatus] = mapped_column(
        _enum(SessionStatus, "session_status"), default=SessionStatus.ACTIVE
    )
    mode: Mapped[ConversationMode] = mapped_column(
        _enum(ConversationMode, "conversation_mode"),
        default=ConversationMode.TEXT,
        server_default=ConversationMode.TEXT.value,
    )
    title: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    extract_status: Mapped[ExtractStatus | None] = mapped_column(
        _enum(ExtractStatus, "extract_status")
    )
    # Claude CLI 프로세스가 죽었을 때 --resume으로 맥락을 잇는 값
    # (docs/spikes/claude-cli.md 5절)
    cli_session_id: Mapped[str | None] = mapped_column(String(64))
    # 세션을 처음 열 때 만든 시스템 프롬프트. CLI를 다시 띄울 때 같은 프롬프트를 쓴다
    # (그사이 프로필을 바꿔도 진행 중인 대화는 그대로)
    system_prompt: Mapped[str | None] = mapped_column(Text)

    turns: Mapped[list["Turn"]] = relationship(
        back_populates="session",
        order_by="Turn.seq",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    notes: Mapped[list["Note"]] = relationship(
        back_populates="session",
        order_by="Note.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Turn(Base):
    __tablename__ = "turn"
    __table_args__ = (UniqueConstraint("session_id", "seq"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_session.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[TurnRole] = mapped_column(_enum(TurnRole, "turn_role"))
    text: Mapped[str] = mapped_column(Text)
    audio_path: Mapped[str | None] = mapped_column(String(500))
    interrupted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    session: Mapped[ConversationSession] = relationship(back_populates="turns")


class Note(Base):
    __tablename__ = "note"
    __table_args__ = (Index("ix_note_kind_done", "kind", "done"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_session.id", ondelete="CASCADE"), index=True
    )
    turn_id: Mapped[str | None] = mapped_column(ForeignKey("turn.id", ondelete="SET NULL"))
    kind: Mapped[NoteKind] = mapped_column(_enum(NoteKind, "note_kind"))
    content: Mapped[str] = mapped_column(Text)
    starred: Mapped[bool] = mapped_column(Boolean, default=False)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    session: Mapped[ConversationSession] = relationship(back_populates="notes")


class Persona(Base):
    __tablename__ = "persona"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    yaml_path: Mapped[str] = mapped_column(String(500))
    version: Mapped[str] = mapped_column(String(64))  # YAML 내용 해시
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class UserProfile(Base):
    """본인용 단일 행(id=1). 서비스화(D6) 때 사용자 테이블로 바꾼다."""

    __tablename__ = "user_profile"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nickname: Mapped[str | None] = mapped_column(String(50))
    interests: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    persona_id: Mapped[str | None] = mapped_column(ForeignKey("persona.id", ondelete="SET NULL"))
    voice: Mapped[str | None] = mapped_column(String(100))
    keep_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
