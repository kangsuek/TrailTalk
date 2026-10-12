"""6. 첫 부분 출력까지의 지연: 콜드 스타트(턴마다 새 프로세스) vs 상주 프로세스.

콜드 스타트는 프로세스 기동부터, 상주는 메시지 전송부터 잰다(서버가 체감하는 지연).
"""

import time

from common import CliSession, median, run

PROMPT = "너는 테스트 봇이다. 한 문장으로 답한다."
QUESTIONS = [
    "오늘 산책 어땠을까?",
    "좋아하는 계절은?",
    "산에서 먹기 좋은 간식은?",
    "아침 운동의 장점 하나만.",
    "걷기 좋은 시간대는?",
]


async def cold(model: str) -> list[float]:
    values = []
    for q in QUESTIONS:
        t0 = time.perf_counter()
        session = CliSession(model=model, system_prompt=PROMPT)
        await session.start()
        await session.send_user(q)
        turn = await session.read_turn(t0)
        values.append(turn.first_delta_s or turn.elapsed_s)
        await session.close()
    return values


async def resident(model: str) -> list[float]:
    session = CliSession(model=model, system_prompt=PROMPT)
    await session.start()
    await session.ask("준비됐어?")  # 워밍업 턴(측정 제외)
    turns = [await session.ask(q) for q in QUESTIONS]
    values = [t.first_delta_s or t.elapsed_s for t in turns]
    await session.close()
    return values


async def main() -> None:
    for model in ("haiku", "sonnet"):
        c, r = await cold(model), await resident(model)
        print(f"{model}: 콜드 중앙값 {median(c)}s {[round(v, 2) for v in c]}")
        print(f"{model}: 상주 중앙값 {median(r)}s {[round(v, 2) for v in r]}")


run(main)
