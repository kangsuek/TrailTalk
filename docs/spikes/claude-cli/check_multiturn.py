"""1. 프로세스 1개에 여러 턴을 보내고 부분 출력과 턴 경계를 확인한다."""

from collections import Counter

from common import CliSession, run, save_fixture


async def main() -> None:
    session = CliSession(system_prompt="너는 테스트 봇이다. 한 문장으로만 답한다.")
    await session.start()
    questions = ["사과는 무슨 색이야?", "바나나는?", "방금 두 과일 이름을 말해줘."]
    for i, q in enumerate(questions, 1):
        turn = await session.ask(q)
        kinds = Counter(
            e["event"]["type"] if e["type"] == "stream_event" else e["type"] for e in turn.events
        )
        deltas = kinds.get("content_block_delta", 0)
        print(
            f"턴{i} 첫 부분출력 {turn.first_delta_s:.2f}s, 전체 {turn.elapsed_s:.2f}s, "
            f"delta {deltas}개, result={turn.result['subtype']} | {turn.text!r}"
        )
    print("pid 유지:", session.proc.returncode is None, "| session_id:", session.session_id)
    print("exit:", await session.close())
    print("녹화:", save_fixture("multiturn", session.raw_lines))


run(main)
