"""본인 프로필(단일 행)과 페르소나 테이블 동기화(계획서 S1-08)."""

import re
from typing import Annotated, Literal, get_args

from pydantic import AfterValidator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Persona as PersonaRow
from app.db.models import UserProfile
from app.persona.loader import LoadedPersona, load_persona
from app.persona.rules import SPEECH_RATE_FAST, SPEECH_RATE_NORMAL, SPEECH_RATE_SLOW
from app.persona.schema import VoiceStyle
from app.voice.tts import OPENAI_VOICES

PROFILE_ID = 1


def line_field(limit: int) -> AfterValidator:
    """앞뒤 공백을 빼고 한 줄(제어 문자 없음), 1~limit자인지 확인한다."""

    def check(value: str) -> str:
        value = value.strip()
        if not value.isprintable():
            raise ValueError("줄바꿈이나 제어 문자는 쓸 수 없습니다")
        if not 1 <= len(value) <= limit:
            raise ValueError(f"1~{limit}자로 입력하세요")
        return value

    return AfterValidator(check)


# 프로필 API와 MCP set_nickname이 같은 규칙을 쓴다
Nickname = Annotated[str, line_field(20)]

_EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")


def _email(value: str) -> str:
    value = value.strip()
    if len(value) > 254 or not _EMAIL.fullmatch(value):
        raise ValueError("이메일 주소 형식이 아닙니다")
    return value


# 이메일 주소(대화 내용을 보낼 곳). 프로필 API가 검증한다. 도구는 이 값을 인자로 받지 않는다
Email = Annotated[str, AfterValidator(_email)]

# 대화 모델(S3-31). 프로필 API와 MCP set_model이 같은 목록을 쓴다(CLI --model 별칭)
ChatModel = Literal["haiku", "sonnet", "opus"]
CHAT_MODELS: tuple[str, ...] = get_args(ChatModel)


def profile_chat_model(profile: UserProfile, settings: Settings) -> str:
    """이 프로필로 대화할 모델. 고르지 않았거나 목록 밖 값이면 서버 기본값(LLM_CHAT_MODEL)."""
    return profile.chat_model if profile.chat_model in CHAT_MODELS else settings.llm_chat_model


def voice_style(base: VoiceStyle, voice: str | None, rate: float | None) -> VoiceStyle:
    """캐릭터 보이스(페르소나 YAML)에 설정 화면의 보이스·말 속도를 덮어쓴다(S3-18).

    voice·rate가 None이면 캐릭터 기본을 쓴다. 목록 밖 보이스(예전 API가 자유 문자열로 저장한 값)도
    캐릭터 기본으로 본다. 말 속도를 정했으면 말투 지시에도 빠르기를 붙인다."""
    update: dict = {}
    if voice in OPENAI_VOICES:
        update["tts_voice"] = voice
    if rate is not None:
        update["speaking_rate"] = rate
        if rate < 1.0:
            hint = SPEECH_RATE_SLOW
        elif rate > 1.1:
            hint = SPEECH_RATE_FAST
        else:
            hint = SPEECH_RATE_NORMAL
        update["instructions"] = f"{base.instructions} {hint}"
    return base.model_copy(update=update) if update else base


def profile_voice(profile: UserProfile, loaded: LoadedPersona) -> VoiceStyle:
    """이 프로필로 합성할 보이스(턴·인사말·마무리 멘트가 함께 쓴다)."""
    return voice_style(loaded.persona.voice, profile.voice, profile.speaking_rate)


async def sync_persona(db: AsyncSession, settings: Settings, persona_id: str) -> LoadedPersona:
    """YAML을 읽고 persona 테이블의 경로·버전(내용 해시)을 맞춘다. commit은 호출하는 쪽이 한다."""
    loaded = load_persona(settings.persona_dir, persona_id)
    row = await db.get(PersonaRow, persona_id)
    if row is None:
        try:
            # 세이브포인트: 동시에 온 다른 요청(화면이 프로필을 두 번 부르는 경우 등)이
            # 먼저 넣었어도 실패하지 않고 그 행을 쓴다
            async with db.begin_nested():
                db.add(
                    PersonaRow(id=persona_id, yaml_path=str(loaded.path), version=loaded.version)
                )
        except IntegrityError:
            pass
        row = await db.get(PersonaRow, persona_id)
        assert row is not None
    if row.version != loaded.version or row.yaml_path != str(loaded.path):
        row.version = loaded.version
        row.yaml_path = str(loaded.path)
    await db.flush()
    return loaded


async def get_profile(db: AsyncSession) -> UserProfile:
    """프로필 행을 돌려준다. 처음 조회하면 기본값으로 만든다."""
    profile = await db.get(UserProfile, PROFILE_ID)
    if profile is not None:
        return profile
    try:
        # 세이브포인트: 동시에 다른 요청이 먼저 만들었어도 바깥 트랜잭션(다른 객체)은 그대로 둔다
        async with db.begin_nested():
            db.add(UserProfile(id=PROFILE_ID))
    except IntegrityError:
        pass
    profile = await db.get(UserProfile, PROFILE_ID)
    assert profile is not None
    return profile


def persona_id_of(profile: UserProfile, settings: Settings) -> str:
    return profile.persona_id or settings.default_persona


async def profile_with_persona(
    db: AsyncSession, settings: Settings
) -> tuple[UserProfile, LoadedPersona]:
    profile = await get_profile(db)
    loaded = await sync_persona(db, settings, persona_id_of(profile, settings))
    return profile, loaded
