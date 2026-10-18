"""2. gpt-4o-transcribe-diarize 실측(과금 소량). make_clips.py를 먼저 돌린다.

결과는 화면과 SPIKE_DIR/results.jsonl에 남긴다.
"""

import json
import re
import statistics

import httpx2
from common import OUT, duration, run, segments, transcribe

DIARIZE = "gpt-4o-transcribe-diarize"
TRANSCRIBE = "gpt-transcribe"
NAMES = ["다니엘", "강석", "필재"]

# 이름 추출 후보: handoff 초안 정규식과 개선안
OLD_NAME = re.compile(r"저는\s*(\S+?)\s*(입니다|이에요|예요|이야|야)")
NEW_NAME = re.compile(
    r"(?:저는|전|제\s*이름은|나는|난)?\s*([가-힣A-Za-z]{1,10}?)"
    r"(?:이라고|라고)?\s*(?:합니다|해요|입니다|이에요|예요|이야|야)"
)


def refs(kind: str) -> list:
    return [OUT / f"reg_{n}{kind}.wav" for n in ("daniel", "gangseok", "piljae")]


async def main() -> None:
    log = (OUT / "results.jsonl").open("a", encoding="utf-8")
    async with httpx2.AsyncClient() as client:

        async def case(label: str, audio: str, model: str = DIARIZE, names=None, ref=None) -> dict:  # noqa: ANN001
            path = OUT / f"{audio}.wav"
            status, body, elapsed = await transcribe(
                client, path, model=model, names=names, refs=ref
            )
            text = (
                segments(body)
                if model == DIARIZE
                else (body.get("text") if isinstance(body, dict) else body)
            )
            print(
                f"\n[{label}] {audio} ({duration(path):.1f}s) {model} → {status} {elapsed:.2f}s"
                f"\n  {text}"
            )
            log.write(
                json.dumps(
                    {
                        "label": label,
                        "audio": audio,
                        "model": model,
                        "status": status,
                        "elapsed": elapsed,
                        "body": body,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            return {"status": status, "elapsed": elapsed, "body": body}

        print("등록 클립 길이:", {p.name: round(duration(p), 2) for p in refs("") + refs("_long")})

        # A. 참조 클립 길이: 그대로(2.2~2.5초) / 앞뒤 무음 채움(2.5~2.8초) / 긴 문장
        await case("A-raw", "mix_three", names=NAMES, ref=refs(""))
        await case("A-pad", "mix_three", names=NAMES, ref=refs("_pad"))
        await case("A-long", "mix_three", names=NAMES, ref=refs("_long"))

        # B. 같은 이름 클립 여러 개
        await case(
            "B-dup",
            "mix_three",
            names=["다니엘", "다니엘", "강석", "필재"],
            ref=[OUT / "reg_daniel_pad.wav", OUT / "reg_daniel_long.wav", *refs("_long")[1:]],
        )

        # C. 상황별(긴 참조 클립)
        for audio in (
            "mix_tv_then_gangseok",
            "mix_stranger_only",
            "mix_quick_turns",
            "mix_daniel_over_tv",
            "mix_jenny_then_daniel",
            "q_piljae_2",
        ):
            await case("C", audio, names=NAMES, ref=refs("_long"))
        # 제니를 known speaker로(4명)
        await case(
            "C-jenny",
            "mix_jenny_then_daniel",
            names=[*NAMES, "제니"],
            ref=[*refs("_long"), OUT / "jenny.wav"],
        )
        # known speaker 없이
        await case("C-none", "mix_three")
        # 대화 도중 등록: 다니엘·강석만 등록된 상태에서 필재가 자기소개
        # → 미등록 라벨 구간에서 이름을 뽑을 수 있나
        await case("C-join", "mix_join", names=NAMES[:2], ref=refs("_long")[:2])

        # D. 지연·본문 비교(짧은 단일 발화, 세 사람 혼합) 각 3회
        lat: dict[str, list[float]] = {}
        for audio in ("q_gangseok_1", "mix_three"):
            for model in (DIARIZE, TRANSCRIBE):
                for i in range(3):
                    kw = {"names": NAMES, "ref": refs("_long")} if model == DIARIZE else {}
                    r = await case(f"D{i}", audio, model=model, **kw)
                    lat.setdefault(f"{audio}/{model}", []).append(r["elapsed"])
        print("\n지연 중앙값:", {k: round(statistics.median(v), 2) for k, v in lat.items()})

        # E. 이름 추출(등록 문장을 known speaker 없이 인식)
        print("\n이름 추출")
        for audio in (
            "reg_daniel",
            "reg_gangseok",
            "reg_piljae",
            "reg_daniel_long",
            "reg_gangseok_long",
            "reg_piljae_long",
            "name_haya",
            "name_rago",
            "name_ireum",
            "name_ieyo",
        ):
            r = await case("E", audio)
            body = r["body"]
            text = body.get("text", "") if isinstance(body, dict) else ""
            old = OLD_NAME.search(text)
            new = NEW_NAME.search(text)
            print(f"  {text!r} → 초안={old and old.group(1)!r} 개선={new and new.group(1)!r}")
    log.close()


if __name__ == "__main__":
    run(main)
