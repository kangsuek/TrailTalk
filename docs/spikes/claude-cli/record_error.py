"""7. 오류 출력 녹화: 존재하지 않는 모델명."""

from common import CliSession, run, save_fixture


async def main() -> None:
    session = CliSession(model="no-such-model-xyz", system_prompt="테스트")
    await session.start()
    try:
        turn = await session.ask("안녕", timeout=60)
        print(
            "result:",
            turn.result.get("subtype"),
            turn.result.get("is_error"),
            (turn.result.get("result") or "")[:200],
        )
    except RuntimeError as exc:
        print("프로세스 종료:", str(exc)[:300])
    print("exit:", await session.close())
    if session.raw_lines:
        print("녹화:", save_fixture("error_invalid_model", session.raw_lines))


run(main)
