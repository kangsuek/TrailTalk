"""격리 보충: 인증 방식(키체인 vs 토큰)에 따라 계정 이메일이 맥락에 붙는지 확인한다.

답변에 실제 이메일이 나오면 화면에는 <EMAIL>로 가려 출력한다.
"""

import re

from common import CliSession, run

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
# 예/아니오 질문은 답이 흔들리므로, 맥락에 실제 값이 있어야 답할 수 있는 도메인을 묻는다
QUESTION = (
    "맥락에 내 이메일 주소가 있으면 @ 뒤의 도메인만 답하고, 없으면 '없음'이라고만 답해. "
    "추측하지 마."
)


async def main() -> None:
    for label, use_token in (("키체인", False), ("토큰", True)) * 2:
        session = CliSession(system_prompt="너는 테스트 봇이다.", use_env_token=use_token)
        await session.start()
        try:
            turn = await session.ask(QUESTION)
            print(label, "|", EMAIL.sub("<EMAIL>", turn.text)[:80])
        finally:
            await session.close()


run(main)
