"""파일 첨부 수신·검증·가공·저장(FR-22, docs/attachment-plan.md 2장).

이미지는 Pillow로 열어 크기를 검사하고 EXIF 회전을 적용한 뒤 긴 변을 줄여 PNG(알파 있음) 또는
JPEG로 다시 인코딩한다(EXIF·위치 정보 제거). 텍스트는 UTF-8(BOM 허용) → cp949 순으로 읽어
UTF-8로 저장한다. 파일은 최종 경로에 바로 쓰고, 턴 저장이 실패하면 호출한 쪽이 `discard`로 지운다.
"""

import asyncio
import base64
import html
import io
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Attachment, Turn
from app.db.types import new_id
from app.errors import AppError

logger = logging.getLogger("trailtalk.attachments")

IMAGE_EXTENSIONS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP", "gif": "GIF"}
TEXT_EXTENSIONS = {"txt", "md", "csv", "json"}
MAX_IMAGE_PIXELS = 40_000_000  # 열자마자 검사해 넘으면 거절한다(디컴프레션 폭탄)
THUMB_PX = 320
DECODE_TIMEOUT_S = 10
NAME_MAX = 100
ORPHAN_GRACE_S = 3600
# 이미지 재인코딩 품질(JPEG)
_JPEG_QUALITY = 85

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def invalid(message: str) -> AppError:
    return AppError("attachment_invalid", message, 400)


def too_large(message: str) -> AppError:
    return AppError("attachment_too_large", message, 413)


@dataclass
class Upload:
    """업로드된 파일 하나(이름·본문). FastAPI의 UploadFile에서 읽어 만든다."""

    name: str
    data: bytes


@dataclass
class Prepared:
    """가공해 디스크에 쓴 첨부. DB 행과 CLI 입력 블록의 재료다."""

    id: str
    name: str
    mime: str
    size: int
    path: str  # attachments_dir 기준 상대 경로
    thumb_path: str | None
    kind: Literal["image", "text"]
    image: bytes | None = None  # 가공한 이미지 바이트(CLI에 base64로 넘긴다)
    text: str | None = None
    chars: int | None = None

    def to_row(self) -> Attachment:
        return Attachment(
            id=self.id,
            name=self.name,
            mime=self.mime,
            size=self.size,
            path=self.path,
            thumb_path=self.thumb_path,
            chars=self.chars,
        )


def clean_name(raw: str) -> str:
    """화면에 보일 이름: 경로 제거, 제어문자 제거, 공백 정리, 길이 제한."""
    name = re.split(r"[\\/]", raw or "")[-1]
    name = "".join(c for c in name if c.isprintable())
    name = " ".join(name.split())
    if len(name) > NAME_MAX:
        stem, dot, ext = name.rpartition(".")
        name = (
            (stem[: NAME_MAX - len(ext) - 1] + dot + ext)
            if dot and len(ext) <= 8
            else name[:NAME_MAX]
        )
    return name.strip(". ") or "file"


def _extension(name: str) -> str:
    return name.rpartition(".")[2].lower() if "." in name else ""


def _decode_text(data: bytes, name: str) -> str:
    if b"\x00" in data:
        raise invalid(f"{name}: 텍스트 파일이 아닌 것 같아요.")
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise invalid(f"{name}: 글자 인코딩을 읽지 못했어요(UTF-8 또는 CP949만 지원해요).")


def _has_alpha(im: Image.Image) -> bool:
    return im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)


def _flatten(im: Image.Image) -> Image.Image:
    """알파가 있으면 흰 바탕에 얹어 RGB로 만든다(썸네일용)."""
    if not _has_alpha(im):
        return im.convert("RGB")
    rgba = im.convert("RGBA")
    base = Image.new("RGB", rgba.size, "white")
    base.paste(rgba, mask=rgba.getchannel("A"))
    return base


def _process_image(data: bytes, name: str, ext: str, max_px: int) -> tuple[bytes, str, bytes]:
    """(가공한 이미지, mime, 썸네일 JPEG). 동기 함수라 스레드에서 돌린다."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            width, height = im.size
            if width * height > MAX_IMAGE_PIXELS:
                raise invalid(f"{name}: 이미지가 너무 커요.")
            if im.format != IMAGE_EXTENSIONS[ext]:
                raise invalid(f"{name}: 파일 내용이 확장자와 달라요.")
            im.seek(0)  # 애니메이션은 첫 프레임만
            im = ImageOps.exif_transpose(im)
            im.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as exc:
        raise invalid(f"{name}: 이미지를 열지 못했어요.") from exc
    im.thumbnail((max_px, max_px))
    out = io.BytesIO()
    if _has_alpha(im):
        im.convert("RGBA").save(out, "PNG", optimize=True)
        mime = "image/png"
    else:
        im.convert("RGB").save(out, "JPEG", quality=_JPEG_QUALITY)
        mime = "image/jpeg"
    thumb = _flatten(im)
    thumb.thumbnail((THUMB_PX, THUMB_PX))
    thumb_out = io.BytesIO()
    thumb.save(thumb_out, "JPEG", quality=_JPEG_QUALITY)
    return out.getvalue(), mime, thumb_out.getvalue()


async def session_usage(db: AsyncSession, session_id: str) -> tuple[int, int]:
    """세션에 이미 붙은 (이미지 수, 텍스트 글자 수)."""
    rows = await db.execute(
        select(
            func.count().filter(Attachment.chars.is_(None)),
            func.coalesce(func.sum(Attachment.chars), 0),
        )
        .join(Turn, Turn.id == Attachment.turn_id)
        .where(Turn.session_id == session_id)
    )
    images, chars = rows.one()
    return int(images), int(chars)


def check_count(settings: Settings, count: int) -> None:
    if count < 1:
        raise invalid("첨부할 파일이 없어요.")
    if count > settings.attachment_max_files:
        raise invalid(f"파일은 한 번에 {settings.attachment_max_files}개까지 보낼 수 있어요.")


def _write(root: Path, relative: str, data: bytes) -> None:
    path = root / relative
    for attempt in (0, 1):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            break
        except FileNotFoundError:  # 고아 정리가 빈 폴더를 막 지웠다
            if attempt:
                raise
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def discard(root: Path, items: list[Prepared]) -> None:
    """저장하지 못한 첨부 파일을 지운다(턴 저장 실패·세션 없음)."""
    for item in items:
        for relative in (item.path, item.thumb_path):
            if relative:
                (root / relative).unlink(missing_ok=True)
    for parent in {(root / item.path).parent for item in items}:
        try:
            parent.rmdir()  # 비었을 때만 지워진다
        except OSError:
            pass


async def prepare(
    settings: Settings, session_id: str, uploads: list[Upload], used: tuple[int, int]
) -> list[Prepared]:
    """업로드를 검증·가공해 디스크에 쓴다. 하나라도 실패하면 쓴 파일을 지우고 AppError를 던진다.

    used: 세션에 이미 붙은 (이미지 수, 텍스트 글자 수). 세션 누적 한도를 검사한다.
    """
    check_count(settings, len(uploads))
    root = settings.attachments_dir
    result: list[Prepared] = []
    images = used[0]
    text_chars = 0
    try:
        for upload in uploads:
            name = clean_name(upload.name)
            ext = _extension(name)
            attachment_id = new_id()
            if ext in IMAGE_EXTENSIONS:
                if len(upload.data) > settings.attachment_image_upload_max_bytes:
                    mb = settings.attachment_image_upload_max_bytes // (1024 * 1024)
                    raise too_large(f"{name}: 이미지는 {mb}MB까지 보낼 수 있어요.")
                images += 1
                if images > settings.attachment_session_max_images:
                    raise invalid(
                        f"이 대화에는 이미지를 {settings.attachment_session_max_images}장까지 "
                        "붙일 수 있어요. 새 대화에서 이어 주세요."
                    )
                try:
                    data, mime, thumb = await asyncio.wait_for(
                        asyncio.to_thread(
                            _process_image, upload.data, name, ext, settings.attachment_image_max_px
                        ),
                        DECODE_TIMEOUT_S,
                    )
                except TimeoutError:
                    raise invalid(f"{name}: 이미지를 처리하지 못했어요.") from None
                out_ext = "png" if mime == "image/png" else "jpg"
                item = Prepared(
                    id=attachment_id,
                    name=name,
                    mime=mime,
                    size=len(data),
                    path=f"{session_id}/{attachment_id}.{out_ext}",
                    thumb_path=f"{session_id}/{attachment_id}.thumb.jpg",
                    kind="image",
                    image=data,
                )
                await asyncio.to_thread(_write, root, item.path, data)
                result.append(item)
                await asyncio.to_thread(_write, root, item.thumb_path, thumb)
            elif ext in TEXT_EXTENSIONS:
                if len(upload.data) > settings.attachment_text_max_bytes:
                    kb = settings.attachment_text_max_bytes // 1024
                    raise too_large(f"{name}: 텍스트 파일은 {kb}KB까지 보낼 수 있어요.")
                text = _decode_text(upload.data, name)
                text_chars += len(text)
                if text_chars > settings.attachment_text_max_chars:
                    raise invalid(
                        f"텍스트는 한 번에 {settings.attachment_text_max_chars:,}자까지 "
                        "보낼 수 있어요."
                    )
                if used[1] + text_chars > settings.attachment_session_max_text_chars:
                    raise invalid("이 대화에 붙인 텍스트가 너무 많아요. 새 대화에서 이어 주세요.")
                data = text.encode("utf-8")
                item = Prepared(
                    id=attachment_id,
                    name=name,
                    mime="text/plain",
                    size=len(data),
                    path=f"{session_id}/{attachment_id}.{ext}",
                    thumb_path=None,
                    kind="text",
                    text=text,
                    chars=len(text),
                )
                await asyncio.to_thread(_write, root, item.path, data)
                result.append(item)
            else:
                raise invalid(
                    f"{name}: 지원하지 않는 형식이에요(이미지 png·jpg·webp·gif, "
                    "텍스트 txt·md·csv·json)."
                )
    except BaseException:
        discard(root, result)
        raise
    return result


def resolve(root: Path, relative: str) -> Path | None:
    """저장 경로를 파일 경로로 바꾼다. attachments_dir 밖이면 None."""
    root = root.resolve()
    path = (root / relative).resolve()
    return path if path.is_relative_to(root) and path != root else None


async def purge_orphans(app, now: float | None = None) -> int:
    """DB에 없는 파일 중 1시간 지난 것을 지운다(업로드 직후 끊겨 행을 못 남긴 파일). 지운 개수."""
    root: Path = app.state.settings.attachments_dir
    if not root.is_dir():
        return 0
    async with app.state.session_factory() as db:
        known = set()
        for path, thumb in await db.execute(select(Attachment.path, Attachment.thumb_path)):
            known.update(p for p in (path, thumb) if p)
    cutoff = (now or time.time()) - ORPHAN_GRACE_S

    def sweep() -> int:
        removed = 0
        for file in root.glob("*/*"):
            relative = file.relative_to(root).as_posix()
            if file.is_file() and relative not in known and file.stat().st_mtime < cutoff:
                file.unlink(missing_ok=True)
                removed += 1
        for folder in root.iterdir():
            if folder.is_dir() and folder.stat().st_mtime < cutoff and not any(folder.iterdir()):
                folder.rmdir()
        return removed

    removed = await asyncio.to_thread(sweep)
    if removed:
        logger.info("고아 첨부 파일 %d개 정리", removed)
    return removed


WRAPPER_NAME_MAX = 40
_CLOSING_TAG = re.compile(r"</\s*attachment", re.IGNORECASE)


def _wrapper_name(name: str) -> str:
    return html.escape(name[:WRAPPER_NAME_MAX], quote=True)


def text_wrapper(name: str, content: str) -> str:
    """텍스트 첨부를 CLI 입력에 넣는 래퍼. 본문 속 닫는 태그는 무력화한다."""
    body = _CLOSING_TAG.sub("</ attachment", content)
    return f'<attachment name="{_wrapper_name(name)}">\n{body}\n</attachment>'


def cli_input(items: list[Prepared], prefix: str, text: str) -> str | list[dict]:
    """CLI에 보낼 사용자 입력: 앱 안내(prefix) + 텍스트 첨부 래퍼 + 사용자 글.

    이미지가 있으면 [이미지 블록…, 텍스트 블록] 배열(질문이 이미지 뒤, M0)이고 없으면 문자열이다.
    """
    wrappers = [text_wrapper(i.name, i.text or "") for i in items if i.kind == "text"]
    full = prefix + "\n".join([*wrappers, text])
    blocks: list[dict] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": i.mime,
                "data": base64.b64encode(i.image or b"").decode("ascii"),
            },
        }
        for i in items
        if i.kind == "image"
    ]
    if not blocks:
        return full
    return [*blocks, {"type": "text", "text": full}]


def load_past_texts(root: Path, turns: list[Turn], budget: int) -> dict[str, str]:
    """다시 열기용: 텍스트 첨부를 최신순으로 합계 budget자까지 디스크에서 읽는다(id → 내용).

    넘치거나 읽지 못하는 첨부는 빠진다(이름만 남는다)."""
    found: dict[str, str] = {}
    left = budget
    for turn in reversed(turns):
        for att in reversed(turn.attachments):
            if att.chars is None or att.chars > left:
                continue
            path = resolve(root, att.path)
            try:
                content = path.read_text(encoding="utf-8") if path else None
            except OSError:
                content = None
            if content is None:
                continue
            found[att.id] = content
            left -= len(content)
    return found
