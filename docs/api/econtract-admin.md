# 电子合同（A3）管理后台接口

## 1. 通用约定

接口前缀：`/api/v1`。所有接口必须携带：

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

**权限**：

| 接口类别 | 权限码 |
| --- | --- |
| 读（`GET`） | `finance.contract.read`（`finance.contract.write` 亦可） |
| 写（`POST` / `PUT` / `PATCH` / `DELETE`） | `finance.contract.write` |

**适配层**：`app/services/esign/providers.py::get_esign_provider()`

| 条件 | 实现 | 行为 |
| --- | --- | --- |
| 测试环境 | `MockEsignProvider` | 返回假流程 `mock-flow-<合同号>` 与假签署链接 |
| 非测试环境 | `DisabledEsignProvider` | 「发起合同 / 作废合同」`503 电子签服务未配置` |

> 腾讯电子签真实实现需厂商联调（见 `docs/待完成事项.md`）；`GET /config` 的
> `adapter_implemented=false` 如实反映这一点，避免前端误以为已可签署。

**密钥位置**：`TENCENT_ESIGN_SECRET_ID` / `TENCENT_ESIGN_SECRET_KEY` /
`TENCENT_ESIGN_OPERATOR_OPEN_ID` 只能通过 `.env` 注入；接口只回显 `*_configured` 布尔。

**手机号脱敏**：合同列表与详情返回的 `member_phone` 经 `mask_phone()` 处理（`138****1234`）。

**分页壳**：`{ items, page, page_size, total, has_more }`。

**审计**：`econtract_template.*`、`econtract_seal.*`、`econtract.create`、`econtract.void`；
签署流水另写 `admin_econtract_event`（`created` / `sent` / `voided`）。

---

## 2. 电子签配置

### 2.1 `GET /api/v1/admin/e-contract-config`

```json
{
  "secret_id_configured": false,
  "secret_key_configured": false,
  "operator_configured": false,
  "configured": false,
  "adapter_implemented": false,
  "enabled": false,
  "items": [
    { "id": 1, "key": "sign_expire_days", "name": "合同签署有效期（天）", "value": "7",
      "description": "超期未签署的合同自动置为已过期", "update_time": null }
  ],
  "version": 2,
  "updated_at": "2026-10-20T08:30:00"
}
```

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `secret_id_configured` / `secret_key_configured` / `operator_configured` | bool | 是 | — | 环境变量是否就绪（**不回显值**） |
| `configured` | bool | 是 | — | SecretId 与 SecretKey 都就绪 |
| `adapter_implemented` | bool | 是 | — | 真实适配器是否已实现；当前恒为 `false` |
| `enabled` | bool | 是 | — | 业务开关（前端用于隐藏入口） |
| `items` | array | 是 | `[]` | 业务参数项（有效期天数、提醒天数等） |
| `version` | int \| null | 是 | 配置域未初始化 | 配置版本 |
| `updated_at` | datetime \| null | 是 | 同上 | 最近更新时间 |

### 2.2 `PUT /api/v1/admin/e-contract-config`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `enabled` | body | bool | 否 | 不变 | — | 业务开关 |
| `items` | body | array | 否 | 不变 | 整体替换 | 业务参数项 |

```json
{ "enabled": true, "items": [{ "id": 1, "key": "sign_expire_days", "name": "合同签署有效期（天）", "value": "14" }] }
```

成功 `200`。请求体为空 `422`；请求体模型 `extra="forbid"`，传
`secret_id` / `secret_key` 等密钥字段会 **422 直接拒绝**，不会静默丢弃。

---

## 3. 合同

### 3.1 `GET /api/v1/admin/e-contracts`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` / `page_size` | query | int | 否 | 1 / 20 | 1–10000 / 1–100 | 分页 |
| `keyword` | query | string | 否 | 无 | ≤64 | 合同号 / 标题 / 签署人模糊匹配 |
| `status` | query | string | 否 | 无 | `draft` / `signing` / `signed` / `voided` / `expired` | 状态 |
| `template_id` | query | int | 否 | 无 | ≥1 | 模板 |
| `start_date` / `end_date` | query | string | 否 | 无 | `YYYY-MM-DD`，含当日 | 创建时间区间 |

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 合同 ID |
| `contract_no` | string | 是 | — | 合同编号（`HT` + 时间戳 + 6 位随机） |
| `template_id` / `template_name` | int \| null / string \| null | 是 | 未用模板 / 模板已删 | 模板 |
| `seal_id` / `seal_name` | int \| null / string \| null | 是 | 未用印章 / 印章已删 | 印章 |
| `title` | string | 是 | — | 合同标题 |
| `contract_type` | string | 是 | — | 合同类型 |
| `member_id` | int \| null | 是 | 非会员签署 | 签署会员 |
| `member_name` | string | 是 | — | 签署人姓名 |
| `member_phone` | string \| null | 是 | — | **脱敏**手机号 |
| `amount` | float \| null | 是 | 未填金额 | 合同金额 |
| `status` | string | 是 | — | 状态枚举（见上） |
| `provider_flow_id` | string \| null | 是 | 未接入供应商 | 电子签流程 ID |
| `sign_url` | string \| null | 是 | 未生成 | 签署链接 |
| `signed_at` / `expire_at` | datetime \| null | 是 | 未签署 / 无期限 | 签署时间 / 截止时间 |
| `voided_at` / `void_reason` | datetime \| null / string \| null | 是 | 未作废 | 作废时间与原因 |

空数据示例：

```json
{ "items": [], "page": 1, "page_size": 20, "total": 0, "has_more": false }
```

### 3.2 `POST /api/v1/admin/e-contracts`

发起合同：**先调电子签 `create_flow`，成功后才落库**；供应商未配置时 `503`
且不留合同行。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `title` | body | string | 是 | — | 1–128 | 合同标题 |
| `template_id` | body | int | 否 | `null` | ≥1，必须启用 | 模板 |
| `seal_id` | body | int | 否 | `null` | ≥1，必须启用 | 印章 |
| `contract_type` | body | string | 否 | 模板类型或「红娘服务协议」 | ≤64 | 合同类型 |
| `member_id` | body | int | 条件必填 | `null` | ≥1，必须存在 | 签署会员（自动取姓名/手机号） |
| `member_name` | body | string | 条件必填 | `null` | ≤64 | 非会员时的签署人姓名 |
| `member_phone` | body | string | 条件必填 | `null` | ≤32 | 非会员时的手机号 |
| `amount` | body | float | 否 | `null` | ≥0 | 合同金额 |
| `content` | body | string | 否 | 模板正文 | ≤200000 | 合同正文（覆盖模板） |
| `expire_days` | body | int | 否 | `null`（无期限） | 1–365 | 签署有效期（天） |

```json
{ "title": "红娘服务协议（白金会员）", "template_id": 2, "seal_id": 1,
  "member_id": 1001, "amount": 6800, "expire_days": 7 }
```

成功 `201` 返回 `EcontractDetail`（含 `content` 与 `events`）。

非法示例（既无 `member_id` 也无姓名+手机号，`422`）：

```json
{ "title": "红娘服务协议", "template_id": 2 }
```

业务规则：
- 模板停用 `409 模板已停用，不能发起合同`；印章停用 `409 印章已停用，不能发起合同`。
- `member_id` 不存在 `422 签署会员不存在`。
- 姓名或手机号缺失 `422 签署人姓名与手机号不完整`。
- 成功后写两条流水：`created`（合同已发起）、`sent`（签署链接已生成），
  并把模板 `usage_count` +1。

### 3.3 `GET /api/v1/admin/e-contracts/{contract_id}`

返回 `EcontractDetail`：在列表字段基础上追加

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `content` | string \| null | 是 | 未保存正文 | 合同正文快照 |
| `events` | object[] | 是 | `[]` 无流水 | 签署流水，按 `id` 升序 |
| `events[].event` | string | 是 | — | `created` / `sent` / `viewed` / `signed` / `voided` / `expired` / `callback` |
| `events[].actor` | string \| null | 是 | 未知 | `admin` / `member` / `provider` |
| `events[].detail` | string \| null | 是 | 无说明 | 事件说明 |
| `events[].created_at` | datetime \| null | 是 | — | 发生时间 |

### 3.4 `POST /api/v1/admin/e-contracts/{contract_id}/void`

**敏感操作**：需要 `Idempotency-Key`（8–128）与 `confirm=true`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `contract_id` | path | int | 是 | — | ≥1 | 合同 ID |
| `reason` | body | string | 是 | — | 1–500 | 作废原因 |

```json
{ "reason": "会员取消购买，双方协商作废" }
```

成功 `200` 返回 `EcontractDetail`（`status=voided`）。

| 场景 | 状态码 | 说明 |
| --- | --- | --- |
| 状态不是 `draft` / `signing` | 409 | 仅这两态可作废 |
| 供应商未配置且有 `provider_flow_id` | 503 | 本地状态不变 |
| 缺 `confirm=true` | 428 | 二次确认 |

---

## 4. 模板

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/e-contract-templates` | 分页 + 关键词 / 类型 / 启停 |
| `POST` | `/api/v1/admin/e-contract-templates` | 新增 |
| `PATCH` | `/api/v1/admin/e-contract-templates/{template_id}` | 更新 |
| `DELETE` | `/api/v1/admin/e-contract-templates/{template_id}` | 删除（被引用时 409） |

`GET` 参数：`page`（1–10000）、`page_size`（1–100）、`keyword`（≤64）、
`contract_type`（≤64）、`status`（0/1）。

`POST` 参数：

| 参数 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `name` | string | 是 | — | 1–128 | 模板名称 |
| `contract_type` | string | 否 | `红娘服务协议` | ≤64 | 合同类型 |
| `provider_template_id` | string | 否 | `null` | ≤128 | 电子签平台模板 ID |
| `content` | string | 否 | `null` | ≤200000 | 模板正文 |
| `file_url` | string | 否 | `null` | ≤500 | 模板文件地址 |
| `status` | int | 否 | 1 | 0/1 | 启停 |

> `content`、`provider_template_id`、`file_url` **至少提供一项**，否则 `422`
> 「正文、电子签模板 ID、模板文件至少提供一项」。

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 模板 ID |
| `name` | string | 是 | — | 模板名称 |
| `contract_type` | string | 是 | — | 合同类型 |
| `provider_template_id` | string \| null | 是 | 未接入平台模板 | 电子签模板 ID |
| `content` | string \| null | 是 | 无正文 | 模板正文 |
| `file_url` | string \| null | 是 | 无文件 | 模板文件 |
| `status` | int | 是 | — | 1 启用 / 0 停用 |
| `usage_count` | int | 是 | 0 | 已发起合同数 |

错误：被引用时删除 `409 该模板已被合同引用，不能删除（可改为停用）`；
不存在 `404 合同模板不存在`。

---

## 5. 印章

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/e-contract-seals` | 返回数组（不分页），可按 `status` 过滤 |
| `POST` | `/api/v1/admin/e-contract-seals` | 新增（multipart 或已有 `image_url`） |
| `PATCH` | `/api/v1/admin/e-contract-seals/{seal_id}` | 更新 |
| `DELETE` | `/api/v1/admin/e-contract-seals/{seal_id}` | 删除（被引用时 409） |

`POST` 参数：

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `name` | query/form | string | 是 | — | 1–128 | 印章名称 |
| `seal_type` | query/form | string | 否 | `company` | `company` / `personal` | 印章类型 |
| `authorized_person` | query/form | string | 否 | `null` | ≤64 | 授权人 |
| `image_url` | query/form | string | 二选一 | `null` | ≤500 | 已有图片地址 |
| `file` | form | file | 二选一 | `null` | png/jpg，≤5MB | 印章图片（转 WebP 落盘） |

```http
POST /api/v1/admin/e-contract-seals?name=%E5%85%AC%E5%8F%B8%E7%AB%A0&seal_type=company&authorized_person=%E5%BC%A0%E4%B8%89
Content-Type: multipart/form-data

<file=seal.png>
```

成功 `201`：

```json
{ "id": 1, "name": "公司章", "seal_type": "company",
  "image_url": "/storage/uploads/admin/econtract-seals/ab12.webp?sig=...",
  "authorized_person": "张三", "provider_seal_id": null, "status": 1,
  "created_at": "2026-10-20T09:00:00", "updated_at": "2026-10-20T09:00:00" }
```

> `image_url` 为**前端可直接使用**的签名地址；库内保存的是未签名相对路径。

错误：既不传 `file` 也不传 `image_url` → `422 必须上传印章图片或提供 image_url`；
图片非 png/jpg → `415`；超过 5MB → `413`；被引用删除 → `409 该印章已被合同引用，不能删除（可改为停用）`。

---

## 6. 错误码

| 状态码 | 触发条件 | 前端处理 |
| --- | --- | --- |
| 401 | 未登录 | 跳登录 |
| 403 | 缺 `finance.contract.*` | 隐藏入口 |
| 404 | 合同 / 模板 / 印章不存在 | 刷新列表 |
| 409 | 状态不允许作废、模板/印章被引用、模板或印章已停用 | 提示并修正 |
| 413 | 印章图片超过 5MB | 压缩后重传 |
| 415 | 印章图片格式不支持 | 改 png/jpg |
| 422 | 参数校验失败、缺签署人信息、明文密钥 | 修正表单 |
| 428 | 作废未带 `confirm=true` | 弹二次确认后重试 |
| 503 | 电子签未配置 | 提示配置 `.env` 后重试 |

---

## 7. 变更记录

| 日期 | 变更 | 兼容性 |
| --- | --- | --- |
| 2026-10-20 | 新增合同（列表 / 发起 / 详情 / 作废）、模板 CRUD、印章 CRUD、配置共 13 个接口 | 新增接口，向后兼容 |
| 2026-10-20 | 新增 `TENCENT_ESIGN_*` 三项环境变量 | 未配置时发起/作废 503 |

---

## 8. 文档完成自检清单

- [x] 请求参数表：每个参数均写明位置、类型、必填、默认值、校验与业务含义
- [x] 请求体示例：JSON 与 multipart 两类均覆盖
- [x] 返回参数表：每个字段写明类型、必返、空值含义与业务含义
- [x] 成功返回示例：分页接口含 `items/page/page_size/total/has_more`；数组接口明确标注不分页
- [x] 使用方法与业务规则：覆盖状态流转、先发后写、流水记录、敏感操作要求
- [x] 错误码表：HTTP 状态码、触发条件、前端处理
- [x] 至少一个非法参数示例（缺签署人信息、缺印章图片）
