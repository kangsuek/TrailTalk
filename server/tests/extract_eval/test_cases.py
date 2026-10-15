"""추출 평가 세트(S2-09) 형식 검사와 리포트 계산. 실제 CLI 없이 돈다."""

from app.config import Settings
from app.jobs.extract import Extraction
from tests.extract_eval.run_eval import Result, case_turns, judge_schema, load_cases, report


def test_cases_are_well_formed():
    cases = load_cases()
    assert len(cases) == 10
    assert len({c["id"] for c in cases}) == len(cases)
    for case in cases:
        turns = case_turns(case)
        assert turns[0].role.value == "assistant"  # 인사말로 시작한다
        assert any(t.role.value == "user" for t in turns)
        assert set(case["gold"]) == {"ideas", "todos"}
        for i in case.get("interrupted", []):
            assert turns[i].interrupted and turns[i].role.value == "assistant"
    assert sum(len(c["gold"]["ideas"]) + len(c["gold"]["todos"]) for c in cases) >= 20


def test_report_counts_recall_and_unsupported():
    extraction = Extraction(
        title="제목",
        summary=["요약"],
        ideas=["아이디어 A", "지어낸 것"],
        todos=["할 일 A"],
        memos=[],
        tags=[],
    )
    r = Result("c1", "설명", ["아이디어 A", "아이디어 B"], ["할 일 A"], extraction=extraction)
    r.gold_found = [True, False, True]
    r.supported = [True, False, True]
    failed = Result("c2", "설명", ["x"], [], error="RuntimeError: 시간 초과")
    text = report([r, failed], Settings(_env_file=None), 1.0, full=True)
    assert "재현율 2/3 (67%) — 오류 있음" in text
    assert "아이디어 1/2 (50%), 할 일 1/1 (100%)" in text
    assert "근거 없는 아이디어·할 일(지어냄·거절한 제안): 1/3" in text
    assert "**근거 없음** [아이디어] 지어낸 것" in text


def test_judge_schema_fixes_array_lengths():
    schema = judge_schema(3, 2)
    assert schema["properties"]["gold_found"]["minItems"] == 3
    assert schema["properties"]["extracted_supported"]["maxItems"] == 2
