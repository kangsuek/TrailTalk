"""끝난 대화 다시 열기(S3-26). 가짜 CLI로 같은 세션에 이어 쓰고 다시 정리하는 흐름을 확인한다."""

import threading
import time
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import ConversationMode, ExtractStatus, Note, NoteKind, SessionStatus
from app.llm.backend import LlmError
from app.services import conversation
from tests.test_cancel import cancel
from tests.test_extract import FIXTURE, end, make_api, oneshot_records, wait_extraction
from tests.test_idle import sweep
from tests.test_sessions import load, session_row, start, turn, turns_of


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


@pytest.fixture
def oneshot(tmp_path, monkeypatch):
    """가짜 CLI 단발 호출(일지 정리)이 낼 출력 줄을 정한다."""
    path = tmp_path / "oneshot.jsonl"

    def set_lines(*lines: str) -> None:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    monkeypatch.setenv("FAKE_CLAUDE_ONESHOT", str(path))
    set_lines(FIXTURE.read_text(encoding="utf-8").strip())
    return set_lines


@pytest.fixture
def api(fake_cli, home, oneshot, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "multiturn")
    with make_api(fake_cli) as client:
        client.fake_cli = fake_cli
        yield client


def reopen(api, session_id: str, mode: str = "text"):
    return api.post(f"/api/sessions/{session_id}/reopen", json={"mode": mode})


def ended_session(api) -> str:
    session_id = start(api)["session"]["id"]
    turn(api, session_id, "바나나는?")
    end(api, session_id)
    return session_id


def notes_of(api, session_id: str) -> list[Note]:
    async def fn(db):
        rows = await db.scalars(
            select(Note).where(Note.session_id == session_id).order_by(Note.created_at)
        )
        return list(rows)

    return load(api, fn)


def test_reopen_continues_the_same_session_with_a_new_cli(api):
    session_id = ended_session(api)
    before = session_row(api, session_id)
    old_turns = turns_of(api, session_id)

    response = reopen(api, session_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session"]["status"] == "active" and body["session"]["ended_at"] is None
    # 전문은 이전 턴 + 재개 인사말이다
    assert [t["id"] for t in body["turns"]][:-1] == [t.id for t in old_turns]
    assert body["turns"][-1]["id"] == body["greeting"]["turn_id"]
    assert body["greeting"]["text"]

    row = session_row(api, session_id)
    assert row.status is SessionStatus.ACTIVE
    assert row.extract_status is None and row.ended_at is None
    assert row.reopened_at is not None
    assert row.started_at == before.started_at  # 일지 날짜는 그대로
    greeting = turns_of(api, session_id)[-1]
    assert greeting.greeting and greeting.seq == old_turns[-1].seq + 1

    # 기록 파일을 지웠으므로 --resume 없이 전문을 넣은 새 프롬프트로 띄운다
    args = api.fake_cli.records()[-1]["args"]
    assert "--resume" not in args
    prompt = args[args.index("--system-prompt") + 1]
    assert "# 이어서 하는 대화" in prompt and "사용자: 바나나는?" in prompt
    assert row.system_prompt == prompt

    turn(api, session_id, "이어서 얘기하자")
    assert turns_of(api, session_id)[-2].seq == greeting.seq + 1  # seq가 이어진다


def test_reend_extracts_again_and_keeps_user_edits(api):
    session_id = ended_session(api)
    notes = notes_of(api, session_id)
    assert notes
    edited = notes[0]
    # 내용을 크게 고친 노트는 다시 정리할 때 원래 표현으로 되살아날 수 있다(정리 지시에 맡기는
    # 알려진 한계, 가짜 CLI는 같은 노트를 다시 낸다). 여기서는 별표·완료가 남는지만 본다
    patched = api.patch(f"/api/notes/{edited.id}", json={"starred": True, "done": True})
    assert patched.status_code == 200
    assert api.patch(f"/api/journal/{session_id}", json={"title": "내 제목"}).status_code == 200
    extractions = len(oneshot_records(api.fake_cli))

    assert reopen(api, session_id).status_code == 200
    turn(api, session_id, "이어서 얘기하자")
    closed = api.post(f"/api/sessions/{session_id}/end")
    assert closed.status_code == 200
    wait_extraction(api, session_id)

    assert len(oneshot_records(api.fake_cli)) == extractions + 1  # 다시 정리했다
    stdin = oneshot_records(api.fake_cli)[-1]["stdin"]
    assert "이어서 얘기하자" in stdin and "바나나는?" in stdin  # 전문 전체를 정리한다
    row = session_row(api, session_id)
    assert row.status is SessionStatus.ENDED and row.extract_status is ExtractStatus.DONE
    assert row.title == "내 제목"
    after = {n.id: n for n in notes_of(api, session_id)}
    assert after[edited.id].starred and after[edited.id].done
    # 같은 정리 결과는 중복으로 걸러져 노트가 늘지 않고, 마무리 개수도 새 노트만 센다
    assert len(after) == len(notes)
    assert closed.json()["saved"] == {"idea": 0, "todo": 0, "memo": 0}


def test_reopen_refuses_live_or_missing_sessions(api):
    session_id = start(api)["session"]["id"]
    live = reopen(api, session_id)
    assert live.status_code == 409 and live.json()["error"]["code"] == "session_not_ended"
    assert api.app.state.runtimes.get(session_id) is not None  # 진행 중인 대화의 런타임은 그대로
    missing = reopen(api, "없는-세션")
    assert missing.status_code == 404
    assert api.app.state.runtimes.get("없는-세션") is None


def test_reopen_switches_mode(api):
    session_id = ended_session(api)
    body = reopen(api, session_id, "voice").json()
    assert body["session"]["mode"] == "voice"
    assert session_row(api, session_id).mode is ConversationMode.VOICE


def test_reopen_stops_running_extraction(fake_cli, home, oneshot, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "multiturn")
    oneshot("__hang__")
    with make_api(fake_cli, extract_wait_s=0.2) as api:
        session_id = start(api)["session"]["id"]
        turn(api, session_id, "바나나는?")
        api.post(f"/api/sessions/{session_id}/end")
        task = api.app.state.extractions[session_id]
        assert reopen(api, session_id).status_code == 200
        assert task.cancelled()
        row = session_row(api, session_id)
        assert row.status is SessionStatus.ACTIVE and row.extract_status is None


def test_reopen_greeting_is_not_trimmed_by_interrupt(api):
    session_id = ended_session(api)
    greeting = reopen(api, session_id).json()["greeting"]
    assert cancel(api, session_id, greeting["turn_id"], -1).status_code == 204
    assert turns_of(api, session_id)[-1].text == greeting["text"]


def test_idle_counts_from_reopen(api):
    session_id = ended_session(api)
    assert reopen(api, session_id).status_code == 200
    assert sweep(api, 29) == []
    assert sweep(api, 31) == [session_id]
    assert session_row(api, session_id).status is SessionStatus.ENDED


def test_failed_reopen_restores_the_ended_session(api, monkeypatch):
    session_id = ended_session(api)
    before = session_row(api, session_id)

    async def fail(*args, **kwargs):
        raise LlmError("llm_error", "인사말을 받지 못했습니다.")

    monkeypatch.setattr(conversation, "_receive_greeting", fail)
    response = reopen(api, session_id)
    assert response.status_code >= 500
    row = session_row(api, session_id)
    assert row.status is SessionStatus.ENDED
    assert row.ended_at == before.ended_at and row.extract_status is ExtractStatus.DONE
    assert row.system_prompt == before.system_prompt and row.reopened_at is None
    assert api.app.state.runtimes.get(session_id) is None
    assert not api.app.state.llm.is_alive(session_id)
    assert not any(t.greeting for t in turns_of(api, session_id))


def test_reopen_then_delete(api):
    session_id = ended_session(api)
    assert reopen(api, session_id).status_code == 200
    refused = api.delete(f"/api/journal/{session_id}")
    assert refused.status_code == 409  # 다시 연 대화는 진행 중이다
    assert api.post(f"/api/sessions/{session_id}/end").status_code == 200
    wait_extraction(api, session_id)
    assert api.delete(f"/api/journal/{session_id}").status_code == 204


def test_failed_reopen_restarts_stopped_extraction(fake_cli, home, oneshot, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "multiturn")
    oneshot("__hang__")
    with make_api(fake_cli, extract_wait_s=0.2) as api:
        session_id = start(api)["session"]["id"]
        turn(api, session_id, "바나나는?")
        api.post(f"/api/sessions/{session_id}/end")
        stopped = api.app.state.extractions[session_id]

        async def fail(*args, **kwargs):
            raise LlmError("llm_error", "인사말을 받지 못했습니다.")

        monkeypatch.setattr(conversation, "_receive_greeting", fail)
        assert reopen(api, session_id).status_code >= 500
        assert stopped.cancelled()
        row = session_row(api, session_id)
        assert row.status is SessionStatus.ENDED and row.extract_status is ExtractStatus.PENDING
        restarted = api.app.state.extractions.get(session_id)
        assert restarted is not None and restarted is not stopped  # 멈춘 정리를 다시 띄웠다


def test_end_waiting_for_extraction_survives_a_reopen(fake_cli, home, oneshot, monkeypatch):
    """끝내기가 정리를 기다리는 동안 다른 기기에서 다시 열어도 끝내기 응답은 깨지지 않는다."""
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "multiturn")
    oneshot("__hang__")
    with make_api(fake_cli, extract_wait_s=5) as api:
        session_id = start(api)["session"]["id"]
        turn(api, session_id, "바나나는?")
        result: dict = {}
        worker = threading.Thread(
            target=lambda: result.update(end=api.post(f"/api/sessions/{session_id}/end"))
        )
        worker.start()
        deadline = time.monotonic() + 5
        while session_id not in api.app.state.extractions and time.monotonic() < deadline:
            time.sleep(0.02)
        assert reopen(api, session_id).status_code == 200
        worker.join(10)
        assert result["end"].status_code == 200
        row = session_row(api, session_id)
        assert row.status is SessionStatus.ACTIVE  # 끝내기가 다시 연 대화의 CLI를 닫지 않았다
        assert api.app.state.llm.is_alive(session_id)


def test_reopen_twice_and_count_only_new_notes(api):
    session_id = ended_session(api)
    first = reopen(api, session_id).json()["greeting"]["turn_id"]
    first_at = session_row(api, session_id).reopened_at
    end(api, session_id)
    assert reopen(api, session_id).status_code == 200
    row = session_row(api, session_id)
    assert row.reopened_at > first_at
    greetings = [t.id for t in turns_of(api, session_id) if t.greeting]
    assert len(greetings) == 2 and greetings[0] == first

    async def save_idea(db):  # 다시 연 뒤 대화 중에 저장한 노트(save_note)
        db.add(Note(session_id=session_id, kind=NoteKind.IDEA, content="새로 떠오른 아이디어"))
        await db.commit()

    load(api, save_idea)
    closed = api.post(f"/api/sessions/{session_id}/end")
    assert closed.json()["saved"] == {"idea": 1, "todo": 0, "memo": 0}


def system_prompt_of(api, session_id: str) -> str:
    return session_row(api, session_id).system_prompt


def test_reopen_uses_journal_summary_and_recent_turns(api):
    """정리가 끝난 일지를 다시 열면 앞부분은 정리로 대신하고 최근 원문만 넣는다(S3-27)."""
    session_id = start(api)["session"]["id"]
    turn(api, session_id, "앞부분 이야기 " + "나" * 3000)
    turn(api, session_id, "중간 이야기 " + "다" * 3000)
    turn(api, session_id, "마지막 이야기")
    end(api, session_id)
    row = session_row(api, session_id)
    assert row.extract_status is ExtractStatus.DONE and row.summary

    assert reopen(api, session_id).status_code == 200
    prompt = system_prompt_of(api, session_id)
    block = prompt[prompt.index("# 이어서 하는 대화") : prompt.index("# 역할 규칙")]
    lines = row.summary.splitlines()  # 요약은 줄바꿈으로 이은 글이다
    assert "<정리>" in block
    assert all(f"- {line}" in block for line in lines)  # 요약 줄이 그대로(글자로 쪼개지지 않고)
    assert any(n.content in block for n in notes_of(api, session_id))  # 이 대화의 노트
    assert "(앞부분은 위 정리로 대신함)" in block
    assert "앞부분 이야기" not in block and "사용자: 마지막 이야기" in block


def test_reopen_without_finished_journal_keeps_full_transcript(
    fake_cli, home, oneshot, monkeypatch
):
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "multiturn")
    oneshot("__hang__")  # 정리가 끝나지 않은 채 다시 연다
    with make_api(fake_cli, extract_wait_s=0.2) as api:
        session_id = start(api)["session"]["id"]
        turn(api, session_id, "앞부분 이야기 " + "나" * 3000)
        turn(api, session_id, "중간 이야기 " + "다" * 3000)
        api.post(f"/api/sessions/{session_id}/end")
        assert reopen(api, session_id).status_code == 200
        prompt = system_prompt_of(api, session_id)
        assert "<정리>" not in prompt and "사용자: 앞부분 이야기" in prompt
