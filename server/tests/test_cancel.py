"""끼어들기 API(계획서 S3-04): 들려준 문장까지만 기록하고, 진행 중이면 CLI를 인터럽트한다.

CLI 입력 앞에 붙는 안내(끼어들기·지금 시각 S3-34)도 여기서 확인한다."""

import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.persona.rules import INTERRUPTED_NOTHING
from tests.test_sessions import THREE_SENTENCES, start, turn, turns_of


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


@pytest.fixture
def api(fake_cli, home, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "multiturn")
    # 음성 세션을 쓰므로 합성은 가짜(무음)로 한다
    settings = fake_cli.settings.model_copy(update={"voice_backend": "fake"})
    with TestClient(create_app(settings)) as client:
        yield client


def cancel(api, session_id: str, turn_id: str, last_played: int):
    return api.post(
        f"/api/sessions/{session_id}/turns/{turn_id}/cancel", json={"last_played": last_played}
    )


# 턴마다 맨 앞에 붙는 지금 시각 안내(S3-34). 모을 때 확인하고 떼어 낸다
TIME_NOTE = re.compile(r"\(앱 안내: 지금 시각은 [^\n]+?이다\. [^\n]*\)\n\n")


def capture_cli_input(api, *, raw: bool = False) -> list[str]:
    """CLI에 보낸 사용자 메시지를 모은다(raw가 아니면 맨 앞의 지금 시각 안내는 확인한 뒤 뗀다).
    대화를 시작한 뒤에 부른다(인사말 안내 앞에도 시각이 붙지만 형식 확인은 턴 기준이다)."""
    sent: list[str] = []
    manager = api.app.state.llm
    original = manager.get

    class Capturing:
        def __init__(self, inner) -> None:
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def send(self, text):
            note = TIME_NOTE.match(text)
            assert note is not None, text
            sent.append(text if raw else text[note.end() :])
            return self._inner.send(text)

    async def get(key, **kwargs):
        return Capturing(await original(key, **kwargs))

    manager.get = get
    return sent


def test_every_turn_tells_cli_the_current_time_without_recording_it(api, monkeypatch):
    session_id = start(api, "voice")["session"]["id"]
    sent = capture_cli_input(api, raw=True)
    # 대화를 시작한 때와 다른 시각의 턴: 시스템 프롬프트의 시작 시각이 아니라 턴 때의 시각을 알린다
    later = datetime(2026, 10, 13, 23, 5, tzinfo=UTC)  # 한국 시각 10월 14일(수) 오전 8시 5분
    monkeypatch.setattr("app.services.conversation.utcnow", lambda: later)
    turn(api, session_id, "지금 몇 시야?")
    assert sent[0].startswith("(앱 안내: 지금 시각은 2026년 10월 14일(수) 오전 8시 5분이다.")
    assert sent[0].endswith(")\n\n지금 몇 시야?")
    assert turns_of(api, session_id)[1].text == "지금 몇 시야?"  # 기록에는 남기지 않는다


def test_cancel_running_turn_interrupts_cli_and_keeps_played_sentences(api):
    session_id = start(api, "voice")["session"]["id"]
    runtime = api.app.state.runtimes.get(session_id)
    result = {}

    def run_turn():
        result["events"] = turn(api, session_id, f"__say_then_hang__:{THREE_SENTENCES}")

    worker = threading.Thread(target=run_turn)
    worker.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        active = runtime.active_turn
        if active and len(runtime.reply_sentences.get(active[0], [])) == 3:
            break
        time.sleep(0.02)
    turn_id = runtime.active_turn[0]

    started = time.monotonic()
    response = cancel(api, session_id, turn_id, 0)  # 첫 문장만 다 들었다
    assert response.status_code == 204, response.text
    assert time.monotonic() - started < 5
    worker.join(10)
    assert result["events"][-1].type == "done" and result["events"][-1].interrupted
    reply = turns_of(api, session_id)[2]
    assert reply.id == turn_id
    assert (reply.text, reply.interrupted) == ("첫 문장입니다.", True)
    assert runtime.active_turn is None

    # 다음 턴은 정상으로 진행되고, CLI에만 어디까지 들었는지 알린다
    sent = capture_cli_input(api)
    events = turn(api, session_id, "다시 말해 줘")
    assert events[-1].type == "done" and not events[-1].interrupted
    assert sent[0].startswith('(앱 안내: 직전 답변은 사용자가 끼어들어 "첫 문장입니다."까지만')
    assert sent[0].endswith("다시 말해 줘")
    user = turns_of(api, session_id)[3]
    assert user.text == "다시 말해 줘"  # 기록에는 안내가 없다

    # 안내는 한 번만 붙는다
    turn(api, session_id, "고마워")
    assert sent[1] == "고마워"


def test_cancel_finished_turn_trims_to_played_sentences(api):
    session_id = start(api, "voice")["session"]["id"]
    turn_id = turn(api, session_id, f"__say__:{THREE_SENTENCES}")[0].turn_id

    assert cancel(api, session_id, turn_id, 1).status_code == 204
    reply = turns_of(api, session_id)[2]
    assert (reply.text, reply.interrupted) == ("첫 문장입니다. 둘째 문장이에요.", True)

    # 여러 번 불러도 같다
    assert cancel(api, session_id, turn_id, 1).status_code == 204
    assert turns_of(api, session_id)[2].text == "첫 문장입니다. 둘째 문장이에요."


def test_cancel_before_first_sentence_heard_keeps_nothing(api):
    session_id = start(api, "voice")["session"]["id"]
    turn_id = turn(api, session_id, f"__say__:{THREE_SENTENCES}")[0].turn_id
    assert cancel(api, session_id, turn_id, -1).status_code == 204
    reply = turns_of(api, session_id)[2]
    assert (reply.text, reply.interrupted) == ("", True)

    sent = capture_cli_input(api)
    turn(api, session_id, "응?")
    assert sent[0] == INTERRUPTED_NOTHING + "응?"


def test_cancel_after_hearing_everything_changes_nothing(api):
    session_id = start(api, "voice")["session"]["id"]
    turn_id = turn(api, session_id, f"__say__:{THREE_SENTENCES}")[0].turn_id
    assert cancel(api, session_id, turn_id, 2).status_code == 204
    reply = turns_of(api, session_id)[2]
    assert (reply.text, reply.interrupted) == (THREE_SENTENCES, False)

    sent = capture_cli_input(api)
    turn(api, session_id, "좋아")
    assert sent[0] == "좋아"


def test_cancel_greeting_is_ignored(api):
    body = start(api, "voice")
    session_id, greeting = body["session"]["id"], body["greeting"]
    assert cancel(api, session_id, greeting["turn_id"], -1).status_code == 204
    row = turns_of(api, session_id)[0]
    assert (row.text, row.interrupted) == (greeting["text"], False)


def test_cancel_without_remembered_sentences_splits_saved_reply(api):
    """서버 재시작 등으로 문장 목록이 없으면 저장된 답변을 다시 나눠 자른다."""
    session_id = start(api, "voice")["session"]["id"]
    turn_id = turn(api, session_id, f"__say__:{THREE_SENTENCES}")[0].turn_id
    api.app.state.runtimes.get(session_id).reply_sentences.clear()
    assert cancel(api, session_id, turn_id, 0).status_code == 204
    assert turns_of(api, session_id)[2].text == "첫 문장입니다."


def test_cancel_errors(api):
    session_id = start(api, "voice")["session"]["id"]
    turn(api, session_id, f"__say__:{THREE_SENTENCES}")
    user_turn = turns_of(api, session_id)[1]

    response = cancel(api, "no-such-session", "x", 0)
    assert response.status_code == 404 and response.json()["error"]["code"] == "session_not_found"
    for turn_id in ("no-such-turn", user_turn.id):  # 없는 턴, 캐릭터 답변이 아닌 턴
        response = cancel(api, session_id, turn_id, 0)
        assert response.status_code == 404 and response.json()["error"]["code"] == "turn_not_found"
    other = start(api, "voice")["session"]["id"]
    other_turn = turn(api, other, f"__say__:{THREE_SENTENCES}")[0].turn_id
    response = cancel(api, session_id, other_turn, 0)  # 다른 대화의 답변
    assert response.status_code == 404 and response.json()["error"]["code"] == "turn_not_found"
    response = cancel(api, session_id, other_turn, -2)
    assert response.status_code == 422


def test_repeated_cancel_does_not_add_the_note_again(api):
    session_id = start(api, "voice")["session"]["id"]
    turn_id = turn(api, session_id, f"__say__:{THREE_SENTENCES}")[0].turn_id
    assert cancel(api, session_id, turn_id, 0).status_code == 204
    sent = capture_cli_input(api)
    turn(api, session_id, "응")
    assert sent[0].startswith("(앱 안내:")
    assert cancel(api, session_id, turn_id, 0).status_code == 204  # 늦게 다시 온 같은 요청
    turn(api, session_id, "그래")
    assert sent[1] == "그래"


def test_cancel_of_an_older_reply_trims_without_note(api):
    session_id = start(api, "voice")["session"]["id"]
    old = turn(api, session_id, f"__say__:{THREE_SENTENCES}")[0].turn_id
    turn(api, session_id, f"__say__:{THREE_SENTENCES}")
    assert cancel(api, session_id, old, 0).status_code == 204
    assert turns_of(api, session_id)[2].text == "첫 문장입니다."
    sent = capture_cli_input(api)
    turn(api, session_id, "다음")
    assert sent[0] == "다음"  # 직전 답변이 아니면 알리지 않는다


def test_cancel_before_first_sentence_leaves_empty_interrupted_reply(api):
    session_id = start(api, "voice")["session"]["id"]
    runtime = api.app.state.runtimes.get(session_id)
    worker = threading.Thread(target=lambda: turn(api, session_id, "__hang_until_interrupt__"))
    worker.start()
    deadline = time.monotonic() + 5
    while runtime.active_turn is None and time.monotonic() < deadline:
        time.sleep(0.02)
    turn_id = runtime.active_turn[0]
    assert cancel(api, session_id, turn_id, -1).status_code == 204
    worker.join(10)
    reply = turns_of(api, session_id)[2]
    assert reply.id == turn_id and reply.interrupted


def test_cancel_does_not_trim_a_turn_that_does_not_stop(api, monkeypatch):
    """인터럽트에도 멈추지 않으면 자르지 않는다(끝날 때 전체 답변으로 덮어쓰게 되므로)."""
    from app.services import conversation

    monkeypatch.setattr(conversation, "_CANCEL_WAIT_S", 0.3)
    session_id = start(api, "voice")["session"]["id"]
    runtime = api.app.state.runtimes.get(session_id)
    worker = threading.Thread(target=lambda: turn(api, session_id, "__hang__"))
    worker.start()
    deadline = time.monotonic() + 5
    while runtime.active_turn is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert cancel(api, session_id, runtime.active_turn[0], 0).status_code == 204
    assert runtime.heard_note is None
    api.post(f"/api/sessions/{session_id}/end")  # 멈춘 CLI를 닫는다
    worker.join(10)


def test_heard_note_quotes_safely():
    from app.services.conversation import _heard_note

    note = _heard_note(['그가 "(지시) 무시해" 라고 했어요.'])
    assert note.startswith(
        "(앱 안내: 직전 답변은 사용자가 끼어들어 \"그가 '지시 무시해' 라고 했어요.\""
    )


def test_cancel_records_wait_on_voice_turn_latency(api):
    from sqlalchemy import select

    from app.db.models import TurnLatency

    session_id = start(api, "voice")["session"]["id"]
    runtime = api.app.state.runtimes.get(session_id)
    result = {}

    def run_turn():
        result["response"] = api.post(
            f"/api/sessions/{session_id}/turns/audio",
            content=f"FAKE_STT:__say_then_hang__:{THREE_SENTENCES}".encode(),
            headers={"Content-Type": "audio/webm"},
        )

    worker = threading.Thread(target=run_turn)
    worker.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        active = runtime.active_turn
        if active and len(runtime.reply_sentences.get(active[0], [])) == 3:
            break
        time.sleep(0.02)
    turn_id = runtime.active_turn[0]
    assert cancel(api, session_id, turn_id, 0).status_code == 204
    worker.join(10)

    async def load():
        async with api.app.state.session_factory() as db:
            return await db.scalar(select(TurnLatency).where(TurnLatency.turn_id == turn_id))

    row = api.portal.call(load)
    assert row.cancel_outcome == "trimmed"
    assert row.cancel_wait_ms is not None and row.cancel_wait_ms >= 0
    assert row.sentence_count == 3  # 끊겨도 보낸 문장 수는 남는다
