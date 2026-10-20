"""끼어들기 기록 업로드(V2-M0-05): 저장, 멱등, 검증."""

from sqlalchemy import select

from app.db.models import BargeInEvent


def event(id_: str = "e1", **extra) -> dict:
    return {
        "id": id_,
        "session_id": "s1",
        "turn_id": "t1",
        "occurred_at": "2026-10-20T05:00:00Z",
        **extra,
    }


def stored(client) -> list[BargeInEvent]:
    async def run():
        async with client.app.state.session_factory() as db:
            return list((await db.scalars(select(BargeInEvent).order_by(BargeInEvent.id))).all())

    return client.portal.call(run)


def test_stores_events_with_defaults(client):
    body = {
        "events": [
            event("e1", probe_to_confirm_ms=240, stop_ms=3, played_ratio=0.5, next_turn_id="t2"),
            event("e2"),
        ]
    }
    response = client.post("/api/barge-in-events", json=body)
    assert response.status_code == 200
    assert response.json() == {"accepted": 2}
    first, second = stored(client)
    assert (first.probe_to_confirm_ms, first.stop_ms, first.played_ratio) == (240, 3, 0.5)
    assert first.next_turn_id == "t2"
    assert first.result == "real"
    assert second.probe_to_confirm_ms is None
    assert first.occurred_at.isoformat().startswith("2026-10-20T05:00:00")


def test_resending_the_same_ids_is_idempotent(client):
    batch = {"events": [event("e1"), event("e1"), event("e2")]}
    assert client.post("/api/barge-in-events", json=batch).json() == {"accepted": 2}
    assert client.post("/api/barge-in-events", json=batch).json() == {"accepted": 0}
    assert len(stored(client)) == 2


def test_result_is_a_free_string_but_bounded(client):
    ok = client.post("/api/barge-in-events", json={"events": [event(result="probe_reverted")]})
    assert ok.json() == {"accepted": 1}
    assert stored(client)[0].result == "probe_reverted"
    long = client.post("/api/barge-in-events", json={"events": [event("e2", result="x" * 33)]})
    assert long.status_code == 422


def test_rejects_bad_events(client):
    bad = [
        event(played_ratio=1.5),
        event(stop_ms=-1),
        event(unknown=1),
        {"id": "e1", "session_id": "s1"},
    ]
    bad.append(event(occurred_at="2026-10-20T05:00:00"))  # 시간대 없음
    for item in bad:
        assert client.post("/api/barge-in-events", json={"events": [item]}).status_code == 422
    assert client.post("/api/barge-in-events", json={"events": [], "x": 1}).status_code == 422
    assert stored(client) == []


def test_empty_batch_and_size_limit(client):
    assert client.post("/api/barge-in-events", json={"events": []}).json() == {"accepted": 0}
    big = {"events": [event(f"e{i}") for i in range(201)]}
    assert client.post("/api/barge-in-events", json=big).status_code == 422
