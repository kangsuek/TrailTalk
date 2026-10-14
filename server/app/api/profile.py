"""GET/PUT /api/profile: 호칭·관심사·보이스·페르소나 설정(설계서 4.6)."""

from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.db.session import DbSession
from app.services.profile import persona_id_of, profile_with_persona, sync_persona

router = APIRouter(tags=["profile"])


def _line(limit: int) -> AfterValidator:
    """앞뒤 공백을 빼고 한 줄(제어 문자 없음), 1~limit자인지 확인한다."""

    def check(value: str) -> str:
        value = value.strip()
        if not value.isprintable():
            raise ValueError("줄바꿈이나 제어 문자는 쓸 수 없습니다")
        if not 1 <= len(value) <= limit:
            raise ValueError(f"1~{limit}자로 입력하세요")
        return value

    return AfterValidator(check)


Nickname = Annotated[str, _line(20)]
Interest = Annotated[str, _line(30)]


class ProfileOut(BaseModel):
    nickname: str | None
    interests: list[str]
    persona_id: str
    voice: str | None
    keep_audio: bool


class ProfileUpdate(BaseModel):
    """보낸 필드만 바꾼다. nickname을 null로 보내면 기본 호칭으로 돌아간다."""

    model_config = ConfigDict(extra="forbid")

    nickname: Nickname | None = None
    interests: Annotated[list[Interest], Field(max_length=10)] = []
    persona_id: Annotated[str, Field(pattern=r"^[a-z0-9_-]{1,64}$")] | None = None
    voice: Annotated[str, _line(100)] | None = None
    keep_audio: bool = False


def _out(profile, settings) -> ProfileOut:
    return ProfileOut(
        nickname=profile.nickname,
        interests=list(profile.interests),
        persona_id=persona_id_of(profile, settings),
        voice=profile.voice,
        keep_audio=profile.keep_audio,
    )


@router.get("/profile")
async def get_profile(request: Request, db: DbSession) -> ProfileOut:
    settings = request.app.state.settings
    profile, _ = await profile_with_persona(db, settings)
    await db.commit()
    return _out(profile, settings)


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
    return _out(profile, settings)
