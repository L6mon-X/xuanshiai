# 互动内容与联盟活动（A10）管理后台接口

## 1. 通用约定

接口前缀：`/api/v1`。需携带 `Authorization: Bearer <access_token>`。

| 接口类别 | 权限码 |
| --- | --- |
| 互动内容 读 | `platform.interact.read` |
| 互动内容 写 | `platform.interact.write` |
| 联盟活动 读 | `platform.alliance.read` |
| 联盟活动 写 | `platform.alliance.write` |

**互动内容（`/admin/interact/contents`）不新建表**：它复用 `admin_content_item`
的 `interactive_message` 域（与通用内容接口同一存储）。本组接口只固定域与权限码，
避免前端直接依赖通用接口的域字符串。域特有字段放在 `extra` 中。

**联盟活动（`/admin/alliance/activities`）** 使用独立表 `admin_alliance_activity`。

分页壳：`{ items, page, page_size, total, has_more }`。

> 其余装修/插件/主题页面（xixun-menu、plugin-center、tool-theme、operate-center）
> 走通用配置接口 `GET|PATCH /admin/configs/{namespace}`，本模块不重复提供接口。

---

## 2. 互动内容

### 2.1 `GET /api/v1/admin/interact/contents`

- 权限：`platform.interact.read`。成功状态：`200 OK`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` | query | int | 否 | 1 | 1–10000 | 页码 |
| `page_size` | query | int | 否 | 20 | 1–100 | 每页条数 |
| `keyword` | query | string | 否 | 无 | ≤64 | 标题/副标题/扩展字段模糊匹配 |
| `status` | query | int | 否 | 无 | 1 / 2 | 1 正常 / 2 停用 |

返回字段（`ContentItemPage`，注意：该页模型沿用通用内容的 `items: list[dict]` 结构）：

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `items[].id` | int | 是 | — | 内容项 ID |
| `items[].domain` | string | 是 | — | 固定 `interactive_message` |
| `items[].title` | string | 是 | 可能为空串 | 标题 |
| `items[].subtitle` | string/null | 是 | 未填 | 副标题 |
| `items[].image_url` | string/null | 是 | 未配图 | 图片地址 |
| `items[].amount` | number/null | 是 | 不涉及金额 | 金额（互动内容通常为空） |
| `items[].status` | int | 是 | — | 1 正常 / 2 停用 |
| `items[].sort` | int | 是 | — | 排序 |
| `items[].extra` | object | 是 | `{}` | 域特有字段（类型、素材、正文等） |
| `items[].created_at` / `updated_at` | string/null | 是 | — | ISO 时间 |
| `total` / `page` / `page_size` | int | 是 | — | 分页字段 |

> 该页模型未包含 `has_more`（沿用既有 `ContentItemPage` 契约），前端按
> `page * page_size < total` 自行判断。

```http
GET /api/v1/admin/interact/contents?page=1&page_size=20&status=1
Authorization: Bearer <access_token>
```

```json
{"total": 1, "page": 1, "page_size": 20,
 "items": [{"id": 7, "domain": "interactive_message", "title": "一起来脱单",
            "subtitle": null, "image_url": "/storage/uploads/admin/a.webp", "amount": null,
            "status": 1, "sort": 0,
            "extra": {"type": "vote", "content": "你更喜欢哪种相亲方式？"},
            "created_at": "2026-10-20T10:00:00", "updated_at": "2026-10-20T10:00:00"}]}
```

空数据：`{"total": 0, "page": 1, "page_size": 20, "items": []}`

### 2.2 `POST /api/v1/admin/interact/contents`

- 权限：`platform.interact.write`。成功状态：`201 Created`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `title` | body | string | 否 | `""` | ≤255 | 标题 |
| `subtitle` | body | string/null | 否 | null | ≤500 | 副标题 |
| `image_url` | body | string/null | 否 | null | ≤500 | 图片 |
| `amount` | body | number/null | 否 | null | — | 金额（互动内容通常不填） |
| `status` | body | int | 否 | 1 | 1 / 2 | 1 正常 / 2 停用 |
| `sort` | body | int | 否 | 0 | — | 排序 |
| `extra` | body | object | 否 | `{}` | 自由字典 | 域特有字段 |

```http
POST /api/v1/admin/interact/contents
Content-Type: application/json

{"title": "一起来脱单", "status": 1, "sort": 0,
 "extra": {"type": "vote", "content": "你更喜欢哪种相亲方式？"}}
```

非法示例：`{"status": 9}` → `422 status 仅支持 1 正常 / 2 停用`。

返回：`ContentItem`（单行，同 2.1 的 `items[]` 结构）。

### 2.3 `PATCH /api/v1/admin/interact/contents/{item_id}`

- 权限：`platform.interact.write`。成功状态：`200 OK`。
- 全部字段可选；`extra` 采用**合并**语义（只覆盖传入的键，不清空其他键）。
- `status` 只接受 1/2。

```http
PATCH /api/v1/admin/interact/contents/7
Content-Type: application/json

{"status": 2, "extra": {"content": "活动结束"}}
```

### 2.4 `DELETE /api/v1/admin/interact/contents/{item_id}`

- 权限：`platform.interact.write`。成功状态：`204 No Content`（无返回体）。
- 物理删除该域内的一条内容项。

---

## 3. 联盟活动

### 3.1 `GET /api/v1/admin/alliance/activities`

- 权限：`platform.alliance.read`。成功状态：`200 OK`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` | query | int | 否 | 1 | 1–10000 | 页码 |
| `page_size` | query | int | 否 | 20 | 1–100 | 每页条数 |
| `keyword` | query | string | 否 | 无 | ≤128 | 标题/地址模糊匹配 |
| `status` | query | int | 否 | 无 | 1–4 | 1报名中 2已结束 3已取消 4草稿 |

返回字段：

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 活动 ID |
| `title` | string | 是 | — | 标题 |
| `cover` | string/null | 是 | 未配图 | 封面相对路径 |
| `store_id` / `store_name` | int/null / string/null | 是 | 未绑定门店 | 主办门店 |
| `start_time` / `end_time` | datetime | 是 | — | 活动时间 |
| `address` | string/null | 是 | 未填 | 地址 |
| `fee` | number | 是 | — | 费用，0 免费 |
| `capacity` | int | 是 | — | 人数上限，0 不限制 |
| `intro` | string/null | 是 | 未填 | 介绍 |
| `status` | int | 是 | — | 1报名中 2已结束 3已取消 4草稿 |
| `sort` | int | 是 | — | 排序 |
| `created_by` | int/null | 是 | — | 创建人 |
| `created_at` / `updated_at` | datetime/null | 是 | — | 时间戳 |

```http
GET /api/v1/admin/alliance/activities?page=1&page_size=20&status=1
Authorization: Bearer <access_token>
```

```json
{"items": [{"id": 4, "title": "联盟双十一", "cover": null, "store_id": 10,
            "store_name": "南京旗舰店", "start_time": "2026-11-11T10:00:00",
            "end_time": "2026-11-11T18:00:00", "address": "南京市玄武区…",
            "fee": 0, "capacity": 100, "intro": null, "status": 1, "sort": 0,
            "created_by": 3, "created_at": "2026-10-20T10:00:00",
            "updated_at": "2026-10-20T10:00:00"}],
 "page": 1, "page_size": 20, "total": 1, "has_more": false}
```

空数据：`{"items": [], "page": 1, "page_size": 20, "total": 0, "has_more": false}`

### 3.2 `POST /api/v1/admin/alliance/activities`

- 权限：`platform.alliance.write`。成功状态：`201 Created`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `title` | body | string | 是 | — | 1–128 | 标题 |
| `cover` | body | string/null | 否 | null | ≤500 | 封面 |
| `store_id` | body | int/null | 否 | null | ≥1，必须为启用的门店 | 主办门店 |
| `start_time` | body | datetime | 是 | — | — | 开始时间 |
| `end_time` | body | datetime | 是 | — | 晚于开始时间 | 结束时间 |
| `address` | body | string/null | 否 | null | ≤255 | 地址 |
| `fee` | body | number | 否 | 0 | 0–1000000 | 费用 |
| `capacity` | body | int | 否 | 0 | 0–1000000 | 人数上限，0 不限制 |
| `intro` | body | string/null | 否 | null | ≤20000 | 介绍 |
| `status` | body | int | 否 | 1 | 1–4 | 状态 |
| `sort` | body | int | 否 | 0 | — | 排序 |

```http
POST /api/v1/admin/alliance/activities
Content-Type: application/json

{"title": "联盟双十一", "store_id": 10, "start_time": "2026-11-11T10:00:00",
 "end_time": "2026-11-11T18:00:00", "address": "南京市玄武区…", "fee": 0,
 "capacity": 100, "status": 1}
```

非法示例：`{"title": "x", "start_time": "2026-11-11T18:00:00", "end_time": "2026-11-11T10:00:00"}` → `422 end_time 必须晚于 start_time`；
`store_id=999999` → `422 主办门店不存在或已停用`。

### 3.3 `PATCH /api/v1/admin/alliance/activities/{activity_id}`

- 权限：`platform.alliance.write`。成功状态：`200 OK`。
- 全部字段可选，至少一个（否则 422）；改 `store_id` 时重新校验门店。

### 3.4 `DELETE /api/v1/admin/alliance/activities/{activity_id}`

- 权限：`platform.alliance.write`。成功状态：`204 No Content`（无返回体）。
- 物理删除活动记录。

---

## 4. 错误码汇总

| 状态码 | 触发条件 | 前端处理 |
| --- | --- | --- |
| 401 | 未登录 | 跳转登录 |
| 403 | 缺对应权限码 | 隐藏入口 |
| 404 | 内容项/活动不存在 | 刷新列表 |
| 422 | 参数、状态枚举、时间顺序、门店非法 | 修正表单 |

## 5. 变更记录

| 日期 | 变更 |
| --- | --- |
| 2026-10-20 | 新增互动内容（复用 `interactive_message` 域）与联盟活动 CRUD 接口（A10） |

## 6. 文档完成自检清单

- [x] 请求参数表完整
- [x] 请求示例与非法示例
- [x] 返回参数表含空值含义
- [x] 明确互动内容页面模型的 `items: list[dict]` 与缺少 `has_more` 的既有契约
- [x] 业务规则说明复用域与合并语义
- [x] 错误码表完整
