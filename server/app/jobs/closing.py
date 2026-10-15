"""마무리 멘트(계획서 S2-04, 설계서 4.4): 세션에 저장한 노트 개수로 "오늘 아이디어 3개, 할 일 1개
저장했어요!" 같은 말을 만든다. 문구는 페르소나 YAML(closing)에 있다(NFR-08)."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Note, NoteKind
from app.persona.schema import SAVED_PLACEHOLDER, Persona

KIND_LABELS = ((NoteKind.IDEA, "아이디어"), (NoteKind.TODO, "할 일"), (NoteKind.MEMO, "메모"))


async def count_notes(db: AsyncSession, session_id: str) -> dict[NoteKind, int]:
    rows = await db.execute(
        select(Note.kind, func.count()).where(Note.session_id == session_id).group_by(Note.kind)
    )
    counts = dict.fromkeys(NoteKind, 0)
    counts.update({kind: count for kind, count in rows})
    return counts


def closing_message(persona: Persona, counts: dict[NoteKind, int]) -> str:
    parts = [f"{label} {counts.get(kind, 0)}개" for kind, label in KIND_LABELS if counts.get(kind)]
    if not parts:
        return persona.closing.nothing
    return persona.closing.saved.replace(SAVED_PLACEHOLDER, ", ".join(parts))
