"""음성 원본 보관(계획서 S3-05): keep_audio면 음성 턴 녹음을 저장하고, 보관 기간이 지나면 지운다."""

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.db.models import Turn, TurnRole
from app.db.types import utcnow
from app.jobs.audio import purge_old_audio
from app.main import create_app
from tests.test_sessions import events_of, start


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


@pytest.fixture
def audio_dir(tmp_path) -> Path:
    return tmp_path / "audio"


@pytest.fixture
def api(fake_cli, home, audio_dir, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "multiturn")
    settings = fake_cli.settings.model_copy(
        update={"voice_backend": "fake", "audio_dir": audio_dir}
    )
    with TestClient(create_app(settings)) as client:
        yield client


def upload(api, session_id: str, data: bytes):
    return api.post(
        f"/api/sessions/{session_id}/turns/audio",
        content=data,
        headers={"Content-Type": "audio/webm"},
    )


def user_turns(api, session_id: str) -> list[Turn]:
    async def run():
        async with api.app.state.session_factory() as db:
            rows = await db.execute(
                select(Turn)
                .where(Turn.session_id == session_id, Turn.role == TurnRole.USER)
                .order_by(Turn.seq)
            )
            return list(rows.scalars())

    return api.portal.call(run)


def keep(api, value: bool) -> None:
    assert api.put("/api/profile", json={"keep_audio": value}).status_code == 200


SPEECH = "FAKE_STT:오늘 북한산 둘레길을 걸었어".encode()


def test_voice_turn_audio_is_kept_when_enabled(api, audio_dir):
    keep(api, True)
    session_id = start(api, "voice")["session"]["id"]
    response = upload(api, session_id, SPEECH)
    assert events_of(response)[-1].type == "done"
    (turn,) = user_turns(api, session_id)
    assert turn.audio_path == f"{session_id}/{turn.id}.webm"
    assert (audio_dir / turn.audio_path).read_bytes() == SPEECH


def test_audio_is_not_kept_by_default_or_for_text_turns(api, audio_dir):
    session_id = start(api, "voice")["session"]["id"]
    upload(api, session_id, SPEECH)  # 기본은 보관하지 않는다
    keep(api, True)
    api.post(f"/api/sessions/{session_id}/turns", json={"text": "글로 보낸 말"})
    assert [t.audio_path for t in user_turns(api, session_id)] == [None, None]
    assert not audio_dir.exists()


def test_audio_is_not_kept_without_a_user_turn(api, audio_dir):
    keep(api, True)
    session_id = start(api, "voice")["session"]["id"]
    assert upload(api, session_id, b"FAKE_STT:").status_code == 422  # 말 없음
    api.post(f"/api/sessions/{session_id}/end")
    assert upload(api, session_id, SPEECH).status_code == 409  # 끝난 대화
    assert user_turns(api, session_id) == []
    assert not audio_dir.exists()


def test_turn_continues_when_audio_cannot_be_written(api, audio_dir):
    audio_dir.write_text("폴더가 아니라 파일")  # 폴더를 만들 수 없다
    keep(api, True)
    session_id = start(api, "voice")["session"]["id"]
    assert events_of(upload(api, session_id, SPEECH))[-1].type == "done"
    (turn,) = user_turns(api, session_id)
    assert turn.audio_path is None


def age_turns(api, session_id: str, days: int) -> None:
    async def run():
        async with api.app.state.session_factory() as db:
            await db.execute(
                update(Turn)
                .where(Turn.session_id == session_id)
                .values(created_at=utcnow() - timedelta(days=days))
            )
            await db.commit()

    api.portal.call(run)


def test_purge_removes_audio_older_than_retention(api, audio_dir):
    keep(api, True)
    old = start(api, "voice")["session"]["id"]
    upload(api, old, SPEECH)
    recent = start(api, "voice")["session"]["id"]
    upload(api, recent, SPEECH)
    age_turns(api, old, 31)
    age_turns(api, recent, 29)
    (old_turn,), (recent_turn,) = user_turns(api, old), user_turns(api, recent)

    assert api.portal.call(purge_old_audio, api.app) == 1
    assert not (audio_dir / old_turn.audio_path).exists()
    assert not (audio_dir / old).exists()  # 빈 세션 폴더도 지운다
    assert user_turns(api, old)[0].audio_path is None
    assert (audio_dir / recent_turn.audio_path).exists()
    assert user_turns(api, recent)[0].audio_path == recent_turn.audio_path
    assert api.portal.call(purge_old_audio, api.app) == 0


def test_purge_clears_missing_files_and_never_leaves_audio_dir(api, audio_dir, tmp_path):
    keep(api, True)
    session_id = start(api, "voice")["session"]["id"]
    upload(api, session_id, SPEECH)
    upload(api, session_id, SPEECH)
    first, second = user_turns(api, session_id)
    (audio_dir / first.audio_path).unlink()  # 이미 지워진 파일
    outside = tmp_path / "outside.txt"
    outside.write_text("지우면 안 되는 파일")

    async def tamper():
        async with api.app.state.session_factory() as db:
            await db.execute(
                update(Turn).where(Turn.id == second.id).values(audio_path="../outside.txt")
            )
            await db.commit()

    api.portal.call(tamper)
    age_turns(api, session_id, 31)
    assert api.portal.call(purge_old_audio, api.app) == 2
    assert outside.exists()
    assert [t.audio_path for t in user_turns(api, session_id)] == [None, None]


@pytest.mark.parametrize("days", [0, -1])
def test_retention_days_must_be_positive(days):
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError, match="audio_retention_days"):
        Settings(_env_file=None, audio_retention_days=days)


def test_audio_file_is_private(api, audio_dir):
    keep(api, True)
    session_id = start(api, "voice")["session"]["id"]
    upload(api, session_id, SPEECH)
    (turn,) = user_turns(api, session_id)
    assert (audio_dir / turn.audio_path).stat().st_mode & 0o777 == 0o600
    assert (audio_dir / session_id).stat().st_mode & 0o777 == 0o700


def test_file_is_removed_when_path_cannot_be_saved(api, audio_dir, monkeypatch):
    """경로를 남기지 못하면 파일을 지운다(DB에 없는 파일은 정리에서도 빠져 영구히 남는다)."""
    from app.services import conversation

    async def fail(db, turn_id, relative):
        # 경로를 실제로 고친 뒤 커밋 전에 실패한다: 롤백이 이 변경을 되돌려야 한다
        await db.execute(update(Turn).where(Turn.id == turn_id).values(audio_path=relative))
        raise RuntimeError("commit")

    monkeypatch.setattr(conversation, "_set_audio_path", fail)
    keep(api, True)
    session_id = start(api, "voice")["session"]["id"]
    assert events_of(upload(api, session_id, SPEECH))[-1].type == "done"  # 턴은 계속한다
    (turn,) = user_turns(api, session_id)
    assert turn.audio_path is None
    assert not any(p.is_file() for p in audio_dir.rglob("*"))


def test_purge_retries_files_it_could_not_delete(api, audio_dir, monkeypatch):
    from app.jobs import audio

    keep(api, True)
    session_id = start(api, "voice")["session"]["id"]
    upload(api, session_id, SPEECH)
    age_turns(api, session_id, 31)

    def denied(root, relative):
        raise PermissionError("denied")

    with monkeypatch.context() as patch:  # 픽스처가 넣은 환경 변수는 건드리지 않는다
        patch.setattr(audio, "_remove", denied)
        assert api.portal.call(purge_old_audio, api.app) == 0
    assert user_turns(api, session_id)[0].audio_path is not None  # 다음에 다시 시도한다
    assert api.portal.call(purge_old_audio, api.app) == 1
    assert user_turns(api, session_id)[0].audio_path is None
