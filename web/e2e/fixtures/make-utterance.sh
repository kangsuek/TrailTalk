#!/usr/bin/env bash
# 음성 흐름 E2E(voice.spec.ts)의 가짜 마이크 파일을 만든다(macOS say + ffmpeg).
# 무음 1초 + 한국어 문장(약 3초) + 무음 20초. Chromium 가짜 장치는 파일을 되풀이하므로 약 24초마다 한 번 말한다.
# 뒤 무음이 짧으면 답변을 듣는 중에 다음 말이 끼어들기로 잡힌다.
#
#   FFMPEG=~/.local/bin/ffmpeg web/e2e/fixtures/make-utterance.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
FFMPEG="${FFMPEG:-ffmpeg}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
say -v Yuna -o "$TMP/speech.aiff" "오늘 산책하면서 생각난 아이디어가 있어" # 가짜 인식 결과(FAKE_STT_TEXT)와 같은 문장
"$FFMPEG" -loglevel error -y \
  -f lavfi -t 1 -i anullsrc=r=16000:cl=mono \
  -i "$TMP/speech.aiff" \
  -f lavfi -t 20 -i anullsrc=r=16000:cl=mono \
  -filter_complex "[1:a]aresample=16000,aformat=channel_layouts=mono[s];[0:a][s][2:a]concat=n=3:v=0:a=1" \
  -c:a pcm_s16le "$DIR/utterance.wav"
echo "만듦: $DIR/utterance.wav"
