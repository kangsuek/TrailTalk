"""지연 평가의 계산·리포트(V2-M0-06). 서비스를 부르지 않는 순수 함수라 단위 테스트한다."""

import math
import statistics
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

Turn = Mapping[str, Any]  # GET /api/latency 의 turns 항목

# 서버가 재는 단계(요청 처리 시작 기준 ms)
SERVER_STAGES = (
    ("stt_ms", "인식"),
    ("first_token_ms", "CLI 첫 글자"),
    ("first_queued_ms", "첫 문장 분할"),
    ("first_synth_ms", "첫 문장 합성"),
    ("first_sentence_ms", "첫 문장 완성"),
    ("done_ms", "턴 종료"),
)
# 브라우저가 보고하는 말 끝 → 첫 소리 구간
CLIENT_STAGES = (
    ("speech_to_request_ms", "무음 대기+전송"),
    ("request_to_playback_ms", "요청 → 첫 소리"),
    ("total_ms", "말 끝 → 첫 소리"),
    ("ack_ms", "맞장구(첫 반응)"),
)


def median(values: Sequence[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def p90(values: Sequence[float]) -> float | None:
    """가장 가까운 순위 방식의 90% 값(서버 요약과 같은 정의)."""
    if not values:
        return None
    ordered = sorted(values)
    return float(ordered[math.ceil(0.9 * len(ordered)) - 1])


def with_total(turn: Turn) -> dict[str, Any]:
    """total_ms 가 없으면(요약 전 원자료) 두 클라이언트 구간의 합으로 채운다."""
    row = dict(turn)
    if row.get("total_ms") is None:
        s, r = row.get("speech_to_request_ms"), row.get("request_to_playback_ms")
        row["total_ms"] = None if s is None or r is None else s + r
    return row


def spread(turns: Iterable[Turn], field: str) -> tuple[float | None, float | None, int]:
    """(중앙값, p90, 값이 있는 턴 수)."""
    values = [v for t in turns if (v := t.get(field)) is not None]
    return median(values), p90(values), len(values)


def split_search(turns: Iterable[Turn]) -> tuple[list[Turn], list[Turn]]:
    """(검색 턴, 비검색 턴). 검색 턴은 답변 지연이 검색 시간에 가려지므로 따로 센다."""
    rows = list(turns)
    return [t for t in rows if t.get("search_used")], [t for t in rows if not t.get("search_used")]


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value / 1000:.2f}"


def stage_table(turns: Sequence[Turn], stages: Sequence[tuple[str, str]]) -> list[str]:
    lines = ["| 구간 | 중앙값(초) | 90%(초) | 턴 수 |", "|---|---|---|---|"]
    for field, label in stages:
        mid, high, count = spread(turns, field)
        lines.append(f"| {label} | {_fmt(mid)} | {_fmt(high)} | {count} |")
    return lines


def turn_rows(turns: Sequence[Turn]) -> list[str]:
    lines = [
        "| # | 인식 | CLI 첫 글자 | 첫 문장 합성 | 첫 문장 완성 | 무음+전송 | 요청→첫 소리 "
        "| 말 끝→첫 소리 | 검색 | 문장 | 글자 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for index, turn in enumerate(turns, 1):
        cells = [
            _fmt(turn.get(f))
            for f in (
                "stt_ms",
                "first_token_ms",
                "first_synth_ms",
                "first_sentence_ms",
                "speech_to_request_ms",
                "request_to_playback_ms",
                "total_ms",
            )
        ]
        search = "O" if turn.get("search_used") else ""
        lines.append(
            f"| {index} | {' | '.join(cells)} | {search} | {turn.get('sentence_count') or ''} "
            f"| {turn.get('reply_chars') or ''} |"
        )
    return lines


def render_report(
    *,
    date: str,
    server_turns: Sequence[Turn],
    browser_turns: Sequence[Turn],
    usage_before: str,
    usage_after: str,
    notes: Sequence[str] = (),
) -> str:
    """docs/eval/latency-<날짜>.md 본문."""
    browser = [with_total(t) for t in browser_turns]
    searched, plain = split_search(browser)
    server_searched, server_plain = split_search(server_turns)
    out = [
        f"# 응답 지연 평가 ({date})",
        "",
        "실제 Claude CLI·OpenAI(인식·합성)를 쓰는 평가용 서버(임시 DB)로 잰다. "
        "스크립트: `server/tests/latency_eval/run_eval.py`. "
        "정의는 삭제된 docs/V2/spec.md 3.2절(git 이력).",
        "",
        f"- 구독 사용량(5시간 창): 시작 {usage_before} → 끝 {usage_after} "
        "(새 평가 서버는 첫 응답 뒤에야 값이 생겨 시작 값은 비어 있을 수 있다. "
        "끝 값이 이 계정의 현재 사용률)",
        *[f"- {note}" for note in notes],
        "",
        f"## 1. 서버 단계 (같은 발화 파일을 서버에 직접 전송, {len(server_turns)}턴 중 "
        f"비검색 {len(server_plain)}턴. 검색 {len(server_searched)}턴은 CLI 시간이 길어 뺀다)",
        "",
        *stage_table(server_plain, SERVER_STAGES),
        "",
        f"## 2. 말 끝 → 첫 소리 (브라우저 구동, 마이크 주입, {len(browser)}턴)",
        "",
        "### 전체",
        "",
        *stage_table(browser, CLIENT_STAGES),
        "",
        f"### 비검색 턴 ({len(plain)}턴)",
        "",
        *stage_table(plain, CLIENT_STAGES),
        "",
        f"### 검색 턴 ({len(searched)}턴, 첫 소리가 검색 안내일 수 있어 따로 본다)",
        "",
        *stage_table(searched, CLIENT_STAGES),
        "",
        f"### 브라우저 턴의 서버 단계 (비검색 {len(plain)}턴)",
        "",
        *stage_table(plain, SERVER_STAGES),
        "",
        "## 3. 턴별 값 (브라우저)",
        "",
        *turn_rows(browser),
        "",
    ]
    return "\n".join(out)
