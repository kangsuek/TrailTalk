"""5. 프로세스 종료 후 session_id로 --resume하면 맥락이 이어지는지 확인한다."""

from common import CliSession, run


async def main() -> None:
    first = CliSession(system_prompt="너는 테스트 봇이다. 짧게 답한다.", persist=True)
    await first.start()
    await first.ask("내가 오늘 정한 비밀 숫자는 7342야. 기억해 둬.")
    session_id = first.session_id
    print("첫 프로세스 종료:", await first.close(), "| session_id:", session_id)

    second = CliSession(
        system_prompt="너는 테스트 봇이다. 짧게 답한다.", resume=session_id, cwd=first.cwd
    )
    await second.start()
    turn = await second.ask("내가 정한 비밀 숫자가 뭐였지?")
    print("재개 후 session_id 동일:", second.session_id == session_id)
    print("맥락 유지:", "7342" in turn.text, "|", turn.text)
    await second.close()

    other_dir = CliSession(system_prompt="너는 테스트 봇이다. 짧게 답한다.", resume=session_id)
    await other_dir.start()
    try:
        turn = await other_dir.ask("내가 정한 비밀 숫자가 뭐였지?")
        print("다른 작업 폴더에서 재개:", turn.result["subtype"], "|", turn.text[:80])
    except RuntimeError as exc:
        print("다른 작업 폴더에서 재개 실패:", str(exc)[:200])
    await other_dir.close()


run(main)
