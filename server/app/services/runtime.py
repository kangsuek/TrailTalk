"""대화 세션의 메모리 상태(서버 프로세스 안에서만 유효).

MCP 도구 인증 토큰, 현재 처리 중인 사용자 턴, 도구가 요청한 세션 상태 변경을 담는다.
DB에 남길 필요가 없는 값만 둔다. 서버가 재시작되면 세션을 다시 열 때 새로 만든다.

턴 처리(S1-08)가 지킬 순서:
- 사용자 턴을 커밋한 뒤 current_user_turn_id를 설정하고 send()를 시작한다(note.turn_id 외래 키).
  턴 시작 때 requested_status를 비우고, 턴이 끝나면 pop_requested_status()로 읽어 반영한 뒤
  current_user_turn_id를 None으로 되돌린다.
- 끼어들기(S3-04): 턴 동안 active_turn에 답변 턴 ID와 CLI 세션을 두고(cancel API가 인터럽트),
  보낸 문장을 remember_sentences로 남긴다(들려준 문장까지 자르기). 자른 뒤 다음 턴에 CLI로 보낼
  안내는 heard_note에 둔다.
- 세션을 끝낼 때는 CLI를 먼저 닫고(llm.close) 런타임을 discard한다. 살아 있는 CLI는 처음 받은
  토큰을 계속 쓰므로, 토큰을 바꾸려면 CLI를 닫은 뒤 새로 ensure해야 한다.
"""

import asyncio
import secrets
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from app.db.models import SessionStatus

_RECENT_REPLIES = 3  # 문장 목록을 기억해 두는 최근 답변 수(끝난 턴의 늦은 끼어들기용)


@dataclass
class ConversationRuntime:
    session_id: str
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    current_user_turn_id: str | None = None  # save_note가 노트를 이 턴에 연결한다
    requested_status: SessionStatus | None = None  # pause_session/end_session이 남긴 요청
    # 한 대화에서 턴은 하나씩만 처리한다(사용자 턴 seq 계산과 CLI 입력 순서)
    turn_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)
    # 진행 중인 답변 턴 ID와 그 CLI 세션(끼어들기 API가 인터럽트를 보낸다)
    active_turn: tuple[str, Any] | None = field(default=None, repr=False, compare=False)
    # 최근 답변 턴 ID → 보낸 문장 목록(들려준 문장까지 자를 때 쓴다)
    reply_sentences: OrderedDict[str, list[str]] = field(
        default_factory=OrderedDict, repr=False, compare=False
    )
    # 다음 턴 CLI 입력 앞에 붙일 안내(직전 답변을 사용자가 어디까지 들었는지)
    heard_note: str | None = None
    # send_email(FR-21)로 메일을 보낸 사용자 턴 ID와 이 대화에서 보낸 횟수(되풀이 방지)
    mailed_turn_ids: set[str] = field(default_factory=set, repr=False, compare=False)
    mail_count: int = 0

    def remember_sentences(self, turn_id: str, sentences: list[str]) -> None:
        """답변 턴의 문장 목록(진행 중에는 같은 리스트가 계속 늘어난다)을 기억한다."""
        self.reply_sentences[turn_id] = sentences
        self.reply_sentences.move_to_end(turn_id)
        while len(self.reply_sentences) > _RECENT_REPLIES:
            self.reply_sentences.popitem(last=False)

    def pop_requested_status(self) -> SessionStatus | None:
        status, self.requested_status = self.requested_status, None
        return status


class RuntimeRegistry:
    def __init__(self) -> None:
        self._items: dict[str, ConversationRuntime] = {}

    def ensure(self, session_id: str) -> ConversationRuntime:
        runtime = self._items.get(session_id)
        if runtime is None:
            runtime = self._items[session_id] = ConversationRuntime(session_id)
        return runtime

    def get(self, session_id: str) -> ConversationRuntime | None:
        return self._items.get(session_id)

    def discard(self, session_id: str) -> None:
        self._items.pop(session_id, None)

    def authenticate(self, session_id: str | None, token: str | None) -> ConversationRuntime | None:
        runtime = self._items.get(session_id or "")
        # bytes로 비교한다(str끼리는 ASCII가 아닌 값이 오면 compare_digest가 예외를 낸다)
        if (
            runtime is None
            or not token
            or not secrets.compare_digest(runtime.token.encode(), token.encode())
        ):
            return None
        return runtime
