"""일지·노트 API(S2-07). 시간대는 기본 Asia/Seoul(UTC+9)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.models import (
    ConversationSession,
    ExtractStatus,
    Note,
    NoteKind,
    SessionStatus,
    Turn,
    TurnLatency,
    TurnRole,
)
from app.persona.loader import load_persona


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
            topics=kw.get("topics", []),
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
    later = add_session(client, kst(2026, 10, 15, 18, 0), title="저녁", topics=["쓰레기통 지도"])
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
    assert first["topics"] == ["쓰레기통 지도"]
    assert body[1]["topics"] == []
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
    persona = load_persona(client.app.state.settings.persona_dir, "jenny").persona
    assert body["persona_name"] == persona.name  # 이름은 YAML에서 온다
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


def test_rename_journal(client):
    session_id = add_session(client, kst(2026, 10, 15, 9), title="자동 제목")
    response = client.patch(f"/api/journal/{session_id}", json={"title": "  산책  앱\n아이디어 "})
    assert response.status_code == 200
    assert response.json()["title"] == "산책 앱 아이디어"  # 줄바꿈·연속 공백은 한 칸으로
    assert response.json()["id"] == session_id
    assert client.get(f"/api/journal/{session_id}").json()["session"]["title"] == "산책 앱 아이디어"
    row = run(client, lambda db: db.get(ConversationSession, session_id))
    assert row.title_edited is True


@pytest.mark.parametrize(
    "body", [{"title": "  \n "}, {"title": "가" * 201}, {"title": None}, {}, {"tags": []}]
)
def test_rename_journal_validation(client, body):
    session_id = add_session(client, kst(2026, 10, 15, 9))
    assert client.patch(f"/api/journal/{session_id}", json=body).status_code == 422


def test_rename_missing_journal(client):
    response = client.patch("/api/journal/nope", json={"title": "제목"})
    assert response.status_code == 404 and response.json()["error"]["code"] == "session_not_found"


def test_delete_journal_removes_everything(client):
    session_id = add_session(client, kst(2026, 10, 15, 9))
    other = add_session(client, kst(2026, 10, 15, 10), title="남는 대화")
    add_note(client, session_id, NoteKind.IDEA, "아이디어")
    audio_dir = client.app.state.settings.audio_dir
    (audio_dir / session_id).mkdir(parents=True)
    (audio_dir / session_id / "t.webm").write_bytes(b"x")

    async def fn(db):
        turn = (await db.execute(select(Turn).where(Turn.session_id == session_id))).scalars()
        first = next(iter(turn))
        first.audio_path = f"{session_id}/t.webm"
        db.add(TurnLatency(turn_id="t", session_id=session_id))

    run(client, fn)
    response = client.delete(f"/api/journal/{session_id}")
    assert response.status_code == 204

    assert client.get(f"/api/journal/{session_id}").status_code == 404
    listed = client.get("/api/journal", params={"from": "2026-10-15", "to": "2026-10-15"}).json()
    assert [i["id"] for i in listed] == [other]
    assert not (audio_dir / session_id).exists()

    async def left(db):
        return [
            (
                await db.scalar(
                    select(func.count()).select_from(model).where(model.session_id == session_id)
                )
            )
            for model in (Turn, Note, TurnLatency)
        ]

    assert run(client, left) == [0, 0, 0]
    again = client.delete(f"/api/journal/{session_id}")
    assert again.status_code == 404 and again.json()["error"]["code"] == "session_not_found"


def test_delete_active_journal_is_refused(client):
    session_id = add_session(client, kst(2026, 10, 15, 9), status=SessionStatus.ACTIVE)
    response = client.delete(f"/api/journal/{session_id}")
    assert response.status_code == 409 and response.json()["error"]["code"] == "session_active"
    assert client.get(f"/api/journal/{session_id}").status_code == 200


def test_detail_has_citations(client):
    session_id = add_session(client, kst(2026, 10, 15, 9))
    note_id = add_note(client, session_id, NoteKind.MEMO, "검색으로 안 사실")
    plain = client.get(f"/api/journal/{session_id}").json()
    assert plain["summary_cites"] == [[], []] and plain["citations"] == []  # 인용 전 일지

    async def fn(db):
        convo = await db.get(ConversationSession, session_id)
        convo.summary_cites = [[], ["https://example.com/b"]]
        convo.citations = [
            {"title": "기사 A", "url": "https://example.com/a"},
            {"title": "기사 B", "url": "https://example.com/b"},
            {"title": "안 쓰인 출처", "url": "https://example.com/c"},
        ]
        (await db.get(Note, note_id)).cites = ["https://example.com/a", "https://example.com/b"]

    run(client, fn)
    body = client.get(f"/api/journal/{session_id}").json()
    # 번호는 요약 → 메모 차례로 처음 인용된 출처부터. 쓰이지 않은 출처는 목록에 없다
    assert body["summary_cites"] == [[], [1]]
    assert body["notes"][0]["cites"] == [2, 1]
    assert body["citations"] == [
        {"n": 1, "title": "기사 B", "url": "https://example.com/b"},
        {"n": 2, "title": "기사 A", "url": "https://example.com/a"},
    ]
    # 메모 내용을 고쳐도 근거 번호는 그대로 돌려준다
    edited = client.patch(f"/api/notes/{note_id}", json={"content": "고친 메모"}).json()
    assert edited["cites"] == [2, 1]


def test_open_ideas_empty(client):
    assert client.get("/api/notes/open-ideas").json() == {
        "items": [],
        "idea_count": 0,
        "todo_count": 0,
    }


def test_open_ideas_newest_first_open_only(client):
    """S3-39: 시작 화면 목록. 날짜 역순, 완료·다른 종류는 뺀다. 별표는 순서에 영향이 없다."""
    old = add_session(client, kst(2026, 10, 14, 9, 0))
    new = add_session(client, kst(2026, 10, 15, 9, 0))
    starred = add_note(
        client, old, NoteKind.IDEA, "별표", starred=True, created_at=kst(2026, 10, 13, 9, 0)
    )
    add_note(client, old, NoteKind.IDEA, "오래된 아이디어", created_at=kst(2026, 10, 14, 10, 0))
    add_note(client, new, NoteKind.IDEA, "새 아이디어", created_at=kst(2026, 10, 15, 10, 0))
    done_at = kst(2026, 10, 15, 11, 0)
    add_note(client, new, NoteKind.IDEA, "끝낸 아이디어", done=True, created_at=done_at)
    add_note(client, new, NoteKind.TODO, "할 일", created_at=kst(2026, 10, 15, 12, 0))

    res = client.get("/api/notes/open-ideas").json()
    body = res["items"]
    assert (res["idea_count"], res["todo_count"]) == (3, 1)  # 완료한 아이디어는 세지 않는다
    assert [n["content"] for n in body] == ["새 아이디어", "오래된 아이디어", "별표"]
    assert [n["session_id"] for n in body] == [new, old, old]
    assert body[2]["starred"] is True and body[2]["id"] == starred

    # 개수를 줄일 수 있고, 완료하면 목록에서 빠진다
    assert [n["content"] for n in client.get("/api/notes/open-ideas?limit=1").json()["items"]] == [
        "새 아이디어"
    ]
    assert client.patch(f"/api/notes/{starred}", json={"done": True}).status_code == 200
    res = client.get("/api/notes/open-ideas").json()
    assert len(res["items"]) == 2 and res["idea_count"] == 2
    assert client.get("/api/notes/open-ideas?limit=0").status_code == 422
