"""첨부 파일 내려받기(FR-22). 앱에는 로그인이 없어 보호는 ID 추측 불가성과 네트워크 경계뿐이다."""

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.db.models import Attachment
from app.db.session import DbSession
from app.errors import AppError
from app.services import attachments

router = APIRouter(tags=["attachments"])


@router.get("/attachments/{attachment_id}", response_class=FileResponse)
async def get_attachment(
    attachment_id: str, request: Request, db: DbSession, thumb: bool = False
) -> FileResponse:
    """이미지는 바로 보이게(inline), 텍스트는 내려받기(attachment)로 준다. thumb=1은 썸네일."""
    row = await db.get(Attachment, attachment_id)
    if row is None:
        raise AppError("attachment_not_found", "첨부를 찾지 못했어요.", 404)
    is_image = row.mime.startswith("image/")
    is_pdf = row.mime == "application/pdf"
    relative = row.thumb_path if thumb and row.thumb_path else row.path
    path = attachments.resolve(request.app.state.settings.attachments_dir, relative)
    if path is None or not path.is_file():
        raise AppError("attachment_not_found", "첨부를 찾지 못했어요.", 404)
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"}
    if is_image:
        media_type = "image/jpeg" if thumb else row.mime
        disposition = "inline"
    elif is_pdf:
        # 브라우저 내장 뷰어로 렌더하지 않고 내려받게 한다
        media_type = "application/pdf"
        disposition = "attachment"
    else:
        media_type = "text/plain; charset=utf-8"
        disposition = "attachment"
    headers["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{quote(row.name, safe='')}"
    return FileResponse(path, media_type=media_type, headers=headers)
