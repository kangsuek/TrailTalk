"""대화 내용 이메일 발송(캐릭터의 send_email 도구, 설계서 FR-21).

받는 사람은 항상 프로필의 이메일 주소 하나다. 도구가 받는 사람을 인자로 받지 않으므로 검색 결과 속
지시로 다른 주소에 보내지 못한다. 메일 서버(SMTP) 정보는 서버 설정(.env)에만 둔다.
"""

import asyncio
import logging
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import ConversationSession, Note, NoteKind, Turn, TurnRole
from app.errors import AppError

logger = logging.getLogger("trailtalk.mail")

_KIND_LABELS = {NoteKind.IDEA: "아이디어", NoteKind.TODO: "할 일", NoteKind.MEMO: "메모"}
_TRANSCRIPT_MAX_CHARS = 100_000  # 아주 긴 대화는 뒤쪽만 보낸다(추출 한도와 같다)


class MailError(AppError):
    def __init__(self, message: str = "메일을 보내지 못했습니다.") -> None:
        super().__init__("mail_failed", message, 502)


def mail_configured(settings: Settings) -> bool:
    return bool(settings.smtp_host and (settings.smtp_from or settings.smtp_user))


def _sender(settings: Settings) -> str:
    return settings.smtp_from or settings.smtp_user or ""


def build_message(settings: Settings, to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr(("TrailTalk", _sender(settings)))
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    return message


# 실패한 단계별 확인할 것(로그에만 남긴다. 접속 직후 끊기는 오류만으로는 원인을 알기 어렵다)
_STAGE_HINTS = {
    "연결": "SMTP_HOST·SMTP_PORT를 확인하세요(방화벽·네트워크, ssl이면 SMTP_SECURITY 포함).",
    "암호화": "SMTP_PORT와 SMTP_SECURITY가 맞는지 확인하세요(587=starttls, 465=ssl).",
    "로그인": "SMTP_USER(Gmail은 전체 주소)와 SMTP_PASSWORD(Gmail은 앱 비밀번호)를 확인하세요.",
    "전송": "SMTP_FROM과 받는 주소가 메일 서버에서 허용되는지 확인하세요.",
}


def _deliver(settings: Settings, message: EmailMessage, stage: list[str]) -> None:
    """메일 서버에 접속해 보낸다. stage[0]에 지금 단계를 적어, 실패했을 때 어디서 막혔는지 안다."""
    host, port = settings.smtp_host or "", settings.smtp_port
    timeout = settings.smtp_timeout_s
    stage[0] = "연결"
    if settings.smtp_security == "ssl":
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(
            host, port, timeout=timeout, context=ssl.create_default_context()
        )
    else:
        smtp = smtplib.SMTP(host, port, timeout=timeout)
    with smtp:
        if settings.smtp_security == "starttls":
            stage[0] = "암호화"
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_user and settings.smtp_password:
            stage[0] = "로그인"
            smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        stage[0] = "전송"
        smtp.send_message(message)


async def send_mail(settings: Settings, to: str, subject: str, body: str) -> None:
    """메일 한 통을 보낸다. 실패하면 MailError(상세는 로그에만, 비밀번호는 남기지 않는다)."""
    if not mail_configured(settings):
        raise MailError("서버에 메일 보내기 설정이 없습니다.")
    message = build_message(settings, to, subject, body)
    stage = ["연결"]
    try:
        await asyncio.to_thread(_deliver, settings, message, stage)
    except (OSError, smtplib.SMTPException, ssl.SSLError, UnicodeError) as exc:
        logger.warning(
            "메일 발송 실패(단계=%s, %s): %s. %s",
            stage[0],
            type(exc).__name__,
            exc,
            _STAGE_HINTS.get(stage[0], ""),
        )
        raise MailError() from exc


def _local(moment: datetime, timezone: str) -> datetime:
    return moment.astimezone(ZoneInfo(timezone))


def _transcript_text(turns: list[Turn], user_name: str | None, persona_name: str) -> str:
    speakers = {TurnRole.USER: user_name or "나", TurnRole.ASSISTANT: persona_name}
    text = "\n".join(f"{speakers[t.role]}: {t.text}" for t in turns if t.text.strip())
    if len(text) > _TRANSCRIPT_MAX_CHARS:
        text = "…" + text[-_TRANSCRIPT_MAX_CHARS:]
    return text


async def compose_session_mail(
    db: AsyncSession,
    settings: Settings,
    session_id: str,
    *,
    user_name: str | None,
    persona_name: str,
    content: str | None = None,
    subject: str | None = None,
    include_transcript: bool = False,
) -> tuple[str, str]:
    """대화 한 개를 (제목, 본문)으로 만든다.

    content가 없으면 일지 요약(있을 때)·저장한 노트·전문을 정해진 형식으로 담는다. content가 있으면
    캐릭터가 사용자의 요청대로 쓴 글을 본문으로 하고, 전문은 include_transcript일 때만 덧붙인다.
    subject는 한 줄로 정리해 쓴다(없으면 대화 제목)."""
    convo = await db.get(ConversationSession, session_id)
    if convo is None:
        raise MailError("대화를 찾을 수 없습니다.")
    started = _local(convo.started_at, settings.timezone)
    heading = " ".join((subject or "").split()) or " ".join((convo.title or "").split())
    heading = heading or "대화 기록"
    turns = list(
        await db.scalars(select(Turn).where(Turn.session_id == session_id).order_by(Turn.seq))
    )
    transcript = _transcript_text(turns, user_name, persona_name)

    if content and content.strip():
        lines = [content.strip()]
        if include_transcript and transcript:
            lines += ["", "[대화]", transcript]
    else:
        notes = list(
            await db.scalars(
                select(Note).where(Note.session_id == session_id).order_by(Note.created_at, Note.id)
            )
        )
        lines = [heading, started.strftime("%Y-%m-%d %H:%M")]
        if convo.summary:
            lines += ["", "[요약]", *(line for line in convo.summary.splitlines() if line.strip())]
        if notes:
            lines += ["", "[저장한 노트]"]
            lines += [f"- ({_KIND_LABELS[n.kind]}) {n.content}" for n in notes]
        if transcript:
            lines += ["", "[대화]", transcript]
    return f"[TrailTalk] {heading} ({started.strftime('%m/%d')})", "\n".join(lines) + "\n"
