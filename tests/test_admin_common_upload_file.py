"""D-7C：后台通用文件上传（公众号安全验证文件）回归。

覆盖：
1. 路由已注册在 /api/v1 下；
2. 不允许的扩展名（.png/.exe 等）在落盘前即被 415 拒绝；
3. .txt/.html 的 content_type 映射正确。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin_common_upload import verify_file_content_type
from app.main import app


client = TestClient(app)


def test_common_upload_file_route_is_registered() -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/admin/common/upload-file" in paths
    # 后台鉴权：未登录直接 401，不会进入落盘逻辑
    assert client.post("/api/v1/admin/common/upload-file").status_code == 401


@pytest.mark.parametrize("filename", ["evil.png", "payload.exe", "noext", "", None])
def test_common_upload_file_rejects_disallowed_extension(filename: str | None) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        verify_file_content_type(filename)
    assert excinfo.value.status_code == 415


@pytest.mark.parametrize(
    ("filename", "expected"),
    [("MP_verify_abc.txt", "text/plain"), ("MP_verify_abc.HTML", "text/html"), ("a.htm", "text/html")],
)
def test_common_upload_file_accepts_verification_files(filename: str, expected: str) -> None:
    assert verify_file_content_type(filename) == expected
