# 后台运营与第三方适配模块迁移（A1 / A2 / A3 / A4 / A5 / A6 / A7 / A8 / A9 / A10）

本目录对应 `后端接口缺失清单.md` A 类新增接口的持久化载体。与 `migrations/m4_m7`
一致：**先迁移、后发版**，且只对 `AUTO_INIT_DB=false` 的生产/预发布库是必需的。
开发/测试环境（`AUTO_INIT_DB=true`）由 `database_setup_marriage.py` 在启动时通过
`BUSINESS_TABLES` 幂等建表，不需要执行本目录脚本。

| 迁移 | 内容 | 对应改动 |
| --- | --- | --- |
| `20261020_01_admin_ops_tables_*` | 10 张运营表 + A9 历史弃海回填 | A4 素材库 / A5 二维码 / A7 话术库 / A8 相亲卡 / A9 会员弃海 / A10 联盟活动 |
| `20261020_02_vendor_adapter_tables_*` | 16 张第三方适配表 | A1 短信 / A6 外呼 / A2 公众号 / A3 电子合同 |

## 一、新表清单

| 表 | 用途 | 接口文档 |
| --- | --- | --- |
| `admin_material_category` | 素材分类 | `docs/api/materials-admin.md` |
| `admin_material` | 素材文件（软删除） | `docs/api/materials-admin.md` |
| `admin_qrcode` | 二维码注册表（含续期） | `docs/api/qrcode-admin.md` |
| `admin_sales_category` | 话术分类 | `docs/api/sales-library-admin.md` |
| `admin_sales_item` | 话术条目（软删除） | `docs/api/sales-library-admin.md` |
| `admin_sales_push` | 话术下发记录 | `docs/api/sales-library-admin.md` |
| `admin_lovecard_template` | 相亲卡模板 | `docs/api/lovecard-admin.md` |
| `admin_lovecard_generation` | 相亲卡生成记录 | `docs/api/lovecard-admin.md` |
| `member_abandonment` | 会员弃海 / 捞回记录 | `docs/api/member-abandonment.md` |
| `admin_alliance_activity` | 联盟活动 | `docs/api/interact-alliance-admin.md` |

> 计数说明：上表列 10 张表；`verify.sql` 第 1/2 项期望的也是 10 行。

## 一、A1/A2/A3/A6 第三方适配表（`20261020_02`）

| 表 | 用途 | 接口文档 |
| --- | --- | --- |
| `admin_sms_signature` | 短信签名报备 | `docs/api/sms-admin.md` |
| `admin_sms_template` | 短信模板 | `docs/api/sms-admin.md` |
| `admin_sms_message` | 短信逐条发送记录 | `docs/api/sms-admin.md` |
| `admin_outbound_number` | 外显号码池 | `docs/api/outbound-call-admin.md` |
| `admin_outbound_task` | 外呼名单 | `docs/api/outbound-call-admin.md` |
| `admin_outbound_record` | 外呼通话记录 | `docs/api/outbound-call-admin.md` |
| `admin_outbound_account` | 外呼账户余额快照 | `docs/api/outbound-call-admin.md` |
| `admin_wechat_fan_group` | 公众号粉丝分组 | `docs/api/wechat-admin.md` |
| `admin_wechat_fan` | 公众号粉丝 | `docs/api/wechat-admin.md` |
| `admin_wechat_autoreply_rule` | 公众号自动回复规则 | `docs/api/wechat-admin.md` |
| `admin_wechat_template` | 公众号模板消息 | `docs/api/wechat-admin.md` |
| `admin_wechat_message` | 公众号发送记录 | `docs/api/wechat-admin.md` |
| `admin_econtract_template` | 电子合同模板 | `docs/api/econtract-admin.md` |
| `admin_econtract_seal` | 电子印章 | `docs/api/econtract-admin.md` |
| `admin_econtract` | 电子合同 | `docs/api/econtract-admin.md` |
| `admin_econtract_event` | 合同签署流水 | `docs/api/econtract-admin.md` |

本批次**不新增敏感列**：短信/公众号/电子签/外呼的密钥一律通过 `.env` 注入
（见 `.env.example` 的 `SMS_*` / `WECHAT_MP_*` / `TENCENT_ESIGN_*` / `OUTBOUND_CALL_*`），
库内 `admin_config_snapshot` 只存非敏感项。`verify.sql` 第 4 项会检出误写入配置域的明文密钥。

## 二、A9 历史口径回填

「弃海会员」的历史定义是「来源客源 `customer_lead.status='LOST'`」。`member_abandonment`
上线后，列表与统计以该表为准，因此 up 脚本末尾把尚无有效弃海记录的此类会员回填为
`abandon_type='lead_sync'`、`abandoned_by=0`（系统）。

回填是**幂等**的：`NOT EXISTS (... restored_at IS NULL)` 保证重复执行不会重复插入；
同一会员的有效弃海记录上限由业务层（`abandon_member` 的 409 校验）与 `verify.sql`
第 4 项共同保证。

## 执行方式

本仓库没有通用迁移 runner；按人工 SQL 迁移方式执行。先确认目标数据库并完成备份：

1. 执行 `20261020_01_admin_ops_tables_up.sql`（全部 `CREATE TABLE IF NOT EXISTS`，可重复执行）。
2. 执行 `20261020_01_admin_ops_tables_verify.sql`，期望：
   - 第 1 项返回 10 行（10 张表全部存在）；
   - 第 2 项返回 0 行；
   - 第 3 项返回 0 行（关键索引齐备）；
   - 第 4 项返回 0 行（无重复有效弃海记录）。
3. 执行 `20261020_02_vendor_adapter_tables_up.sql`，再执行
   `20261020_02_vendor_adapter_tables_verify.sql`，期望第 1 项 16 行、第 2/3/4 项各 0 行。
4. 再发布依赖这些表的后端版本。

## 回滚

两个 `down.sql` 都**不会自动回滚**，执行时以 `SQLSTATE 45000` 阻断。原因：这些表落库后
即承载运营业务数据（含对账凭据），自动 DROP 会造成不可逆数据丢失。
如需回滚，按 down.sql 注释中的三步（manifest → 导出确认 → 定向 DDL）执行。
