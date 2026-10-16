"""세션 종료 추출(계획서 S2-02, 설계서 4.4): 대화 전문을 일지(제목·요약·태그·노트)로 정리한다.

세션이 끝나면(끝내기 API, end_session 도구, 무발화 타임아웃) ensure_extraction이 세션당 하나의
백그라운드 작업을 띄운다. 가벼운 모델을 CLI 단발 호출로 부르고(app/llm/claude_cli.run_oneshot),
결과를 Pydantic 스키마로 검증한다. 실패하면 한 번 다시 시도하고, 그래도 실패하면 failed로 둔다.
아이디어·할 일·메모는 중복(app/jobs/dedupe.py)을 거른 뒤 노트로 저장한다.
상태(conversation_session.extract_status)는 pending → done/failed다.
"""

import asyncio
import logging
from collections.abc import Sequence
from typing import Annotated

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from sqlalchemy import func, select

from app.db.models import ConversationSession, ExtractStatus, Note, NoteKind, Turn, TurnRole
from app.jobs.dedupe import matches_saved, new_items
from app.llm.backend import LlmError
from app.llm.claude_cli import run_oneshot
from app.persona.rules import EXTRACT_INSTRUCTION, EXTRACT_SAVED_SECTION
from app.services.profile import profile_with_persona

logger = logging.getLogger("trailtalk.extract")

ATTEMPTS = 2  # 첫 시도 + 재시도 1회
TRANSCRIPT_LIMIT = 100_000  # 이보다 긴 전문은 앞부분을 잘라 뒷부분을 남긴다

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]


class Extraction(BaseModel):
    """추출 결과 스키마. CLI --json-schema에도 이 스키마를 넘긴다."""

    model_config = ConfigDict(extra="forbid")

    title: Title
    summary: Annotated[list[Line], Field(min_length=1, max_length=3)]
    ideas: Annotated[list[Line], Field(max_length=10)]
    todos: Annotated[list[Line], Field(max_length=10)]
    memos: Annotated[list[Line], Field(max_length=10)]
    tags: Annotated[list[Tag], Field(max_length=5)]


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _clean_tags(tags: Sequence[str]) -> list[str]:
    """화면이 앞에 #을 붙이므로 모델이 붙인 #은 뗀다. 빈 값·중복은 뺀다(순서 유지)."""
    cleaned = (_one_line(tag.lstrip("#＃ \t")) for tag in tags)
    return list(dict.fromkeys(tag for tag in cleaned if tag))


def _escape_tags(text: str) -> str:
    """글 안에서 프롬프트의 구분 태그(<대화>, <저장한 노트>)를 닫지 못하게 한다."""
    return text.replace("</대화>", "</ 대화>").replace("</저장한 노트>", "</ 저장한 노트>")


def build_transcript(turns: list[Turn], assistant: str) -> str:
    lines = []
    for t in turns:
        speaker = "사용자" if t.role is TurnRole.USER else assistant
        mark = " (말이 끊김)" if t.interrupted else ""
        text = _escape_tags(" ".join(t.text.split()))
        lines.append(f"{speaker}: {text}{mark}")
    kept: list[str] = []
    size = 0
    for line in reversed(lines):  # 너무 길면 뒷부분(최근 대화)을 줄 단위로 남긴다
        size += len(line) + 1
        if size > TRANSCRIPT_LIMIT:
            kept.append("(앞부분 생략)")
            break
        kept.append(line)
    return "\n".join(reversed(kept))


SAVED_LABELS = {NoteKind.IDEA: "아이디어", NoteKind.TODO: "할 일", NoteKind.MEMO: "메모"}


def build_prompt(
    turns: list[Turn], assistant: str, saved: Sequence[tuple[NoteKind, str]] = ()
) -> str:
    """saved: 대화 중 save_note로 이미 저장한 노트(종류, 내용). 추출이 같은 항목을 다시 뽑지 않게
    알려 준다. 종류를 붙여 다른 종류의 항목까지 빼지 않게 한다. 노트는 모델이 만든 글이라
    (웹 내용이 섞일 수 있다) 태그로 감싸 지시로 따르지 않게 한다."""
    lines = [
        f"- [{SAVED_LABELS[NoteKind(kind)]}] {_escape_tags(' '.join(content.split()))}"
        for kind, content in saved
        if content.strip()
    ]
    section = EXTRACT_SAVED_SECTION.format(items="\n".join(lines)) if lines else ""
    return EXTRACT_INSTRUCTION.format(
        assistant=assistant, saved=section, transcript=build_transcript(turns, assistant)
    )


async def _call(app: FastAPI, prompt: str) -> Extraction:
    settings = app.state.settings
    raw = await run_oneshot(
        settings,
        prompt,
        model=settings.llm_light_model,
        json_schema=Extraction.model_json_schema(),
        timeout_s=settings.extract_timeout_s,
    )
    return Extraction.model_validate(raw)


async def _shielded(app: FastAPI, coro) -> None:
    """DB 쓰기를 취소에서 보호한다. 추출 작업은 asyncio 태스크라 앱 종료 때 asyncio 취소를 받는데,
    anyio CancelScope(shield)는 이를 막지 못한다. 그래서 쓰기를 별도 태스크로 돌려 끝까지 마치게
    하고, cancel_all이 남은 쓰기를 기다린다(커밋 도중 끊겨 죽은 커넥션이 풀에 남지 않게)."""
    writes: set[asyncio.Task] = app.state.extract_writes
    task = asyncio.create_task(coro)
    writes.add(task)
    task.add_done_callback(writes.discard)
    await asyncio.shield(task)


async def _set_status(app: FastAPI, session_id: str, status: ExtractStatus) -> None:
    async def write() -> None:
        async with app.state.session_factory() as db:
            convo = await db.get(ConversationSession, session_id)
            if convo is not None:
                convo.extract_status = status
                await db.commit()

    await _shielded(app, write())


async def run_extraction(app: FastAPI, session_id: str) -> Extraction | None:
    """세션 하나를 정리한다. 이미 done/failed면 아무것도 하지 않는다. 결과(실패면 None)."""
    settings = app.state.settings
    async with app.state.session_factory() as db:
        convo = await db.get(ConversationSession, session_id)
        if convo is None or convo.extract_status in (ExtractStatus.DONE, ExtractStatus.FAILED):
            return None
        convo.extract_status = ExtractStatus.PENDING
        rows = await db.execute(
            select(Turn).where(Turn.session_id == session_id).order_by(Turn.seq)
        )
        turns = list(rows.scalars())
        notes = await db.execute(
            select(Note.kind, Note.content)
            .where(Note.session_id == session_id)
            .order_by(Note.created_at)
        )
        saved = [(kind, content) for kind, content in notes]  # 대화 중 save_note로 저장한 노트
        _, loaded = await profile_with_persona(db, settings)
        await db.commit()
    if not any(t.role is TurnRole.USER for t in turns):
        # 인사만 하고 끝난 대화는 정리할 것이 없다(사용량을 쓰지 않는다)
        await _set_status(app, session_id, ExtractStatus.DONE)
        return None

    prompt = build_prompt(turns, loaded.persona.name, saved)
    result: Extraction | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            result = await _call(app, prompt)
            break
        except (LlmError, ValidationError) as exc:
            # 대화에서 나온 내용(모델 출력)은 로그에 남기지 않는다
            reason = (
                f"스키마 오류 {exc.error_count()}건"
                if isinstance(exc, ValidationError)
                else exc.code
            )
            logger.warning(
                "추출 실패(session=%s, %d/%d): %s", session_id, attempt, ATTEMPTS, reason
            )
    if result is None:
        await _set_status(app, session_id, ExtractStatus.FAILED)
        return None

    async def save() -> None:
        async with app.state.session_factory() as db:
            convo = await db.get(ConversationSession, session_id)
            if convo is None:
                return
            # 요약은 줄 목록으로 저장하므로 항목 안의 줄바꿈은 한 칸으로 줄인다
            # (빈 줄·줄 수 초과 방지)
            convo.title = _one_line(result.title)
            convo.summary = "\n".join(line for line in map(_one_line, result.summary) if line)
            convo.tags = _clean_tags(result.tags)
            # 대화 중 save_note로 저장한 노트와 겹치지 않는 항목만 노트로 남긴다(S2-03).
            # 같은 종류의 저장 노트와는 괄호 설명을 뺀 글로도 비교한다(matches_saved)
            rows = await db.execute(
                select(Note.kind, Note.content).where(Note.session_id == session_id)
            )
            saved_notes = [(kind, content) for kind, content in rows]
            existing = [content for _, content in saved_notes]
            for kind, items in (
                (NoteKind.IDEA, result.ideas),
                (NoteKind.TODO, result.todos),
                (NoteKind.MEMO, result.memos),
            ):
                same_kind = [content for k, content in saved_notes if k is kind]
                fresh = [i for i in items if not any(matches_saved(s, i) for s in same_kind)]
                for content in new_items(existing, fresh):
                    db.add(Note(session_id=session_id, kind=kind, content=content))
                    existing.append(content)
            # 정리하는 사이 새 턴(오프라인 큐의 기록 등, S3-12)이 들어왔으면 끝내지 않고 한 번 더
            # 돈다(_guarded가 pending을 보고 다시 부른다)
            now_turns = await db.scalar(
                select(func.count()).select_from(Turn).where(Turn.session_id == session_id)
            )
            done = now_turns == len(turns)
            convo.extract_status = ExtractStatus.DONE if done else ExtractStatus.PENDING
            await db.commit()

    await _shielded(app, save())
    logger.info("추출 완료(session=%s)", session_id)
    return result


def ensure_extraction(app: FastAPI, session_id: str) -> asyncio.Task | None:
    """세션의 추출 작업을 띄운다. 이미 돌고 있으면 그 작업을 돌려준다(세션당 하나).

    앱이 끝나는 중이면 띄우지 않는다(pending으로 남아 다음 시작 때 정리된다).
    """
    if app.state.extract_closed:
        return None
    tasks: dict[str, asyncio.Task] = app.state.extractions
    task = tasks.get(session_id)
    if task is None or task.done():  # 끝난(잊기 직전의) 작업은 새 요청을 받을 수 없다
        task = asyncio.create_task(_guarded(app, session_id), name=f"extract-{session_id}")
        tasks[session_id] = task

        def forget(done: asyncio.Task) -> None:
            if tasks.get(session_id) is done:
                tasks.pop(session_id)

        task.add_done_callback(forget)
    return task


async def wait_extraction(app: FastAPI, session_id: str, timeout_s: float) -> None:
    """진행 중인 추출이 끝나길 최대 timeout_s 기다린다. 시간이 지나도 추출은 멈추지 않는다."""
    task = app.state.extractions.get(session_id)
    if task is None:
        return
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout_s)
    except TimeoutError:
        logger.info("추출이 아직 끝나지 않아 먼저 응답(session=%s)", session_id)
    except Exception:  # 정리 실패가 끝내기 응답까지 실패로 만들지 않는다(세션은 이미 끝났다)
        logger.exception("추출 대기 중 예외(session=%s)", session_id)


async def _status(app: FastAPI, session_id: str) -> ExtractStatus | None:
    async with app.state.session_factory() as db:
        return await db.scalar(
            select(ConversationSession.extract_status).where(ConversationSession.id == session_id)
        )


_RERUNS = 5


async def _guarded(app: FastAPI, session_id: str) -> Extraction | None:
    try:
        result = await run_extraction(app, session_id)
        # 이 작업이 도는 사이에 다시 정리 요청(retry)이나 새 턴(오프라인 큐의 기록)이 pending으로
        # 바꿨으면 다시 돈다(그 요청의 ensure_extraction은 돌던 이 작업을 받아 새로 띄우지 않았다).
        # 기록이 계속 들어와도 끝나도록 횟수에 상한을 둔다(남으면 다음 기록이나 앱 시작 때 정리)
        for _ in range(_RERUNS):
            if await _status(app, session_id) is not ExtractStatus.PENDING:
                break
            result = await run_extraction(app, session_id)
        return result
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("추출 작업 예외(session=%s)", session_id)
        await _set_status(app, session_id, ExtractStatus.FAILED)
        return None


async def cancel_all(app: FastAPI) -> None:
    """앱 종료 때 남은 추출을 멈추고 새 추출을 받지 않는다. 진행 중인 DB 쓰기는 끝까지 기다린다.

    pending으로 남은 세션은 다음 시작 때 다시 정리한다(S2-06).
    """
    app.state.extract_closed = True
    tasks = list(app.state.extractions.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.wait(tasks)
    writes = list(app.state.extract_writes)
    if writes:
        await asyncio.wait(writes)
