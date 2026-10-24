# 二维码管理（A5）管理后台接口

## 1. 通用约定

接口前缀：`/api/v1`。需携带 `Authorization: Bearer <access_token>`。

| 接口类别 | 权限码 |
| --- | --- |
| 读（`GET`） | `platform.qrcode.read`（`platform.qrcode.write` 亦可） |
| 写（`POST` / `PATCH` / `DELETE`） | `platform.qrcode.write` |

- 出图：`type=h5` 由后端用 `qrcode` 库本地渲染 PNG，落盘 `{upload_dir}/admin/qrcodes/<uuid>.png`。
- `type=miniprogram`（小程序码）走微信公众号适配器（`WECHAT_MP_*`），凭据未配置时生成一律 `503 公众号凭据未配置`；
  已配置时调用 `wxa/getwxacodeunlimit` 产出小程序码 PNG。`target_url` 此时表示小程序页面路径。
- 数据库存相对路径；返回的 `image_url` 为按当前管理员现签的临时地址（`kind=admin`）。
- 审计：`qrcode.create` / `qrcode.renew` / `qrcode.update` / `qrcode.delete`。
- 分页壳：`{ items, page, page_size, total, has_more }`。

---

## 2. `GET /api/v1/admin/qrcodes`

- 用途：分页查询二维码（类型 / 场景 / 状态 / 创建时间筛选）。
- 权限：`platform.qrcode.read`。成功状态：`200 OK`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` | query | int | 否 | 1 | 1–10000 | 页码 |
| `page_size` | query | int | 否 | 20 | 1–100 | 每页条数 |
| `keyword` | query | string | 否 | 无 | ≤64 | 名称 / 指向地址模糊匹配 |
| `scene` | query | string | 否 | 无 | ≤32 | 场景 `h5` / `follow` |
| `status` | query | int | 否 | 无 | 0 / 1 | 1 有效 / 0 已失效 |
| `created_start` | query | string | 否 | 无 | `YYYY-MM-DD` | 创建时间起（含） |
| `created_end` | query | string | 否 | 无 | `YYYY-MM-DD` | 创建时间止（含） |

返回字段：

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 二维码 ID |
| `name` | string | 是 | — | 名称 |
| `scene` | string | 是 | — | `h5` 落地页 / `follow` 关注公众号 |
| `type` | string | 是 | — | `h5` / `miniprogram` |
| `target_url` | string | 是 | — | 指向地址（小程序为 path） |
| `description` | string/null | 是 | 未填写 | 用途描述 |
| `expire_at` | datetime | 是 | — | 失效时间 |
| `status` | int | 是 | — | 1 有效 / 0 已失效 |
| `image_url` | string | 是 | — | 图片现签地址 |
| `renew_count` | int | 是 | — | 累计续期次数 |
| `last_renewed_at` | datetime/null | 是 | 从未续期 | 最近续期时间 |
| `created_by` | int/null | 是 | — | 创建管理员 |
| `created_at` / `updated_at` | datetime/null | 是 | — | 时间戳 |

请求示例：

```http
GET /api/v1/admin/qrcodes?page=1&page_size=20&status=1&scene=h5
Authorization: Bearer <access_token>
```

返回示例：

```json
{"items": [{"id": 3, "name": "双十一落地页", "scene": "h5", "type": "h5",
            "target_url": "https://www.xuanshi.com/subpages/mutual/index?id=9",
            "description": "会场入口", "expire_at": "2026-11-20T00:00:00", "status": 1,
            "image_url": "/storage/uploads/admin/qrcodes/ab12.png?expires=1768&kind=admin&user=3&revision=0&signature=9f",
            "renew_count": 0, "last_renewed_at": null, "created_by": 3,
            "created_at": "2026-10-20T10:00:00", "updated_at": "2026-10-20T10:00:00"}],
 "page": 1, "page_size": 20, "total": 1, "has_more": false}
```

空数据：`{"items": [], "page": 1, "page_size": 20, "total": 0, "has_more": false}`

错误：401 / 403 / 422（参数非法）。

---

## 3. `POST /api/v1/admin/qrcodes`

- 用途：生成二维码并登记有效期。
- 权限：`platform.qrcode.write`。成功状态：`201 Created`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `name` | body | string | 是 | — | 1–128 | 名称 |
| `scene` | body | string | 否 | `h5` | `h5` / `follow` | 场景 |
| `type` | body | string | 否 | `h5` | `h5` / `miniprogram` | 载体 |
| `target_url` | body | string | 是 | — | 1–500 | 指向地址 |
| `description` | body | string/null | 否 | null | ≤500 | 描述 |
| `expire_days` | body | int | 否 | 30 | 1–3650 | 有效期天数（折算 `expire_at = now + days`） |

```http
POST /api/v1/admin/qrcodes
Content-Type: application/json

{"name": "双十一落地页", "scene": "h5", "type": "h5",
 "target_url": "https://www.xuanshi.com/subpages/mutual/index?id=9",
 "description": "会场入口", "expire_days": 30}
```

非法示例：`{"name": "x", "scene": "unknown", "target_url": "https://a.com"}` → `422`；
`type=miniprogram` 且公众号凭据未配置 → `503 公众号凭据未配置`。

返回：`QrcodeItem`（同第 2 节行结构，`image_url` 现签）。

业务规则：

- 顺序：先出图（h5/follow 本地渲染，miniprogram 调公众号适配器，不可用时在此 503）→ 落盘 → 登记行 → 审计。
- `expire_days` 折算后的时间以服务端时钟为准。

---

## 4. `POST /api/v1/admin/qrcodes/{qrcode_id}/renew`

- 用途：续期。
- 权限：`platform.qrcode.write`。成功状态：`200 OK`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `qrcode_id` | path | int | 是 | — | ≥1 | 二维码 ID |
| `days` | body | int | 是 | — | 1–365 | 续期天数 |

续期公式：`expire_at = GREATEST(expire_at, NOW()) + INTERVAL days DAY`，同时把 `status` 翻回 `1`，
`renew_count + 1`，写 `last_renewed_at`。

```http
POST /api/v1/admin/qrcodes/3/renew
Content-Type: application/json

{"days": 90}
```

非法示例：`{"days": 0}` → `422`。

返回：`QrcodeItem`。

业务规则：已过期的二维码可续期复活；`PATCH` 改 `target_url` 会沿用**既有行的 `type`** 重新出图（小程序码不会降级成普通二维码）。

---

## 5. `PATCH /api/v1/admin/qrcodes/{qrcode_id}`

- 权限：`platform.qrcode.write`。成功状态：`200 OK`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `qrcode_id` | path | int | 是 | — | ≥1 | 二维码 ID |
| `name` | body | string | 否 | — | 1–128 | 新名称 |
| `target_url` | body | string | 否 | — | 1–500 | 新指向地址 |
| `description` | body | string/null | 否 | — | ≤500 | 新描述 |

```http
PATCH /api/v1/admin/qrcodes/3
Content-Type: application/json

{"target_url": "https://www.xuanshi.com/subpages/mutual/index?id=10"}
```

非法示例：`{}` → `422 至少提供一个需要修改的字段`。

业务规则：

- 改动 `target_url` 时后端**重新渲染并落盘新图**，`image_url` 指向新文件（旧图内容已失效）。
- 未改动 `target_url` 时沿用原图，仅更新名称/描述。

返回：`QrcodeItem`。

---

## 6. `DELETE /api/v1/admin/qrcodes/{qrcode_id}`

- 权限：`platform.qrcode.write`。成功状态：`204 No Content`（无返回体）。
- 物理删除注册行；磁盘图片保留（历史扫码记录不受影响）。

---

## 7. 错误码汇总

| 状态码 | 触发条件 | 前端处理 |
| --- | --- | --- |
| 401 | 未登录 | 跳转登录 |
| 403 | 缺 `platform.qrcode.*` | 隐藏入口 |
| 404 | 二维码不存在 | 刷新列表 |
| 422 | 枚举/天数/空更新非法 | 修正表单 |
| 503 | 小程序码需要公众号凭据未配置 | 配置 `WECHAT_MP_*` 或改用 h5 类型 |

## 8. 变更记录

| 日期 | 变更 |
| --- | --- |
| 2026-10-20 | 新增二维码列表 / 生成 / 续期 / 更新 / 删除接口（A5） |

## 9. 文档完成自检清单

- [x] 请求参数表含位置/类型/必填/默认值/校验/含义
- [x] 请求示例与非法示例
- [x] 返回参数表与空数据示例
- [x] 业务规则覆盖顺序、续期公式、旧图失效
- [x] 错误码表完整
