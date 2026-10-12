"""2. 생성 도중 인터럽트 후 같은 프로세스로 다음 턴이 이어지는지 확인한다."""

import asyncio
import time

from common import CliSession, run, save_fixture


async def main() -> None:
    session = CliSession(system_prompt="너는 테스트 봇이다.")
    await session.start()
    sent = time.perf_counter()
    await session.send_user("1부터 200까지 숫자를 쉼표로 구분해 모두 써줘.")
    partial = await session.read_turn(sent, on_delta=lambda t: len(t.text) > 40)
    print(f"중단 전 부분 출력({time.perf_counter() - sent:.2f}s): {partial.text[:60]!r}")

    request_id = await session.send_interrupt()
    t0 = time.perf_counter()
    events = []
    result = None
    while result is None:
        event = await session.read_event(timeout=60)
        if event is None:
            print("프로세스 종료됨:", await session.stderr())
            return
        events.append(event)
        if event["type"] == "control_response":
            print(
                "control_response:",
                event.get("response", {}).get("subtype"),
                "request_id 일치:",
                event.get("response", {}).get("request_id") == request_id,
            )
        if event["type"] == "result":
            result = event
    print(
        f"인터럽트 후 result까지 {time.perf_counter() - t0:.2f}s: subtype={result['subtype']}, "
        f"is_error={result['is_error']}, terminal_reason={result.get('terminal_reason')}"
    )

    await asyncio.sleep(0.5)
    turn = await session.ask("방금 무엇을 하던 중이었는지 한 문장으로 말해줘.")
    print(f"다음 턴 정상: result={turn.result['subtype']} | {turn.text!r}")
    print("exit:", await session.close())
    print("녹화:", save_fixture("interrupt", session.raw_lines))


run(main)
