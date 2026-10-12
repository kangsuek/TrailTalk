from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, StatementError

from app.db.models import (
    ConversationSession,
    Note,
    NoteKind,
    Persona,
    SessionStatus,
    Turn,
    TurnRole,
    UserProfile,
)


async def make_session(db, **values) -> ConversationSession:
    session = ConversationSession(**values)
    db.add(session)
    await db.commit()
    return session


async def test_session_defaults_and_turn_order(db_session):
    convo = await make_session(db_session, tags=["산책", "아이디어"])
    db_session.add_all(
        [
            Turn(session_id=convo.id, seq=2, role=TurnRole.ASSISTANT, text="좋아요!"),
            Turn(session_id=convo.id, seq=1, role=TurnRole.USER, text="안녕"),
        ]
    )
    await db_session.commit()
    db_session.expunge_all()

    loaded = await db_session.get(ConversationSession, convo.id)
    await db_session.refresh(loaded, ["turns"])
    assert len(loaded.id) == 36
    assert loaded.status is SessionStatus.ACTIVE
    assert loaded.tags == ["산책", "아이디어"]
    assert [t.seq for t in loaded.turns] == [1, 2]
    assert loaded.turns[0].role is TurnRole.USER
    assert loaded.turns[0].interrupted is False


async def test_duplicate_seq_rejected(db_session):
    convo = await make_session(db_session)
    db_session.add_all(
        [
            Turn(session_id=convo.id, seq=1, role=TurnRole.USER, text="a"),
            Turn(session_id=convo.id, seq=1, role=TurnRole.USER, text="b"),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.parametrize(
    ("table", "column", "extra"),
    [
        ("conversation_session", "status", "id, started_at, tags"),
        ("turn", "role", "id, session_id, seq, text, interrupted, created_at"),
        ("note", "kind", "id, session_id, content, starred, done, created_at"),
    ],
)
async def test_check_constraints_reject_unknown_values(db_session, table, column, extra):
    convo = await make_session(db_session)
    values = {
        "id": "'x1'",
        "started_at": "'2026-10-12 00:00:00'",
        "created_at": "'2026-10-12 00:00:00'",
        "tags": "'[]'",
        "session_id": f"'{convo.id}'",
        "seq": "1",
        "text": "'t'",
        "content": "'c'",
        "interrupted": "0",
        "starred": "0",
        "done": "0",
    }
    cols = [c.strip() for c in extra.split(",")]
    sql = (
        f"INSERT INTO {table} ({column}, {', '.join(cols)}) "
        f"VALUES ('unknown', {', '.join(values[c] for c in cols)})"
    )
    with pytest.raises(IntegrityError):
        await db_session.execute(text(sql))


async def test_invalid_enum_rejected_by_orm(db_session):
    db_session.add(ConversationSession(status="sleeping"))
    with pytest.raises((StatementError, LookupError)):
        await db_session.commit()


async def test_delete_session_cascades_and_turn_delete_nulls_note(db_session):
    convo = await make_session(db_session)
    turn = Turn(session_id=convo.id, seq=1, role=TurnRole.USER, text="저장해줘")
    db_session.add(turn)
    await db_session.commit()
    note = Note(session_id=convo.id, turn_id=turn.id, kind=NoteKind.IDEA, content="지도")
    db_session.add(note)
    await db_session.commit()

    await db_session.execute(text("DELETE FROM turn WHERE id = :id"), {"id": turn.id})
    await db_session.commit()
    db_session.expunge_all()
    assert (await db_session.get(Note, note.id)).turn_id is None

    await db_session.execute(
        text("DELETE FROM conversation_session WHERE id = :id"), {"id": convo.id}
    )
    await db_session.commit()
    assert (await db_session.execute(select(Note))).scalars().all() == []


async def test_orm_delete_session_removes_children(db_session):
    convo = await make_session(db_session)
    db_session.add(Turn(session_id=convo.id, seq=1, role=TurnRole.USER, text="a"))
    db_session.add(Note(session_id=convo.id, kind=NoteKind.TODO, content="b"))
    await db_session.commit()
    await db_session.delete(convo)
    await db_session.commit()
    assert (await db_session.execute(select(Turn))).scalars().all() == []
    assert (await db_session.execute(select(Note))).scalars().all() == []


async def test_foreign_key_enforced(db_session):
    db_session.add(Turn(session_id="no-such-session", seq=1, role=TurnRole.USER, text="a"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_datetimes_are_utc_aware(db_session):
    kst = timezone(timedelta(hours=9))
    started = datetime(2026, 10, 12, 7, 30, tzinfo=kst)
    convo = await make_session(db_session, started_at=started)
    db_session.expunge_all()
    loaded = await db_session.get(ConversationSession, convo.id)
    assert loaded.started_at.tzinfo is UTC
    assert loaded.started_at == started
    assert loaded.started_at.hour == 22  # 07:30 KST = 전날 22:30 UTC


async def test_naive_datetime_rejected(db_session):
    db_session.add(ConversationSession(started_at=datetime(2026, 10, 12, 7, 30)))
    with pytest.raises(StatementError):
        await db_session.commit()


async def test_user_profile_persona_reference(db_session):
    db_session.add(Persona(id="jenny", yaml_path="personas/jenny.yaml", version="abc"))
    db_session.add(
        UserProfile(id=1, nickname="다니엘님", interests=["등산", "테크"], persona_id="jenny")
    )
    await db_session.commit()
    db_session.expunge_all()
    profile = await db_session.get(UserProfile, 1)
    assert profile.interests == ["등산", "테크"]
    assert profile.keep_audio is False
    assert profile.updated_at.tzinfo is UTC


async def test_user_profile_rejects_unknown_persona(db_session):
    db_session.add(UserProfile(id=1, persona_id="no-such-persona"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_user_profile_is_single_row(db_session):
    db_session.add(UserProfile(id=2))
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_deleting_persona_clears_profile_reference(db_session):
    db_session.add(Persona(id="jenny", yaml_path="personas/jenny.yaml", version="abc"))
    db_session.add(UserProfile(id=1, persona_id="jenny"))
    await db_session.commit()
    await db_session.execute(text("DELETE FROM persona WHERE id = 'jenny'"))
    await db_session.commit()
    db_session.expunge_all()
    assert (await db_session.get(UserProfile, 1)).persona_id is None


async def test_json_list_in_place_change_is_saved(db_session):
    convo = await make_session(db_session, tags=["a"])
    convo.tags.append("b")
    await db_session.commit()
    db_session.expunge_all()
    assert (await db_session.get(ConversationSession, convo.id)).tags == ["a", "b"]
