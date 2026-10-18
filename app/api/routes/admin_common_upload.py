"""后台通用文件上传：公众号安全验证文件（.txt/.html）。

与 ``matchmaker_staff_admin.common_upload``（图片专用，非图片返回 415）并列，
本接口只接受微信公众平台要求的校验文件，落盘目录与签名方式保持一致。
"""

from pathlib import Path as FilePath
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentMatchmakerAdmin, declare_permission, get_current_matchmaker_admin
from app.core.config import settings
from app.db.session import get_db
from app.schemas.matchmaker_staff_admin import CommonUploadResponse
from app.services.media_access import MEDIA_CATEGORY_ADMIN, sign_media_url
from app.services.profile import _read_limited

router = APIRouter(prefix="/admin")

# 公众号安全验证文件：仅 .txt / .html / .htm，单个不超过 1MB
VERIFY_FILE_EXTENSIONS: dict[str, str] = {
    ".txt": "text/plain",
    ".html": "text/html",
    ".htm": "text/html",
}
VERIFY_FILE_MAX_BYTES = 1024 * 1024


def verify_file_content_type(filename: str | None) -> str:
    """校验扩展名并返回响应中的 content_type；不允许的扩展名直接 415。"""
    suffix = FilePath(filename or "").suffix.lower()
    content_type = VERIFY_FILE_EXTENSIONS.get(suffix)
    if content_type is None:
        raise HTTPException(415, detail="仅支持上传 .txt 或 .html 文件")
    return content_type


@declare_permission("matchmaker.manage")
@router.post("/common/upload-file", response_model=CommonUploadResponse, status_code=201)
async def common_upload_file(
    file: UploadFile = File(...),
    current: CurrentMatchmakerAdmin = Depends(get_current_matchmaker_admin),
    db: AsyncSession = Depends(get_db),
) -> CommonUploadResponse:
    current.require("matchmaker.manage")
    content_type = verify_file_content_type(file.filename)
    data = await _read_limited(file, VERIFY_FILE_MAX_BYTES)
    directory = FilePath(settings.upload_dir) / "admin"
    directory.mkdir(parents=True, exist_ok=True)
    name = uuid4().hex
    suffix = FilePath(file.filename or "").suffix.lower()
    target = directory / f"{name}{suffix}"
    target.write_bytes(data)
    return CommonUploadResponse(
        # 与图片上传一致：后台资源仅后台签发链路，挂载层验签时校验账号状态。
        url=sign_media_url(
            f"/storage/uploads/admin/{name}{suffix}",
            category=MEDIA_CATEGORY_ADMIN,
            viewer=current.account.id,
        ),
        content_type=content_type,
        size=len(data),
    )
