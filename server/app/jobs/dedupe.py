"""노트 중복 제거(계획서 S2-03, 설계서 4.4): 추출 결과에서 대화 중 save_note로 저장한 것을 거른다.

정규화(NFKC, 소문자, 공백·문장부호 제거)한 문자열이 같거나, 짧은 쪽이 긴 쪽에 들어 있거나, 비슷한
정도가 기준 이상이면 같은 내용으로 본다. 숫자나 부정 여부가 다르면 다른 내용이다.
짧은 문자열은 몇 글자만 같아도 비율이 높게 나오므로
포함·유사도 비교는 일정 길이 이상일 때만 한다.
"""

import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher

SIMILARITY = 0.8  # 0.75면 "주말에 북한산 가기"·"주말에 관악산 가기"가 같다고 나온다
MIN_CONTAIN_CHARS = 8  # 포함 관계로 중복을 판정할 짧은 쪽의 최소 길이(정규화 후)
MIN_SIMILAR_CHARS = 6  # 유사도로 판정할 짧은 쪽의 최소 길이(정규화 후)

_DROP = re.compile(r"[\W_]+")
_NUMBER = re.compile(r"\d+")
# 부정 표현("않", "못하", 띄어 쓴 "안"). 있고 없음이 다르면 반대 뜻이다
_NEGATION = re.compile(r"않|못\s?하|(?:^|\s)안\s")


def normalize(text: str) -> str:
    return _DROP.sub("", unicodedata.normalize("NFKC", text).lower())


def is_duplicate(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    if na == nb:
        return True
    # 숫자(시각·개수·날짜·버전)나 부정 여부가 다르면 비슷해 보여도 다른 항목이다
    if _NUMBER.findall(na) != _NUMBER.findall(nb):
        return False
    if bool(_NEGATION.search(f" {a} ")) != bool(_NEGATION.search(f" {b} ")):
        return False
    short, long = sorted((na, nb), key=len)
    if len(short) >= MIN_CONTAIN_CHARS and short in long:
        return True
    if len(short) < MIN_SIMILAR_CHARS:
        return False
    return SequenceMatcher(None, na, nb, autojunk=False).ratio() >= SIMILARITY


def new_items(existing: Iterable[str], candidates: Iterable[str]) -> list[str]:
    """candidates 중 existing과도, 앞서 고른 것과도 겹치지 않는 항목(순서 유지)."""
    seen = list(existing)
    kept: list[str] = []
    for item in candidates:
        if not normalize(item) or any(is_duplicate(item, other) for other in seen):
            continue
        kept.append(item)
        seen.append(item)
    return kept
