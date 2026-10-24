# 销售话术库（A7）管理后台接口

## 1. 通用约定

接口前缀：`/api/v1`。需携带 `Authorization: Bearer <access_token>`。

| 接口类别 | 权限码 |
| --- | --- |
| 读（`GET`） | `platform.sales.read`（`platform.sales.write` 亦可） |
| 写（`POST` / `PATCH` / `DELETE`） | `platform.sales.write` |

- 分类与条目为**平台级全局配置**，不随管理员数据范围收敛（仅受权限码约束）。
- 下发目标必须是**有效服务红娘**：`users.status=1` 且持有 `user_role.role_code='service_matchmaker'`（`status=1`）。
- 审计：`sales_category.create/update/delete`、`sales_item.create/update/delete/push`。
- 分页壳：`{ items, page, page_size, total, has_more }`。

---

## 2. 话术分类

### 2.1 `GET /api/v1/admin/sales-library/categories`

- 权限：`platform.sales.read`。成功状态：`200 OK`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` | query | int | 否 | 1 | 1–10000 | 页码 |
| `page_size` | query | int | 否 | 100 | 1–200 | 每页条数 |
| `keyword` | query | string | 否 | 无 | ≤64 | 分类名模糊匹配 |

返回字段：

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 分类 ID |
| `name` | string | 是 | — | 分类名 |
| `sort` | int | 是 | — | 排序 |
| `enabled` | bool | 是 | — | 是否启用 |
| `item_count` | int | 是 | — | 分类下有效条目数（软删除不计） |
| `created_at` | datetime/null | 是 | — | 创建时间 |

```http
GET /api/v1/admin/sales-library/categories?page=1&page_size=100
Authorization: Bearer <access_token>
```

```json
{"items": [{"id": 1, "name": "开场话术", "sort": 0, "enabled": true, "item_count": 6,
            "created_at": "2026-10-20T10:00:00"}],
 "page": 1, "page_size": 100, "total": 1, "has_more": false}
```

空数据：`{"items": [], "page": 1, "page_size": 100, "total": 0, "has_more": false}`

### 2.2 `POST /api/v1/admin/sales-library/categories`

- 权限：`platform.sales.write`。成功状态：`201 Created`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `name` | body | string | 是 | — | 1–64 | 分类名（同租户内唯一） |
| `sort` | body | int | 否 | 0 | 0–100000 | 排序 |
| `enabled` | body | bool | 否 | true | — | 是否启用 |

```http
POST /api/v1/admin/sales-library/categories
Content-Type: application/json

{"name": "开场话术", "sort": 0, "enabled": true}
```

非法示例：`{"name": ""}` → `422`。

### 2.3 `PATCH /api/v1/admin/sales-library/categories/{category_id}`

- 权限：`platform.sales.write`。成功状态：`200 OK`。
- 全部可选，至少一个（否则 422）。

### 2.4 `DELETE /api/v1/admin/sales-library/categories/{category_id}`

- 权限：`platform.sales.write`。成功状态：`204 No Content`（无返回体）。
- 分类下仍有有效条目 → `409 分类下还有话术条目，不能删除`。

---

## 3. 话术条目

### 3.1 `GET /api/v1/admin/sales-library/items`

- 权限：`platform.sales.read`。成功状态：`200 OK`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` | query | int | 否 | 1 | 1–10000 | 页码 |
| `page_size` | query | int | 否 | 20 | 1–100 | 每页条数 |
| `keyword` | query | string | 否 | 无 | ≤64 | 标题/正文模糊匹配 |
| `category_id` | query | int | 否 | 无 | ≥1 | 按分类筛选 |
| `status` | query | int | 否 | 无 | 0 / 1 | 1 上架 / 0 下架 |

返回字段：

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 条目 ID |
| `category_id` / `category_name` | int / string/null | 是 | 分类已删 | 所属分类 |
| `title` | string | 是 | — | 话术标题 |
| `content` | string | 是 | — | 话术正文 |
| `media_url` | string/null | 是 | 无配套素材 | 素材相对路径（未现签，后台资源需前端按后台媒体规则取用） |
| `pick_limit` | int | 是 | — | 每日可取用次数上限，0 不限制 |
| `status` | int | 是 | — | 1 上架 / 0 下架 |
| `sort` | int | 是 | — | 排序 |
| `created_by` | int/null | 是 | — | 创建人 |
| `created_at` / `updated_at` | datetime/null | 是 | — | 时间戳 |

```http
GET /api/v1/admin/sales-library/items?page=1&page_size=20&category_id=1&status=1
Authorization: Bearer <access_token>
```

```json
{"items": [{"id": 5, "category_id": 1, "category_name": "开场话术", "title": "首次破冰",
            "content": "您好，我是宣智爱红娘…", "media_url": null, "pick_limit": 3,
            "status": 1, "sort": 0, "created_by": 3,
            "created_at": "2026-10-20T10:00:00", "updated_at": "2026-10-20T10:00:00"}],
 "page": 1, "page_size": 20, "total": 1, "has_more": false}
```

空数据：`{"items": [], "page": 1, "page_size": 20, "total": 0, "has_more": false}`

### 3.2 `POST /api/v1/admin/sales-library/items`

- 权限：`platform.sales.write`。成功状态：`201 Created`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `category_id` | body | int | 是 | — | ≥1，分类必须存在 | 所属分类 |
| `title` | body | string | 是 | — | 1–128 | 标题 |
| `content` | body | string | 是 | — | 1–20000 | 正文 |
| `media_url` | body | string/null | 否 | null | ≤500 | 配套素材相对路径 |
| `pick_limit` | body | int | 否 | 0 | 0–10000 | 每日取用上限，0 不限制 |
| `sort` | body | int | 否 | 0 | 0–100000 | 排序 |

```http
POST /api/v1/admin/sales-library/items
Content-Type: application/json

{"category_id": 1, "title": "首次破冰", "content": "您好，我是宣智爱红娘…", "pick_limit": 3}
```

非法示例：`{"category_id": 0, "title": "x", "content": "y"}` → `422`；分类不存在 → `422 话术分类不存在`。

### 3.3 `PATCH /api/v1/admin/sales-library/items/{item_id}`

- 权限：`platform.sales.write`。成功状态：`200 OK`。
- 全部可选，至少一个（否则 422）；`status` 只接受 0/1；改分类时目标分类必须存在（否则 422）。

### 3.4 `DELETE /api/v1/admin/sales-library/items/{item_id}`

- 权限：`platform.sales.write`。成功状态：`204 No Content`（无返回体）。
- 软删除（写 `deleted_at`）。

---

## 4. 下发给红娘

### 4.1 `POST /api/v1/admin/sales-library/items/{item_id}/push`

- 权限：`platform.sales.write`。成功状态：`200 OK`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `item_id` | path | int | 是 | — | ≥1 | 话术条目 ID |
| `matchmaker_ids` | body | int[] | 是 | — | 1–200 个，去重 | 下发目标（`users.id`） |
| `note` | body | string/null | 否 | null | ≤500 | 下发备注 |

```http
POST /api/v1/admin/sales-library/items/5/push
Content-Type: application/json

{"matchmaker_ids": [88, 89, 999999], "note": "双十一活动话术"}
```

非法示例：`{"matchmaker_ids": []}` → `422`。

返回字段：

| 字段 | 类型 | 必返 | 含义 |
| --- | --- | --- | --- |
| `item_id` | int | 是 | 话术条目 ID |
| `pushed` | int[] | 是 | 成功下发的红娘 ID |
| `skipped` | object[] | 是 | 跳过的目标：`{matchmaker_id, reason}` |

返回示例：

```json
{"item_id": 5, "pushed": [88, 89],
 "skipped": [{"matchmaker_id": 999999, "reason": "非有效服务红娘"}]}
```

业务规则：

- 逐个校验目标，非服务红娘跳过并在 `skipped` 说明原因，**不阻断**其余目标。
- 每个成功目标写一行 `admin_sales_push`；整批写一条审计 `sales_item.push`（reason 记录成功/总数）。
- 同一批重复调用会重复下发（如需幂等请由前端按 `Idempotency-Key` 去重）。

### 4.2 `GET /api/v1/admin/sales-library/items/push-records`

- 权限：`platform.sales.read`。成功状态：`200 OK`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` | query | int | 否 | 1 | 1–10000 | 页码 |
| `page_size` | query | int | 否 | 20 | 1–100 | 每页条数 |
| `item_id` | query | int | 否 | 无 | ≥1 | 按话术条目筛选 |

返回字段：

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 下发记录 ID |
| `item_id` / `item_title` | int / string/null | 是 | 条目已删 | 话术条目 |
| `matchmaker_id` | int | 是 | — | 目标红娘 `users.id` |
| `matchmaker_name` | string/null | 是 | 用户已删 | 红娘昵称 |
| `note` | string/null | 是 | 未填 | 下发备注 |
| `pushed_by` | int | 是 | — | 操作人 |
| `created_at` | datetime/null | 是 | — | 下发时间 |

```json
{"items": [{"id": 31, "item_id": 5, "item_title": "首次破冰", "matchmaker_id": 88,
            "matchmaker_name": "王红娘", "note": "双十一活动话术", "pushed_by": 3,
            "created_at": "2026-10-20T12:00:00"}],
 "page": 1, "page_size": 20, "total": 1, "has_more": false}
```

---

## 5. 错误码汇总

| 状态码 | 触发条件 | 前端处理 |
| --- | --- | --- |
| 401 | 未登录 | 跳转登录 |
| 403 | 缺 `platform.sales.*` | 隐藏入口 |
| 404 | 分类/条目不存在 | 刷新列表 |
| 409 | 分类下仍有条目 | 先清空再删 |
| 422 | 参数校验失败 / 分类不存在 / 下发目标为空 | 修正表单 |

## 6. 变更记录

| 日期 | 变更 |
| --- | --- |
| 2026-10-20 | 新增销售话术库分类 / 条目 CRUD 与下发、下发记录接口（A7） |

## 7. 文档完成自检清单

- [x] 请求参数表完整
- [x] 请求示例与非法示例
- [x] 返回参数表含空值含义与分页字段
- [x] 业务规则覆盖下发校验与跳过语义
- [x] 错误码表完整
