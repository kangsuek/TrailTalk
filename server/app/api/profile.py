"""GET/PUT /api/profile: 호칭·관심사·보이스·말 속도·페르소나·대화 모델 설정
(설계서 4.6, 설정 화면 S3-18·S3-31).

GET /api/voices·/api/voices/{voice}/sample: 설정 화면의 보이스 목록과 미리 듣기.
"""

import base64
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.client_config import ClientConfig
from app.db.session import DbSession
from app.errors import AppError
from app.persona.rules import VOICE_SAMPLE_TEXT
from app.services.mail import mail_configured
from app.services.profile import (
    CHAT_MODELS,
    ChatModel,
    Email,
    Nickname,
    line_field,
    persona_id_of,
    profile_with_persona,
    sync_persona,
    voice_style,
)
from app.voice.tts import OPENAI_VOICES, SPEAKING_RATE_MAX, SPEAKING_RATE_MIN

router = APIRouter(tags=["profile"])


Interest = Annotated[str, line_field(30)]
Voice = Literal[OPENAI_VOICES]  # type: ignore[valid-type]  # 틀린 이름은 422
SpeakingRate = Annotated[float, Field(ge=SPEAKING_RATE_MIN, le=SPEAKING_RATE_MAX)]


class ProfileOut(BaseModel):
    nickname: str | None
    interests: list[str]
    persona_id: str
    voice: str | None  # null이면 캐릭터 기본 보이스
    speaking_rate: float | None  # null이면 캐릭터 기본 말 속도
    email: str | None  # 대화 내용을 보낼 주소. null이면 설정 안 함
    mail_ready: bool  # 서버에 메일 발송(SMTP) 설정이 있는가(없으면 주소를 넣어도 보내지 못한다)
    keep_audio: bool
    chat_model: ChatModel | None  # 대화 모델(S3-31). null이면 서버 기본값
    default_chat_model: str  # 서버 기본 대화 모델(설정 화면의 "기본(…)" 표시용)
    # 클라이언트 설정값(읽기 전용, 규약 5절)
    client: ClientConfig


class ProfileUpdate(BaseModel):
    """보낸 필드만 바꾼다. nickname·email·voice·speaking_rate·chat_model을 null로 보내면
    기본값으로 돌아간다.

    chat_model은 진행 중인 대화에도 다음 답변부터 쓴다.
    """

    model_config = ConfigDict(extra="forbid")

    nickname: Nickname | None = None
    email: Email | None = None
    interests: Annotated[list[Interest], Field(max_length=10)] = []
    persona_id: Annotated[str, Field(pattern=r"^[a-z0-9_-]{1,64}$")] | None = None
    voice: Voice | None = None
    speaking_rate: SpeakingRate | None = None
    keep_audio: bool = False
    chat_model: ChatModel | None = None


def _out(profile, request: Request) -> ProfileOut:
    settings = request.app.state.settings
    return ProfileOut(
        nickname=profile.nickname,
        interests=list(profile.interests),
        persona_id=persona_id_of(profile, settings),
        voice=profile.voice if profile.voice in OPENAI_VOICES else None,  # 목록 밖 옛 값은 기본으로
        speaking_rate=profile.speaking_rate,
        email=profile.email,
        mail_ready=mail_configured(settings),
        keep_audio=profile.keep_audio,
        chat_model=profile.chat_model if profile.chat_model in CHAT_MODELS else None,
        default_chat_model=settings.llm_chat_model,
        client=request.app.state.client_config,
    )


@router.get("/profile")
async def get_profile(request: Request, db: DbSession) -> ProfileOut:
    settings = request.app.state.settings
    profile, _ = await profile_with_persona(db, settings)
    await db.commit()
    return _out(profile, request)


@router.put("/profile")
async def put_profile(body: ProfileUpdate, request: Request, db: DbSession) -> ProfileOut:
    settings = request.app.state.settings
    profile, _ = await profile_with_persona(db, settings)
    changes = body.model_dump(exclude_unset=True)
    if "persona_id" in changes and changes["persona_id"] is not None:
        await sync_persona(db, settings, changes["persona_id"])  # 없는 페르소나면 404
    for name, value in changes.items():
        if name == "interests":
            value = list(dict.fromkeys(value))  # 순서를 지키며 중복 제거
        setattr(profile, name, value)
    await db.commit()
    return _out(profile, request)


class VoicesOut(BaseModel):
    """설정 화면에서 고를 수 있는 보이스와 캐릭터 기본값(페르소나 YAML)."""

    voices: list[str]
    default_voice: str
    default_rate: float
    min_rate: float
    max_rate: float


@router.get("/voices")
async def list_voices(request: Request, db: DbSession) -> VoicesOut:
    _, loaded = await profile_with_persona(db, request.app.state.settings)
    await db.commit()
    return VoicesOut(
        voices=list(OPENAI_VOICES),
        default_voice=loaded.persona.voice.tts_voice,
        default_rate=loaded.persona.voice.speaking_rate,
        min_rate=SPEAKING_RATE_MIN,
        max_rate=SPEAKING_RATE_MAX,
    )


@router.get(
    "/voices/{voice}/sample",
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}}, "description": "미리 듣기 MP3"}},
)
async def voice_sample(
    voice: Voice,
    request: Request,
    db: DbSession,
    rate: Annotated[SpeakingRate | None, Query()] = None,
) -> Response:
    """보이스를 고정 문장으로 미리 들려준다(보이스·속도별로 한 번만 합성해 둔다)."""
    app = request.app
    _, loaded = await profile_with_persona(db, app.state.settings)
    await db.commit()
    # 속도는 0.05 단위로 묶는다(값을 조금씩 바꾼 요청마다 새로 합성·캐시하지 않게)
    rate = None if rate is None else round(round(rate / 0.05) * 0.05, 2)
    style = voice_style(loaded.persona.voice, voice, rate)
    audio = await app.state.speech.cached(app, VOICE_SAMPLE_TEXT, style)
    if audio is None:
        raise AppError("voice_unavailable", "지금은 목소리를 들려줄 수 없어요.", 503)
    return Response(
        base64.b64decode(audio),
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )
