"""기존 일지 아이디어 주제 분류(계획서 S3-17): 주제(topics)가 생기기 전에 정리한 일지에 한 번
주제를 붙인다.

정리가 끝났고 아직 분류하지 않은(topics가 NULL인) 대화들의 제목·요약·아이디어를 모아 CLI 단발
호출 한 번으로 분류한다(대화마다 부르지 않아야 같은 아이디어에 같은 이름이 붙는다). 이미 주제가 붙은
대화의 주제도 함께 알려 같은 이름을 고르게 한다. 분류한 대화는 주제가 없어도 빈 목록으로 표시해
다시 돌리면 남은 대화만 분류한다. 실제 Claude CLI를 써서 구독 사용량이 든다.

    (cd server && uv run python -m app.jobs.topics_backfill)

앱이 쓰는 DB(설정 DATABASE_URL)에 쓴다. 시작할 때 마이그레이션을 head까지 적용한다.
"""

import asyncio
import logging
from collections.abc import Sequence
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db.models import ConversationSession, ExtractStatus, Note, NoteKind
from app.jobs.extract import MAX_KNOWN_TOPICS, Topic, clean_topics, known_topics
from app.llm.claude_cli import run_oneshot
from app.persona.rules import EXTRACT_TOPICS_SECTION, TOPICS_BACKFILL_INSTRUCTION

logger = logging.getLogger("trailtalk.topics_backfill")

MAX_SESSIONS = 200  # 한 번에 분류하는 일지 수(프롬프트 크기 상한)
TIMEOUT_S = 180


class SessionTopics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    topics: Annotated[list[Topic], Field(max_length=3)]


class Backfill(BaseModel):
    """분류 결과 스키마. CLI --json-schema에도 이 스키마를 넘긴다."""

    model_config = ConfigDict(extra="forbid")

    sessions: list[SessionTopics]


def _one_line(text: str) -> str:
    # 일지 글은 모델이 만든 것이라 구분 태그를 닫지 못하게 한다
    text = " ".join(text.split())
    for tag in ("일지", "기존 주제"):
        text = text.replace(f"</{tag}>", f"</ {tag}>")
    return text


def build_prompt(
    sessions: list[ConversationSession],
    ideas: dict[str, list[str]],
    timezone: str,
    known: Sequence[str] = (),
) -> str:
    tz = ZoneInfo(timezone)
    blocks = []
    for convo in sessions:
        local = convo.started_at.astimezone(tz)
        lines = [
            f"- id: {convo.id}",
            f"  날짜: {local.month}월 {local.day}일",
            f"  제목: {_one_line(convo.title or '')}",
            f"  요약: {_one_line(convo.summary or '')}",
        ]
        lines += [f"  아이디어: {_one_line(idea)}" for idea in ideas.get(convo.id, [])]
        blocks.append("\n".join(lines))
    prompt = TOPICS_BACKFILL_INSTRUCTION.format(journals="\n".join(blocks))
    lines = [f"- {_one_line(name)}" for name in known if name.strip()]
    if lines:
        prompt += "\n" + EXTRACT_TOPICS_SECTION.format(items="\n".join(lines))
    return prompt


async def backfill_topics(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> int:
    """아직 분류하지 않은 정리된 일지에 주제를 붙인다. 분류한 일지 수를 돌려준다(주제 없음 포함).
    실패는 LlmError·ValidationError로 던진다(아무것도 바꾸지 않는다)."""
    async with session_factory() as db:
        rows = await db.execute(
            select(ConversationSession)
            .where(
                ConversationSession.extract_status == ExtractStatus.DONE,
                ConversationSession.title.is_not(None),
                ConversationSession.topics.is_(None),
            )
            .order_by(ConversationSession.started_at)
            .limit(MAX_SESSIONS)
        )
        targets = list(rows.scalars())
        if not targets:
            return 0
        notes = await db.execute(
            select(Note.session_id, Note.content)
            .where(
                Note.session_id.in_([s.id for s in targets]),
                Note.kind == NoteKind.IDEA,
            )
            .order_by(Note.created_at)
        )
        ideas: dict[str, list[str]] = {}
        for session_id, content in notes:
            ideas.setdefault(session_id, []).append(content)
        prompt = build_prompt(
            targets, ideas, settings.timezone, (await known_topics(db))[:MAX_KNOWN_TOPICS]
        )

    raw = await run_oneshot(
        settings,
        prompt,
        model=settings.llm_light_model,
        json_schema=Backfill.model_json_schema(),
        timeout_s=TIMEOUT_S,
    )
    result = Backfill.model_validate(raw)

    target_ids = {s.id for s in targets}
    updated = 0
    async with session_factory() as db:
        # 호출하는 사이 다른 대화가 붙인 주제까지 보고 표기를 맞춘다
        known = await known_topics(db)
        for item in result.sessions:
            if item.id not in target_ids:  # 모델이 지어낸 id·같은 id 반복은 무시한다
                continue
            target_ids.discard(item.id)
            convo = await db.get(ConversationSession, item.id)
            if convo is None or convo.topics is not None:  # 그사이 정리됐으면 두고 간다
                continue
            convo.topics = clean_topics(item.topics, known)
            known = known + [t for t in convo.topics if t not in known]
            updated += 1
        await db.commit()
    if len(targets) == MAX_SESSIONS:
        logger.info("한 번에 %d개까지 분류한다. 남은 일지는 다시 실행하면 분류한다", MAX_SESSIONS)
    return updated


async def _main() -> None:
    from app.db.migrate import upgrade_to_head
    from app.db.session import create_engine_for, create_session_factory

    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    await upgrade_to_head(settings.database_url)
    engine = create_engine_for(settings.database_url)
    try:
        updated = await backfill_topics(settings, create_session_factory(engine))
    finally:
        await engine.dispose()
    print(f"주제를 붙인 일지: {updated}개")


if __name__ == "__main__":
    asyncio.run(_main())
