"""음성 원본 보관 기간 정리(계획서 S3-05, 설계서 4.4): 보관 기간이 지난 녹음을 지운다.

녹음은 프로필 keep_audio가 켜진 음성 턴에서 저장된다(services/conversation.py `_keep_audio`).
무발화 감시 루프(app/jobs/idle.py)가 앱 시작 때와 매 주기 함께 부른다.
"""

import asyncio
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import select, update

from app.db.models import Turn
from app.db.types import utcnow

logger = logging.getLogger("trailtalk.audio")


def _remove(root: Path, relative: str) -> None:
    """파일을 지우고 비게 된 세션 폴더도 지운다. audio_dir 밖을 가리키는 경로는 건드리지 않는다."""
    root = root.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        logger.warning("보관 폴더 밖 경로라 지우지 않음: %s", relative)
        return
    path.unlink(missing_ok=True)
    parent = path.parent
    if parent != root and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()


def remove_session_audio(root: Path, session_id: str) -> None:
    """대화 하나의 녹음 폴더를 통째로 지운다(대화 삭제). 경로를 남기지 못한 파일까지 지운다."""
    root = root.resolve()
    path = (root / session_id).resolve()
    if not path.is_relative_to(root) or path == root:
        logger.warning("보관 폴더 밖 경로라 지우지 않음: %s", session_id)
        return
    if path.is_dir():
        shutil.rmtree(path)


async def purge_old_audio(app: FastAPI, now: datetime | None = None) -> int:
    """보관 기간이 지난 녹음을 지우고 턴의 경로를 비운다. 정리한 턴 수.

    파일이 이미 없거나 보관 폴더 밖 경로면 경로만 비운다. 지우지 못하면 경로를 남겨 다시 시도한다.
    """
    settings = app.state.settings
    cutoff = (now or utcnow()) - timedelta(days=settings.audio_retention_days)
    async with app.state.session_factory() as db:
        rows = list(
            await db.execute(
                select(Turn.id, Turn.audio_path).where(
                    Turn.audio_path.is_not(None), Turn.created_at < cutoff
                )
            )
        )
        cleared: list[str] = []
        for turn_id, relative in rows:
            try:
                await asyncio.to_thread(_remove, settings.audio_dir, relative)
            except OSError:
                # 경로를 남겨 다음 차례에 다시 지운다(보관 기간을 넘겨 남지 않게)
                logger.warning("음성 원본 삭제 실패, 다음에 다시 시도: %s", relative, exc_info=True)
                continue
            cleared.append(turn_id)
        if cleared:
            await db.execute(
                update(Turn)
                .where(Turn.id.in_(cleared))
                .values(audio_path=None)
                .execution_options(synchronize_session=False)
            )
            await db.commit()
            logger.info("보관 기간이 지난 음성 원본 %d건 정리", len(cleared))
    return len(cleared)
