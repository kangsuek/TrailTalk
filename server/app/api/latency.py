"""GET /api/latency: 음성 턴 지연 측정 요약(계획서 S3-07, NFR-01 측정값 기록용)."""

import math
import statistics
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.db.models import TurnLatency
from app.db.session import DbSession

router = APIRouter(tags=["latency"])

# 요약에 중앙값을 내는 단계(ms)
STAGES = (
    "upload_ms",
    "stt_ms",
    "first_token_ms",
    "first_sentence_ms",
    "done_ms",
    "speech_to_request_ms",
    "request_to_playback_ms",
)


class LatencyTurn(BaseModel):
    turn_id: str
    session_id: str
    created_at: datetime
    audio_bytes: int | None
    upload_ms: int | None
    stt_ms: int | None
    first_token_ms: int | None
    first_sentence_ms: int | None
    done_ms: int | None
    speech_to_request_ms: int | None
    request_to_playback_ms: int | None
    first_sound_notice: bool | None
    # 말 끝 → 캐릭터 첫 소리(NFR-01). 웹 보고가 있을 때만
    total_ms: int | None


class Spread(BaseModel):
    median: float | None
    p90: float | None


class LatencySummary(BaseModel):
    count: int  # 전체 지연(total_ms)이 있는 턴 수
    total_ms: Spread
    # 첫 소리가 답변 문장인 턴만(검색 안내 음성으로 시작한 턴을 뺀 값)
    total_ms_reply: Spread
    stages: dict[str, float | None]  # 단계별 중앙값


class LatencyOut(BaseModel):
    turns: list[LatencyTurn]
    summary: LatencySummary


def _p90(values: list[int]) -> float | None:
    """가장 가까운 순위 방식의 90% 값."""
    if not values:
        return None
    ordered = sorted(values)
    return float(ordered[math.ceil(0.9 * len(ordered)) - 1])


def _median(values: list[int]) -> float | None:
    return float(statistics.median(values)) if values else None


def _total(row: TurnLatency) -> int | None:
    if row.speech_to_request_ms is None or row.request_to_playback_ms is None:
        return None
    return row.speech_to_request_ms + row.request_to_playback_ms


@router.get("/latency")
async def latency(db: DbSession, limit: Annotated[int, Query(ge=1, le=500)] = 100) -> LatencyOut:
    """최근 음성 턴부터 limit개의 지연과 요약(중앙값·90% 값)."""
    rows = list(
        (
            await db.scalars(
                select(TurnLatency).order_by(TurnLatency.created_at.desc()).limit(limit)
            )
        ).all()
    )
    turns = [
        LatencyTurn(
            turn_id=row.turn_id,
            session_id=row.session_id,
            created_at=row.created_at,
            audio_bytes=row.audio_bytes,
            first_sound_notice=row.first_sound_notice,
            **{stage: getattr(row, stage) for stage in STAGES},
            total_ms=_total(row),
        )
        for row in rows
    ]
    totals = [t.total_ms for t in turns if t.total_ms is not None]
    reply_totals = [
        t.total_ms for t in turns if t.total_ms is not None and not t.first_sound_notice
    ]
    stages = {
        stage: _median([v for t in turns if (v := getattr(t, stage)) is not None])
        for stage in STAGES
    }
    return LatencyOut(
        turns=turns,
        summary=LatencySummary(
            count=len(totals),
            total_ms=Spread(median=_median(totals), p90=_p90(totals)),
            total_ms_reply=Spread(median=_median(reply_totals), p90=_p90(reply_totals)),
            stages=stages,
        ),
    )
