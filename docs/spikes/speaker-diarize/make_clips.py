"""1. OpenAI TTS로 참가자 흉내 오디오를 만든다(과금 소량). 결과는 SPIKE_DIR의 16kHz 모노 WAV.

남성 참가자 셋(onyx·ash·verse)은 일부러 비슷한 목소리로 고른다.
미등록: coral(TV 여성)·ballad(행인 남성), 제니: nova.
"""

import asyncio

import httpx2
from common import OUT, RATE, ffmpeg, headers, run, url

VOICE = {
    "daniel": "onyx",
    "gangseok": "ash",
    "piljae": "verse",
    "tv": "coral",
    "stranger": "ballad",
    "jenny": "nova",
}

LINES = {
    # 등록 문장(짧은 것·긴 것·이름 추출 변형)
    "reg_daniel": ("daniel", "저는 다니엘입니다."),
    "reg_gangseok": ("gangseok", "저는 강석입니다."),
    "reg_piljae": ("piljae", "저는 필재입니다."),
    "reg_daniel_long": (
        "daniel",
        "안녕하세요, 저는 다니엘이라고 합니다. 오늘 같이 산책하면서 이야기 나눠요.",
    ),
    "reg_gangseok_long": (
        "gangseok",
        "안녕하세요, 저는 강석입니다. 오늘 산책 같이 하게 돼서 반가워요.",
    ),
    "reg_piljae_long": ("piljae", "반갑습니다, 저는 필재예요. 저도 오늘 대화에 같이 참여할게요."),
    "name_haya": ("daniel", "저는 하야입니다."),
    "name_rago": ("gangseok", "다니엘이라고 합니다."),
    "name_ireum": ("piljae", "제 이름은 필재예요."),
    "name_ieyo": ("gangseok", "강석이에요."),
    # 화자별 질문
    "q_daniel_1": ("daniel", "오늘 날씨 어때? 오후에 비 온대?"),
    "q_daniel_2": ("daniel", "근처에 조용한 카페 있을까?"),
    "q_gangseok_1": ("gangseok", "어제 얘기한 앱 아이디어 다시 정리해 줘."),
    "q_gangseok_2": ("gangseok", "주말에 등산 갈 만한 데 추천해 줘."),
    "q_piljae_1": ("piljae", "그 책 제목이 뭐였지?"),
    "q_piljae_2": ("piljae", "내일 회의가 몇 시였는지 기억나?"),
    # 미등록·제니
    "tv": ("tv", "오늘의 날씨입니다. 서울은 오후부터 비가 내리겠습니다."),
    "stranger": ("stranger", "아 저기요, 지하철역이 어느 쪽이에요?"),
    "jenny": ("jenny", "좋아요, 그럼 근처 카페를 찾아볼게요."),
}

# 이어 붙인 시험 오디오: (이름, [(클립, 앞 무음 초)])
MIXES = {
    "mix_three": [("q_daniel_1", 0.3), ("q_gangseok_1", 0.6), ("q_piljae_1", 0.6)],
    "mix_tv_then_gangseok": [("tv", 0.3), ("q_gangseok_2", 0.6)],
    "mix_stranger_only": [("stranger", 0.3)],
    "mix_jenny_then_daniel": [("jenny", 0.3), ("q_daniel_2", 0.5)],
    # 대화 도중 새 사람이 들어와 자기소개(필재는 아직 등록 전)
    "mix_join": [("q_daniel_1", 0.3), ("reg_piljae_long", 0.6)],
    "mix_quick_turns": [("q_piljae_2", 0.3), ("q_daniel_2", 0.2), ("q_gangseok_2", 0.2)],
}


def silence(seconds: float, out) -> None:  # noqa: ANN001
    ffmpeg("-f", "lavfi", "-i", f"anullsrc=r={RATE}:cl=mono", "-t", f"{seconds}", str(out))


def concat(parts: list, out) -> None:  # noqa: ANN001
    inputs: list[str] = []
    for p in parts:
        inputs += ["-i", str(p)]
    ffmpeg(
        *inputs,
        "-filter_complex",
        f"concat=n={len(parts)}:v=0:a=1",
        "-ar",
        str(RATE),
        "-ac",
        "1",
        str(out),
    )


async def main() -> None:
    async with httpx2.AsyncClient() as client:

        async def synth(name: str, voice: str, text: str) -> None:
            raw = OUT / f"{name}.raw.wav"
            if (OUT / f"{name}.wav").exists():
                return
            r = await client.post(
                url("/audio/speech"),
                headers=headers(),
                json={
                    "model": "gpt-4o-mini-tts",
                    "voice": voice,
                    "input": text,
                    "response_format": "wav",
                    "instructions": "자연스러운 한국어 대화체로 말한다.",
                },
                timeout=60,
            )
            r.raise_for_status()
            raw.write_bytes(r.content)
            ffmpeg("-i", str(raw), "-ar", str(RATE), "-ac", "1", str(OUT / f"{name}.wav"))
            raw.unlink()
            print("합성", name)

        await asyncio.gather(*(synth(n, VOICE[who], text) for n, (who, text) in LINES.items()))

    # 등록 클립 2.5초로 무음 채우기(앞 0.3초 + 뒤)
    for name in ("reg_daniel", "reg_gangseok", "reg_piljae"):
        src = OUT / f"{name}.wav"
        ffmpeg("-i", str(src), "-af", "adelay=300,apad=whole_dur=2.5", str(OUT / f"{name}_pad.wav"))
    for name, parts in MIXES.items():
        files = []
        for i, (clip, gap) in enumerate(parts):
            s = OUT / f"_gap_{name}_{i}.wav"
            silence(gap, s)
            files += [s, OUT / f"{clip}.wav"]
        tail = OUT / f"_gap_{name}_end.wav"
        silence(0.5, tail)
        concat([*files, tail], OUT / f"{name}.wav")
        for f in files[::2] + [tail]:
            f.unlink()
        print("혼합", name)
    # 다니엘 질문 뒤로 TV가 작게 깔린 오디오(동시 소리)
    ffmpeg(
        "-i",
        str(OUT / "q_daniel_2.wav"),
        "-i",
        str(OUT / "tv.wav"),
        "-filter_complex",
        "[1]volume=0.35[b];[0][b]amix=inputs=2:duration=longest:normalize=0",
        "-ar",
        str(RATE),
        "-ac",
        "1",
        str(OUT / "mix_daniel_over_tv.wav"),
    )
    print("완료:", OUT)


if __name__ == "__main__":
    run(main)
