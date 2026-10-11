# 后台筛选参数迁移

按「先迁移、后发版」顺序执行。开发/测试环境在 `AUTO_INIT_DB=true` 时由
`database_setup_marriage.py` 的 `_ensure_filter_columns()` 幂等补齐同一批对象；
生产/预发布保持 `AUTO_INIT_DB=false`，只使用本目录的显式迁移。

| 迁移 | 内容 |
| --- | --- |
| `20261011_01_admin_filter_columns_*` | 后台筛选参数补列（22 列 + 4 个索引） |

---

## 一、2026-10-11 后台筛选参数补列

对应 `docs/后端筛选参数缺口清单.md`。清单里的会员资料、客源线索、内容类筛选项有
一部分在现有表上没有对应列，不补列新版本的筛选 SQL 会报 `Unknown column`。

覆盖范围：

- **users**（9 列）：`source`、`region`、`cert_status`、`wechat_added`、`promoted`、
  `newcomer`、`activity_signup`、`level`、`fetched_at`。
- **user_profile**（2 列）：`car`、`household`。
- **customer_lead**（11 列）：`age`、`height`、`marriage`、`education`、`occupation`、
  `residence`、`hometown`、`xiangqin_status`、`bind_mode`、`wechat_added`、`assigned_at`。
- **索引**（4 个）：`idx_users_source`、`idx_users_fetched`、`idx_customer_lead_assigned`、
  `idx_customer_lead_xiangqin`。

`admin_content_item`（落地页 / 自由表单 / 内容单页）的 `type`、`qrcode_type`、
`xiangqin_status` **不补列**：该表的域特有字段按设计存放在 `extra_json`，对应筛选走
`JSON_UNQUOTE(JSON_EXTRACT(extra_json, '$.<key>'))`。

**幂等性**：`INFORMATION_SCHEMA` 检查 + `PREPARE`/`EXECUTE` 动态 DDL，可重复执行；
表不存在时补列与索引跳过。所有新增 `NOT NULL` 列都带默认值，存量行自动落到默认值，
不会改写业务数据。

**执行与校验**：

1. 执行 `20261011_01_admin_filter_columns_up.sql`。
2. 执行 `20261011_01_admin_filter_columns_verify.sql`，期望：第 1 项缺失列查询返回 0 行；
   第 2 项返回 22 行；第 3 项返回 4 行且 `NON_UNIQUE=1`、`SUB_PART` 为空；
   第 4 项返回 0 行。
3. 再发布依赖这些列的后端版本。

**顺序要求**：必须**先迁移、后发版**。新版本代码的会员/线索/内容筛选会直接引用这些列。

## 回滚

`20261011_01_admin_filter_columns_down.sql` 当前**不会自动回滚**，执行时会以
`SQLSTATE 45000` 阻断。原因与 `migrations/m4_m7/20260916_01` 相同：up 只做「不存在才 ADD」，
回滚时无法区分本次新增的列与迁移前就存在的同名列。如需回滚，按 down.sql 注释里的三步
（manifest → 定向 DDL → 人工审核）执行。
