"""본인 프로필(단일 행)과 페르소나 테이블 동기화(계획서 S1-08)."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Persona as PersonaRow
from app.db.models import UserProfile
from app.persona.loader import LoadedPersona, load_persona

PROFILE_ID = 1


async def sync_persona(db: AsyncSession, settings: Settings, persona_id: str) -> LoadedPersona:
    """YAML을 읽고 persona 테이블의 경로·버전(내용 해시)을 맞춘다. commit은 호출하는 쪽이 한다."""
    loaded = load_persona(settings.persona_dir, persona_id)
    row = await db.get(PersonaRow, persona_id)
    if row is None:
        db.add(PersonaRow(id=persona_id, yaml_path=str(loaded.path), version=loaded.version))
    elif row.version != loaded.version or row.yaml_path != str(loaded.path):
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
