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


def _deliver(settings: Settings, message: EmailMessage) -> None:
    host, port = settings.smtp_host or "", settings.smtp_port
    timeout = settings.smtp_timeout_s
    if settings.smtp_security == "ssl":
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(
            host, port, timeout=timeout, context=ssl.create_default_context()
        )
    else:
        smtp = smtplib.SMTP(host, port, timeout=timeout)
    with smtp:
        if settings.smtp_security == "starttls":
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_user and settings.smtp_password:
            smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        smtp.send_message(message)


async def send_mail(settings: Settings, to: str, subject: str, body: str) -> None:
    """메일 한 통을 보낸다. 실패하면 MailError(상세는 로그에만, 비밀번호는 남기지 않는다)."""
    if not mail_configured(settings):
        raise MailError("서버에 메일 보내기 설정이 없습니다.")
    message = build_message(settings, to, subject, body)
    try:
        await asyncio.to_thread(_deliver, settings, message)
    except (OSError, smtplib.SMTPException, ssl.SSLError, UnicodeError) as exc:
        logger.warning("메일 발송 실패(%s): %s", type(exc).__name__, exc)
        raise MailError() from exc


def _local(moment: datetime, timezone: str) -> datetime:
    return moment.astimezone(ZoneInfo(timezone))


async def compose_session_mail(
    db: AsyncSession,
    settings: Settings,
    session_id: str,
    *,
    user_name: str | None,
    persona_name: str,
) -> tuple[str, str]:
    """대화 한 개를 (제목, 본문)으로 만든다. 진행 중인 대화는 지금까지의 노트와 전문을 쓴다."""
    convo = await db.get(ConversationSession, session_id)
    if convo is None:
        raise MailError("대화를 찾을 수 없습니다.")
    started = _local(convo.started_at, settings.timezone)
    heading = convo.title or "대화 기록"
    notes = list(
        await db.scalars(
            select(Note).where(Note.session_id == session_id).order_by(Note.created_at, Note.id)
        )
    )
    turns = list(
        await db.scalars(select(Turn).where(Turn.session_id == session_id).order_by(Turn.seq))
    )

    lines = [heading, started.strftime("%Y-%m-%d %H:%M")]
    if convo.summary:
        lines += ["", "[요약]", *(line for line in convo.summary.splitlines() if line.strip())]
    if notes:
        lines += ["", "[저장한 노트]"]
        lines += [f"- ({_KIND_LABELS[n.kind]}) {n.content}" for n in notes]
    speakers = {TurnRole.USER: user_name or "나", TurnRole.ASSISTANT: persona_name}
    transcript = [f"{speakers[t.role]}: {t.text}" for t in turns if t.text.strip()]
    if transcript:
        text = "\n".join(transcript)
        if len(text) > _TRANSCRIPT_MAX_CHARS:
            text = "…" + text[-_TRANSCRIPT_MAX_CHARS:]
        lines += ["", "[대화]", text]
    subject = f"[TrailTalk] {' '.join(heading.split())} ({started.strftime('%m/%d')})"
    return subject, "\n".join(lines) + "\n"
