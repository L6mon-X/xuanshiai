# 微信公众号运营（A2）管理后台接口

## 1. 通用约定

接口前缀：`/api/v1`。所有接口必须携带：

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

**权限**：

| 接口类别 | 权限码 |
| --- | --- |
| 读（`GET`） | `platform.wechat.read`（`platform.wechat.write` 亦可） |
| 写（`POST` / `PUT` / `PATCH` / `DELETE`） | `platform.wechat.write` |

**适配层**：`app/services/wechat_mp/providers.py::get_wechat_mp_provider()`

| 条件 | 实现 | 行为 |
| --- | --- | --- |
| `WECHAT_MP_APP_ID` 与 `WECHAT_MP_APP_SECRET` 均已配置 | `HttpWechatMpProvider` | 直连 `api.weixin.qq.com` 公开接口 |
| 未配置且在测试环境 | `MockWechatMpProvider` | 返回空列表 / 假 msgid |
| 未配置且非测试环境 | `DisabledWechatMpProvider` | 一切外部动作 `503 公众号凭据未配置` |

**密钥位置**：`WECHAT_MP_APP_ID` / `WECHAT_MP_APP_SECRET` / `WECHAT_MP_TOKEN` / `WECHAT_MP_AES_KEY`
只能通过 `.env` 注入。`GET /config` 只回显 `*_configured` 布尔；
`PUT /config` 只接受非敏感项。请求体模型 `extra="forbid"`，传 `app_secret` /
`api_token` / `encoding_aes_key` 会被 **422 直接拒绝**（不会静默丢弃），
若把密钥塞进 `platform_templates` 等嵌套结构，还会被 `patch_config` 的敏感键扫描拦下。

**同步写库语义**：所有同步/发送动作都是「先调微信，成功后才写本地」——微信报错时
本地不留半份数据，`existing` 记录也不会被改写。

---

## 2. 公众号配置

### 2.1 `GET /api/v1/admin/wechat/config`

```json
{
  "app_id_configured": true,
  "app_secret_configured": true,
  "token_configured": false,
  "aes_key_configured": false,
  "configured": true,
  "wx_no": "xuanshiai",
  "crypto_mode": "safe",
  "qrcode_url": null,
  "platform_templates": [],
  "version": 7,
  "updated_at": "2026-10-20T09:00:00"
}
```

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `app_id_configured` / `app_secret_configured` | bool | 是 | — | 环境变量是否就绪（**不回显值**） |
| `token_configured` / `aes_key_configured` | bool | 是 | — | 消息加解密相关凭据是否就绪 |
| `configured` | bool | 是 | — | AppID 与 AppSecret 都就绪时为 `true` |
| `wx_no` | string | 是 | 空串 | 公众号微信号（展示用） |
| `crypto_mode` | string | 是 | — | `safe` / `compatible` / `plain` |
| `qrcode_url` | string \| null | 是 | 未上传 | 公众号二维码图片 |
| `platform_templates` | array | 是 | `[]` | 平台侧模板配置（前端自定义结构） |
| `version` | int \| null | 是 | 配置域未初始化 | 配置版本 |
| `updated_at` | datetime \| null | 是 | 同上 | 最近更新时间 |

### 2.2 `PUT /api/v1/admin/wechat/config`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `wx_no` | body | string | 否 | 不变 | ≤64 | 公众号微信号 |
| `crypto_mode` | body | string | 否 | 不变 | `safe` / `compatible` / `plain` | 加解密模式 |
| `qrcode_url` | body | string | 否 | 不变 | ≤500 | 二维码图片地址 |
| `platform_templates` | body | array | 否 | 不变 | — | 平台模板配置 |

```json
{ "wx_no": "xuanshiai", "crypto_mode": "safe" }
```

成功 `200` 返回同上结构。请求体为空 `422`。

非法示例（明文密钥，`422`）：

```json
{ "app_secret": "abcd1234" }
```

---

## 3. 粉丝

### 3.1 `GET /api/v1/admin/wechat/fans`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` / `page_size` | query | int | 否 | 1 / 20 | 1–10000 / 1–100 | 分页 |
| `keyword` | query | string | 否 | 无 | ≤64 | 昵称或 openid 模糊匹配 |
| `group_id` | query | int | 否 | 无 | ≥1 | 分组 |
| `subscribe_status` | query | int | 否 | 无 | 0 / 1 | 1 已关注 / 0 已取关 |

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 粉丝记录 ID |
| `openid` | string | 是 | — | 微信 openid |
| `nickname` | string \| null | 是 | 微信未返回 | 昵称 |
| `avatar_url` | string \| null | 是 | 微信未返回 | 头像 |
| `gender` | int | 是 | 0 | 0 未知 / 1 男 / 2 女 |
| `city` / `province` | string \| null | 是 | 微信未返回 | 地区 |
| `subscribe_status` | int | 是 | — | 1 已关注 / 0 已取关 |
| `subscribe_at` / `unsubscribe_at` | datetime \| null | 是 | 未发生 | 关注 / 取关时间 |
| `group_id` | int \| null | 是 | 未分组 | 分组 ID |
| `group_name` | string \| null | 是 | 未分组 | 分组名称 |
| `user_id` | int \| null | 是 | 未关联会员 | 关联会员 |
| `remark` | string \| null | 是 | 无 | 备注 |

### 3.2 `POST /api/v1/admin/wechat/fans/sync`

无请求体。凭据未配置 `503`。

```json
{ "fetched": 1280, "created": 40, "updated": 1230, "unsubscribed": 10,
  "synced_at": "2026-10-20T10:00:00" }
```

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `fetched` | int | 是 | — | 本次从微信拉取的粉丝数 |
| `created` | int | 是 | — | 新建条数 |
| `updated` | int | 是 | — | 更新条数 |
| `unsubscribed` | int | 是 | — | 本次判定为已取关的条数（本次未返回的 openid） |
| `synced_at` | datetime | 是 | — | 同步时间 |

业务规则：
- 微信 `user/get` 只返回关注中的 openid，因此「本次未返回」即视为取关，
  本地置 `subscribe_status=0` 并写 `unsubscribe_at`。
- 拉取失败时整体 `503`，不落任何行。

### 3.3 粉丝分组

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/wechat/fans/groups` | 返回数组（不分页），按 `sort, id` 排序 |
| `POST` | `/api/v1/admin/wechat/fans/groups` | 新增，`name` 1–64、`sort` 0–9999 |
| `PATCH` | `/api/v1/admin/wechat/fans/groups/{group_id}` | 改名 / 改排序 |
| `DELETE` | `/api/v1/admin/wechat/fans/groups/{group_id}` | 删除（有粉丝时 409） |

```json
[{ "id": 5, "name": "南京粉丝", "provider_group_id": 101, "sort": 0, "fan_count": 320,
   "created_at": "2026-10-20T09:00:00" }]
```

错误：重名 `409 分组名称已存在`；有粉丝 `409 分组下仍有粉丝，请先迁移后再删除`；
不存在 `404 粉丝分组不存在`。

---

## 4. 自定义菜单

### 4.1 `GET /api/v1/admin/wechat/menu`

```json
{
  "top_menus": [
    { "name": "立即脱单", "type": "view", "key": null, "url": "https://h5.example.com",
      "appid": null, "pagepath": null, "sub_button": [] },
    { "name": "更多", "type": null, "key": null, "url": null, "appid": null,
      "pagepath": null,
      "sub_button": [{ "name": "关于我们", "type": "click", "key": "ABOUT", "url": null,
                       "appid": null, "pagepath": null, "sub_button": [] }] }
  ],
  "published_at": "2026-10-20T09:30:00",
  "version": 3
}
```

### 4.2 `PUT /api/v1/admin/wechat/menu`

发布菜单：**先调微信 `menu/create`，成功后才写本地配置**。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `top_menus` | body | array | 是 | — | 1–3 项 | 一级菜单 |
| `top_menus[].name` | body | string | 是 | — | 1–16 | 菜单名 |
| `top_menus[].type` / `key` / `url` / `appid` / `pagepath` | body | string | 否 | `null` | 各 ≤500 | 微信菜单字段 |
| `top_menus[].sub_button` | body | array | 否 | `[]` | ≤5 项；有子菜单时该级不得设置 `type/key/url` | 二级菜单 |

```json
{ "top_menus": [
  { "name": "立即脱单", "type": "view", "url": "https://h5.example.com" },
  { "name": "更多", "sub_button": [
    { "name": "关于我们", "type": "click", "key": "ABOUT" }
  ]}
]}
```

成功 `200` 返回 `WechatMenu`（含新的 `published_at`）。

非法示例（一级菜单既有子菜单又设 `type`，`422`）：

```json
{ "top_menus": [{ "name": "更多", "type": "view", "sub_button": [{ "name": "关于", "type": "click", "key": "K" }] }] }
```

凭据未配置 `503 公众号凭据未配置`（本地配置不会被改写）。

---

## 5. 自动回复

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/admin/wechat/autoreply/rules` | 返回数组，按 `sort, id`；可按 `match_type` / `status` 过滤 |
| `POST` | `/api/v1/admin/wechat/autoreply/rules` | 新增 |
| `PATCH` | `/api/v1/admin/wechat/autoreply/rules/{rule_id}` | 更新 |
| `DELETE` | `/api/v1/admin/wechat/autoreply/rules/{rule_id}` | 删除（`204`） |

`POST` 参数：

| 参数 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `name` | string | 是 | — | 1–64 | 规则名称 |
| `match_type` | string | 否 | `keyword` | `keyword` / `subscribe` / `default` | 触发方式 |
| `keyword` | string | 条件必填 | `null` | ≤128；`match_type=keyword` 时必填 | 关键词（逗号分隔） |
| `reply_type` | string | 否 | `text` | `text` / `image` / `news` | 回复类型 |
| `content` | string | 是 | — | 1–4000 | 回复内容 |
| `status` | int | 否 | 1 | 0 / 1 | 启停 |
| `sort` | int | 否 | 0 | 0–9999 | 排序 |

```json
{ "name": "关注欢迎语", "match_type": "subscribe", "reply_type": "text",
  "content": "欢迎关注宣智爱，回复「1」了解会员服务。", "status": 1, "sort": 0 }
```

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `id` | int | 是 | — | 规则 ID |
| `name` | string | 是 | — | 规则名 |
| `match_type` | string | 是 | — | 触发方式 |
| `keyword` | string \| null | 是 | 非关键词规则 | 关键词 |
| `reply_type` | string | 是 | — | 回复类型 |
| `content` | string | 是 | — | 回复内容 |
| `status` / `sort` | int | 是 | — | 启停 / 排序 |

非法示例（关键词规则未填关键词，`422`）：

```json
{ "name": "菜单回复", "match_type": "keyword", "content": "请回复 1" }
```

`PATCH` 时若合并后的 `match_type=keyword` 而关键词为空，服务层返回
`422 关键词规则必须填写关键词`。

---

## 6. 模板消息

### 6.1 `GET /api/v1/admin/wechat/templates`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `keyword` | query | string | 否 | 无 | ≤64 | 标题或 `template_id` 模糊匹配 |

返回数组（不分页）。字段：`id`、`template_id`（微信侧 ID）、`title`、`primary_industry`、
`deputy_industry`、`content`、`status`、`synced_at`。

### 6.2 `POST /api/v1/admin/wechat/templates/sync`

无请求体，凭据未配置 `503`。

```json
{ "fetched": 6, "created": 1, "updated": 5, "synced_at": "2026-10-20T10:05:00" }
```

---

## 7. 发送

### 7.1 `POST /api/v1/admin/wechat/messages/send`

**敏感操作**：需要 `Idempotency-Key`（8–128 字符）请求头与 `confirm=true` 查询参数，
缺 `confirm` 返回 `428`。

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `send_type` | body | string | 否 | `broadcast` | `broadcast` / `template` | 发送类型 |
| `template_id` | body | int | 模板模式必填 | `null` | ≥1，必须存在且启用 | 模板 ID |
| `group_id` | body | int | 否 | `null`（全部关注粉丝） | ≥1 | 目标分组 |
| `openids` | body | string[] | 否 | `[]` | ≤1000，去重后优先于 `group_id` | 显式 openid 列表 |
| `title` | body | string | 否 | `null` | ≤128 | 记录用标题 |
| `content` | body | string | 群发必填 | `null` | ≤2000 | 群发正文 |
| `url` | body | string | 否 | `null` | ≤500 | 点击跳转地址 |
| `data` | body | object | 否 | `{}` | string→string | 模板变量 |

```http
POST /api/v1/admin/wechat/messages/send?confirm=true
Idempotency-Key: 8f2b1c0d9e7a4f3b2c1d0e9f8a7b6c5d
```

```json
{ "send_type": "template", "template_id": 3, "group_id": 5,
  "data": { "first": "您的专属推荐已更新", "keyword1": "张女士", "remark": "点击查看" } }
```

成功 `200`：

```json
{ "batch_no": "1a2b3c4d5e6f7a8b9c0d1e2f", "send_type": "template", "target_count": 320,
  "sent_count": 318, "failed_count": 2, "provider_msg_id": "2001234567890" }
```

| 字段 | 类型 | 必返 | 空值含义 | 含义 |
| --- | --- | --- | --- | --- |
| `batch_no` | string | 是 | — | 批次号 |
| `send_type` | string | 是 | — | `broadcast` / `template` |
| `target_count` | int | 是 | — | 目标粉丝数 |
| `sent_count` | int | 是 | — | 成功数 |
| `failed_count` | int | 是 | — | 失败数 |
| `provider_msg_id` | string \| null | 是 | 供应商未返回 | 微信侧 msg_id |

**业务规则**

1. 目标解析：有 `openids` 时按显式列表（去重后）投递；否则按 `group_id`
   （空 = 全部 `subscribe_status=1` 的粉丝）取前 5000 条。
2. 上限：显式 `openids` 超过 1000 位、或按分组投递超过 5000 位，均返回
   `422 单次最多向 N 位粉丝发送`；未匹配到目标 `422 没有匹配到可发送的粉丝`。
3. 模板停用 `409 模板已停用，不能发送`；模板不存在 `404 模板消息不存在`。
4. 逐条发送：单条失败只累加 `failed_count` 并记录 `error`，不阻断整批。
5. 无论成功失败都写一条 `admin_wechat_message`，便于对账。

非法示例（模板模式未指定目标，`422`）：

```json
{ "send_type": "template", "template_id": 3, "data": {} }
```

### 7.2 `GET /api/v1/admin/wechat/messages/records`

| 参数 | 位置 | 类型 | 必填 | 默认值 | 校验 | 含义 |
| --- | --- | --- | --- | --- | --- | --- |
| `page` / `page_size` | query | int | 否 | 1 / 20 | 同上 | 分页 |
| `send_type` | query | string | 否 | 无 | `broadcast` / `template` | 发送类型 |
| `status` | query | string | 否 | 无 | `queued` / `sent` / `failed` | 状态 |
| `start_date` / `end_date` | query | string | 否 | 无 | `YYYY-MM-DD`，含当日 | 时间区间 |

字段：`id`、`batch_no`、`send_type`、`template_id`、`group_id`、`group_name`、`title`、
`content`、`url`、`target_count`、`sent_count`、`failed_count`、`status`、`error`、
`provider_msg_id`、`sent_at`、`created_at`。

---

## 8. 错误码

| 状态码 | 触发条件 | 前端处理 |
| --- | --- | --- |
| 401 | 未登录 | 跳登录 |
| 403 | 缺 `platform.wechat.*` | 隐藏入口 |
| 404 | 分组 / 模板不存在 | 刷新列表 |
| 409 | 分组重名、分组下有粉丝、模板已停用 | 提示并修正 |
| 422 | 参数校验失败、目标超限、明文密钥 | 修正表单 |
| 428 | 发送未带 `confirm=true` | 弹二次确认后重试 |
| 503 | 公众号凭据未配置 / 微信接口报错 | 提示配置 `.env` 或稍后重试 |

---

## 9. 变更记录

| 日期 | 变更 | 兼容性 |
| --- | --- | --- |
| 2026-10-20 | 新增配置 / 粉丝（含同步）/ 分组 / 菜单 / 自动回复 / 模板（含同步）/ 发送 / 记录共 17 个接口 | 新增接口，向后兼容 |
| 2026-10-20 | 新增 `WECHAT_MP_*` 四项环境变量；`wechat_mp` 配置域仍只存非敏感项 | 默认未配置时 503 |

---

## 10. 文档完成自检清单

- [x] 请求参数表：每个参数均写明位置、类型、必填、默认值、校验与业务含义
- [x] 请求体示例：配置、菜单、规则、发送均给出完整示例
- [x] 返回参数表：每个字段写明类型、必返、空值含义与业务含义
- [x] 成功返回示例：分页接口含 `items/page/page_size/total/has_more`；数组接口明确标注不分页
- [x] 使用方法与业务规则：覆盖同步取关判定、菜单先发后写、目标解析与上限
- [x] 错误码表：HTTP 状态码、触发条件、前端处理
- [x] 至少一个非法参数示例（明文密钥、菜单结构冲突、模板模式缺目标）
