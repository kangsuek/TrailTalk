"""무발화 타임아웃(계획서 S2-06, 설계서 4.4): 오래 말이 없는 세션을 서버가 끝낸다.

클라이언트 타이머의 안전망이다. 끝내기를 누르지 않고 떠난 세션도 여기서 끝나므로 CLI·런타임(MCP
토큰)·CLI 기록 파일이 정리되고 일지 정리(추출)가 돈다.
종료는 conversation.end_session을 그대로 쓴다.

앱이 시작하면 바로 한 번 돌고(서버가 꺼진 동안 지난 세션, 정리 중에 꺼져 pending으로 남은 추출),
그 뒤 idle_check_interval_s마다 돈다. 보관 기간이 지난 음성 원본 정리(app/jobs/audio.py)도
함께 한다.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import func, select

from app.db.models import ConversationSession, ExtractStatus, SessionStatus, Turn
from app.db.types import utcnow
from app.jobs import audio, extract
from app.llm.claude_cli import delete_cli_session_file
from app.services import conversation

logger = logging.getLogger("trailtalk.idle")


def _last_turn_at():
    return (
        select(Turn.session_id, func.max(Turn.created_at).label("last_at"))
        .group_by(Turn.session_id)
        .subquery()
    )


async def _idle_sessions(
    app: FastAPI, cutoff: datetime, session_id: str | None = None
) -> dict[str, datetime]:
    """끝나지 않았고 마지막 턴(없으면 시작 시각)이 cutoff보다 오래된 세션 → 마지막 활동 시각.
    다시 연 대화는 다시 연 시각도 활동으로 본다(재개 인사말을 받기 전에 끝내지 않게)."""
    last_turn = _last_turn_at()
    query = (
        select(
            ConversationSession.id,
            ConversationSession.started_at,
            ConversationSession.reopened_at,
            last_turn.c.last_at,
        )
        .outerjoin(last_turn, last_turn.c.session_id == ConversationSession.id)
        .where(ConversationSession.status != SessionStatus.ENDED)
    )
    if session_id is not None:
        query = query.where(ConversationSession.id == session_id)
    async with app.state.session_factory() as db:
        rows = await db.execute(query)
        last = {
            sid: max(at for at in (started_at, reopened_at, last_at) if at is not None)
            for sid, started_at, reopened_at, last_at in rows
        }
        return {sid: at for sid, at in last.items() if at < cutoff}


async def sweep_idle(app: FastAPI, now: datetime | None = None) -> list[str]:
    """마지막 턴(없으면 시작 시각)이 idle_timeout_s보다 오래된 세션을 끝낸다. 끝낸 세션 ID 목록.
    끝난 시각(ended_at)은 그 마지막 활동 시각으로 남긴다.

    세션마다 DB 세션을 새로 열어, 한 세션의 실패가 다른 세션 정리를 막지 않게 한다.
    """
    settings = app.state.settings
    cutoff = (now or utcnow()) - timedelta(seconds=settings.idle_timeout_s)
    ended: list[str] = []
    for session_id in await _idle_sessions(app, cutoff):
        runtime = app.state.runtimes.get(session_id)
        if runtime is not None and runtime.turn_lock.locked():
            continue  # 답변 중이면 다음 차례에 다시 본다
        # 앞 세션을 끝내는 동안 말을 걸었을 수 있어 끝내기 직전에 다시 확인한다
        idle = await _idle_sessions(app, cutoff, session_id)
        if session_id not in idle:
            continue
        try:
            async with app.state.session_factory() as db:
                convo = await db.get(ConversationSession, session_id)
                if convo is None:
                    continue
                # 끝난 시각은 마지막 활동 시각이다(서버가 꺼져 있던 동안이 끼어들지 않게)
                await conversation.end_session(app, db, convo, ended_at=idle[session_id])
        except Exception:
            logger.exception("무발화 세션 종료 실패(session=%s)", session_id)
            continue
        ended.append(session_id)
        logger.info("무발화로 세션 종료(session=%s)", session_id)
    return ended


async def resume_pending(app: FastAPI) -> list[str]:
    """끝났지만 정리가 pending으로 남은 세션(정리 중 서버 종료 등)의 추출을 다시 띄운다.

    종료 도중 꺼졌다면 CLI 기록 파일이 남았을 수 있어 함께 지운다(없으면 아무 일도 없다).
    """
    async with app.state.session_factory() as db:
        rows = await db.execute(
            select(ConversationSession.id, ConversationSession.cli_session_id).where(
                ConversationSession.status == SessionStatus.ENDED,
                ConversationSession.extract_status == ExtractStatus.PENDING,
            )
        )
        pending = list(rows)
    for session_id, cli_session_id in pending:
        await asyncio.to_thread(delete_cli_session_file, cli_session_id)
        extract.ensure_extraction(app, session_id)
    if pending:
        logger.info("남은 일지 정리 재개 %d건", len(pending))
    return [session_id for session_id, _ in pending]


async def run(app: FastAPI) -> None:
    """앱 수명 동안 도는 감시 루프. 한 번 실패해도 다음 차례에 다시 돈다."""
    first = True
    while True:
        try:
            if first:
                await resume_pending(app)
                first = False
            await sweep_idle(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("무발화 감시 실패")
        try:
            await audio.purge_old_audio(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("음성 원본 정리 실패")
        await asyncio.sleep(app.state.settings.idle_check_interval_s)
