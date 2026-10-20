# 相亲卡模板（A8）管理后台接口

## 1. 通用约定

接口前缀：`/api/v1`。需携带 `Authorization: Bearer <access_token>`。

| 接口类别 | 权限码 |
| --- | --- |
| 读（`GET`） | `platform.lovecard.read`（`platform.lovecard.write` 亦可） |
| 写（`POST` / `PATCH` / `DELETE`） | `platform.lovecard.write` |

- 模板条件（活动、报名时间、地区、籍贯、身高/年龄范围、推广/服务红娘、标签）保存在
  `admin_lovecard_template`；生成结果保存在 `admin_lovecard_generation`。
- **出图依赖尚未接入的卡片渲染器**：`POST /{template_id}/generate` 在校验模板后返回 `503`，
  不会写入任何生成行。渲染器接入后按本文约定返回 `images`（现签 URL 列表）。
- 审计：`lovecard_template.create/update/delete`。
- 分页壳：`{ items, page, page_size, total, has_more }`。

---

## 2. `GET /api/v1/admin/lovecard-templates`

- 权限：`platform.lovecard.read`。成功状态：`200 OK`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` | query | int | 否 | 1 | 1–10000 | 页码 |
| `page_size` | query | int | 否 | 20 | 1–100 | 每页条数 |
| `keyword` | query | string | 否 | 无 | ≤64 | 模板名/二维码文案模糊匹配 |
| `enabled` | query | bool | 否 | 无 | true/false | 是否启用 |

返回字段：

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 模板 ID |
| `name` | string | 是 | — | 模板名 |
| `style` | int | 是 | — | 样式编号 1–25 |
| `activity_id` | int/null | 是 | 未关联 | 关联线下活动 |
| `register_start` / `register_end` | datetime/null | 是 | 不限 | 报名时间窗 |
| `region_code` | string/null | 是 | 不限 | 地区筛选 |
| `native_place` | string/null | 是 | 不限 | 籍贯筛选 |
| `height_min` / `height_max` | int/null | 是 | 不限 | 身高范围（cm） |
| `age_min` / `age_max` | int/null | 是 | 不限 | 年龄范围 |
| `promoter_id` / `matchmaker_id` | int/null | 是 | 未指定 | 推广/服务红娘 `users.id` |
| `qrcode_desc` | string/null | 是 | 未填 | 卡片内二维码说明文案 |
| `qrcode_expire_days` | int/null | 是 | 未设置 | 二维码有效期（天） |
| `limit_latest` | int | 是 | — | 取最新会员前 N 条生成 |
| `tags` | string[] | 是 | `[]` | 会员标签筛选 |
| `enabled` | bool | 是 | — | 是否启用 |
| `created_by` | int/null | 是 | — | 创建人 |
| `created_at` / `updated_at` | datetime/null | 是 | — | 时间戳 |

```http
GET /api/v1/admin/lovecard-templates?page=1&page_size=20&enabled=true
Authorization: Bearer <access_token>
```

```json
{"items": [{"id": 2, "name": "双十一卡片", "style": 3, "activity_id": 9,
            "register_start": "2026-10-20T00:00:00", "register_end": "2026-11-10T00:00:00",
            "region_code": "320100", "native_place": "南京", "height_min": 155, "height_max": 185,
            "age_min": 25, "age_max": 35, "promoter_id": null, "matchmaker_id": 88,
            "qrcode_desc": "扫码加入活动", "qrcode_expire_days": 30, "limit_latest": 5,
            "tags": ["教师"], "enabled": true, "created_by": 3,
            "created_at": "2026-10-20T10:00:00", "updated_at": "2026-10-20T10:00:00"}],
 "page": 1, "page_size": 20, "total": 1, "has_more": false}
```

空数据：`{"items": [], "page": 1, "page_size": 20, "total": 0, "has_more": false}`

---

## 3. `POST /api/v1/admin/lovecard-templates`

- 权限：`platform.lovecard.write`。成功状态：`201 Created`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `name` | body | string | 是 | — | 1–128 | 模板名 |
| `style` | body | int | 否 | 1 | 1–25 | 样式编号 |
| `activity_id` | body | int/null | 否 | null | ≥1，活动必须存在 | 关联活动 |
| `register_start` / `register_end` | body | datetime/null | 否 | null | 起早于止 | 报名时间窗 |
| `region_code` | body | string/null | 否 | null | ≤64 | 地区 |
| `native_place` | body | string/null | 否 | null | ≤64 | 籍贯 |
| `height_min` / `height_max` | body | int/null | 否 | null | 0–300，下限 ≤ 上限 | 身高范围 |
| `age_min` / `age_max` | body | int/null | 否 | null | 0–120，下限 ≤ 上限 | 年龄范围 |
| `promoter_id` / `matchmaker_id` | body | int/null | 否 | null | ≥1，必须是有效服务红娘 | 红娘 |
| `qrcode_desc` | body | string/null | 否 | null | ≤500 | 二维码文案 |
| `qrcode_expire_days` | body | int/null | 否 | null | 1–3650 | 二维码有效期 |
| `limit_latest` | body | int | 否 | 5 | 1–200 | 取最新 N 条 |
| `tags` | body | string[] | 否 | `[]` | ≤50 个 | 标签 |
| `enabled` | body | bool | 否 | true | — | 是否启用 |

```http
POST /api/v1/admin/lovecard-templates
Content-Type: application/json

{"name": "双十一卡片", "style": 3, "age_min": 25, "age_max": 35,
 "matchmaker_id": 88, "qrcode_desc": "扫码加入活动", "qrcode_expire_days": 30,
 "limit_latest": 5, "tags": ["教师"], "enabled": true}
```

非法示例：`{"name": "x", "style": 26}` → `422`；`{"name": "x", "age_min": 40, "age_max": 30}` → `422`；
`{"name": "x", "matchmaker_id": 999999}` → `422 红娘目标 999999 不是有效服务红娘`。

---

## 4. `PATCH /api/v1/admin/lovecard-templates/{template_id}`

- 权限：`platform.lovecard.write`。成功状态：`200 OK`。
- 全部字段可选，至少一个（否则 422）。`tags` 传数组时整体替换。
- 返回：`LovecardTemplateItem`。

非法示例：`{}` → `422 至少提供一个需要修改的字段`。

---

## 5. `POST /api/v1/admin/lovecard-templates/{template_id}/generate`

- 用途：按模板条件批量生成相亲卡。
- 权限：`platform.lovecard.write`。成功状态：`200 OK`（渲染器接入后）。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `template_id` | path | int | 是 | — | ≥1 | 模板 ID |
| `limit` | body | int/null | 否 | 模板 `limit_latest` | 1–200 | 本次生成数量上限 |

```http
POST /api/v1/admin/lovecard-templates/2/generate
Content-Type: application/json

{"limit": 10}
```

当前行为（渲染器未接入）：模板存在且启用时返回：

```json
{"detail": "相亲卡渲染服务未配置，暂不能生成卡片图片"}
```

状态码 `503`。模板停用时先返回 `409 模板已停用，不能生成`。

返回字段（渲染器接入后）：

| 字段 | 类型 | 必返 | 含义 |
| --- | --- | --- | --- |
| `template_id` | int | 是 | 模板 ID |
| `batch_no` | string | 是 | 本批次号 |
| `generated` | int | 是 | 成功生成张数 |
| `images` | string[] | 是 | 图片现签 URL 列表 |
| `failures` | object[] | 是 | 失败项 `{user_id, error}` |

业务规则：

- 会员筛选顺序：模板条件 → 排除已在弃海池的会员 → 按 `users.created_at DESC` 取前 N 条。
- 每张图写一行 `admin_lovecard_generation`（`status` 为 `success`/`failed`），失败不阻断整批。
- 单次上限 200 张。

---

## 6. `GET /api/v1/admin/lovecard-templates/generations`

- 权限：`platform.lovecard.read`。成功状态：`200 OK`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` | query | int | 否 | 1 | 1–10000 | 页码 |
| `page_size` | query | int | 否 | 20 | 1–100 | 每页条数 |
| `template_id` | query | int | 否 | 无 | ≥1 | 按模板筛选 |
| `status` | query | string | 否 | 无 | `pending` / `success` / `failed` | 生成状态 |

返回字段：

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 记录 ID |
| `template_id` | int | 是 | — | 模板 |
| `batch_no` | string/null | 是 | 历史数据无批次 | 批次号 |
| `user_id` | int | 是 | — | 会员 ID |
| `nickname` | string/null | 是 | 用户已删 | 会员昵称 |
| `image_url` | string/null | 是 | 未生成 | 图片现签地址 |
| `status` | string | 是 | — | `pending` / `success` / `failed` |
| `error` | string/null | 是 | 无错误 | 失败原因 |
| `generated_by` | int/null | 是 | — | 操作人 |
| `created_at` | datetime/null | 是 | — | 生成时间 |

```json
{"items": [{"id": 41, "template_id": 2, "batch_no": "20261020120000ab12", "user_id": 1024,
            "nickname": "小满", "image_url": null, "status": "failed",
            "error": "渲染服务未配置", "generated_by": 3, "created_at": "2026-10-20T12:00:00"}],
 "page": 1, "page_size": 20, "total": 1, "has_more": false}
```

---

## 7. `DELETE /api/v1/admin/lovecard-templates/{template_id}`

- 权限：`platform.lovecard.write`。成功状态：`204 No Content`（无返回体）。
- 物理删除模板；历史生成记录保留（`template_id` 仍可追溯）。

---

## 8. 错误码汇总

| 状态码 | 触发条件 | 前端处理 |
| --- | --- | --- |
| 401 | 未登录 | 跳转登录 |
| 403 | 缺 `platform.lovecard.*` | 隐藏入口 |
| 404 | 模板不存在 | 刷新列表 |
| 409 | 模板已停用仍尝试生成 | 先启用模板 |
| 422 | 参数/范围/红娘目标非法 | 修正表单 |
| 503 | 卡片渲染器未接入 | 提示暂不可生成 |

## 9. 变更记录

| 日期 | 变更 |
| --- | --- |
| 2026-10-20 | 新增相亲卡模板 CRUD、批量生成与生成记录接口（A8）；生成依赖的渲染器待接入 |

## 10. 文档完成自检清单

- [x] 请求参数表完整
- [x] 请求示例与非法示例
- [x] 返回参数表含空值含义与分页字段
- [x] 业务规则覆盖筛选顺序、批次、失败不阻断
- [x] 错误码表完整（含 503 的当前实际行为）
