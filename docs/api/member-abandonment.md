# 会员弃海（A9 / B3）管理后台接口

## 1. 通用约定

接口前缀：`/api/v1`。需要登录的接口必须携带：

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

**权限**（依赖注入按路径 `/admin/members` 自动映射，无需逐个接口声明）：

| 接口类别 | 权限码 |
| --- | --- |
| 读（`GET`） | `matchmaker.member.read`（`matchmaker.member.manage` 亦可） |
| 写（`POST` / `PATCH` / `DELETE`） | `matchmaker.member.manage` |

**数据范围（D-16）**：弃海记录本身不带归属列，归属以会员在 `resource_assignment`
中生效记录的 `matchmaker_id` / `organization_id` 判定。四档语义（`ALL` / `SELF` /
`STORE` / `ORGANIZATION`）由 `CurrentMatchmakerAdmin.scope_exists_clause` 统一实现；
越权读取一律按 `404 会员不存在` 返回，不泄露存在性。

**弃海口径**：`member_abandonment` 表中 `restored_at IS NULL` 的有效记录即「在弃海池」。
历史口径（来源客源 `customer_lead.status='LOST'`）由迁移 `20261020_01` 回填为
`abandon_type='lead_sync'`，因此列表与计数连续。

**审计**：写接口写入 `business_audit_log`，`action` 为 `member.abandon` / `member.restore`，
`resource_type='users'`，`resource_id` 为会员 ID。

**分页壳**：`{ items, page, page_size, total, has_more }`，`has_more = page * page_size < total`。

---

## 2. 弃海会员列表

### 2.1 `GET /api/v1/admin/members/abandoned`

#### 基本信息

- 用途：分页查询当前仍在弃海池的会员，返回结构与会员 CRM 列表一致，并追加弃海维度字段。
- 权限：`matchmaker.member.read`。
- 成功状态：`200 OK`。

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` | query | int | 否 | 1 | 1–1000 | 页码 |
| `page_size` | query | int | 否 | 20 | 1–100 | 每页条数 |
| `search` | query | string | 否 | 无 | ≤64 | 昵称 / 手机号模糊匹配 |
| `matchmaker_id` | query | int | 否 | 无 | ≥1 | 按当前归属服务红娘筛选 |
| `organization_id` | query | int | 否 | 无 | ≥1 | 按当前归属门店筛选 |
| `abandon_type` | query | string | 否 | 无 | `manual` / `lead_sync` / `auto` | 弃海来源 |
| `start_date` | query | string | 否 | 无 | `YYYY-MM-DD` | 弃海时间起（含当日） |
| `end_date` | query | string | 否 | 无 | `YYYY-MM-DD` | 弃海时间止（含当日） |

#### 请求示例

```http
GET /api/v1/admin/members/abandoned?page=1&page_size=20&abandon_type=manual
Authorization: Bearer <access_token>
```

非法示例（`abandon_type` 不在枚举内，返回 422）：

```http
GET /api/v1/admin/members/abandoned?abandon_type=lost
```

#### 返回参数

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `items` | array | 是 | `[]` 表示无数据 | 弃海会员行 |
| `items[].id` | int | 是 | — | 会员 `users.id` |
| `items[].nickname` | string/null | 是 | 未设置昵称 | 昵称 |
| `items[].phone` | string/null | 是 | 未登记手机号 | 手机号 |
| `items[].gender` | int/null | 是 | 未知 | 1男 2女 |
| `items[].status` | int | 是 | — | 账号状态 1正常 2禁用 3注销 |
| `items[].is_vip` | bool | 是 | — | 是否有效会员 |
| `items[].matchmaker_id` | int/null | 是 | 未分派 | 当前归属服务红娘 |
| `items[].abandoned_at` | datetime | 是 | — | 弃海时间 |
| `items[].abandoned_reason` | string | 是 | — | 弃海原因 |
| `items[].abandon_type` | string | 是 | — | `manual` / `lead_sync` / `auto` |
| `items[].abandoned_by` | int | 是 | — | 弃海操作人（`matchmaker_admin_account.id`）；`0` 表示迁移回填 |
| 其余字段 | — | 是 | — | 与 `GET /admin/matchmaker/members` 的 `MemberListItem` 完全一致（身高、收入、学历、星座等） |
| `page` | int | 是 | — | 当前页码 |
| `page_size` | int | 是 | — | 每页条数 |
| `total` | int | 是 | — | 总条数 |
| `has_more` | bool | 是 | — | 是否还有下一页 |

#### 返回示例

```json
{
  "items": [
    {
      "id": 1024,
      "nickname": "小满",
      "phone": "13800000000",
      "gender": 2,
      "status": 1,
      "is_vip": true,
      "matchmaker_id": 88,
      "abandoned_at": "2026-10-18T09:30:00",
      "abandoned_reason": "三个月未回复消息",
      "abandon_type": "manual",
      "abandoned_by": 3
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1,
  "has_more": false
}
```

空数据示例：`{"items": [], "page": 1, "page_size": 20, "total": 0, "has_more": false}`

#### 使用方法与业务规则

- 前置条件：后台管理员登录且具备 `matchmaker.member.read`。
- 排序：固定 `abandoned_at DESC, id DESC`。
- 只返回仍在池中的记录（`restored_at IS NULL`）；已捞回的历史记录请用 `/abandonments`。
- 列表行不做联系方式掩码（与会员 CRM 列表口径一致，展示层按权限控制）。

#### 错误

| 状态码 | 触发条件 | 前端处理 |
| --- | --- | --- |
| 401 | 未登录 / 登录态失效 | 跳转登录 |
| 403 | 缺少 `matchmaker.member.read` | 隐藏入口或提示无权限 |
| 422 | 参数类型/枚举/日期格式不合法 | 修正参数 |
| 500 | 数据库异常 | 提示稍后重试 |

---

## 3. 弃海记录（含已捞回）

### 3.1 `GET /api/v1/admin/members/abandonments`

#### 基本信息

- 用途：分页查询弃海与捞回审计记录（不退池的历史也保留）。
- 权限：`matchmaker.member.read`。
- 成功状态：`200 OK`。

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` | query | int | 否 | 1 | 1–1000 | 页码 |
| `page_size` | query | int | 否 | 20 | 1–100 | 每页条数 |
| `active_only` | query | bool | 否 | false | true/false | 仅看仍在弃海池的记录 |
| `abandon_type` | query | string | 否 | 无 | `manual` / `lead_sync` / `auto` | 弃海来源 |
| `search` | query | string | 否 | 无 | ≤64 | 昵称 / 手机号模糊匹配 |

#### 请求示例

```http
GET /api/v1/admin/members/abandonments?page=1&page_size=20&active_only=false
Authorization: Bearer <access_token>
```

#### 返回参数

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `items[].id` | int | 是 | — | 记录 ID |
| `items[].user_id` | int | 是 | — | 会员 `users.id` |
| `items[].nickname` | string/null | 是 | 未设置 | 会员昵称 |
| `items[].reason` | string | 是 | — | 弃海原因 |
| `items[].abandon_type` | string | 是 | — | `manual` / `lead_sync` / `auto` |
| `items[].abandoned_by` | int | 是 | — | 弃海操作人；`0` 表示迁移回填 |
| `items[].abandoned_at` | datetime | 是 | — | 弃海时间 |
| `items[].restored_by` | int/null | 是 | 未捞回 | 捞回操作人 |
| `items[].restored_at` | datetime/null | 是 | 未捞回 | 捞回时间 |
| `items[].restore_reason` | string/null | 是 | 未填 | 捞回备注 |
| `items[].assigned_matchmaker_id` | int/null | 是 | 捞回未分派 | 捞回时分派的服务红娘 |
| `page` / `page_size` / `total` / `has_more` | — | 是 | — | 分页字段 |

#### 返回示例

```json
{
  "items": [
    {
      "id": 7,
      "user_id": 1024,
      "nickname": "小满",
      "reason": "三个月未回复消息",
      "abandon_type": "manual",
      "abandoned_by": 3,
      "abandoned_at": "2026-10-18T09:30:00",
      "restored_by": 3,
      "restored_at": "2026-10-19T10:00:00",
      "restore_reason": "客户回心转意",
      "assigned_matchmaker_id": 88
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1,
  "has_more": false
}
```

#### 使用方法与业务规则

- 排序：`ab.id DESC`。
- `active_only=true` 等价于只看 `/abandoned` 的记录集合，但返回结构为审计行（含捞回字段）。

#### 错误

同 2.1。

---

## 4. 放入弃海池

### 4.1 `POST /api/v1/admin/members/{member_id}/abandon`

#### 基本信息

- 用途：把会员放入弃海池。
- 权限：`matchmaker.member.manage`。
- Content-Type：`application/json`。
- 成功状态：`201 Created`。

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `member_id` | path | int | 是 | — | ≥1 | 会员 `users.id` |
| `reason` | body | string | 是 | — | 1–500 字 | 弃海原因 |
| `abandon_type` | body | string | 否 | `manual` | `manual` / `lead_sync` / `auto` | 弃海来源 |

#### 请求示例

```http
POST /api/v1/admin/members/1024/abandon
Authorization: Bearer <access_token>
Content-Type: application/json

{ "reason": "三个月未回复消息", "abandon_type": "manual" }
```

非法示例（原因为空，返回 422）：

```json
{ "reason": "" }
```

#### 返回参数

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 弃海记录 ID |
| `user_id` | int | 是 | — | 会员 ID |
| `nickname` | string/null | 是 | 未设置 | 会员昵称 |
| `reason` | string | 是 | — | 弃海原因 |
| `abandon_type` | string | 是 | — | 弃海来源 |
| `abandoned_by` | int | 是 | — | 操作人 |
| `abandoned_at` | datetime | 是 | — | 弃海时间 |
| `restored_by` / `restored_at` / `restore_reason` / `assigned_matchmaker_id` | null | 是 | 新建记录恒为空 | 捞回字段 |

#### 返回示例

```json
{
  "id": 12,
  "user_id": 1024,
  "nickname": "小满",
  "reason": "三个月未回复消息",
  "abandon_type": "manual",
  "abandoned_by": 3,
  "abandoned_at": "2026-10-20T10:00:00",
  "restored_by": null,
  "restored_at": null,
  "restore_reason": null,
  "assigned_matchmaker_id": null
}
```

#### 使用方法与业务规则

- 前置条件：会员必须落在当前账号数据范围内（否则 404）。
- 幂等性：同一会员已存在有效弃海记录时返回 `409 该会员已在弃海池`；重复调用不会产生第二条有效记录。
- 该操作**不修改** `users` 表状态（与客源弃海置 `status='LOST'` 不同），只登记弃海记录。
- 审计：`action='member.abandon'`，`resource_type='users'`，`reason` 截断到 255 字。

#### 错误

| 状态码 | 触发条件 | 前端处理 |
| --- | --- | --- |
| 401 | 未登录 | 跳转登录 |
| 403 | 缺少 `matchmaker.member.manage` | 提示无权限 |
| 404 | 会员不存在或超出数据范围 | 刷新列表 |
| 409 | 该会员已在弃海池 | 提示已在池中 |
| 422 | 参数校验失败 | 修正表单 |

---

## 5. 捞取弃海会员

### 5.1 `POST /api/v1/admin/members/{member_id}/restore`

#### 基本信息

- 用途：把会员从弃海池捞回，可同时分派服务红娘。
- 权限：`matchmaker.member.manage`。
- 成功状态：`200 OK`。

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `member_id` | path | int | 是 | — | ≥1 | 会员 `users.id` |
| `reason` | body | string | 是 | — | 1–500 字 | 捞回备注 |
| `matchmaker_id` | body | int/null | 否 | null | ≥1，且必须是有效服务红娘 | 捞回后分派的服务红娘 `users.id` |

#### 请求示例

```http
POST /api/v1/admin/members/1024/restore
Authorization: Bearer <access_token>
Content-Type: application/json

{ "reason": "客户回心转意", "matchmaker_id": 88 }
```

非法示例（分派对象不是服务红娘，返回 422）：

```json
{ "reason": "捞回", "matchmaker_id": 999999 }
```

#### 返回参数

同 4.1 的弃海记录结构，其中 `restored_by` / `restored_at` / `restore_reason` /
`assigned_matchmaker_id` 被回填。

#### 返回示例

```json
{
  "id": 12,
  "user_id": 1024,
  "nickname": "小满",
  "reason": "三个月未回复消息",
  "abandon_type": "manual",
  "abandoned_by": 3,
  "abandoned_at": "2026-10-20T10:00:00",
  "restored_by": 3,
  "restored_at": "2026-10-20T11:00:00",
  "restore_reason": "客户回心转意",
  "assigned_matchmaker_id": 88
}
```

#### 使用方法与业务规则

- 前置条件：会员有有效的弃海记录（`restored_at IS NULL`），否则 `409 该会员不在弃海池`。
- 分派校验：`matchmaker_id` 必须是 `user_role.role_code='service_matchmaker'` 且 `status=1` 的启用用户。
- 分派写入 `resource_assignment`（`source='abandon_restore'`, `status=1`），与客源入库的归属写入口径一致。
- 审计：`action='member.restore'`。

#### 错误

| 状态码 | 触发条件 | 前端处理 |
| --- | --- | --- |
| 401 / 403 | 未登录 / 缺权限 | 同上 |
| 404 | 会员不存在或超出数据范围 | 刷新列表 |
| 409 | 该会员不在弃海池 | 刷新列表 |
| 422 | 原因非法或分派对象不是服务红娘 | 修正表单 |

---

## 6. 批量弃海

### 6.1 `POST /api/v1/admin/members/batch-abandon`（A18，2026-10-24）

#### 基本信息

- 用途：批量把会员放入弃海池，与 `batch-status` 同构，包成一次事务 + 一份汇总审计。
- 权限：`matchmaker.member.manage`；`Content-Type: application/json`；成功 `200 OK`。
- **敏感操作**：必须携带 `Idempotency-Key`（8–128）与 `confirm=true`；缺幂等键 `422`，缺二次确认 `428`；`operation` 为 `matchmaker.member.batch_abandon`。

#### 请求参数

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `member_ids` | body | int[] | 是 | — | 1–200 个正整数（去重） | 待弃海会员 `users.id` |
| `reason` | body | string | 是 | — | 1–500 字 | 弃海原因 |
| `abandon_type` | body | string | 否 | `manual` | `manual`/`lead_sync`/`auto` | 弃海来源 |
| `Idempotency-Key` | header | string | 是 | — | 8–128 | 幂等键 |
| `confirm` | query | bool | 是 | — | 必须 `true` | 二次确认 |

#### 请求示例

```http
POST /api/v1/admin/members/batch-abandon?confirm=true
Authorization: Bearer <access_token>
Idempotency-Key: 6f1c-abcdef-0123456789
Content-Type: application/json

{ "member_ids": [1, 2, 3], "reason": "批量清理失联会员", "abandon_type": "manual" }
```

非法示例（缺 `confirm=true` 返回 428；`member_ids=[]` 返回 422）。

#### 返回参数

| 字段 | 类型 | 必返 | 含义 |
| --- | --- | --- | --- |
| `succeeded` | int[] | 是 | 成功弃海的 member_id |
| `failed` | array | 是 | 逐条失败项 `{id, error}` |
| `failed[].id` | int | 是 | 失败会员 ID |
| `failed[].error` | string | 是 | `会员不存在`（越权/不存在）/ `该会员已在弃海池` |

#### 返回示例

```json
{ "succeeded": [1], "failed": [ { "id": 2, "error": "该会员已在弃海池" }, { "id": 3, "error": "会员不存在" } ] }
```

#### 使用方法与业务规则

- 越权/不存在/已在池的 id 归入 `failed`，不整体 4xx；全部失败仍返 200（部分成功语义）。
- 写操作前对作用域内目标行加 `FOR UPDATE` 锁，防并发重复写入有效记录。
- 一份汇总审计：`action='member.batch_abandon'`，`resource_type='users'`，`resource_id=NULL`，成员清单记入 `after_json`。
- 幂等：同 `Idempotency-Key` 重放直接返回上次结果，不重复弃海。

#### 错误

| 状态码 | 触发条件 | 前端处理 |
| --- | --- | --- |
| 401 / 403 | 未登录 / 缺 `matchmaker.member.manage` | 登录 / 提示无权限 |
| 422 | 缺 `Idempotency-Key`、body 参数非法 | 补齐头与参数 |
| 428 | 缺 `confirm=true` | 弹二次确认 |

---

## 7. 会员列表新增弃海筛选（B3）

### 7.1 `GET /api/v1/admin/matchmaker/members` 新增参数

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `abandoned` | query | bool | 否 | 无 | true/false | `true` 仅弃海会员；`false` 排除弃海会员；不传不限制 |

- 谓词：`EXISTS/NOT EXISTS (SELECT 1 FROM member_abandonment ma WHERE ma.user_id = u.id AND ma.restored_at IS NULL)`。
- 返回结构：`MemberListItem` 新增 `abandoned: bool`（默认 `false`），表示当前是否在弃海池。

### 7.2 `GET /api/v1/admin/matchmaker/members/statistics` 新增字段

| 字段 | 类型 | 必返 | 含义 |
| --- | --- | --- | --- |
| `abandoned` | int | 是 | 当前账号数据范围内、仍在弃海池的会员数（默认 `0`） |

> 统计口径已按 `scope_exists_clause` 收口，门店/组织账号不会看到全局弃海规模。

---

## 8. 变更记录

| 日期 | 变更 | 兼容性 |
| --- | --- | --- |
| 2026-10-24 | 新增批量弃海 `POST /admin/members/batch-abandon`（A18，幂等 + 二次确认 + 部分成功语义） | 新增接口，向后兼容 |
| 2026-10-20 | 新增 `/admin/members/abandoned`、`/abandonments`、`/{member_id}/abandon`、`/{member_id}/restore` | 新增接口，向后兼容 |
| 2026-10-20 | `GET /admin/matchmaker/members` 新增 `abandoned` 筛选参数；`MemberListItem` 新增 `abandoned` 字段 | 新增可选参数与字段，旧客户端不受影响 |
| 2026-10-20 | `GET /admin/matchmaker/members/statistics` 新增 `abandoned` 计数 | 新增字段，旧客户端忽略即可 |

---

## 9. 文档完成自检清单

- [x] 请求参数表：每个参数均写明位置、类型、必填、默认值、校验与业务含义
- [x] 请求体示例：给出完整 HTTP 示例；无请求体的接口已明确标注
- [x] 返回参数表：每个字段写明类型、必返、空值含义与业务含义
- [x] 成功返回示例：分页接口含 `items/page/page_size/total/has_more` 说明；给出空数据示例
- [x] 使用方法与业务规则：覆盖前置条件、幂等、状态流转与边界场景
- [x] 错误码表：HTTP 状态码、触发条件、前端处理
- [x] 至少一个非法参数示例
