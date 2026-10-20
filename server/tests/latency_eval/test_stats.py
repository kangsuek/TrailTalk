"""지연 평가 계산의 단위 테스트(서비스를 부르지 않는다)."""

from tests.latency_eval.stats import (
    median,
    p90,
    render_report,
    split_search,
    spread,
    with_total,
)


def test_median_and_p90_use_nearest_rank():
    assert median([]) is None
    assert p90([]) is None
    assert median([3, 1, 2]) == 2.0
    assert p90(list(range(1, 11))) == 9.0  # 10개 중 9번째
    assert p90([5]) == 5.0


def test_total_is_filled_from_client_parts_only_when_both_exist():
    assert (
        with_total({"speech_to_request_ms": 1800, "request_to_playback_ms": 4000})["total_ms"]
        == 5800
    )
    assert with_total({"speech_to_request_ms": 1800})["total_ms"] is None
    assert with_total({"total_ms": 7, "speech_to_request_ms": 1})["total_ms"] == 7


def test_spread_skips_missing_values():
    turns = [{"stt_ms": 100}, {"stt_ms": None}, {"stt_ms": 300}, {}]
    assert spread(turns, "stt_ms") == (200.0, 300.0, 2)
    assert spread([], "stt_ms") == (None, None, 0)


def test_split_search_separates_search_turns():
    searched, plain = split_search([{"search_used": True}, {"search_used": False}, {}])
    assert len(searched) == 1
    assert len(plain) == 2


def test_report_has_sections_and_values():
    server = [
        {"stt_ms": 800, "first_token_ms": 2000, "first_synth_ms": 1000, "first_sentence_ms": 3100}
    ]
    browser = [
        {"speech_to_request_ms": 1800, "request_to_playback_ms": 4200, "search_used": False},
        {"speech_to_request_ms": 1900, "request_to_playback_ms": 9000, "search_used": True},
    ]
    report = render_report(
        date="2026-10-20",
        server_turns=server,
        browser_turns=browser,
        usage_before="10%",
        usage_after="11%",
        notes=["메모"],
    )
    assert "# 응답 지연 평가 (2026-10-20)" in report
    assert "시작 10% → 끝 11%" in report
    assert "- 메모" in report
    assert "| 인식 | 0.80 | 0.80 | 1 |" in report
    assert "### 비검색 턴 (1턴)" in report
    assert "### 검색 턴 (1턴" in report
    assert "| 말 끝 → 첫 소리 | 8.45 | 10.90 | 2 |" in report  # 6.0과 10.9의 중앙값, p90
