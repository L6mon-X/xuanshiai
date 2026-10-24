# 短信管理（A1）管理后台接口

## 1. 通用约定

接口前缀：`/api/v1`。所有接口必须携带：

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

**权限**（每个接口用 `@declare_permission` 声明并在函数体二次 `require`）：

| 接口类别 | 权限码 |
| --- | --- |
| 读（`GET`） | `platform.sms.read`（`platform.sms.write` 亦可） |
| 写（`POST` / `PATCH` / `DELETE`） | `platform.sms.write` |

**供应商适配层**：签名 / 模板为纯本地配置，任何 provider 下都可用；`POST /admin/sms/send`
通过 `app/services/sms/providers.py::get_sms_template_provider()` 取值：

| `SMS_TEMPLATE_PROVIDER` | 行为 |
| --- | --- |
| `disabled`（默认） | 发送接口 `503 短信服务未配置`，**不写任何记录** |
| `mock` | 仅 development/testing；返回假流水号 `mock-<后4位>-<模板编码>` |
| 其他任意值 | `503 短信服务供应商未实现` |

**密钥位置**：`SMS_ACCESS_KEY` / `SMS_ACCESS_SECRET` 只能通过 `.env` 注入（见 `.env.example`），
接口不接受、不回显、不落库。

**分页壳**：`{ items, page, page_size, total, has_more }`，`has_more = page * page_size < total`。

**审计**：写入 `business_audit_log`，`action` 为 `sms_signature.create/update/delete`、
`sms_template.create/update/delete`、`sms.send`（`reason` 存批次号）。

**手机号脱敏**：`GET /admin/sms/records` 返回的 `phone` 一律经 `mask_phone()` 处理，
形如 `138****1234`；`keyword` 按号码片段匹配，接口从不回显完整号码。

---

## 2. 短信签名

### 2.1 `GET /api/v1/admin/sms/signatures`

- 用途：分页查询签名报备。
- 权限：`platform.sms.read`。成功状态：`200 OK`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` | query | int | 否 | 1 | 1–10000 | 页码 |
| `page_size` | query | int | 否 | 20 | 1–100 | 每页条数 |
| `keyword` | query | string | 否 | 无 | ≤64 | 名称模糊匹配 |
| `status` | query | string | 否 | 无 | `pending` / `approved` / `rejected` | 报备状态；不在枚举内则该条件不生效 |

```http
GET /api/v1/admin/sms/signatures?page=1&page_size=20&status=approved
```

```json
{
  "items": [
    {
      "id": 3,
      "name": "宣智爱",
      "provider_ref": "SIG-20261020-01",
      "status": "approved",
      "audit_remark": "营业执照已提交",
      "created_at": "2026-10-20T09:12:00",
      "updated_at": "2026-10-20T09:30:00"
    }
  ],
  "page": 1, "page_size": 20, "total": 1, "has_more": false
}
```

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 签名 ID |
| `name` | string | 是 | — | 签名内容（不含 `【】`） |
| `provider_ref` | string \| null | 是 | 未报备到供应商 | 供应商侧签名 ID |
| `status` | string | 是 | — | `pending` 待报备 / `approved` 已通过 / `rejected` 未通过 |
| `audit_remark` | string \| null | 是 | 无备注 | 报备备注 |
| `created_at` / `updated_at` | datetime \| null | 是 | — | 时间戳 |

### 2.2 `POST /api/v1/admin/sms/signatures`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `name` | body | string | 是 | — | 1–64，租户内唯一 | 签名内容 |
| `status` | body | string | 否 | `pending` | `pending` / `approved` / `rejected` | 报备状态 |
| `audit_remark` | body | string | 否 | `null` | ≤255 | 报备备注 |

```json
{ "name": "宣智爱", "status": "pending", "audit_remark": "已提交运营商" }
```

成功 `201`，返回 `SmsSignatureItem`。重名返回 `409`（唯一键 `uk_admin_sms_signature_name`）。

非法示例（`status` 越界，`422`）：

```json
{ "name": "宣智爱", "status": "waiting" }
```

### 2.3 `PATCH /api/v1/admin/sms/signatures/{signature_id}`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `signature_id` | path | int | 是 | — | ≥1 | 签名 ID |
| `name` / `status` / `audit_remark` | body | — | 否 | — | 同上 | 仅传需修改项 |

请求体为空返回 `422 至少提供一个需要修改的字段`；签名不存在 `404`。

### 2.4 `DELETE /api/v1/admin/sms/signatures/{signature_id}`

成功 `204`。仍被模板引用时 `409 该签名仍被模板引用，不能删除`。

---

## 3. 短信模板

### 3.1 `GET /api/v1/admin/sms/templates`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` / `page_size` | query | int | 否 | 1 / 20 | 同上 | 分页 |
| `keyword` | query | string | 否 | 无 | ≤64 | 名称或编码模糊匹配 |
| `scene` | query | string | 否 | 无 | ≤32 | 场景标识精确匹配 |
| `status` | query | int | 否 | 无 | 0 / 1 | 1 启用 / 0 停用 |

返回 `SmsTemplatePage`，`items[].signature_name` 为 JOIN 出的签名名称（签名缺失时 `null`）。

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 模板 ID |
| `name` | string | 是 | — | 模板名称 |
| `code` | string | 是 | — | 供应商模板编码（发送时使用），租户内唯一 |
| `content` | string | 是 | — | 模板正文，变量以 `{name}` 占位 |
| `signature_id` | int \| null | 是 | 未绑定签名 | 关联签名 ID |
| `signature_name` | string \| null | 是 | 签名不存在 | 关联签名名称 |
| `scene` | string | 是 | — | 场景标识，如 `notice` / `activity` / `vip` |
| `status` | int | 是 | — | 1 启用 / 0 停用 |

### 3.2 `POST /api/v1/admin/sms/templates`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `name` | body | string | 是 | — | 1–64 | 模板名称 |
| `code` | body | string | 是 | — | 1–64，租户内唯一 | 供应商模板编码 |
| `content` | body | string | 是 | — | 1–1000 | 模板正文 |
| `signature_id` | body | int | 否 | `null` | ≥1，必须存在 | 关联签名 |
| `scene` | body | string | 否 | `notice` | ≤32 | 场景标识 |
| `status` | body | int | 否 | 1 | 0 / 1 | 启停 |

```json
{ "name": "活动开场提醒", "code": "ACT_START", "content": "您好{name}，活动将于{time}开始。", "signature_id": 3, "scene": "activity" }
```

成功 `201`。`signature_id` 不存在 `404 短信签名不存在`；`code` 重复 `409`。

### 3.3 `PATCH /api/v1/admin/sms/templates/{template_id}` / 3.4 `DELETE ...`

更新语义同签名；删除不做引用校验（历史发送记录保留模板内容快照
`admin_sms_message.content`）。删除成功 `204`。

---

## 4. 群发

### 4.1 `POST /api/v1/admin/sms/send`

**敏感操作**：必须同时满足

| 要求 | 说明 | 缺失时 |
| --- | --- | --- |
| `Idempotency-Key` 请求头 | 8–128 字符，同键同载荷只执行一次 | `422` |
| `confirm=true` 查询参数 | 二次确认 | `428 敏感操作需要二次确认：请携带 confirm=true` |

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `template_id` | body | int | 二选一 | `null` | ≥1；与 `content` 互斥 | 模板 ID |
| `content` | body | string | 二选一 | `null` | ≤1000；与 `template_id` 互斥 | 自由文本 |
| `user_ids` | body | int[] | 二选一 | `[]` | ≤500 项；与 `phones` 至少一类 | 目标会员 `users.id` |
| `phones` | body | string[] | 二选一 | `[]` | ≤100 项 | 额外手机号 |
| `variables` | body | object | 否 | `{}` | 值会被转成字符串 | 模板变量，仅 `template_id` 模式生效 |

```http
POST /api/v1/admin/sms/send?confirm=true
Idempotency-Key: 3f6b0c1d9a2e4f7b8c0d1e2f3a4b5c6d
```

```json
{
  "template_id": 12,
  "user_ids": [1001, 1002],
  "phones": ["13800000000"],
  "variables": { "name": "张女士", "time": "10月25日 14:00" }
}
```

成功 `200`：

```json
{ "batch_no": "9f2c1a7d4b8e4c0fa1b2c3d4", "total": 3, "sent": 2, "failed": 1,
  "skipped": [{ "target": 1001, "reason": "会员不存在或未登记手机号" }] }
```

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `batch_no` | string | 是 | — | 批次号（24 位十六进制），可用于记录核对 |
| `total` | int | 是 | — | 解析出的目标总数（含被跳过项） |
| `sent` | int | 是 | — | 成功条数 |
| `failed` | int | 是 | — | 失败条数（供应商拒绝或网络异常） |
| `skipped` | object[] | 是 | `[]` 表示无跳过 | `{target: 会员 ID, reason: 跳过原因}` |

非法示例（模板与文本同时给出，`422`）：

```json
{ "template_id": 12, "content": "您好", "phones": ["13800000000"] }
```

**业务规则**

1. 供应商未配置时先抛 `503`，整批不落库（不会留下 `queued` 孤儿记录）——
   `send_sms` 在解析目标之前先调 `ensure_sms_template_configured()`。
2. 模板停用 `409 模板已停用，不能群发`。
3. 逐条发送：单条失败只把该条置 `failed` 并记录 `error`，不阻断整批。
4. 会员手机号从 `users.phone` 读取；会员不存在或未登记手机号计入 `skipped`。
5. 自由文本模式的供应商模板编码固定为 `free_text`。
6. 成功后向 `admin_sms_statistics` 追加一行**增量**（`success_count=成功数`、
   `failed_count=失败数`、`remaining_count=0`）。该表是增量账本：管理端首页与
   `GET /admin/sms/quota` 都对三列做 `SUM()`，余量本身由充值/账本任务写入，
   发送动作不改变余量。

---

## 5. 发送记录与余量

### 5.1 `GET /api/v1/admin/sms/records`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` / `page_size` | query | int | 否 | 1 / 20 | 同通用约定 | 分页 |
| `keyword` | query | string | 否 | 无 | ≤32 | 手机号片段匹配 |
| `template_id` | query | int | 否 | 无 | ≥1 | 按模板筛选 |
| `status` | query | string | 否 | 无 | `queued` / `sent` / `failed` | 发送状态 |
| `start_date` / `end_date` | query | string | 否 | 无 | `YYYY-MM-DD`，含当日 | 发送时间区间 |

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 记录 ID |
| `batch_no` | string | 是 | — | 批次号 |
| `template_id` | int \| null | 是 | 自由文本发送 | 模板 ID |
| `template_name` | string \| null | 是 | 模板已删除 | 模板名称 |
| `phone` | string | 是 | — | **脱敏**手机号 `138****1234` |
| `user_id` | int \| null | 是 | 非会员号码 | 关联会员 |
| `content` | string | 是 | — | 实际发送内容（变量已替换） |
| `status` | string | 是 | — | `queued` / `sent` / `failed` |
| `provider_ref` | string \| null | 是 | 未成功 | 供应商流水号 |
| `error` | string \| null | 是 | 无错误 | 失败原因（≤500 字） |
| `sent_at` | datetime \| null | 是 | 未成功 | 发送成功时间 |

空数据示例：

```json
{ "items": [], "page": 1, "page_size": 20, "total": 0, "has_more": false }
```

### 5.2 `GET /api/v1/admin/sms/quota`

```json
{ "provider": "disabled", "remaining_count": 860, "success_count": 140, "failed_count": 3,
  "updated_at": "2026-10-20T10:05:00" }
```

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `provider` | string | 是 | — | 当前 `SMS_TEMPLATE_PROVIDER` 值 |
| `remaining_count` | int | 是 | 尚无统计行时为 0 | 账本 `SUM(remaining_count)`，即当前余量 |
| `success_count` | int | 是 | 同上 | 账本 `SUM(success_count)`，累计成功数 |
| `failed_count` | int | 是 | 同上 | 账本 `SUM(failed_count)`，累计失败数 |
| `updated_at` | datetime \| null | 是 | 尚无统计行 | 最近一次账本写入时间 |

> 与 `GET /admin/dashboard`（管理端首页短信卡片）同口径，两处数字一致。
> 这里的余量是本地账本值，不是供应商实时余额；真实厂商接入后应补充
> `provider.fetch_balance()`（见 `docs/待完成事项.md`）。

---

## 6. 错误码

| 状态码 | 触发条件 | 前端处理 |
| --- | --- | --- |
| 401 | 未登录或令牌过期 | 跳登录 |
| 403 | 缺 `platform.sms.*` 权限 | 隐藏入口 |
| 404 | 签名 / 模板不存在 | 刷新列表 |
| 409 | 签名重名、签名被模板引用、模板停用后群发 | 提示并修正 |
| 422 | 参数校验失败、缺 `Idempotency-Key` | 修正表单 |
| 428 | 群发未带 `confirm=true` | 弹二次确认后重试 |
| 503 | 短信供应商未配置/未实现 | 提示配置 `.env` 后重试 |

---

## 7. 变更记录

| 日期 | 变更 | 兼容性 |
| --- | --- | --- |
| 2026-10-20 | 新增签名 / 模板 CRUD、群发、记录、余量共 11 个接口 | 新增接口，向后兼容 |
| 2026-10-20 | `SmsProvider` 协议新增 `send_template()`；新增 `sms_template_provider` 配置 | 新增能力，旧验证码通道不受影响 |

---

## 8. 文档完成自检清单

- [x] 请求参数表：每个参数均写明位置、类型、必填、默认值、校验与业务含义
- [x] 请求体示例：给出完整 HTTP 示例（含 `Idempotency-Key` 与 `confirm`）
- [x] 返回参数表：每个字段写明类型、必返、空值含义与业务含义
- [x] 成功返回示例：分页接口含 `items/page/page_size/total/has_more`；给出空数据示例
- [x] 使用方法与业务规则：覆盖供应商 fail-closed、逐条失败隔离、余量累计口径
- [x] 错误码表：HTTP 状态码、触发条件、前端处理
- [x] 至少一个非法参数示例
