# 后台通用文件上传（公众号安全验证文件）

用于公众号「安全验证」上传 `MP_verify_*.txt` / `*.html` 校验文件。图片上传请继续使用
`POST /api/v1/admin/common/upload`（图片专用，非图片返回 415）。

## 请求

| 项 | 值 |
|---|---|
| URL | `/api/v1/admin/common/upload-file` |
| Method | `POST` |
| 鉴权 | 后台管理员登录态（`Authorization: Bearer <token>`），需 `matchmaker.manage` 权限 |
| Content-Type | `multipart/form-data` |
| 参数 | `file`：文件字段，必填 |

## 文件限制

- 扩展名：`.txt`、`.html`、`.htm`（大小写不敏感，按文件名后缀判断）
- 大小：单个文件不超过 1MB
- 落盘目录：`{upload_dir}/admin/`（与图片上传同一目录）；返回 URL 为
  `/storage/uploads/admin/<uuid><ext>`，与其他后台资源一样按当前管理员签发签名参数。

## 成功响应（201）

```json
{
  "url": "/storage/uploads/admin/6f1c...e2.txt?kind=admin&expires=...&signature=...",
  "content_type": "text/plain",
  "size": 12,
  "purpose": "avatar"
}
```

> `purpose` 沿用通用上传响应模型的默认值，前端不依赖该字段。

## 错误

| 状态码 | 场景 | detail |
|---|---|---|
| 401 | 未登录或登录态失效 | — |
| 403 | 已登录但缺少 `matchmaker.manage` 权限 | — |
| 413 | 文件超过 1MB | `文件大小不能超过1MB` |
| 415 | 扩展名不在允许范围 | `仅支持上传 .txt 或 .html 文件` |
| 422 | 缺少 `file` 字段 | FastAPI 校验错误数组 |

## 回归测试

`tests/test_admin_common_upload_file.py`：断言路由已注册、未登录 401、不允许的扩展名被 415 拒绝、
允许扩展名的 content_type 映射。
