"""음성 턴 지연 측정(계획서 S3-07): 서버 단계 시각 기록, 웹 보고, 요약."""

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import TurnLatency
from app.db.types import utcnow
from app.main import create_app
from tests.test_sessions import events_of, start


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


@pytest.fixture
def api(fake_cli, home, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_FIXTURE", "multiturn")
    settings = fake_cli.settings.model_copy(update={"voice_backend": "fake"})
    with TestClient(create_app(settings)) as client:
        yield client


THREE = "첫 문장입니다. 둘째 문장이에요. 셋째 문장이죠."


def upload(api, session_id: str, text: str):
    return api.post(
        f"/api/sessions/{session_id}/turns/audio",
        content=f"FAKE_STT:{text}".encode(),
        headers={"Content-Type": "audio/webm"},
    )


def rows(api) -> list[TurnLatency]:
    async def run():
        async with api.app.state.session_factory() as db:
            return list((await db.scalars(select(TurnLatency))).all())

    return api.portal.call(run)


def report(api, session_id: str, turn_id: str, speech: int, playback: int, notice=None):
    body = {"speech_to_request_ms": speech, "request_to_playback_ms": playback}
    if notice is not None:
        body["first_sound_notice"] = notice
    return api.post(f"/api/sessions/{session_id}/turns/{turn_id}/latency", json=body)


def test_voice_turn_records_server_stages_in_order(api):
    session_id = start(api, "voice")["session"]["id"]
    events = events_of(upload(api, session_id, f"__say__:{THREE}"))
    turn_id = next(e.turn_id for e in events if e.type == "turn")
    (row,) = rows(api)
    assert row.turn_id == turn_id and row.session_id == session_id
    assert row.audio_bytes == len(f"FAKE_STT:__say__:{THREE}".encode())
    stages = [row.upload_ms, row.first_token_ms, row.first_sentence_ms, row.done_ms]
    assert all(v is not None and v >= 0 for v in stages + [row.stt_ms])
    assert stages == sorted(stages)  # 업로드 ≤ 첫 글자 ≤ 첫 문장 ≤ 끝
    assert row.speech_to_request_ms is None and row.request_to_playback_ms is None


def test_text_turns_are_not_measured(api):
    session_id = start(api, "voice")["session"]["id"]
    api.post(f"/api/sessions/{session_id}/turns", json={"text": "글로 보낸 말"})
    assert rows(api) == []


def test_failed_voice_turn_still_records_end(api):
    session_id = start(api, "voice")["session"]["id"]
    events = events_of(upload(api, session_id, "__crash__"))
    assert events[-1].type == "error"
    (row,) = rows(api)
    assert row.done_ms is not None and row.first_sentence_ms is None


def test_web_reports_latency_and_can_overwrite(api):
    session_id = start(api, "voice")["session"]["id"]
    events = events_of(upload(api, session_id, f"__say__:{THREE}"))
    turn_id = next(e.turn_id for e in events if e.type == "turn")
    assert report(api, session_id, turn_id, 1300, 1800, notice=True).status_code == 204
    assert rows(api)[0].first_sound_notice is True
    assert report(api, session_id, turn_id, 1250, 1700).status_code == 204
    (row,) = rows(api)
    assert (row.speech_to_request_ms, row.request_to_playback_ms) == (1250, 1700)
    assert row.first_sound_notice is False


def test_report_errors(api):
    session_id = start(api, "voice")["session"]["id"]
    events = events_of(upload(api, session_id, f"__say__:{THREE}"))
    turn_id = next(e.turn_id for e in events if e.type == "turn")
    other = start(api, "voice")["session"]["id"]

    response = report(api, "no-such-session", turn_id, 1, 1)
    assert response.json()["error"]["code"] == "session_not_found"
    for sid, tid in ((session_id, "no-such-turn"), (other, turn_id)):
        response = report(api, sid, tid, 1, 1)
        assert response.status_code == 404 and response.json()["error"]["code"] == "turn_not_found"
    for speech, playback in ((-1, 1), (1, 10 * 60 * 1000 + 1)):
        assert report(api, session_id, turn_id, speech, playback).status_code == 422


def add_rows(
    api, session_id: str, values: list[tuple[int | None, int | None, int]], notice=frozenset()
) -> None:
    """(말 끝 → 요청, 요청 → 첫 소리, 인식) 값으로 측정 행을 오래된 것부터 만든다.
    notice: 첫 소리가 검색 안내였던 행 번호."""

    async def run():
        async with api.app.state.session_factory() as db:
            base = utcnow() - timedelta(hours=1)
            for i, (speech, playback, stt) in enumerate(values):
                db.add(
                    TurnLatency(
                        turn_id=f"t{i}",
                        session_id=session_id,
                        created_at=base + timedelta(minutes=i),
                        stt_ms=stt,
                        speech_to_request_ms=speech,
                        request_to_playback_ms=playback,
                        first_sound_notice=i in notice,
                    )
                )
            await db.commit()

    api.portal.call(run)


def test_summary_reports_median_and_p90_of_total(api):
    session_id = start(api, "voice")["session"]["id"]
    # 전체 지연: 1000, 2000, …, 10000 (웹 보고 없는 행은 전체에서 빠진다)
    values = [(500 * (i + 1), 500 * (i + 1), 100 * (i + 1)) for i in range(10)]
    add_rows(api, session_id, values + [(None, None, 5000)], notice={0, 1})

    body = api.get("/api/latency").json()
    assert body["turns"][0]["turn_id"] == "t10"  # 최근 것부터
    assert body["turns"][1]["total_ms"] == 10000 and body["turns"][0]["total_ms"] is None
    summary = body["summary"]
    assert summary["count"] == 10
    assert summary["total_ms"] == {"median": 5500.0, "p90": 9000.0}
    # 첫 소리가 검색 안내였던 두 턴(1000, 2000)을 뺀 값: 3000~10000
    assert summary["total_ms_reply"] == {"median": 6500.0, "p90": 10000.0}
    assert summary["stages"]["stt_ms"] == 600.0  # 100~1000과 5000의 중앙값
    assert summary["stages"]["first_token_ms"] is None

    limited = api.get("/api/latency", params={"limit": 3}).json()
    assert [t["turn_id"] for t in limited["turns"]] == ["t10", "t9", "t8"]
    assert api.get("/api/latency", params={"limit": 0}).status_code == 422


def test_summary_is_empty_without_measurements(api):
    body = api.get("/api/latency").json()
    assert body == {
        "turns": [],
        "summary": {
            "count": 0,
            "total_ms": {"median": None, "p90": None},
            "total_ms_reply": {"median": None, "p90": None},
            "stages": {
                "upload_ms": None,
                "stt_ms": None,
                "first_token_ms": None,
                "first_sentence_ms": None,
                "done_ms": None,
                "speech_to_request_ms": None,
                "request_to_playback_ms": None,
                "open_llm_ms": None,
                "first_queued_ms": None,
                "first_synth_ms": None,
                "synth_wait_ms": None,
                "cancel_wait_ms": None,
            },
            "search_count": 0,
            "total_ms_search": {"median": None, "p90": None},
            "total_ms_no_search": {"median": None, "p90": None},
        },
    }


def test_voice_turn_records_detail_stages(api, caplog):
    caplog.set_level("INFO", logger="trailtalk.conversation")
    session_id = start(api, "voice")["session"]["id"]
    upload(api, session_id, f"__say__:{THREE}")
    (row,) = rows(api)
    assert row.sentence_count == 3
    assert row.reply_chars == len("첫 문장입니다.") + len("둘째 문장이에요.") + len(
        "셋째 문장이죠."
    )
    assert (row.tool_count, row.search_used) == (0, False)
    for value in (row.open_llm_ms, row.first_queued_ms, row.first_synth_ms, row.synth_wait_ms):
        assert value is not None and value >= 0
    # 문장이 분할돼 나온 뒤에야 첫 문장을 보낸다
    assert row.first_token_ms <= row.first_queued_ms <= row.first_sentence_ms
    assert row.cli_resumed is False
    assert row.cli_age_ms is not None
    # 한 줄 요약 로그
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("턴 지연(")]
    assert len(lines) == 1
    assert f"turn={row.turn_id}" in lines[0] and "sentences=3" in lines[0]
    assert "first_synth=" in lines[0] and "search=False" in lines[0]


def test_latency_api_exposes_detail_and_search_summary(api):
    session_id = start(api, "voice")["session"]["id"]
    events = events_of(upload(api, session_id, f"__say__:{THREE}"))
    turn_id = next(e.turn_id for e in events if e.type == "turn")
    report(api, session_id, turn_id, 1000, 2000)
    body = api.get("/api/latency").json()
    (item,) = body["turns"]
    assert item["sentence_count"] == 3 and item["search_used"] is False
    assert item["first_queued_ms"] is not None and item["cli_resumed"] is False
    assert body["summary"]["search_count"] == 0
    assert body["summary"]["total_ms_no_search"]["median"] == 3000.0
    assert body["summary"]["total_ms_search"]["median"] is None
    assert body["summary"]["stages"]["first_synth_ms"] is not None
