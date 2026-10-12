"""S0-05. .env의 CLAUDE_CODE_OAUTH_TOKEN으로 인증되는지 확인한다(토큰 값은 출력하지 않는다)."""

from common import CliSession, run


async def main() -> None:
    session = CliSession(system_prompt="너는 테스트 봇이다.", use_env_token=True)
    await session.start()
    turn = await session.ask("'토큰 인증 확인'이라고만 답해.")
    init = session.init_event or {}
    print("apiKeySource:", init.get("apiKeySource"), "| model:", init.get("model"))
    print("result:", turn.result["subtype"], "is_error:", turn.result["is_error"], "|", turn.text)
    print("exit:", await session.close())

    # 토큰이 키체인보다 우선하는지: 잘못된 토큰이면 실패해야 한다
    bad = CliSession(
        system_prompt="테스트", env={"CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat01-invalid"}
    )
    await bad.start()
    try:
        turn = await bad.ask("안녕", timeout=60)
        print(
            "잘못된 토큰:",
            "is_error=",
            turn.result["is_error"],
            "|",
            (turn.result.get("result") or "")[:120],
        )
    except RuntimeError as exc:
        print("잘못된 토큰: 프로세스 종료 |", str(exc)[:200])
    print("exit:", await bad.close())


run(main)
