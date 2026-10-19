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
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
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
    # 끝난 대화를 마지막으로 다시 연 시각(S3-26). 일지 날짜는 started_at 그대로 두고, 프롬프트의
    # 대화 시작 시각·마무리 멘트의 "이번에 남긴 노트" 기준으로 쓴다. 다시 연 적이 없으면 NULL
    reopened_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[SessionStatus] = mapped_column(
        _enum(SessionStatus, "session_status"), default=SessionStatus.ACTIVE
    )
    mode: Mapped[ConversationMode] = mapped_column(
        _enum(ConversationMode, "conversation_mode"),
        default=ConversationMode.TEXT,
        server_default=ConversationMode.TEXT.value,
    )
    title: Mapped[str | None] = mapped_column(String(200))
    # 사용자가 일지 목록에서 제목을 고쳤다. 일지를 다시 정리해도(늦게 온 턴·다시 정리) 제목은
    # 그대로 둔다
    title_edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    summary: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=list)
    # 이 대화에서 다룬 아이디어의 주제 이름(일지 정리 때 기존 주제에서 고른다). 일지 목록의
    # 아이디어별 보기가 같은 이름끼리 묶는다(S3-17). NULL은 주제가 생기기 전에 정리해 아직 분류하지
    # 않은 대화다(app/jobs/topics_backfill.py가 채운다). 빈 목록은 분류했지만 아이디어가 없는 것이다
    topics: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(JSON(none_as_null=True)), default=list
    )
    # 일지 인용(S3-23): 요약 줄마다 근거 출처 URL 목록과 출처 제목 [{title, url}]. 번호는 조회할
    # 때 남은 요약·메모 기준으로 매긴다(app/jobs/extract.number_citations). 출처가 없으면 NULL
    summary_cites: Mapped[list | None] = mapped_column(JSON(none_as_null=True))
    citations: Mapped[list | None] = mapped_column(JSON(none_as_null=True))
    # 확인할 것(S3-24): 정해지지 않았거나 찾지 못했거나 원문 확인이 필요한 것. 새 형식으로 정리한
    # 일지는 빈 목록이라도 [], NULL이면 예전 형식이다(요약 첫 줄이 결론이 아니다)
    checks: Mapped[list | None] = mapped_column(JSON(none_as_null=True))
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
    # 캐릭터 답변이 웹 검색·페이지 읽기로 본 출처 [{title, url}](S3-23, 일지 인용용). 없으면 NULL
    sources: Mapped[list | None] = mapped_column(JSON(none_as_null=True))
    interrupted: Mapped[bool] = mapped_column(Boolean, default=False)
    # 다시 연 대화의 인사말(S3-26). 첫 인사말(seq 0)처럼 끼어들어도 자르지 않는다
    greeting: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    session: Mapped[ConversationSession] = relationship(back_populates="turns")


class TurnLatency(Base):
    """음성 턴의 지연 측정(계획서 S3-07, NFR-01). ms 단위, 서버가 요청 처리를 시작한 때 기준이다
    (upload_ms에는 세션 확인 같은 앞 단계도 들어 있다). 웹이 말 끝 → 요청, 요청 → 첫 소리를 재서
    보고한다.

    turn_id는 캐릭터 답변 턴 ID다. 답변 행은 첫 문장 때 생기고 오류로 끝나면 없을 수도 있어
    외래 키를 두지 않는다.
    """

    __tablename__ = "turn_latency"

    turn_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("conversation_session.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    audio_bytes: Mapped[int | None] = mapped_column(Integer)
    upload_ms: Mapped[int | None] = mapped_column(Integer)
    stt_ms: Mapped[int | None] = mapped_column(Integer)
    first_token_ms: Mapped[int | None] = mapped_column(Integer)
    first_sentence_ms: Mapped[int | None] = mapped_column(Integer)
    done_ms: Mapped[int | None] = mapped_column(Integer)
    speech_to_request_ms: Mapped[int | None] = mapped_column(Integer)
    request_to_playback_ms: Mapped[int | None] = mapped_column(Integer)
    # 첫 소리가 답변 문장이 아니라 검색 안내 음성이었다(검색 턴은 답변 지연이 가려진다)
    first_sound_notice: Mapped[bool | None] = mapped_column(Boolean)


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
    # 메모의 근거 출처 URL 목록(S3-23, 번호는 조회할 때 매긴다). 없으면 NULL
    cites: Mapped[list | None] = mapped_column(JSON(none_as_null=True))
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
    voice: Mapped[str | None] = mapped_column(String(100))  # OpenAI 보이스(null이면 캐릭터 기본)
    speaking_rate: Mapped[float | None] = mapped_column(Float)  # 말 속도(null이면 캐릭터 기본)
    # 대화 모델(S3-31, haiku·sonnet·opus). null이면 서버 기본값(LLM_CHAT_MODEL)
    chat_model: Mapped[str | None] = mapped_column(String(20))
    # 대화 내용을 보낼 본인 이메일 주소(캐릭터의 send_email 도구). null이면 설정 안 함
    email: Mapped[str | None] = mapped_column(String(254))
    keep_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
