"""노트 중복 제거(S2-03)."""

import pytest

from app.jobs.dedupe import is_duplicate, new_items, normalize


def test_normalize_drops_case_space_punctuation_and_width():
    assert normalize("  Claude Code를 업데이트!! ") == normalize("ｃｌａｕｄｅ code를 업데이트")


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("산책 앱에 음성 메모 기능 추가하기", "산책 앱에 음성 메모 기능 추가하기"),  # 같은 내용
        ("산책 앱에 음성 메모 기능 추가하기", "산책앱에 음성메모 기능을 추가"),  # 표현만 다름
        ("Claude Code 업데이트하기", "claude code를 업데이트하기."),
        ("uv 문서 읽기", "uv 문서 읽기!"),  # 짧아도 정규화 결과가 같으면 중복
        ("동네 빵집 지도 만들기", "동네 빵집 지도 만들기 — 주말에 시작"),  # 짧은 쪽이 포함됨
        ("블로그 글 쓰기", "블로그에 글 쓰기"),  # 조사 차이
        ("편안한 신발 사기", "편안한 신발 사기!"),  # "안"이 낱말 안에 있으면 부정이 아니다
    ],
)
def test_duplicates(a, b):
    assert is_duplicate(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("산책 앱에 음성 메모 기능 추가하기", "등산 코스를 지도에 정리하기"),  # 다른 내용
        ("앱 만들기", "게임 앱 만들기"),  # 짧은 문자열의 우연한 겹침
        ("주말에 북한산 가기", "주말에 관악산 가기"),
        ("우유 2개 사기", "우유 3개 사기"),  # 숫자만 다름
        ("3시에 엄마한테 전화하기", "5시에 엄마한테 전화하기"),
        ("Python 3.12로 업그레이드", "Python 3.11로 업그레이드"),
        ("2026년 10월 20일 병원 예약", "2026년 10월 21일 병원 예약"),
        ("내일 은행 가기", "내일 은행 가지 않기"),  # 부정
        ("서버 배포 자동화하기", "서버 배포 자동화 못 하기"),
        ("주말 등산 가기", "주말 등산 안 가기"),
    ],
)
def test_not_duplicates(a, b):
    assert not is_duplicate(a, b)


def test_new_items_filters_existing_and_repeats_in_order():
    existing = ["산책 앱에 음성 메모 기능 추가하기"]
    candidates = [
        "산책앱에 음성메모 기능을 추가",  # 저장된 노트와 중복
        "등산 코스를 지도에 정리하기",
        "등산 코스를 지도에 정리하기!",  # 추출 결과 안의 중복
        "  ",
        "😊",  # 정규화하면 빈 문자열
        "친구에게 앱 아이디어 보여 주기",
    ]
    assert new_items(existing, candidates) == [
        "등산 코스를 지도에 정리하기",
        "친구에게 앱 아이디어 보여 주기",
    ]
