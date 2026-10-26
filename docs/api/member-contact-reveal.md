# 会员完整联系方式查看接口（A19 权限门控解密）

> 归属模块：红娘后台 · 会员 CRM
> 路由文件：`app/api/routes/matchmaker_crm_admin.py` → `member_contact_reveal`
> 权限码来源：`app/api/dependencies.py` `CurrentMatchmakerAdmin.require`
> 脱敏口径来源：`app/core/sensitive_fields.py`（详情接口掩码，本接口是唯一返原值出口）

## 背景与定位

后台「会员详情」接口（`GET /api/v1/admin/matchmaker/members/{member_id}`）对微信号做**服务端强制掩码**（隐私纵深），
`REDACTION_LEVEL_STANDARD` 与 `REDACTION_LEVEL_ELEVATED` 两档均不返回完整值，手机号在详情里为全值但不落审计。

产品清单 A19 反馈：详情页微信号被固定显示为 `zha****`，业务红娘无法在授权范围内查看完整微信号去添加客户。
为在不放松默认脱敏的前提下满足该诉求，新增本接口——它是**唯一返回原值的出口**，必须同时满足：

1. 显式权限门控（`matchmaker.member.manage`）；
2. D-16 数据作用域校验（只能看到本账号可见范围内的会员）；
3. **每一次查看逐条落审计**（`business_audit_log`，action=`member.contact_reveal`）；
4. 越权与不存在统一 404，避免通过状态码差异枚举会员 ID。

> 与手机号一样在详情返回全值不同：微信号在详情永远掩码，只有调用本接口且权限/范围通过时才返回原值。

---

## 基本信息

| 项 | 值 |
| --- | --- |
| 完整 URL | `GET /api/v1/admin/matchmaker/members/{member_id}/contact` |
| HTTP Method | `GET` |
| 是否需要登录 | 是（红娘后台 Token，`get_current_matchmaker_admin`） |
| 所需权限 | `matchmaker.member.manage`（或超级权限 `*`） |
| 请求 Content-Type | 无请求体（参数走 path + query） |
| 响应 Content-Type | `application/json` |
| 成功状态码 | `200` |
| 幂等 | 只读查询，天然幂等；但**每次调用都会新增一条审计记录**（设计如此，用于追溯谁看过） |

---

## 请求参数

| 参数名 | 位置 | 类型 | 必填 | 默认值 | 校验规则 | 业务含义 | 合法示例 | 非法示例 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `member_id` | path | integer | 是 | — | `ge=1` | 目标会员用户 ID | `9` | `0`、`-1`、`abc` |
| `field` | query | string | 否 | `wechat` | 枚举 `wechat` \| `phone`（正则 `^(wechat|phone)$`） | 要查看的联系方式字段 | `wechat` | `email`、`id_card`（不在枚举 → `422`） |

说明：
- `field=wechat` 从 `user_profile.wechat` 取值；若库中 `user_profile.wechat` 列尚未就绪（迁移未执行），返回 `503` 而非拼 `NULL` 误导前端。
- `field=phone` 从 `users.phone` 取值，不依赖 `user_profile` 表。

### 请求示例

```http
GET /api/v1/admin/matchmaker/members/9/contact?field=wechat HTTP/1.1
Authorization: Bearer <matchmaker-admin-token>
Accept: application/json
```

无请求体。

非法示例（`field` 不在允许枚举，FastAPI 校验层拦截）：

```http
GET /api/v1/admin/matchmaker/members/9/contact?field=id_card HTTP/1.1
Authorization: Bearer <matchmaker-admin-token>
```

---

## 返回参数

| 字段 | 类型 | 必返 | 空值含义 | 业务含义 | 示例值 |
| --- | --- | --- | --- | --- | --- |
| `member_id` | integer | 是 | — | 回显被查看的会员 ID | `9` |
| `field` | string | 是 | — | 回显本次查看的字段：`wechat` / `phone` | `"wechat"` |
| `value` | string \| null | 是 | `null` 表示该会员此字段未填写或仅空白字符（库中为空/仅空格） | **完整未脱敏**的联系方式原值 | `"zhang_san_wx88"` |

### 返回示例

成功（有值）：

```json
{
  "member_id": 9,
  "field": "wechat",
  "value": "zhang_san_wx88"
}
```

成功（该字段未填写，库中为空或仅空格）：

```json
{
  "member_id": 9,
  "field": "wechat",
  "value": null
}
```

---

## 使用方法与业务规则

- **前置条件**：调用方已登录红娘后台，且账号持有 `matchmaker.member.manage` 权限（或 `*`）；目标会员落在账号数据作用域内。
- **调用顺序**：进入会员详情页 → 详情接口返回掩码微信号 → 用户点击「查看微信 / 查看手机」→ 前端携带 `field` 调本接口取原值并展示。
- **权限语义**：权限校验在读取列信息之前执行；无权限直接 `403`，不会产生任何查询或审计写入。
- **数据作用域**：使用 `CurrentMatchmakerAdmin.scope_exists_clause`（基于 `resource_assignment`），与会员列表/详情同源；`ALL` 数据范围或持 `*` 时等价 `1 = 1`，其余按归属 EXISTS 过滤。
- **软删除**：若 `users.deleted_at` 列存在，会自动追加 `u.deleted_at IS NULL` 守卫，已注销会员按不存在处理（`404`）。
- **审计**：无论返回值是否为空，只要权限与作用域校验通过并成功定位到会员行，即写入一条 `business_audit_log`（`actor_user_id`、`action='member.contact_reveal'`、`resource_type='users'`、`resource_id=member_id`、`reason='查看完整{field}'`）并提交。这是可追溯性的关键，不可省略。
- **不泄露存在性**：越权与不存在合并为 `404`，前端无法据此枚举会员 ID。
- **频率建议**：本接口逐次落审计，不建议前端在列表页批量/自动调用；应仅在用户显式点击「查看」时按需调用。

---

## 错误

| HTTP 状态码 | 触发条件 | 错误响应示例 | 前端处理建议 |
| --- | --- | --- | --- |
| `403` | 缺少 `matchmaker.member.manage` 权限（且无 `*`） | `{"detail": "缺少权限：matchmaker.member.manage"}` | 提示无权限，隐藏「查看」入口 |
| `404` | 会员不存在，或不在当前账号数据作用域内（含已软删） | `{"detail": "会员不存在或无权限"}` | 提示无法查看，不区分越权/不存在 |
| `422` | `member_id < 1` 或 `field` 不在 `wechat`/`phone` 枚举 | FastAPI 校验错误体 | 检查请求参数 |
| `503` | `field=wechat` 但 `user_profile.wechat` 列未就绪（迁移未执行） | `{"detail": "微信号列未就绪，无法查看完整微信号"}` | 提示稍后重试或联系管理员执行迁移 |

---

## 变更记录

| 日期 | 变更 | 说明 |
| --- | --- | --- |
| 2026-10-24 | 新增接口 | 响应产品清单 A19：详情微信号固定掩码，新增权限门控 + 逐次审计的原值查看出口 |
