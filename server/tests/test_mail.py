"""대화 내용 이메일(app/services/mail.py)."""

import smtplib

import pytest

from app.db.models import ConversationSession, Note, NoteKind, Turn, TurnRole
from app.services import mail
from app.services.mail import MailError, build_message, compose_session_mail, send_mail


@pytest.fixture
def settings(make_settings):
    return make_settings(
        smtp_host="smtp.test", smtp_user="bot@test", smtp_password="secret", smtp_security="none"
    )


def test_mail_configured(make_settings):
    assert not mail.mail_configured(make_settings())
    assert not mail.mail_configured(make_settings(smtp_host="smtp.test"))  # 보내는 주소 없음
    assert mail.mail_configured(make_settings(smtp_host="smtp.test", smtp_from="a@b.co"))


def test_build_message_keeps_headers_clean(settings):
    message = build_message(settings, "me@example.com", "제목", "본문")
    assert message["To"] == "me@example.com" and "bot@test" in message["From"]
    assert message.get_content().strip() == "본문"
    with pytest.raises(ValueError):  # 줄바꿈으로 헤더를 끼워 넣을 수 없다
        build_message(settings, "me@example.com", "제목\nBcc: x@y.z", "본문")


class FakeSmtp:
    instances: list["FakeSmtp"] = []
    fail = False

    def __init__(self, host, port, timeout=None, **kwargs):
        self.host, self.port, self.log = host, port, []
        FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.log.append("starttls")

    def login(self, user, password):
        self.log.append(("login", user, password))

    def send_message(self, message):
        if FakeSmtp.fail:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials secret")
        self.log.append(("send", message["To"]))


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSmtp.instances, FakeSmtp.fail = [], False
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)


async def test_send_mail_logs_in_and_sends(settings):
    await send_mail(settings, "me@example.com", "제목", "본문")
    [smtp] = FakeSmtp.instances
    assert (smtp.host, smtp.port) == ("smtp.test", 587)
    assert smtp.log == [("login", "bot@test", "secret"), ("send", "me@example.com")]


async def test_send_mail_starttls(make_settings):
    settings = make_settings(smtp_host="smtp.test", smtp_from="bot@test")
    await send_mail(settings, "me@example.com", "제목", "본문")
    assert FakeSmtp.instances[0].log == ["starttls", ("send", "me@example.com")]


async def test_send_mail_failure_hides_details(settings, caplog):
    FakeSmtp.fail = True
    with pytest.raises(MailError) as info:
        await send_mail(settings, "me@example.com", "제목", "본문")
    assert "secret" not in info.value.message and info.value.status_code == 502


async def test_send_mail_without_server_settings(make_settings):
    with pytest.raises(MailError):
        await send_mail(make_settings(), "me@example.com", "제목", "본문")
    assert FakeSmtp.instances == []


async def test_compose_session_mail(db_session, make_settings):
    settings = make_settings()
    convo = ConversationSession(title="산책\n앱", summary="첫 줄\n둘째 줄")
    db_session.add(convo)
    await db_session.flush()
    db_session.add_all(
        [
            Turn(session_id=convo.id, seq=0, role=TurnRole.ASSISTANT, text="안녕하세요!"),
            Turn(session_id=convo.id, seq=1, role=TurnRole.USER, text="앱 만들고 싶어"),
            Note(session_id=convo.id, kind=NoteKind.TODO, content="프로토타입 만들기"),
        ]
    )
    await db_session.commit()
    subject, body = await compose_session_mail(
        db_session, settings, convo.id, user_name=None, persona_name="캐릭터"
    )
    assert "\n" not in subject and subject.startswith("[TrailTalk] 산책 앱")
    assert "[요약]\n첫 줄\n둘째 줄" in body
    assert "- (할 일) 프로토타입 만들기" in body
    assert "캐릭터: 안녕하세요!\n나: 앱 만들고 싶어" in body


async def test_compose_unknown_session(db_session, make_settings):
    with pytest.raises(MailError):
        await compose_session_mail(
            db_session, make_settings(), "none", user_name=None, persona_name="x"
        )
