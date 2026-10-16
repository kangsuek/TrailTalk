"""오프라인 큐의 말을 대답 없이 기록만 남기기(계획서 S3-12): POST .../turns/audio/record."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import ConversationSession, ExtractStatus, Turn, TurnRole
from app.main import create_app
from tests.test_sessions import start


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


@pytest.fixture
def api(fake_cli, home, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "multiturn")
    # 세션 종료 추출(일지 정리)은 고정 결과를 낸다
    oneshot = tmp_path / "oneshot.jsonl"
    oneshot.write_text(
        (Path(__file__).parent / "fixtures" / "claude_cli" / "extract.jsonl").read_text()
    )
    monkeypatch.setenv("FAKE_CLAUDE_ONESHOT", str(oneshot))
    settings = fake_cli.settings.model_copy(update={"voice_backend": "fake"})
    with TestClient(create_app(settings)) as client:
        yield client


def record(api, session_id: str, text: str):
    return api.post(
        f"/api/sessions/{session_id}/turns/audio/record",
        content=f"FAKE_STT:{text}".encode(),
        headers={"Content-Type": "audio/webm"},
    )


def turns(api, session_id: str) -> list[Turn]:
    async def run():
        async with api.app.state.session_factory() as db:
            rows = await db.scalars(
                select(Turn).where(Turn.session_id == session_id).order_by(Turn.seq)
            )
            return list(rows.all())

    return api.portal.call(run)


def session(api, session_id: str) -> ConversationSession:
    async def run():
        async with api.app.state.session_factory() as db:
            return await db.get(ConversationSession, session_id)

    return api.portal.call(run)


def test_record_saves_user_turn_without_reply(api):
    session_id = start(api, "voice")["session"]["id"]
    response = record(api, session_id, "연결이 끊긴 동안 한 말")
    assert response.status_code == 201
    assert response.json() == {"text": "연결이 끊긴 동안 한 말"}
    rows = turns(api, session_id)
    assert [(t.seq, t.role, t.text) for t in rows][1:] == [
        (1, TurnRole.USER, "연결이 끊긴 동안 한 말")
    ]  # 캐릭터 답변은 없다


def oneshot_calls(fake_cli) -> int:
    """일지 정리(단발 호출, --json-schema) 횟수"""
    return sum("--json-schema" in r.get("args", []) for r in fake_cli.records())


def test_record_to_ended_session_reorganizes_journal(api, fake_cli):
    session_id = start(api, "voice")["session"]["id"]
    assert api.post(f"/api/sessions/{session_id}/end").status_code == 200
    assert session(api, session_id).extract_status is ExtractStatus.DONE
    # 사용자 말 없이 인사만 하고 끝나 정리할 것이 없었다(CLI를 부르지 않음)
    assert oneshot_calls(fake_cli) == 0

    assert record(api, session_id, "끝난 뒤에 도착한 말").status_code == 201
    assert turns(api, session_id)[-1].text == "끝난 뒤에 도착한 말"
    # 일지를 다시 정리한다(가짜 추출이 끝날 때까지 기다린다)
    task = api.app.state.extractions.get(session_id)
    if task is not None:
        api.portal.call(lambda: task)
    assert session(api, session_id).extract_status is ExtractStatus.DONE
    assert oneshot_calls(fake_cli) == 1  # 기록한 말로 다시 정리했다


def test_record_errors(api):
    session_id = start(api, "voice")["session"]["id"]
    response = record(api, session_id, "")
    assert response.status_code == 422 and response.json()["error"]["code"] == "no_speech"
    response = record(api, "no-such-session", "말")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session_not_found"
    assert len(turns(api, session_id)) == 1  # 인사말뿐


def test_record_during_journal_organizing_is_included(api, fake_cli, monkeypatch):
    """일지를 정리하는 도중에 기록이 들어오면 한 번 더 정리해 그 말도 반영한다."""
    import time as _time

    session_id = start(api, "voice")["session"]["id"]
    api.post(f"/api/sessions/{session_id}/turns", json={"text": "산책 중 떠오른 생각"})
    monkeypatch.setenv("FAKE_CLAUDE_ONESHOT_DELAY", "1")  # 정리가 1초 걸린다
    api.app.state.settings.extract_wait_s = 0  # 끝내기가 정리를 기다리지 않는다
    assert api.post(f"/api/sessions/{session_id}/end").status_code == 200
    assert record(api, session_id, "정리 중에 도착한 말").status_code == 201

    deadline = _time.monotonic() + 10
    while _time.monotonic() < deadline:
        if (
            session(api, session_id).extract_status is ExtractStatus.DONE
            and oneshot_calls(fake_cli) >= 2
        ):
            break
        _time.sleep(0.1)
    prompts = [r["stdin"] for r in fake_cli.records() if "--json-schema" in r.get("args", [])]
    assert len(prompts) == 2 and "정리 중에 도착한 말" in prompts[-1]
    assert session(api, session_id).extract_status is ExtractStatus.DONE


def test_record_is_rejected_while_a_turn_is_running(api):
    import threading
    import time as _time

    session_id = start(api, "voice")["session"]["id"]
    runtime = api.app.state.runtimes.get(session_id)
    worker = threading.Thread(
        target=lambda: api.post(
            f"/api/sessions/{session_id}/turns", json={"text": "__hang_until_interrupt__"}
        )
    )
    worker.start()
    deadline = _time.monotonic() + 5
    while not runtime.turn_lock.locked() and _time.monotonic() < deadline:
        _time.sleep(0.02)
    response = record(api, session_id, "겹친 말")
    assert response.status_code == 409 and response.json()["error"]["code"] == "turn_in_progress"
    api.post(f"/api/sessions/{session_id}/end")
    worker.join(10)


def test_several_records_during_organizing_all_reach_journal(api, fake_cli, monkeypatch):
    """정리 도중 기록이 여러 번 들어와도 끝까지 다시 정리한다(pending에 멈추지 않는다)."""
    import time as _time

    session_id = start(api, "voice")["session"]["id"]
    api.post(f"/api/sessions/{session_id}/turns", json={"text": "산책 중 떠오른 생각"})
    monkeypatch.setenv("FAKE_CLAUDE_ONESHOT_DELAY", "1.5")  # 정리 한 번에 1.5초
    api.app.state.settings.extract_wait_s = 0
    api.post(f"/api/sessions/{session_id}/end")  # 첫 정리: 0~1.5초
    assert record(api, session_id, "첫째 보관한 말").status_code == 201  # 첫 정리 도중
    _time.sleep(2.0)
    # 두 번째 정리(1.5~3초) 도중. 이 뒤로 기록이 없으니 세 번째 정리는 _guarded가 스스로 돌려야 한다
    assert record(api, session_id, "둘째 보관한 말").status_code == 201

    deadline = _time.monotonic() + 15
    while _time.monotonic() < deadline:
        if session(api, session_id).extract_status is ExtractStatus.DONE:
            break
        _time.sleep(0.1)
    assert session(api, session_id).extract_status is ExtractStatus.DONE
    prompts = [r["stdin"] for r in fake_cli.records() if "--json-schema" in r.get("args", [])]
    assert "둘째 보관한 말" in prompts[-1] and len(prompts) == 3
