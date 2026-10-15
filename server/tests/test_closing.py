"""마무리 멘트(S2-04)."""

import pytest

from app.config import settings
from app.db.models import NoteKind
from app.jobs.closing import closing_message
from app.persona.loader import load_persona
from app.persona.schema import Closing


@pytest.fixture
def persona():
    return load_persona(settings.persona_dir, settings.default_persona).persona


def counts(idea=0, todo=0, memo=0):
    return {NoteKind.IDEA: idea, NoteKind.TODO: todo, NoteKind.MEMO: memo}


def test_counts_fill_placeholder_in_kind_order(persona):
    text = closing_message(persona, counts(idea=3, todo=1))
    assert text == persona.closing.saved.replace("{저장}", "아이디어 3개, 할 일 1개")
    assert closing_message(persona, counts(memo=2)) == persona.closing.saved.replace(
        "{저장}", "메모 2개"
    )


def test_nothing_saved_uses_other_line(persona):
    assert closing_message(persona, counts()) == persona.closing.nothing


@pytest.mark.parametrize(
    "data",
    [
        {"saved": "오늘 정리했어요!", "nothing": "또 봐요!"},  # 자리표시자 없음
        {"saved": "오늘 {저장} 저장!", "nothing": "{저장} 없어요"},  # 없는 경우에 자리표시자
    ],
)
def test_closing_placeholder_rules(data):
    with pytest.raises(ValueError):
        Closing.model_validate(data)
