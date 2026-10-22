# 后端全量测试与 Ruff 历史治理清单

> 记录日期：2026-09-25。本文记录当前后端全量无集成检查的真实结果，用于区分消息/媒体稳定门禁与存量治理项。不删除、跳过或改写失败用例，不把这些结果描述为本轮消息链路已通过。

## 当前门禁结果

| 检查 | 命令 | 结果 | 结论 |
| --- | --- | --- | --- |
| 消息/申请/媒体定向测试 | `python -m pytest tests/test_social_features.py tests/test_social_message_idempotency.py tests/test_discovery_features.py tests/test_member_follow_up_media.py -q` | `60 passed` | 本轮消息/媒体定向门禁通过 |
| 后端全量无集成测试 | `python -m pytest tests --ignore=tests/integration --ignore=tests/live --ignore=tests/manual -q` | `2129 passed, 6 failed, 6 skipped, 22 warnings` | 全量仍未收绿 |
| 全仓 Ruff | `python -m ruff check .` | `56 errors` | 全仓静态检查仍未收绿 |
| 前端核心门禁 | `cd ../xuanshiai-vue && npm test` | `13/13 passed` | 前端消息核心门禁通过 |

后端全量检查未连接共享开发或生产 MySQL/Redis。6 个跳过项来自显式的隔离数据库或 Windows 运行能力条件，不能作为通过证据。

## Pytest 失败清单

### 1. M4/M7 迁移资产缺失

- **测试**：`tests/test_m4_m7_column_migration.py::test_m4_m7_migration_scripts_are_paired`
- **失败信号**：`migrations/m4_m7/20260916_01_m4_m7_backoffice_columns_up.sql` 与对应 `down.sql` 不存在。
- **责任模块**：`migrations/m4_m7/` 迁移资产；同时需要核对 `tests/test_m4_m7_column_migration.py` 与当前迁移目录命名约定。
- **当前归属判断**：本轮后端工作树未修改 `migrations/` 或该测试；属于存量迁移资产/基线问题，不能归因于消息或媒体改动。
- **修复要求**：确认目标迁移是否应恢复为受控的 up/down 成对文件，或更新测试以匹配已批准的迁移目录；必须先核对数据库发布与回滚策略，不能只创建空文件满足断言。
- **回归命令**：`python -m pytest tests/test_m4_m7_column_migration.py -q`
- **处置结果（2026-09-27）**：已补齐受控迁移资产 `migrations/m4_m7/20260916_01_m4_m7_backoffice_columns_{up,down,verify}.sql` 与 `README.md`，逐条镜像 `database_setup_marriage.py` 的 `_ensure_m4..m7` helper（`database_setup_marriage.py:3384-3502`）。发布与回滚方式见 `migrations/m4_m7/README.md`；`down` 恢复 `commission_entry.order_id NOT NULL` 仅当表内无 `order_id IS NULL` 数据时执行，否则脚本跳过该步并输出 `rollback_blocked` 提示。已在 `compose.ai-test.yml` 的独立测试 MySQL（127.0.0.1:3307）一次性临时库上完成 up×2（幂等）/verify/down×2（幂等）/再 up/NULL 数据回滚阻塞的全路径演练后删除临时库。

### 2. 生产 Mock 支付错误契约不一致

- **测试**：`tests/test_pricing_config.py::test_mock_wechat_payment_is_rejected_outside_test_environments`
- **失败信号**：`Settings(... environment="production", wechat_payment_mode="mock")` 确实被拒绝，但 `ValidationError` 展示文本未匹配测试期待的 `微信支付 Mock`。
- **责任模块**：`app/core/config.py` 的生产配置校验与 `tests/test_pricing_config.py` 的错误契约。
- **当前归属判断**：本轮后端工作树未修改 `app/core/config.py` 或该测试；属于既有错误信息/测试契约漂移。安全行为仍然是 fail-closed，不能为了让测试通过而放宽生产 Mock 禁止规则。
- **修复要求**：统一稳定错误码或稳定错误消息，并同步测试；优先使用可供客户端/运维识别的错误码，避免测试依赖 Pydantic 拼装后的完整字符串。
- **回归命令**：`python -m pytest tests/test_pricing_config.py::test_mock_wechat_payment_is_rejected_outside_test_environments -q`

### 3. 生产真实支付模式被其他生产门禁拦截

- **测试**：`tests/test_pricing_config.py::test_real_wechat_payment_mode_is_available_for_production`
- **失败信号**：`wechat_payment_mode="real"` 的 `Settings` 构造在支付字段断言前失败，当前异常来自生产配置/AI 门禁组合，而不是 `wechat_payment_mode` 字段本身。
- **责任模块**：`app/core/config.py` 的生产配置默认值与 `_validate_ai_feature_gates()`，以及 `tests/test_pricing_config.py` 的最小生产配置夹具。
- **当前归属判断**：本轮后端工作树未修改配置实现或该测试；属于生产设置默认值与测试隔离不完整的存量问题。修复时不得削弱 AI 生产 fail-closed。
- **修复要求**：让“验证真实支付模式可用”的测试显式提供所有无关生产门禁所需的关闭值，或拆分纯支付配置校验，保证测试只验证目标契约。
- **回归命令**：`python -m pytest tests/test_pricing_config.py::test_real_wechat_payment_mode_is_available_for_production -q`

### 4. 资料标签目录与测试数据不一致

- **测试**：`tests/test_profile_features.py::test_profile_validates_mbti_height_and_tags`
- **失败信号**：`interest_tags=["健身", "旅行", "摄影"]` 未通过当前 `ALL_TAG_OPTIONS` 校验。
- **责任模块**：`app/core/profile_tags.py` 标签目录、`app/schemas/auth.py` 兼容字段校验、对应标签同步测试/文档。
- **当前归属判断**：本轮后端工作树未修改标签目录、资料 Schema 或该测试；属于目录版本与测试快照漂移。前端标签同步检查另有错误的后端根目录参数，不能把该检查当作目录已一致的证据。
- **修复要求**：确定当前产品标签目录的唯一来源，更新测试数据或目录并同步前端契约；保留自定义标签和旧字段兼容规则的安全校验。
- **回归命令**：`python -m pytest tests/test_profile_features.py -q`；跨仓再执行 `cd ../xuanshiai-vue && node tests/test-personal-tags.js`

### 5. 行政区编码未归一化

- **测试**：`tests/test_regions.py::test_region_route_codes_can_be_normalized_to_tree_codes`
- **失败信号**：`list_cities("110000")` 未归一化到树编码 `"11"`，直接返回 404；同类问题存在于 `list_districts("110100")`。
- **责任模块**：`app/services/regions.py` 的省/市编码归一化，以及 `tests/test_regions.py`。
- **当前归属判断**：本轮后端工作树未修改地区服务或该测试；属于存量服务契约缺口，与消息/媒体无关。
- **修复要求**：在服务边界统一处理 2/4/6 位行政区编码，保留非法编码 404；补充省、市、区三级及空值/异常长度回归覆盖。
- **回归命令**：`python -m pytest tests/test_regions.py -q`

### 6. 语音 WebSocket 生产 fail-closed 测试夹具被配置门禁拦截

- **测试**：`tests/test_voice_ws.py::test_production_fail_closed`
- **失败信号**：测试想验证 WebSocket 关闭行为，但 `Settings(...)` 在建立客户端前因生产配置门禁抛出 `ValidationError`。
- **责任模块**：`app/core/config.py` 生产 AI 门禁、`tests/test_voice_ws.py` 的生产测试设置夹具。
- **当前归属判断**：本轮后端工作树未修改配置实现或该测试；语音路由本身仍保留关闭时返回 WebSocket policy violation 的 fail-closed 路径，当前失败首先是夹具无法构造设置。
- **修复要求**：给测试提供满足“AI 全部关闭”的最小生产配置，或将路由门禁测试与 Settings 构造测试分离；不能关闭生产门禁来迁就测试。
- **回归命令**：`python -m pytest tests/test_voice_ws.py::test_production_fail_closed -q`

## Ruff 诊断清单

本次 `python -m ruff check . --output-format=json` 共 56 项：`F401=36`、`F841=10`、`E702=6`、`E402=2`、`F821=2`。以下按文件完整列出，作为后续责任模块和回归范围索引。

### 业务代码

| 文件 | 行号 | 规则 | 责任/建议 |
| --- | ---: | --- | --- |
| `app/api/routes/activity_admin.py` | 13, 25 | `F401` ×3 | 清理未使用的 `CurrentUser`、`get_current_admin`、`ActivitySignupStatusUpdate`；回归活动后台路由测试 |
| `app/api/routes/ai_compatibility.py` | 35 | `F401` | 清理 `CompatibilitySnapshotRead`；回归兼容性路由测试 |
| `app/api/routes/finance.py` | 278 | `F821` | 补齐或修正 `admin_grant_credits` 的导入/调用契约；回归财务管理测试 |
| `app/api/routes/matchmaker.py` | 26, 47 | `F401` ×5 | 清理未使用的评分 Schema 与服务导入；确认评分路由是否遗漏后再回归红娘路由测试 |
| `app/api/routes/member_media_admin.py` | 20 | `F401` | 清理 `MemberMediaItem`；回归后台媒体列表/替换测试 |
| `app/api/routes/merchant_admin.py` | 307 | `F821` | 补齐 SQLAlchemy `text` 导入；回归商家订单详情路由测试 |
| `app/services/ai/audit.py` | 220 | `F401` | 清理或实际使用 `pymysql` 导入，核对审计写入分支后回归 AI 审计测试 |
| `app/services/matchmaker_workspace.py` | 82, 85 | `F401` ×2 | 清理未使用的工作台状态 Schema；回归工作台服务测试 |
| `app/services/member_auth_admin.py` | 768, 770, 772, 774, 776, 778 | `E702` ×6 | 将分号连接的赋值拆为独立语句；回归会员后台资料类型更新测试 |
| `app/services/organization_admin.py` | 243 | `F841` | 删除未使用的 `user_scope` 或补回实际 SQL 使用；回归组织报表测试 |
| `app/services/voice/stream_tts_provider.py` | 35, 120 | `F401` ×2 | 清理未使用的阿里云异常与 Token TTL 导入；回归流式 TTS 客户端测试 |

### AI 集成测试代码

| 文件 | 行号 | 规则 | 责任/建议 |
| --- | ---: | --- | --- |
| `tests/integration/ai/test_ai_compatibility_engine_real_db.py` | 18 | `F401` | 清理未使用的 `CompatibilitySnapshotStatus`；在隔离 MySQL/Redis 集成环境回归 |
| `tests/integration/ai/test_ai_entry_profile_real_db.py` | 528 | `F841` | 删除未使用的 `projection_b` 或补充断言；在隔离 MySQL 集成环境回归 |
| `tests/integration/ai/test_ai_memory_phase3_real_db.py` | 26, 154 | `F401`, `F841` | 清理 `MemoryLedger` 导入并处理 `claim_id`；在隔离 MySQL 集成环境回归 |
| `tests/integration/ai/test_ai_memory_projection_real_db.py` | 13, 22, 24 | `F401` ×3 | 清理未使用类型、Ledger 和异常导入；在隔离 MySQL 集成环境回归 |
| `tests/integration/ai/test_ai_memory_real_db.py` | 657, 665 | `F841` ×2 | 删除未使用的 `session`/`records` 或补充断言；在隔离 MySQL 集成环境回归 |

### 普通测试代码

| 文件 | 行号 | 规则 | 责任/建议 |
| --- | ---: | --- | --- |
| `tests/test_ai_compatibility_compare.py` | 12, 14 | `F401` ×2 | 清理未使用的比较类型导入；回归该测试文件 |
| `tests/test_ai_memory_derivations.py` | 40, 42 | `E402` ×2 | 调整模块导入顺序；回归该测试文件及内存派生测试 |
| `tests/test_ai_memory_materializer.py` | 21, 22, 202 | `F401` ×2, `F841` | 清理未使用 Fake Session/Store 并处理 `corrected`；回归物化器测试 |
| `tests/test_ai_memory_projection_outbox.py` | 21 | `F401` | 清理 `GRANT_KWARGS`；回归 outbox 测试 |
| `tests/test_ai_memory_projections.py` | 20, 459, 554 | `F401` ×2, `F841` | 清理未使用策略/函数导入并处理 `key`；回归投影测试 |
| `tests/test_apportion_config_admin.py` | 17, 25 | `F401` ×2 | 清理未使用路由模块和 Schema 导入；回归分摊配置后台测试 |
| `tests/test_backfill_ai_memory.py` | 16 | `F401` | 清理 `asyncio`；回归 backfill 测试 |
| `tests/test_bulk_materialization.py` | 222 | `F841` | 删除或使用 `baseline`；回归批量物化测试 |
| `tests/test_m4_finalize_ext.py` | 13 | `F401` ×2 | 清理未使用 `AsyncMock`/`MagicMock`；回归 M4 扩展测试 |
| `tests/test_m7_activity_merchant_video_ext.py` | 150 | `F401` | 清理未使用 `timedelta`；回归 M7 扩展测试 |
| `tests/test_m9_system_finance_ext.py` | 86 | `F401` | 清理未使用 `app.api.router`；回归系统财务测试 |
| `tests/test_persona_cache_invalidation.py` | 18 | `F401` | 清理未使用 `PersonaProjectionSession`；回归 Persona 缓存测试 |
| `tests/test_stream_tts_client.py` | 12 | `F401` | 清理未使用 `MagicMock`；回归流式 TTS 测试 |
| `tests/test_task_websocket_notifications.py` | 497, 519 | `F841` ×2 | 删除或使用未使用的 `db`；回归任务 WebSocket 通知测试 |

## 处理边界与优先级

1. **P0/P1 安全与生产门禁**：先修复配置测试夹具/错误契约，但保持生产 Mock、AI 和语音 fail-closed；不得为了全量收绿而放宽门禁。
2. **P1 迁移与公开契约**：先确认 M4/M7 迁移资产来源、发布窗口、备份和回滚，再恢复或调整迁移测试。
3. **P1 业务契约**：补齐地区编码归一化和资料标签目录同步，分别补服务层回归与跨仓目录检查。
4. **P2 静态清理**：按业务模块批量处理 Ruff，业务代码与 AI 集成测试分开回归；`F821` 必须优先于纯未使用导入清理。
5. 全量检查稳定后，才评估是否把后端 CI 从消息/媒体改动域扩大到全仓。

## 当前工作树归属

- 本轮后端变更路径：`.github/workflows/backend-ci.yml`、`docs/DEVELOPMENT.md`、`.gitignore`、`README.md`、`docs/MEDIA_STORAGE_ACCESS_REVIEW.md`、`scripts/reproduce_upload_exposure.py`。
- 本轮未修改上述 6 个失败对应的实现/测试，也未修改 Ruff 报告中的业务文件。
- 因此 6 个 pytest 失败和 56 个 Ruff 错误均登记为存量治理项，不阻塞已通过的消息/媒体定向门禁，但阻塞后端全仓绿色。

## 不可替代的验证

- 本清单不替代真实 HTTP 消息联调、隔离 MySQL/Redis 集成测试、HBuilderX 构建、微信开发者工具、真机和 HTTPS/部署验收。
- `scripts/reproduce_upload_exposure.py` 的匿名 `200` 结果仍是 P0 媒体风险证据，不是通过标准。
- 当前未执行提交、推送、发布或上线。

---

## 2026-10-16 重新基线（AI 模块接手后）

> 记录日期：2026-10-16。基线提交 `f63239d`，工作树含同日 AI 模块改动（FIX-01/04/05/07/09/10）。**上一节的 `2129 passed / 6 failed` 与 `56 errors` 是 2026-09-25 的历史记录，已不代表当前状态**，保留仅供对照；两次失败集合**零重叠**。

| 检查 | 命令 | 结果 | 结论 |
| --- | --- | --- | --- |
| 后端全量无集成测试 | `.venv/Scripts/python.exe -m pytest --ignore=tests/integration -q -p no:randomly` | `8 failed, 2650 passed, 13 skipped, 27 warnings in 183.19s` | 8 项失败**全部为环境缺失**，无业务回归 |
| 全仓 Ruff（app/tests/scripts） | `.venv/Scripts/python.exe -m ruff check app tests scripts` | `All checks passed!` | 已收零；09-25 记录的 `56 errors` 全部处理完毕 |

Python 3.12.7（项目自带 venv `.venv/`），未连接共享开发或生产 MySQL/Redis；13 个 skip 来自显式隔离数据库条件与 `LIVE_API_BASE` 未设置的实时 HTTP 用例，不作为通过证据。

计数口径：FIX 改动落地过程中先测得 `2646 passed`（FIX-01/04/05/07/09/10 的测试已计入），补齐 FIX-05 的 Provider 侧提取用例后为 `2650 passed`（+4）。两次 failed 集合完全相同，均为此处 8 项环境失败。

### 与 09-25 基线的差异

- 09-25 记录的 6 项失败（`m4_m7` 迁移资产、`pricing_config` ×2、资料标签目录、行政区编码归一、语音 WS 门禁夹具）**已全部修复，当前 0 项复现**。历史处置记录见上文对应小节。
- `test_admin_permission_coverage::test_no_backoffice_route_is_permission_blind` 曾于 2026-10-16 早间为唯一真实回归（改密接口权限盲区），已由 FIX-01 修复收绿。

### 当前 Pytest 失败清单（8 项，全部环境归因）

| # | 测试 | 单行原因 | 归因（非业务） | 解封条件 |
| --- | --- | --- | --- | --- |
| 1 | `tests/test_ai_governance_contracts.py::test_ai_product_and_security_decisions_are_frozen` | `FileNotFoundError: PRODUCT.md not found above backend root`（:13） | 缺后端同级 `PRODUCT.md` | 取回 `E:/Xuanshiai/PRODUCT.md` |
| 2-3 | `tests/test_memory_docs_contract.py::test_product_md_declares_memory_kernel_shadow_scope` / `::test_product_md_declares_deferred_scope` | `required document is missing: E:/Xuanshiai/PRODUCT.md`（:24） | 同上 | 同上 |
| 4-6 | `tests/test_memory_docs_contract.py::test_architecture_doc_declares_frozen_contract` / `::test_architecture_doc_declares_no_downstream_switch_and_privacy_floor` / `::test_architecture_doc_declares_subject_write_guard` | `required document is missing: E:/Xuanshiai/docs/architecture/ai-memory-kernel-core-v1.md`（:24） | 缺架构文档 | 取回该架构文档 |
| 7 | `tests/test_community_demo_seed.py::test_member_seed_assets_resolve_to_frontend_files` | `AssertionError: 缺少素材 anime:001`（:100） | 缺兄弟前端仓库 `xuanshiai-vue` | 克隆前端仓库到同级目录 |
| 8 | `tests/test_voice_cleanup.py::test_symlink_inside_upload_dir_follows_target_expiry` | `assert not True`（:220） | Windows 无符号链接权限（权限不同时该用例在 fail/skip 间浮动） | 以管理员/开发者模式创建符号链接，或在 POSIX 环境运行 |

**这 8 项均不随业务改动而变**：补齐上述缺失资产后应全部转绿。任何后续改动只要仍为这 8 项，即视为未引入回归。

### 归属与边界

- 本次基线对应的业务改动：`app/api/dependencies.py`（改密豁免）、`app/services/ai/gateway.py` + `providers.py`（token 用量透传）、`app/services/voice/gateway.py`（语音时长用量）、`app/services/ai_avatar.py`（分身失败审计）、`app/services/derivation_outbox.py`（心跳续租）、`app/workers/*`（结构化日志）。
- 本清单**不替代**真实 HTTP 联调、隔离 MySQL/Redis 集成测试、真实 Provider 跑分、真机与部署验收；上述项目在本机仍为 `NOT_RUN`。

---

## 2026-10-16 真实 MySQL 集成验证（FIX-11 解锁）

> 首次在真实 MySQL 上执行 AI 记忆域集成套件。此前该套件**从未在任何环境被实际执行过**（CI 无真实库、本机无 Docker、文档命令一律 `--ignore=tests/integration`）。

| 检查 | 命令 | 结果 | 结论 |
| --- | --- | --- | --- |
| FIX-11 六个目标文件 | `$env:AI_TEST_DATABASE_URL="mysql+aiomysql://root:123456@127.0.0.1:3306/xuanshiai_ai_test"` + `pytest {投影/purge围栏/授权代际/清理重授权/记忆/phase3} -q -p no:randomly` | `31 passed in 34.51s` | 记忆域真实库路径打通 |
| `tests/integration/ai` 全域 | 同上，目录级 | `14 failed, 140 passed, 5 skipped, 6 errors in 242.76s` | 6 ERROR = 缺 Redis；3 SKIP = 缺语音凭证；1 SKIP = Windows 子进程；1 SKIP = 数据依赖；2 失败 = `voice/ws-ticket` 503；3 失败 = 缺真实 Provider；**7 失败待逐项定性** |

### 环境

- 本地 MySQL 8.0.44（`MySQL80` 服务在运行），测试库 `xuanshiai_ai_test`（与开发库 `xuanshiai` 分离）。
- **无 Redis、无 Docker、无语音凭证、`AI_ENABLED=false` / `AI_PROVIDER=mock`** ⇒ Redis 类、语音类、真实 Provider 类用例仍不可闭环。

### 本次暴露的真实缺陷（已修复）

1. `test_ai_memory_purge_grant_fence_real_db.py`：前置断言基于「同秒 ⇒ 快照相同」，但快照自 `ce72b9e`（10-10）起绑定持久 `grant_id`，恒不相等 ⇒ 断言自 10-10 起恒红且从未被执行。已改为断言代际必然不同。
2. `test_ai_memory_real_db.py:290`：`ORDER BY id` 引用不存在的列（`ai_memory_observation` 主键为 `observation_id`）⇒ `(1054, "Unknown column 'id' in 'order clause'")`。已改用 `observation_id`。

### 边界

7 项「空结果 / None」失败**未定性**，不得归为环境。真实 Provider 跑分、语音链路、真机验收在本机仍为 `NOT_RUN`，不以 Mock 冒充验收。

---

## 2026-10-18 同步上游 `9f939eb` 后的重新基线

> 触发：`git pull --tags origin main` 报 `local changes ... would be overwritten`（详见 `docs/待完成事项.md` 2026-10-18 节）。同步方式：丢弃与上游逐字重复的 2 处本地改动后 `git pull --ff-only`，**纯快进、无 merge commit**。基线提交 `9f939eb`。

| 检查 | 命令 | 结果 | 结论 |
| --- | --- | --- | --- |
| 后端全量无集成测试 | `.venv/Scripts/python.exe -m pytest --ignore=tests/integration -q -p no:randomly` | `7 failed, 2679 passed, 15 skipped in 192.33s` | 7 项**全部为环境缺失**，无业务回归 |
| 权限覆盖 + 改密契约 | `pytest tests/test_admin_permission_coverage.py tests/test_admin_password_change_contract.py -q` | `15 passed` | 上游 `2e23f11` 的豁免生效，本地 5 例行为测试同时通过 |
| 记忆域真实 MySQL（FIX-11 六文件） | `AI_TEST_DATABASE_URL=...` + `pytest {六文件} -q` | `31 passed in 34.99s` | 与同步前一致，上游改动未影响记忆域 |
| 全仓 Ruff | `ruff check app tests scripts` | `All checks passed!` | 0 告警 |

### 失败清单（7 项，全部环境归因）

| 测试 | 归因 | 解封条件 |
| --- | --- | --- |
| `test_ai_governance_contracts::test_ai_product_and_security_decisions_are_frozen` | 缺 `E:/Xuanshiai/PRODUCT.md` | 取回同级 `PRODUCT.md` |
| `test_memory_docs_contract` ×2（`test_product_md_*`） | 同上 | 同上 |
| `test_memory_docs_contract` ×3（`test_architecture_doc_*`） | 缺 `E:/Xuanshiai/docs/architecture/ai-memory-kernel-core-v1.md` | 取回该架构文档 |
| `test_community_demo_seed::test_member_seed_assets_resolve_to_frontend_files` | 缺兄弟前端仓库 `xuanshiai-vue` | 克隆到同级目录 |

> 与 2026-10-16 基线的差异：失败数由 8 降为 7、skip 由 13 升为 15。**不是修复了什么业务缺陷**，而是语音符号链接两个用例从"不稳定失败"改为"确定性 skip"（见下）。pass 数 2650 → 2679 的增量来自上游新增测试（`test_admin_common_upload_file` / `test_customer_lead_contact_guard` / `test_member_media_admin_ext` / `test_offline_vip_admin_ext` / `test_m6_partner_ext` 等）。

### 本次修复的两处测试稳定性缺陷

1. **全量偶发卡死定位到具体用例**：`tests/test_voice_cleanup.py::test_worker_forever_loop_schedules_cleanup`。根因是该用例只把 `_run_round` 打桩，却在首轮真实触发了需要 DB 会话的**记忆状态 TTL 清理**（`last_memory_state_cleanup_at = -inf` ⇒ 首轮必然执行），与其 docstring 声称的"避免测试触碰数据库"矛盾。整套件跑到此处时连接池已绑定前序用例的已关闭事件循环，该 await 永不完成；而 `await task` 等的是不可取消的 Future ⇒ 进程 CPU 归零、日志停在该用例、15 分钟无进展。诊断手法：`-o faulthandler_timeout=180` 转储线程栈，可见事件循环空闲于 `select()`。修复：按 `test_ai_memory_ttl_cleanup` 同口径把 `_run_memory_state_ttl_cleanup_round` 打桩为空转，并显式钉住 retention 间隔。
2. **符号链接两个用例的环境探测无效**：原逻辑只捕获 `os.symlink` 抛出的异常来判断"环境是否支持"，但本机实测该调用**既不抛异常也建不出真链接**（`link.is_symlink()` 为 False），导致两个用例比的是"链接不存在"这一假前提。已在创建后补 `if not link.is_symlink(): pytest.skip(...)`，与 docstring 的"symlink 不可用的环境自动 skip"一致。顺带核实：越界目标文件确实未被删除，删的只是链接本身（且前提不成立），**不存在路径穿越缺陷**。

## 2026-10-22 浏览额度按「不同用户」计次 + 额度口径统一（改造后基线）

> 触发：资料查看额度由"请求次数"改为"当天不同 `user_id` 个数"；同时修正 `/users/me/quotas` 的上限来源与时区日键。改动文件：`app/core/redis.py`、`app/services/discovery.py`、`app/services/quotas.py`、`app/api/routes/ai_moxiang.py`、`scripts/diagnose_login_blocker.py`、`tests/test_discovery_features.py`。**无 schema/迁移、无接口字段结构变化。**

| 检查 | 命令 | 结果 | 结论 |
| --- | --- | --- | --- |
| 后端全量无集成测试 | `.venv/Scripts/python.exe -m pytest --ignore=tests/integration -q` | `7 failed, 2751 passed, 15 skipped in 429.02s` | 7 项**全部为环境缺失**，0 业务回归 |
| 额度/会员共享定向 | `pytest tests/test_vip_authorization_consistency.py tests/test_discovery_features.py -k "membership_row_is_shared or browse or quota" -q` | `11 passed` | 额度解析与会员来源仍共享同一行 |
| 浏览额度相关集成（真实 MySQL） | `AI_TEST_DATABASE_URL=...` + `pytest tests/integration/ai/test_ai_recommend_real_db.py -k "browse_side_effects or view_profile_still" -q` | `2 passed` | `include_card` 仍无副作用；`view_profile` 单次仍 +1（计数键类型未变） |
| 全仓 Ruff | `ruff check app tests scripts` | `All checks passed!` | 0 告警 |

### 失败清单（7 项，全部环境归因）

| 测试 | 归因 |
| --- | --- |
| `test_ai_governance_contracts::test_ai_product_and_security_decisions_are_frozen` | 缺 `E:/Xuanshiai/PRODUCT.md` |
| `test_memory_docs_contract::test_product_md_declares_memory_kernel_shadow_scope` | 同上 |
| `test_memory_docs_contract::test_product_md_declares_deferred_scope` | 同上 |
| `test_memory_docs_contract::test_architecture_doc_declares_frozen_contract` | 缺 `E:/Xuanshiai/docs/architecture/ai-memory-kernel-core-v1.md` |
| `test_memory_docs_contract::test_architecture_doc_declares_no_downstream_switch_and_privacy_floor` | 同上 |
| `test_memory_docs_contract::test_architecture_doc_declares_subject_write_guard` | 同上 |
| `test_community_demo_seed::test_member_seed_assets_resolve_to_frontend_files` | 缺同级前端仓 `xuanshiai-vue`（实际在 `no upload/` 下，非同级） |

### 与 2026-10-19 基线（`8 failed / 2678 passed / 15 skipped`）的差异

- 失败数 8 → 7：`test_ai_profile_sessions::test_extraction_accumulates_fields_on_latest_draft` 本次**转绿**。此前三次复跑全败、曾判定为实现缺陷（`draft_id` 无写入点），本轮改为通过 ⇒ 该用例受执行顺序/库内状态影响，**结论需重开观察**，不应继续当作确定性失败。
- `passed` 2678 → 2751（+73）：其中 11 条为本次新增的额度用例，其余来自工作区已合并的上游测试（`3577c89` 含 upstream merge）。
- 本次改造首轮全量曾出现 `9 failed`，多出的是 `test_vip_authorization_consistency::test_effective_membership_row_is_shared_by_status_and_rights_consumers`——原因是 `resolve_browse_limit` 一度用 `isinstance(db, AsyncSession)` 跳过会员查询，导致额度解析不再与会员来源共享同一行。**已移除该保护**（生产路径 db 恒为 AsyncSession），并把该断言恢复为 3 次调用。

### 新增/重写用例（`tests/test_discovery_features.py`）

| 用例 | 作用 |
| --- | --- |
| `test_profile_browse_quota_uses_redis_fallback_reader`（重写） | 白盒改打桩 `consume_daily_unique`，验证 -1（已计费）分支返回剩余 |
| `test_browse_quota_uses_redis_fallback_for_remaining_count`（重写） | 同口径，固定 limit 后断言 `limit-1` |
| `test_repeat_view_of_same_target_consumes_once` | 同一 target 3 次 ⇒ 剩余 [7,7,7]、台账只 1 条 |
| `test_ninth_distinct_target_is_rejected` | 8 个不同用户依次 7→0，第 9 个 429 |
| `test_high_match_bonus_serves_extra_distinct_targets` | 常规满后高匹配走奖励池，返回 4 |
| `test_bonus_pool_exhausted_then_rejected` | 8+5=13 个成功后第 14 个 429 |
| `test_exhausted_quota_still_opens_already_viewed_target` | 额度耗尽后打开已看过用户仍放行（返回 0） |
| `test_points_pool_marks_target_to_avoid_double_charge` | 积分池扣一次后重复看不重复扣（seen 生效） |
| `test_browse_quota_keys_use_utc_daily_key` | 计数键与 seen 键均为 UTC 日键且不相等 |
| `test_resolve_browse_limit_reads_snapshot_for_non_vip` | 普通用户上限来自快照 |
| `test_resolve_browse_limit_reads_package_rights_for_vip` | VIP 上限来自套餐 rights |
| `test_quota_summary_uses_same_browse_limit_as_discovery` | `/users/me/quotas` 与扣费上限同源 |
