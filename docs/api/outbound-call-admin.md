# 电话外呼（A6）管理后台接口

## 1. 通用约定

接口前缀：`/api/v1`。所有接口必须携带：

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

**权限**：

| 接口类别 | 权限码 |
| --- | --- |
| 读（`GET`） | `platform.outbound.read`（`platform.outbound.write` 亦可） |
| 写（`POST` / `PUT` / `PATCH` / `DELETE`） | `platform.outbound.write` |

**供应商适配层**：`app/services/outbound_call/providers.py::get_outbound_provider()`

| `OUTBOUND_CALL_PROVIDER` | 行为 |
| --- | --- |
| `disabled`（默认） | `GET /balance`、`POST /tasks/{id}/call` 返回 `503 外呼平台未配置` |
| `mock` | 仅 development/testing；返回假通话（`duration=30`、`result=connected`） |
| 其他任意值 | `503 外呼平台供应商未实现` |

**密钥位置**：`OUTBOUND_CALL_BASE_URL` / `OUTBOUND_CALL_ACCOUNT` / `OUTBOUND_CALL_SECRET` 只能
通过 `.env` 注入；`GET|PUT /config` 的响应体只回显 `*_configured` 布尔值。

**手机号脱敏**：号码池、名单、记录三处列表的 `phone` 一律经 `mask_phone()` 返回
（`138****1234`）。真实号码只在服务端拨号时从库内读取。

**分页壳**：`{ items, page, page_size, total, has_more }`。

**审计**：`outbound_number.create/update/delete`、`outbound_task.import`、`outbound_task.call`。

---

## 2. 平台配置

### 2.1 `GET /api/v1/admin/outbound-call/config`

```json
{
  "provider": "disabled",
  "configured": false,
  "base_url_configured": false,
  "account_configured": false,
  "secret_configured": false,
  "account_name": "宣智爱外呼",
  "call_center_url": "https://call.example.com/desk",
  "record_download_url": "https://call.example.com/records",
  "version": 4,
  "updated_at": "2026-10-20T08:00:00"
}
```

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `provider` | string | 是 | — | 当前 `OUTBOUND_CALL_PROVIDER` |
| `configured` | bool | 是 | — | provider 非 `disabled` 且 base_url + account 均已配置 |
| `base_url_configured` / `account_configured` / `secret_configured` | bool | 是 | — | 对应环境变量是否就绪（**不回显值**） |
| `account_name` | string \| null | 是 | 未设置 | 账户显示名（非敏感） |
| `call_center_url` | string \| null | 是 | 未设置 | 坐席工作台地址（仅前端跳转用） |
| `record_download_url` | string \| null | 是 | 未设置 | 录音下载入口地址 |
| `version` | int \| null | 是 | 配置域尚未初始化 | 配置版本号 |
| `updated_at` | datetime \| null | 是 | 同上 | 最近更新时间 |

### 2.2 `PUT /api/v1/admin/outbound-call/config`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `provider` | body | string | 否 | 不变 | ≤32 | 供应商标识（仅记录，实际以环境变量为准） |
| `account_name` | body | string | 否 | 不变 | ≤128 | 账户显示名 |
| `call_center_url` | body | string | 否 | 不变 | ≤500 | 坐席工作台地址 |
| `record_download_url` | body | string | 否 | 不变 | ≤500 | 录音下载入口 |

```json
{ "account_name": "宣智爱外呼", "call_center_url": "https://call.example.com/desk" }
```

成功 `200` 返回同上 `OutboundConfig`。请求体为空 `422`；请求体模型 `extra="forbid"`，
携带密钥类键（如 `secret`）会被 **422 直接拒绝**，不会静默丢弃。

---

## 3. 账户余额

### 3.1 `GET /api/v1/admin/outbound-call/balance`

供应商未配置时 `503`。成功 `200`：

```json
{ "provider": "mock", "account_name": "mock-account", "balance": 1000.0, "currency": "CNY",
  "checked_at": "2026-10-20T10:00:00" }
```

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `provider` | string | 是 | — | 供应商 |
| `account_name` | string \| null | 是 | 供应商未返回 | 账户名 |
| `balance` | float | 是 | — | 余额 |
| `currency` | string | 是 | — | 币种，默认 `CNY` |
| `checked_at` | datetime \| null | 是 | — | 本次查询时间（同时写入 `admin_outbound_account` 快照） |

> 查询失败不落库：避免把网络异常的默认值当成真实余额展示。

---

## 4. 外显号码池

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/outbound-call/numbers` | 分页 + 状态 / 号码片段 |
| `POST` | `/api/v1/admin/outbound-call/numbers` | 新增号码 |
| `PATCH` | `/api/v1/admin/outbound-call/numbers/{number_id}` | 修改号码 / 停用 / 绑红娘 |
| `DELETE` | `/api/v1/admin/outbound-call/numbers/{number_id}` | 删除号码 |

`GET` 参数：`page`（1–10000）、`page_size`（1–100）、`status`（0/1）、`keyword`（≤32）。

`POST` 参数：

| 参数 | 类型 | 必填 | 校验 | 含义 |
| --- | --- | --- | --- | --- |
| `phone` | string | 是 | 5–32，租户内唯一 | 外显号码 |
| `area` | string | 否 | ≤64 | 归属地 |
| `bound_matchmaker_id` | int | 否 | ≥1，且必须是有效服务红娘 | 绑定红娘 |
| `remark` | string | 否 | ≤255 | 备注 |

```json
{ "phone": "02512345678", "area": "南京", "bound_matchmaker_id": 88, "remark": "玄武店" }
```

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 号码 ID |
| `phone` | string | 是 | — | **脱敏**号码 |
| `area` | string \| null | 是 | 未填 | 归属地 |
| `status` | int | 是 | — | 1 启用 / 0 停用 |
| `bound_matchmaker_id` | int \| null | 是 | 未绑定 | 绑定红娘 |
| `bound_matchmaker_name` | string \| null | 是 | 未绑定或红娘已删 | 红娘昵称 |
| `remark` | string \| null | 是 | 无 | 备注 |

错误：号码重复 `409 该外显号码已存在`；`bound_matchmaker_id` 非有效服务红娘
`422 绑定的红娘不存在或不是有效服务红娘`；不存在 `404 外显号码不存在`。

---

## 5. 外呼名单

### 5.1 `GET /api/v1/admin/outbound-call/tasks`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` / `page_size` | query | int | 否 | 1 / 20 | 1–10000 / 1–100 | 分页 |
| `status` | query | string | 否 | 无 | `pending` / `calling` / `done` / `failed` / `canceled` | 状态 |
| `matchmaker_id` | query | int | 否 | 无 | ≥1 | 跟进红娘 |
| `keyword` | query | string | 否 | 无 | ≤64 | 号码或姓名模糊匹配 |

### 5.2 `POST /api/v1/admin/outbound-call/tasks`

导入 `.xlsx` 名单（multipart）。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `file` | form | file | 是 | — | `.xlsx`，≤5MB，≤2000 数据行 | 名单文件 |
| `default_matchmaker_id` | query | int | 否 | 无 | ≥1，必须是有效服务红娘 | 未填红娘列时的默认跟进人 |

**表头识别**（包含匹配）：手机号列必须存在（`手机` / `电话` / `phone`），
可选列「姓名 / 昵称 / name」「红娘 / 跟进人 / matchmaker」。

```http
POST /api/v1/admin/outbound-call/tasks?default_matchmaker_id=88
Content-Type: multipart/form-data

<file=名单.xlsx>
```

成功 `201`：

```json
{ "batch_no": "6c1f2d3e4a5b6c7d8e9f0a1b", "total": 120, "created": 118, "skipped": 2,
  "errors": [{ "row": 7, "reason": "红娘「李四」未找到" }] }
```

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `batch_no` | string | 是 | — | 导入批次号 |
| `total` | int | 是 | — | 解析出的有效行数（手机号非空的行） |
| `created` | int | 是 | — | 实际写入条数 |
| `skipped` | int | 是 | — | 跳过条数，等于 `errors.length` |
| `errors` | object[] | 是 | `[]` 表示全部成功 | `{row: Excel 行号, reason: 原因}` |

业务规则：
- `.xls` 旧格式 `400 暂不支持 .xls 旧格式…`；非 `.xlsx` `400 仅支持 .xlsx 格式的 Excel 文件`；
  缺手机号列 `400 模板表头缺少「手机号」列…`；无数据行 `400 文件内没有可导入的数据行`。
- 号码能在 `users.phone` 命中时自动写入 `member_id`，否则留空。
- 红娘列按昵称或实名精确匹配有效服务红娘；未命中该行记入 `errors` 并跳过。
- 单次超过 2000 行 `400 单次最多导入 2000 行…`。

### 5.3 `POST /api/v1/admin/outbound-call/tasks/{task_id}/call`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `task_id` | path | int | 是 | — | ≥1 | 名单 ID |
| `caller_number` | body | string | 否 | 自动选号 | 5–32，必须在号码池中且启用 | 指定外显号码 |

请求体可省略。自动选号顺序：绑定该名单跟进红娘的启用号码优先，其次未绑定的启用号码。

```json
{ "caller_number": "02512345678" }
```

成功 `200` 返回该名单行（状态变为 `done`，同时写入一条 `admin_outbound_record`）。

| 场景 | 状态码 | 说明 |
| --- | --- | --- |
| 供应商未配置 | 503 | 名单状态不变，仍为 `pending`，配置后可直接重呼 |
| 名单已完成/已取消 | 409 | 不可重复外呼 |
| 指定外显号码不在池中或停用 | 422 | — |
| 供应商调用异常 | 502 | 名单置 `failed` 并在 `remark` 记录原因 |

---

## 6. 通话记录

### 6.1 `GET /api/v1/admin/outbound-call/records`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` / `page_size` | query | int | 否 | 1 / 20 | 同上 | 分页 |
| `result` | query | string | 否 | 无 | `connected` / `no_answer` / `busy` / `reject` / `invalid` | 通话结果 |
| `matchmaker_id` | query | int | 否 | 无 | ≥1 | 跟进红娘 |
| `start_date` / `end_date` | query | string | 否 | 无 | `YYYY-MM-DD`，含当日 | 时间区间 |

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 记录 ID |
| `task_id` | int \| null | 是 | 非名单外呼 | 关联名单 |
| `phone` | string | 是 | — | **脱敏**号码 |
| `matchmaker_id` | int \| null | 是 | 未分配 | 跟进红娘 |
| `matchmaker_name` | string \| null | 是 | 未分配 | 红娘昵称 |
| `direction` | string | 是 | — | `outbound` 呼出 / `inbound` 呼入 |
| `result` | string \| null | 是 | 未接通 | 通话结果 |
| `duration` | int | 是 | 0 | 通话时长（秒） |
| `recording_url` | string \| null | 是 | 无录音 | 录音地址 |
| `provider_call_id` | string \| null | 是 | 供应商未返回 | 供应商通话 ID |
| `started_at` / `ended_at` | datetime \| null | 是 | — | 通话起止 |

空数据示例：

```json
{ "items": [], "page": 1, "page_size": 20, "total": 0, "has_more": false }
```

---

## 7. 错误码

| 状态码 | 触发条件 | 前端处理 |
| --- | --- | --- |
| 401 | 未登录 | 跳登录 |
| 403 | 缺 `platform.outbound.*` | 隐藏入口 |
| 400 | Excel 格式 / 表头 / 行数不合法 | 提示重新下载模板 |
| 404 | 号码 / 名单不存在 | 刷新列表 |
| 409 | 号码重复、名单已完成或已取消 | 刷新后重试 |
| 413 | 文件超过 5MB | 拆分文件 |
| 422 | 参数校验失败、红娘无效、号码不在池中 | 修正表单 |
| 502 | 供应商调用异常 | 稍后重试并检查配置 |
| 503 | 外呼平台未配置/未实现 | 提示配置 `.env` |

---

## 8. 变更记录

| 日期 | 变更 | 兼容性 |
| --- | --- | --- |
| 2026-10-20 | 新增配置 / 余额 / 号码池 / 名单（含导入与呼叫）/ 记录共 10 个接口 | 新增接口，向后兼容 |
| 2026-10-20 | 新增 `OUTBOUND_CALL_*` 五项环境变量 | 默认 `disabled`，未配置时 503 |

---

## 9. 文档完成自检清单

- [x] 请求参数表：每个参数均写明位置、类型、必填、默认值、校验与业务含义
- [x] 请求体示例：JSON 与 multipart 两类均给出完整示例
- [x] 返回参数表：每个字段写明类型、必返、空值含义与业务含义
- [x] 成功返回示例：分页接口含 `items/page/page_size/total/has_more`；给出空数据示例
- [x] 使用方法与业务规则：覆盖导入识别规则、自动选号、fail-closed 语义
- [x] 错误码表：HTTP 状态码、触发条件、前端处理
- [x] 至少一个非法参数示例（Excel 格式与号码不在池中）
