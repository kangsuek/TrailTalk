"""세션 종료 추출(계획서 S2-02, 설계서 4.4): 대화 전문을 일지(제목·요약·태그·노트)로 정리한다.

세션이 끝나면(끝내기 API, end_session 도구, 무발화 타임아웃) ensure_extraction이 세션당 하나의
백그라운드 작업을 띄운다. 가벼운 모델을 CLI 단발 호출로 부르고(app/llm/claude_cli.run_oneshot),
결과를 Pydantic 스키마로 검증한다. 실패하면 한 번 다시 시도하고, 그래도 실패하면 failed로 둔다.
아이디어·할 일·메모는 중복(app/jobs/dedupe.py)을 거른 뒤 노트로 저장한다.
아이디어 주제(topics, S3-17)는 지난 대화의 주제 목록을 함께 주어 같은 아이디어면 같은 이름을
고르게 하고, 공백·대소문자만 다른 이름은 기존 이름으로 맞춘다.
상태(conversation_session.extract_status)는 pending → done/failed다.
"""

import asyncio
import logging
import re
from collections.abc import Sequence
from typing import Annotated

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from sqlalchemy import func, select

from app.db.models import ConversationSession, ExtractStatus, Note, NoteKind, Turn, TurnRole
from app.jobs.dedupe import matches_saved, new_items, normalize
from app.jobs.page_title import improve_titles
from app.llm.backend import LlmError
from app.llm.claude_cli import run_oneshot
from app.persona.rules import (
    EXTRACT_INSTRUCTION,
    EXTRACT_SAVED_SECTION,
    EXTRACT_SOURCES_SECTION,
    EXTRACT_TOPICS_SECTION,
)
from app.services.profile import profile_with_persona

logger = logging.getLogger("trailtalk.extract")

ATTEMPTS = 2  # 첫 시도 + 재시도 1회
TRANSCRIPT_LIMIT = 100_000  # 이보다 긴 전문은 앞부분을 잘라 뒷부분을 남긴다
MAX_KNOWN_TOPICS = 50  # 추출에 알려 주는 지난 주제 수(최근 대화 순)
MAX_SOURCES = 30  # 추출에 알려 주는 출처 수(대화 순서, URL 중복 없이)

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
Topic = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
# 한 항목이 조금 넘쳐도 정리 전체가 실패하지 않게 여유를 둔다(지시는 한 문장)
Sentence = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
SourceIds = Annotated[list[Annotated[int, Field(ge=1, le=MAX_SOURCES)]], Field(max_length=10)]


class ReportLine(BaseModel):
    """일지 보고서의 한 문장과 근거 출처 번호(<출처> 목록의 번호). 번호는 서버가 검증한다."""

    model_config = ConfigDict(extra="forbid")

    text: Sentence
    sources: SourceIds


class Extraction(BaseModel):
    """추출 결과 스키마. CLI --json-schema에도 이 스키마를 넘긴다."""

    model_config = ConfigDict(extra="forbid")

    title: Title
    # 일지 보고서(S3-22): 첫 문장 결론 → 핵심 내용 → 세부 내용. 문장마다 근거 출처 번호
    conclusion: Sentence
    conclusion_sources: SourceIds
    key_points: Annotated[list[ReportLine], Field(min_length=1, max_length=5)]
    details: Annotated[list[ReportLine], Field(max_length=8)]
    ideas: Annotated[list[Line], Field(max_length=10)]
    todos: Annotated[list[Line], Field(max_length=10)]
    memos: Annotated[list[Line], Field(max_length=10)]
    tags: Annotated[list[Tag], Field(max_length=5)]
    topics: Annotated[list[Topic], Field(max_length=3)]


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _clean_tags(tags: Sequence[str]) -> list[str]:
    """화면이 앞에 #을 붙이므로 모델이 붙인 #은 뗀다. 빈 값·중복은 뺀다(순서 유지)."""
    cleaned = (_one_line(tag.lstrip("#＃ \t")) for tag in tags)
    return list(dict.fromkeys(tag for tag in cleaned if tag))


def clean_topics(topics: Sequence[str], known: Sequence[str]) -> list[str]:
    """주제 이름을 한 줄로 정리하고, 정규화해서 같은 이름은 하나만 남긴다(순서 유지). 공백·대소문자·
    문장부호만 다른 지난 주제가 있으면 그 이름으로 바꿔 같은 아이디어가 한 묶음이 되게 한다."""
    by_key = {normalize(name): name for name in reversed(known) if normalize(name)}
    kept: dict[str, str] = {}
    for topic in topics:
        name = _one_line(topic)
        key = normalize(name)
        if key and key not in kept:
            kept[key] = by_key.get(key, name)
    return list(kept.values())


def _escape_tags(text: str) -> str:
    """글 안에서 프롬프트의 구분 태그(<대화>, <저장한 노트>, <기존 주제>)를 닫지 못하게 한다."""
    for tag in ("대화", "저장한 노트", "기존 주제", "출처"):
        text = text.replace(f"</{tag}>", f"</ {tag}>")
    return text


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


def collect_sources(turns: list[Turn]) -> list[dict]:
    """대화에서 캐릭터가 본 출처를 대화 순서대로 모은다(URL 중복 없이, 최대 MAX_SOURCES개)."""
    found: dict[str, dict] = {}
    for turn in turns:
        for source in turn.sources or []:
            url = source.get("url") if isinstance(source, dict) else None
            if not isinstance(url, str) or url in found:
                continue
            if len(found) >= MAX_SOURCES:
                return list(found.values())
            title = source.get("title")
            found[url] = {"title": title if isinstance(title, str) else None, "url": url}
    return list(found.values())


SAVED_LABELS = {NoteKind.IDEA: "아이디어", NoteKind.TODO: "할 일", NoteKind.MEMO: "메모"}


def build_prompt(
    turns: list[Turn],
    assistant: str,
    saved: Sequence[tuple[NoteKind, str]] = (),
    topics: Sequence[str] = (),
    sources: Sequence[dict] = (),
) -> str:
    """saved: 대화 중 save_note로 이미 저장한 노트(종류, 내용). 추출이 같은 항목을 다시 뽑지 않게
    알려 준다. 종류를 붙여 다른 종류의 항목까지 빼지 않게 한다. 노트는 모델이 만든 글이라
    (웹 내용이 섞일 수 있다) 태그로 감싸 지시로 따르지 않게 한다.
    topics: 지난 대화의 아이디어 주제. 같은 아이디어면 같은 이름을 고르게 한다(같은 이유로 태그로
    감싼다)."""
    lines = [
        f"- [{SAVED_LABELS[NoteKind(kind)]}] {_escape_tags(' '.join(content.split()))}"
        for kind, content in saved
        if content.strip()
    ]
    section = EXTRACT_SAVED_SECTION.format(items="\n".join(lines)) if lines else ""
    topic_lines = [f"- {_escape_tags(_one_line(t))}" for t in topics if t.strip()]
    topic_section = (
        EXTRACT_TOPICS_SECTION.format(items="\n".join(topic_lines)) if topic_lines else ""
    )
    source_lines = []
    for n, src in enumerate(sources, start=1):
        title = _escape_tags(_one_line(src.get("title") or "(제목 없음)"))
        source_lines.append(f"[{n}] {title} — {_escape_tags(src['url'])}")
    source_section = (
        EXTRACT_SOURCES_SECTION.format(items="\n".join(source_lines)) if source_lines else ""
    )
    return EXTRACT_INSTRUCTION.format(
        assistant=assistant,
        topics=topic_section,
        sources=source_section,
        saved=section,
        transcript=build_transcript(turns, assistant),
    )


async def known_topics(db, exclude_session_id: str | None = None) -> list[str]:
    """지난 대화들의 아이디어 주제(최근 대화 순, 정규화해서 중복 없이). 프롬프트에는 앞의
    MAX_KNOWN_TOPICS개만 넣고, 표기 맞춤(clean_topics)에는 전부 쓴다."""
    query = select(ConversationSession.topics).order_by(ConversationSession.started_at.desc())
    if exclude_session_id is not None:
        query = query.where(ConversationSession.id != exclude_session_id)
    names: dict[str, str] = {}
    for topics in (await db.execute(query)).scalars():
        for name in topics or []:
            key = normalize(name)
            if key and key not in names:
                names[key] = name
    return list(names.values())


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


# 모델이 문장 끝에 직접 적은 출처 번호(번호는 sources로만 받는다). 문장 중간의 "[2024]"는 둔다
_CITE_MARK = re.compile(r"(?:\s*\[\d{1,2}\])+(?=[.!?。]?\s*$)")


def _sentence(text: str) -> str:
    one = _one_line(text)
    return _CITE_MARK.sub("", one).strip() or one


def _host(url: str) -> str:
    host = re.sub(r"^https?://", "", url).split("/")[0]
    return host.removeprefix("www.") or url


def build_report(result: Extraction, sources: Sequence[dict]) -> tuple[dict, list[str]]:
    """추출 결과로 일지 보고서와 평문 요약 줄을 만든다.

    출처 번호는 <출처> 목록에 있는 것만 남기고, 실제로 인용된 출처만 처음 인용된 순서대로 1부터
    다시 번호를 매긴다(모델이 URL·번호를 지어내지 못하게). 요약 줄(목록·기억 블록·주제 분류용)은
    결론과 핵심 내용 앞 두 개를 굵게 표시 없이 쓴다.
    """
    renumber: dict[int, int] = {}
    citations: list[dict] = []

    def cites(ids: Sequence[int]) -> list[int]:
        out: list[int] = []
        for i in ids:
            if not 1 <= i <= len(sources):
                continue  # 목록에 없는 번호는 버린다
            if i not in renumber:
                renumber[i] = len(renumber) + 1
                src = sources[i - 1]
                title = _one_line(src.get("title") or "") or _host(src["url"])
                citations.append({"n": renumber[i], "title": title, "url": src["url"]})
            if renumber[i] not in out:
                out.append(renumber[i])
        return out

    def lines(items: Sequence[ReportLine]) -> list[dict]:
        kept = []
        for item in items:
            text = _sentence(item.text)
            if text:
                kept.append({"text": text, "cites": cites(item.sources)})
        return kept

    conclusion = _sentence(result.conclusion)
    report = {
        "conclusion": conclusion,
        "conclusion_cites": cites(result.conclusion_sources),
        "key_points": lines(result.key_points),
        "details": lines(result.details),
        "citations": citations,
    }
    plain = [conclusion, *(p["text"] for p in report["key_points"][:2])]
    summary = [line for line in (p.replace("**", "") for p in plain) if line][:3]
    return report, summary


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
        topics = await known_topics(db, exclude_session_id=session_id)
        _, loaded = await profile_with_persona(db, settings)
        # 예전 형식(요약 줄만)으로 정리를 마친 일지를 새 형식으로 다시 정리한다: 노트는 이미
        # 뽑았으므로 다시 넣지 않는다(고친 노트가 되살아나거나 표현만 다른 중복이 생기지 않게)
        reformat = convo.report is None and bool(convo.summary)
        await db.commit()
    if not any(t.role is TurnRole.USER for t in turns):
        # 인사만 하고 끝난 대화는 정리할 것이 없다(사용량을 쓰지 않는다)
        await _set_status(app, session_id, ExtractStatus.DONE)
        return None

    sources = collect_sources(turns)
    prompt = build_prompt(turns, loaded.persona.name, saved, topics[:MAX_KNOWN_TOPICS], sources)
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
    if settings.fetch_source_titles:
        # 인용된 출처 가운데 제목이 도메인뿐인 것은 기사 제목을 읽어 온다(S3-22)
        cited = [*result.conclusion_sources]
        for line in [*result.key_points, *result.details]:
            cited.extend(line.sources)
        sources = await improve_titles(sources, cited)

    async def save() -> None:
        async with app.state.session_factory() as db:
            convo = await db.get(ConversationSession, session_id)
            if convo is None:
                return
            if not convo.title_edited:  # 사용자가 고친 제목은 두고 간다
                convo.title = _one_line(result.title)
            # 요약은 줄 목록으로 저장한다(각 줄은 한 줄로 정리돼 있다)
            convo.report, summary = build_report(result, sources)
            convo.summary = "\n".join(summary)
            convo.tags = _clean_tags(result.tags)
            # 정리하는 사이 다른 대화가 붙인 주제까지 보고 표기를 맞춘다
            known = await known_topics(db, exclude_session_id=session_id)
            convo.topics = clean_topics(result.topics, known)
            # 대화 중 save_note로 저장한 노트와 겹치지 않는 항목만 노트로 남긴다(S2-03).
            # 같은 종류의 저장 노트와는 괄호 설명을 뺀 글로도 비교한다(matches_saved)
            rows = await db.execute(
                select(Note.kind, Note.content).where(Note.session_id == session_id)
            )
            saved_notes = [(kind, content) for kind, content in rows]
            existing = [content for _, content in saved_notes]
            for kind, items in (
                (NoteKind.IDEA, [] if reformat else result.ideas),
                (NoteKind.TODO, [] if reformat else result.todos),
                (NoteKind.MEMO, [] if reformat else result.memos),
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


async def cancel_extraction(app: FastAPI, session_id: str, timeout_s: float) -> None:
    """돌고 있는 추출을 멈추고(CLI는 kill), 이미 시작한 결과 쓰기가 끝나길 최대 timeout_s 기다린다.

    쓰기는 취소에서 보호된 별도 태스크(_shielded)라 추출 태스크를 취소해도 끝까지 돈다.
    대화를 지우기 전에 불러 지운 뒤에 쓰기가 커밋되지 않게 한다. 부른 쪽의 취소는 그대로 전파된다.
    """
    deadline = asyncio.get_running_loop().time() + timeout_s
    task = app.state.extractions.get(session_id)
    if task is not None and not task.done():
        task.cancel()
        await asyncio.wait({task}, timeout=timeout_s)
    writes = set(app.state.extract_writes)
    remaining = deadline - asyncio.get_running_loop().time()
    if writes and remaining > 0:
        await asyncio.wait(writes, timeout=remaining)


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
