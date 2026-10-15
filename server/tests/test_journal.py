"""일지·노트 API(S2-07). 시간대는 기본 Asia/Seoul(UTC+9)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import (
    ConversationSession,
    ExtractStatus,
    Note,
    NoteKind,
    SessionStatus,
    Turn,
    TurnRole,
)


def run(client, fn):
    async def go():
        async with client.app.state.session_factory() as db:
            result = await fn(db)
            await db.commit()
            return result

    return client.portal.call(go)


def add_session(client, started_at, *, spoke=True, title="제목", summary="첫 줄\n둘째 줄", **kw):
    async def fn(db):
        convo = ConversationSession(
            started_at=started_at,
            title=title,
            summary=summary,
            status=kw.get("status", SessionStatus.ENDED),
            extract_status=kw.get("extract_status", ExtractStatus.DONE),
            tags=kw.get("tags", ["산책"]),
        )
        db.add(convo)
        await db.flush()
        db.add(Turn(session_id=convo.id, seq=0, role=TurnRole.ASSISTANT, text="안녕하세요!"))
        if spoke:
            db.add(Turn(session_id=convo.id, seq=1, role=TurnRole.USER, text="앱 아이디어 있어"))
            db.add(
                Turn(
                    session_id=convo.id,
                    seq=2,
                    role=TurnRole.ASSISTANT,
                    text="오 좋아요.",
                    interrupted=True,
                )
            )
        return convo.id

    return run(client, fn)


def add_note(client, session_id, kind, content, **kw):
    async def fn(db):
        note = Note(session_id=session_id, kind=kind, content=content, **kw)
        db.add(note)
        await db.flush()
        return note.id

    return run(client, fn)


def kst(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=UTC) - timedelta(hours=9)  # 현지 시각 → UTC


def test_list_by_local_date_range(client):
    late = add_session(client, kst(2026, 10, 14, 23, 59), title="전날 밤")
    early = add_session(client, kst(2026, 10, 15, 0, 1), title="자정 직후")
    later = add_session(client, kst(2026, 10, 15, 18, 0), title="저녁")
    add_session(client, kst(2026, 10, 15, 12, 0), spoke=False)  # 인사말만 있는 대화는 뺀다
    add_note(client, later, NoteKind.IDEA, "아이디어")
    add_note(client, later, NoteKind.IDEA, "아이디어 2")
    add_note(client, later, NoteKind.TODO, "할 일")

    body = client.get("/api/journal", params={"from": "2026-10-15", "to": "2026-10-15"}).json()
    assert [item["id"] for item in body] == [later, early]  # 최신순
    first = body[0]
    assert first["date"] == "2026-10-15"
    assert first["title"] == "저녁"
    assert first["summary"] == ["첫 줄", "둘째 줄"]
    assert first["tags"] == ["산책"]
    assert first["journal_status"] == "done" and first["status"] == "ended"
    assert first["counts"] == {"idea": 2, "todo": 1, "memo": 0}

    body = client.get("/api/journal", params={"from": "2026-10-14", "to": "2026-10-14"}).json()
    assert [(item["id"], item["date"]) for item in body] == [(late, "2026-10-14")]


def test_default_range_is_last_30_days(client):
    now = datetime.now(UTC)
    recent = add_session(client, now - timedelta(days=3))
    add_session(client, now - timedelta(days=40))
    active = add_session(
        client, now, status=SessionStatus.ACTIVE, extract_status=None, title=None, summary=None
    )
    body = client.get("/api/journal").json()
    assert [item["id"] for item in body] == [active, recent]
    assert body[0]["journal_status"] is None and body[0]["summary"] == []


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"from": "2026-10-16", "to": "2026-10-15"}, "invalid_range"),
        ({"from": "2025-01-01", "to": "2026-10-15"}, "invalid_range"),
        ({"from": "10/15"}, "validation_error"),
        ({"to": "9999-12-31"}, "invalid_range"),  # 시간대 변환이 넘치는 날짜
        ({"from": "0001-01-01", "to": "0001-01-02"}, "invalid_range"),
    ],
)
def test_list_rejects_bad_ranges(client, params, code):
    response = client.get("/api/journal", params=params)
    assert response.status_code == 422 and response.json()["error"]["code"] == code


def test_detail_has_summary_notes_and_transcript(client):
    session_id = add_session(client, kst(2026, 10, 15, 9))
    idea = add_note(client, session_id, NoteKind.IDEA, "쓰레기통 지도", starred=True)
    add_note(client, session_id, NoteKind.TODO, "데이터 찾기")
    body = client.get(f"/api/journal/{session_id}").json()
    assert body["session"]["id"] == session_id and body["session"]["date"] == "2026-10-15"
    assert [(n["id"], n["kind"], n["starred"], n["done"]) for n in body["notes"]][0] == (
        idea,
        "idea",
        True,
        False,
    )
    assert [n["content"] for n in body["notes"]] == ["쓰레기통 지도", "데이터 찾기"]
    assert [(t["seq"], t["role"], t["text"], t["interrupted"]) for t in body["turns"]] == [
        (0, "assistant", "안녕하세요!", False),
        (1, "user", "앱 아이디어 있어", False),
        (2, "assistant", "오 좋아요.", True),
    ]
    missing = client.get("/api/journal/nope")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "session_not_found"


def test_patch_note_changes_only_sent_fields(client):
    session_id = add_session(client, kst(2026, 10, 15, 9))
    note_id = add_note(client, session_id, NoteKind.TODO, "데이터 찾기")

    body = client.patch(f"/api/notes/{note_id}", json={"done": True}).json()
    assert (body["done"], body["starred"], body["content"]) == (True, False, "데이터 찾기")
    body = client.patch(f"/api/notes/{note_id}", json={"starred": True, "content": "  새 내용 "})
    assert body.json()["content"] == "새 내용" and body.json()["done"] is True

    detail = client.get(f"/api/journal/{session_id}").json()
    assert detail["notes"][0]["starred"] is True and detail["notes"][0]["done"] is True


@pytest.mark.parametrize(
    "body",
    [
        {"content": "   "},
        {"content": "가" * 501},
        {"done": None},
        {"pinned": True},
        {"done": "yes"},
    ],
)
def test_patch_note_validation(client, body):
    session_id = add_session(client, kst(2026, 10, 15, 9))
    note_id = add_note(client, session_id, NoteKind.TODO, "데이터 찾기")
    response = client.patch(f"/api/notes/{note_id}", json=body)
    assert response.status_code == 422


def test_patch_missing_note(client):
    response = client.patch("/api/notes/nope", json={"done": True})
    assert response.status_code == 404 and response.json()["error"]["code"] == "note_not_found"
