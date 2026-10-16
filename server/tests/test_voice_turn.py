"""음성 턴(S3-03): 업로드 → 인식 → 문장별 소리. 가짜 CLI와 가짜·모의 음성 provider로 시험한다."""

import asyncio
import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.models import Turn, TurnRole
from app.errors import AppError
from app.main import create_app
from app.voice.fake import SILENCE_MP3, FakeStt, FakeTts
from tests.test_sessions import _http, events_of, start

FIXTURES = Path(__file__).parent / "fixtures" / "claude_cli"
SILENCE_B64 = base64.b64encode(SILENCE_MP3).decode()
THREE = "첫 문장입니다. 둘째 문장이에요. 셋째 문장이죠."


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


def voice_settings(fake_cli, **overrides):
    return fake_cli.settings.model_copy(update={"voice_backend": "fake", **overrides})


@pytest.fixture
def api(fake_cli, home, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "multiturn")
    with TestClient(create_app(voice_settings(fake_cli))) as client:
        yield client


def upload(api, session_id: str, data: bytes, content_type: str = "audio/webm"):
    return api.post(
        f"/api/sessions/{session_id}/turns/audio",
        content=data,
        headers={"Content-Type": content_type},
    )


def count_turns(api, session_id: str) -> int:
    async def run():
        async with api.app.state.session_factory() as db:
            return await db.scalar(
                select(func.count()).select_from(Turn).where(Turn.session_id == session_id)
            )

    return api.portal.call(run)


def user_texts(api, session_id: str) -> list[str]:
    async def run():
        async with api.app.state.session_factory() as db:
            rows = await db.scalars(
                select(Turn.text)
                .where(Turn.session_id == session_id, Turn.role == TurnRole.USER)
                .order_by(Turn.seq)
            )
            return list(rows)

    return api.portal.call(run)


def write_fixture(tmp_path, name: str, turns: list[list[str]]) -> str:
    """녹화 줄 목록(턴별)으로 임시 녹화를 만들고 FAKE_CLAUDE_FIXTURE에 넣을 이름을 돌려준다."""
    path = tmp_path / f"{name}.jsonl"
    path.write_text("\n".join(line for turn in turns for line in turn) + "\n", encoding="utf-8")
    return str(path.with_suffix(""))  # 가짜 CLI는 이름 뒤에 .jsonl을 붙인다(절대 경로 허용)


def recorded_turns(name: str) -> list[list[str]]:
    turns: list[list[str]] = [[]]
    for line in (FIXTURES / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        turns[-1].append(line)
        if json.loads(line).get("type") == "result":
            turns.append([])
    return [turn for turn in turns if turn]


def text_delta(text: str) -> str:
    return json.dumps(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": text},
            },
        },
        ensure_ascii=False,
    )


def with_single_delta(turn: list[str], text: str) -> list[str]:
    """턴의 글 조각을 하나로 합쳐 여러 문장이 한 번에 오게 한다."""
    out, replaced = [], False
    for line in turn:
        event = json.loads(line).get("event") or {}
        if event.get("type") == "content_block_delta":
            if not replaced:
                out.append(text_delta(text))
                replaced = True
            continue
        out.append(line)
    return out


# ---- 오디오 업로드 ----


def test_audio_turn_streams_transcript_then_sentences_with_audio(api):
    started = start(api, "voice")
    assert started["greeting"]["audio"] == SILENCE_B64
    session_id = started["session"]["id"]

    response = upload(api, session_id, "FAKE_STT:사과는 무슨 색이야?".encode())
    assert response.status_code == 200, response.text
    events = events_of(response)
    types = [e.type for e in events]
    assert types[:2] == ["transcript", "turn"]
    assert types[-1] == "done"
    assert events[0].text == "사과는 무슨 색이야?"
    sentences = [e for e in events if e.type == "sentence"]
    assert [s.index for s in sentences] == list(range(len(sentences)))
    assert sentences and all(s.audio == SILENCE_B64 for s in sentences)
    assert user_texts(api, session_id) == ["사과는 무슨 색이야?"]


def test_default_fake_text_and_reply_hint(api):
    session_id = start(api, "voice")["session"]["id"]
    events = events_of(upload(api, session_id, b"webm-bytes"))
    assert events[0].text == api.app.state.settings.fake_stt_text
    # 인식 힌트로 직전 캐릭터 답변(인사말)을 넘긴다
    greeting = api.app.state.stt.prompts[0]
    assert greeting
    upload(api, session_id, b"webm-bytes")
    reply = events[-1].text
    assert api.app.state.stt.prompts[1] == reply[-200:]


@pytest.mark.parametrize("data", [b"FAKE_STT:", b"FAKE_STT:   ", b"FAKE_STT:...!?"])
def test_no_speech_is_json_error_without_user_turn(api, data):
    session_id = start(api, "voice")["session"]["id"]
    response = upload(api, session_id, data)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_speech"
    assert count_turns(api, session_id) == 1  # 인사말만


def test_empty_audio_is_invalid(api):
    session_id = start(api, "voice")["session"]["id"]
    response = upload(api, session_id, b"")
    assert (response.status_code, response.json()["error"]["code"]) == (400, "audio_invalid")


def test_too_large_audio_is_rejected(fake_cli, home, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "multiturn")
    with TestClient(create_app(voice_settings(fake_cli, stt_max_bytes=10))) as api:
        session_id = start(api, "voice")["session"]["id"]
        response = upload(api, session_id, b"x" * 11)
        assert (response.status_code, response.json()["error"]["code"]) == (413, "audio_invalid")
        assert count_turns(api, session_id) == 1


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (AppError("stt_failed", "음성 처리에 실패했습니다.", 502), 502),
        (AppError("stt_timeout", "음성 처리 시간이 초과되었습니다.", 504), 504),
        (AppError("voice_unavailable", "음성 서비스를 쓸 수 없습니다.", 503), 503),
    ],
)
def test_stt_failure_is_json_error(api, error, status):
    class BrokenStt:
        async def transcribe(self, audio, *, prompt=None):
            raise error

    session_id = start(api, "voice")["session"]["id"]
    api.app.state.stt = BrokenStt()
    response = upload(api, session_id, b"webm-bytes")
    assert (response.status_code, response.json()["error"]["code"]) == (status, error.code)
    assert count_turns(api, session_id) == 1


def test_chunked_upload_without_length_is_limited(fake_cli, home, monkeypatch):
    """Content-Length 없이 나눠 보내도 실제로 받은 크기로 막는다."""
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "multiturn")
    with TestClient(create_app(voice_settings(fake_cli, stt_max_bytes=10))) as api:
        session_id = start(api, "voice")["session"]["id"]

        def chunks():
            yield b"x" * 6
            yield b"x" * 6

        response = api.post(
            f"/api/sessions/{session_id}/turns/audio",
            content=chunks(),
            headers={"Content-Type": "audio/webm"},
        )
        assert (response.status_code, response.json()["error"]["code"]) == (413, "audio_invalid")


def test_unknown_session_and_ended_session(api):
    assert upload(api, "nope", b"x").json()["error"]["code"] == "session_not_found"
    session_id = start(api, "voice")["session"]["id"]
    api.post(f"/api/sessions/{session_id}/end")
    assert upload(api, session_id, b"x").json()["error"]["code"] == "session_ended"


def test_text_session_audio_upload_has_no_sound(api):
    started = start(api, "text")
    assert started["greeting"]["audio"] is None
    events = events_of(upload(api, started["session"]["id"], b"webm-bytes"))
    assert events[0].type == "transcript"
    assert all(e.audio is None for e in events if e.type == "sentence")


def test_text_turn_in_voice_session_has_sound(api):
    session_id = start(api, "voice")["session"]["id"]
    events = events_of(api.post(f"/api/sessions/{session_id}/turns", json={"text": "안녕"}))
    assert events[0].type == "turn"  # 텍스트 턴에는 transcript가 없다
    assert all(e.audio == SILENCE_B64 for e in events if e.type == "sentence")


# ---- 합성 실패·순서 ----


class ScriptedTts:
    """문장별로 지연·실패를 정하는 모의 TTS."""

    def __init__(self, delays: dict[str, float] | None = None, fail: set[str] | None = None):
        self.delays = delays or {}
        self.fail = fail or set()
        self.started: list[str] = []
        self.cancelled: list[str] = []
        self.log: list[tuple[str, str]] = []  # ("start"|"end", 문장)

    async def synthesize(self, text, voice):
        self.started.append(text)
        self.log.append(("start", text))
        try:
            await asyncio.sleep(self.delays.get(text, 0))
        except asyncio.CancelledError:
            self.cancelled.append(text)
            raise
        self.log.append(("end", text))
        if text in self.fail:
            raise AppError("tts_failed", "음성 처리에 실패했습니다.", 502)
        return text.encode()


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def test_tts_failure_sends_sentence_without_audio(api):
    session_id = start(api, "voice")["session"]["id"]
    api.app.state.tts = ScriptedTts(fail={"둘째 문장이에요."})
    events = events_of(
        api.post(f"/api/sessions/{session_id}/turns", json={"text": f"__say__:{THREE}"})
    )
    sentences = [e for e in events if e.type == "sentence"]
    assert [(s.text, s.audio) for s in sentences] == [
        ("첫 문장입니다.", b64("첫 문장입니다.")),
        ("둘째 문장이에요.", None),
        ("셋째 문장이죠.", b64("셋째 문장이죠.")),
    ]
    assert events[-1].type == "done" and not events[-1].interrupted


def test_cli_crash_sends_and_keeps_sentences_waiting_for_sound(api):
    """CLI가 답변 도중 죽어도 합성을 기다리던 문장과 끝 조각까지 글로 보내고 끊긴 답변으로
    남긴다."""
    session_id = start(api, "voice")["session"]["id"]
    tts = ScriptedTts(delays={"첫 문장입니다.": 0.5, "둘째 문장이에요.": 0.5})
    api.app.state.tts = tts
    events = events_of(
        api.post(
            f"/api/sessions/{session_id}/turns",
            json={"text": "__say_then_crash__:첫 문장입니다. 둘째 문장이에요. 셋째"},
        )
    )
    assert events[-1].type == "error" and events[-1].code == "llm_process_exited"
    sentences = [e for e in events if e.type == "sentence"]
    assert [(s.index, s.text, s.audio) for s in sentences] == [
        (0, "첫 문장입니다.", None),
        (1, "둘째 문장이에요.", None),
        (2, "셋째", None),
    ]
    assert set(tts.cancelled) == {"첫 문장입니다.", "둘째 문장이에요."}  # 들을 수 없는 소리

    async def reply():
        async with api.app.state.session_factory() as db:
            return await db.scalar(
                select(Turn).where(Turn.session_id == session_id).order_by(Turn.seq.desc())
            )

    turn = api.portal.call(reply)
    assert (turn.role, turn.text, turn.interrupted) == (
        TurnRole.ASSISTANT,
        "첫 문장입니다. 둘째 문장이에요. 셋째",
        True,
    )


def test_sentences_in_one_chunk_are_synthesized_together_but_sent_in_order(
    fake_cli, home, monkeypatch, tmp_path
):
    turns = recorded_turns("multiturn")
    fixture = write_fixture(tmp_path, "batch", [turns[0], with_single_delta(turns[1], THREE)])
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", fixture)
    with TestClient(create_app(voice_settings(fake_cli))) as api:
        session_id = start(api, "voice")["session"]["id"]
        # 첫 문장이 가장 늦게 끝나도 순서대로 보낸다
        tts = ScriptedTts(delays={"첫 문장입니다.": 0.3, "둘째 문장이에요.": 0.1})
        api.app.state.tts = tts
        events = events_of(api.post(f"/api/sessions/{session_id}/turns", json={"text": "말해"}))
    sentences = [e for e in events if e.type == "sentence"]
    assert [(s.index, s.text) for s in sentences] == [
        (0, "첫 문장입니다."),
        (1, "둘째 문장이에요."),
        (2, "셋째 문장이죠."),
    ]
    assert all(s.audio == b64(s.text) for s in sentences)
    # 한 조각에 온 두 문장은 동시에 합성을 시작했다(첫 문장이 끝나기 전에 둘째도 시작).
    # 마지막 문장은 다음 글자를 봐야 끝나므로 답변이 끝날 때(flush) 나온다
    assert tts.log.index(("start", "둘째 문장이에요.")) < tts.log.index(("end", "첫 문장입니다."))
    assert tts.started == ["첫 문장입니다.", "둘째 문장이에요.", "셋째 문장이죠."]


def test_slow_synthesis_does_not_hold_cli_reading(fake_cli, home, monkeypatch):
    """합성을 기다리는 동안에도 CLI를 끝까지 읽는다: 모든 문장의 합성이 첫 문장이 끝나기 전에
    시작된다(문장마다 따로 온 조각이어도)."""
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "multiturn")
    with TestClient(create_app(voice_settings(fake_cli))) as api:
        session_id = start(api, "voice")["session"]["id"]
        tts = ScriptedTts(delays={"첫 문장입니다.": 0.5})
        api.app.state.tts = tts
        events = events_of(
            api.post(
                f"/api/sessions/{session_id}/turns", json={"text": f"__say__:{THREE} 끝이에요"}
            )
        )
    first_end = tts.log.index(("end", "첫 문장입니다."))
    assert tts.log.index(("start", "셋째 문장이죠.")) < first_end
    sentences = [e.text for e in events if e.type == "sentence"]
    assert sentences == ["첫 문장입니다.", "둘째 문장이에요.", "셋째 문장이죠.", "끝이에요"]


async def test_disconnect_cancels_pending_synthesis(fake_cli, home, monkeypatch, tmp_path):
    """실제 서버에서 첫 문장을 받고 끊으면 아직 합성 중인 문장은 취소된다."""
    import socket

    import uvicorn

    turns = recorded_turns("multiturn")
    fixture = write_fixture(tmp_path, "batch", [turns[0], with_single_delta(turns[1], THREE)])
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", fixture)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    app = create_app(voice_settings(fake_cli, internal_base_url=f"http://127.0.0.1:{port}"))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    try:
        while not server.started:
            if serving.done():
                serving.result()
            await asyncio.sleep(0.05)
        created = await _http(port, "/api/sessions", {"mode": "voice"})
        session_id = json.loads(created.split(b"\r\n\r\n", 1)[1])["session"]["id"]
        tts = ScriptedTts(delays={"둘째 문장이에요.": 30, "셋째 문장이죠.": 30})
        app.state.tts = tts
        await _http(
            port, f"/api/sessions/{session_id}/turns", {"text": "말해"}, until=b"event: sentence"
        )
        runtime = app.state.runtimes.get(session_id)
        for _ in range(100):
            if not runtime.turn_lock.locked():
                break
            await asyncio.sleep(0.05)
        assert not runtime.turn_lock.locked()
        # 합성 중이던 문장(CLI를 끝까지 읽어 셋째도 이미 시작)은 모두 취소된다
        assert sorted(tts.cancelled) == ["둘째 문장이에요.", "셋째 문장이죠."]
    finally:
        server.should_exit = True
        await serving


# ---- 검색 안내 ----


def test_search_without_words_gets_notice(fake_cli, home, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "web_search")
    with TestClient(create_app(voice_settings(fake_cli))) as api:
        session_id = start(api, "voice")["session"]["id"]
        tts = FakeTts()
        api.app.state.tts = tts
        events = events_of(
            api.post(f"/api/sessions/{session_id}/turns", json={"text": "날씨 알려줘"})
        )
        starts = [e for e in events if e.type == "tool" and e.phase == "start"]
    assert starts and starts[0].name == "web_search"
    notice = starts[0].notice
    assert notice is not None and notice.audio == SILENCE_B64
    assert notice.text  # 문구는 페르소나 YAML에서 온다
    # 안내는 답변 문장이 아니다: 문장 번호와 저장된 답변에 들어가지 않는다
    sentences = [e for e in events if e.type == "sentence"]
    assert sentences[0].index == 0 and notice.text not in events[-1].text


def test_notice_is_cached(fake_cli, home, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "web_search")
    with TestClient(create_app(voice_settings(fake_cli))) as api:
        tts = FakeTts()
        for _ in range(2):
            session_id = start(api, "voice")["session"]["id"]
            api.app.state.tts = tts
            events_of(api.post(f"/api/sessions/{session_id}/turns", json={"text": "날씨"}))
    notices = [t for t in tts.texts if t.startswith("잠깐")]
    assert len(notices) == 1


def test_search_after_words_has_no_notice(fake_cli, home, monkeypatch, tmp_path):
    turns = recorded_turns("web_search")
    search = []
    for line in turns[1]:
        block = (json.loads(line).get("event") or {}).get("content_block") or {}
        if block.get("type") == "tool_use":
            search.append(text_delta("잠깐 찾아볼게요! "))  # 캐릭터가 먼저 말한다
        search.append(line)
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", write_fixture(tmp_path, "said", [turns[0], search]))
    with TestClient(create_app(voice_settings(fake_cli))) as api:
        session_id = start(api, "voice")["session"]["id"]
        events = events_of(api.post(f"/api/sessions/{session_id}/turns", json={"text": "날씨"}))
    types = [e.type for e in events]
    first_tool = types.index("tool")
    assert events[first_tool - 1].type == "sentence"
    assert events[first_tool - 1].text == "잠깐 찾아볼게요!"
    assert events[first_tool - 1].audio == SILENCE_B64
    assert events[first_tool].notice is None


def test_symbol_only_words_before_search_still_get_notice(fake_cli, home, monkeypatch, tmp_path):
    """도구 앞 글이 기호뿐이라 소리가 없으면 아무 말 없이 시작한 것과 같다."""
    turns = recorded_turns("web_search")
    search = []
    for line in turns[1]:
        block = (json.loads(line).get("event") or {}).get("content_block") or {}
        if block.get("type") == "tool_use":
            search.append(text_delta("🔍🔍🔍 "))
        search.append(line)
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", write_fixture(tmp_path, "sym", [turns[0], search]))
    with TestClient(create_app(voice_settings(fake_cli))) as api:
        session_id = start(api, "voice")["session"]["id"]
        events = events_of(api.post(f"/api/sessions/{session_id}/turns", json={"text": "날씨"}))
    first_tool = [e.type for e in events].index("tool")
    assert events[first_tool - 1].type == "sentence" and events[first_tool - 1].audio is None
    assert events[first_tool].notice is not None


def test_text_session_search_has_no_notice(fake_cli, home, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "web_search")
    with TestClient(create_app(voice_settings(fake_cli))) as api:
        session_id = start(api, "text")["session"]["id"]
        events = events_of(api.post(f"/api/sessions/{session_id}/turns", json={"text": "날씨"}))
    assert all(e.notice is None for e in events if e.type == "tool")


# ---- 인사말·마무리 ----


def test_greeting_audio_failure_still_starts(api):
    class Broken:
        async def synthesize(self, text, voice):
            raise AppError("voice_unavailable", "음성 서비스를 쓸 수 없습니다.", 503)

    api.app.state.tts = Broken()
    started = start(api, "voice")
    assert started["greeting"]["audio"] is None and started["greeting"]["text"]


def test_closing_audio_only_in_voice_session(api):
    voice_id = start(api, "voice")["session"]["id"]
    closed = api.post(f"/api/sessions/{voice_id}/end").json()
    assert closed["closing"] and closed["closing_audio"] == SILENCE_B64
    text_id = start(api, "text")["session"]["id"]
    assert api.post(f"/api/sessions/{text_id}/end").json()["closing_audio"] is None


def test_fake_backend_is_selected_by_setting(api, client):
    assert isinstance(api.app.state.stt, FakeStt)
    assert isinstance(api.app.state.tts, FakeTts)
    assert not isinstance(client.app.state.stt, FakeStt)  # 기본은 OpenAI
