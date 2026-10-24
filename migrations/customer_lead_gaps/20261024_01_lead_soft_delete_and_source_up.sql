-- =============================================================================
-- 客源线索缺口补全迁移（A14 来源字典 / A16 软删除）（up）
--
-- 背景：后端接口缺失清单.md
--   A16 客源删除：新增 DELETE /admin/customer-leads/{id} 与 batch-delete，采用
--       软删除（deleted_at）。删除后的客源不应再占用联系方式唯一键，因此
--       active_phone / active_wechat 生成列需纳入 deleted_at 判定。
--   A14 来源管理：新增 customer_lead_source 字典表，支撑来源 CRUD/reorder；
--       与既有自由文本 customer_lead.source 按名称对齐（兼容并存）。
--
-- 幂等：全部基于 INFORMATION_SCHEMA 检查 + PREPARE/EXECUTE 动态 DDL，可重复
--       执行；表不存在时静默跳过。请在已选定目标数据库的会话中执行（MySQL 8+）。
-- =============================================================================

SET NAMES utf8mb4;

-- -----------------------------------------------------------------------------
-- 0. 新建来源字典表 customer_lead_source（A14）
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `customer_lead_source` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `name` varchar(64) NOT NULL COMMENT '来源名称（与 customer_lead.source 自由文本按名称对齐）',
    `color` varchar(16) DEFAULT NULL COMMENT '展示颜色',
    `enabled` tinyint NOT NULL DEFAULT 1 COMMENT '是否启用 1是 0否',
    `sort` int NOT NULL DEFAULT 0 COMMENT '排序，越小越靠前',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_customer_lead_source` (`name`),
    KEY `idx_customer_lead_source_sort` (`enabled`, `sort`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客源来源字典配置';

-- 幂等播种来源（与前端 love-customer-list 常量一致 + 批量导入）；存在同名则跳过，不覆盖运营手工调整
INSERT IGNORE INTO `customer_lead_source` (`name`, `sort`, `enabled`) VALUES
    ('抖音', 10, 1), ('微信群', 20, 1), ('本地群', 30, 1), ('身边朋友', 40, 1),
    ('同行群', 50, 1), ('朋友圈', 60, 1), ('朋友介绍', 70, 1), ('QQ', 80, 1),
    ('其他渠道', 90, 1), ('落地页', 100, 1), ('批量导入', 110, 1);

-- -----------------------------------------------------------------------------
-- 1. customer_lead 幂等补列：deleted_at / deleted_by（A16）
-- -----------------------------------------------------------------------------
SET @cl_soft_missing = (
    SELECT GROUP_CONCAT(CONCAT('ADD COLUMN ', w.column_ddl) ORDER BY w.ord SEPARATOR ', ')
    FROM (
        SELECT 1 AS ord, 'deleted_at' AS column_name,
               '`deleted_at` datetime DEFAULT NULL COMMENT ''软删除时间；空为有效''' AS column_ddl
        UNION ALL SELECT 2, 'deleted_by',
               '`deleted_by` bigint unsigned DEFAULT NULL COMMENT ''删除操作人 matchmaker_admin_account.id'''
    ) AS w
    JOIN INFORMATION_SCHEMA.TABLES t
      ON t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = 'customer_lead'
    LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
      ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'customer_lead' AND c.COLUMN_NAME = w.column_name
    WHERE c.COLUMN_NAME IS NULL
);
SET @cl_soft_ddl = IF(@cl_soft_missing IS NULL, 'SELECT 1',
    CONCAT('ALTER TABLE `customer_lead` ', @cl_soft_missing));
PREPARE cl_soft_stmt FROM @cl_soft_ddl;
EXECUTE cl_soft_stmt;
DEALLOCATE PREPARE cl_soft_stmt;

-- 2. 幂等创建索引 idx_customer_lead_deleted
SET @cl_tbl_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customer_lead');
SET @cl_idx_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customer_lead'
      AND INDEX_NAME = 'idx_customer_lead_deleted');
SET @cl_idx_ddl = IF(@cl_tbl_exists > 0 AND @cl_idx_exists = 0,
    'ALTER TABLE `customer_lead` ADD KEY `idx_customer_lead_deleted` (`deleted_at`)', 'SELECT 1');
PREPARE cl_idx_stmt FROM @cl_idx_ddl;
EXECUTE cl_idx_stmt;
DEALLOCATE PREPARE cl_idx_stmt;

-- -----------------------------------------------------------------------------
-- 3. 重建 active_phone 生成列（纳入 deleted_at 判定）
--    旧定义不含 deleted_at 时才重建；重建前先删唯一索引，重建后恢复。
-- -----------------------------------------------------------------------------
SET @cl_ap_needs = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS c
    JOIN INFORMATION_SCHEMA.TABLES t
      ON t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = 'customer_lead'
    WHERE c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'customer_lead'
      AND c.COLUMN_NAME = 'active_phone'
      AND c.GENERATION_EXPRESSION NOT LIKE '%deleted_at%'
);
SET @cl_ap_drop = IF(@cl_tbl_exists > 0 AND @cl_ap_needs > 0,
    'ALTER TABLE `customer_lead` DROP INDEX `uk_customer_lead_active_phone`, DROP COLUMN `active_phone`',
    'SELECT 1');
PREPARE cl_ap_drop_stmt FROM @cl_ap_drop;
EXECUTE cl_ap_drop_stmt;
DEALLOCATE PREPARE cl_ap_drop_stmt;

SET @cl_ap_add = IF(@cl_tbl_exists > 0 AND @cl_ap_needs > 0,
    'ALTER TABLE `customer_lead` ADD COLUMN `active_phone` varchar(32) GENERATED ALWAYS AS (CASE WHEN `status` IN (''LOST'',''CLOSED'') OR `deleted_at` IS NOT NULL THEN NULL ELSE NULLIF(TRIM(`phone`), '''') END) STORED COMMENT ''有效手机号（弃海/关闭/删除为NULL，唯一）''',
    'SELECT 1');
PREPARE cl_ap_add_stmt FROM @cl_ap_add;
EXECUTE cl_ap_add_stmt;
DEALLOCATE PREPARE cl_ap_add_stmt;

SET @cl_ap_uk = IF(@cl_tbl_exists > 0 AND @cl_ap_needs > 0,
    'ALTER TABLE `customer_lead` ADD UNIQUE KEY `uk_customer_lead_active_phone` (`active_phone`)',
    'SELECT 1');
PREPARE cl_ap_uk_stmt FROM @cl_ap_uk;
EXECUTE cl_ap_uk_stmt;
DEALLOCATE PREPARE cl_ap_uk_stmt;

-- -----------------------------------------------------------------------------
-- 4. 重建 active_wechat 生成列（纳入 deleted_at 判定）
-- -----------------------------------------------------------------------------
SET @cl_aw_needs = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS c
    JOIN INFORMATION_SCHEMA.TABLES t
      ON t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = 'customer_lead'
    WHERE c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'customer_lead'
      AND c.COLUMN_NAME = 'active_wechat'
      AND c.GENERATION_EXPRESSION NOT LIKE '%deleted_at%'
);
SET @cl_aw_drop = IF(@cl_tbl_exists > 0 AND @cl_aw_needs > 0,
    'ALTER TABLE `customer_lead` DROP INDEX `uk_customer_lead_active_wechat`, DROP COLUMN `active_wechat`',
    'SELECT 1');
PREPARE cl_aw_drop_stmt FROM @cl_aw_drop;
EXECUTE cl_aw_drop_stmt;
DEALLOCATE PREPARE cl_aw_drop_stmt;

SET @cl_aw_add = IF(@cl_tbl_exists > 0 AND @cl_aw_needs > 0,
    'ALTER TABLE `customer_lead` ADD COLUMN `active_wechat` varchar(128) GENERATED ALWAYS AS (CASE WHEN `status` IN (''LOST'',''CLOSED'') OR `deleted_at` IS NOT NULL THEN NULL ELSE NULLIF(TRIM(`wechat`), '''') END) STORED COMMENT ''有效微信（弃海/关闭/删除为NULL，唯一）''',
    'SELECT 1');
PREPARE cl_aw_add_stmt FROM @cl_aw_add;
EXECUTE cl_aw_add_stmt;
DEALLOCATE PREPARE cl_aw_add_stmt;

SET @cl_aw_uk = IF(@cl_tbl_exists > 0 AND @cl_aw_needs > 0,
    'ALTER TABLE `customer_lead` ADD UNIQUE KEY `uk_customer_lead_active_wechat` (`active_wechat`)',
    'SELECT 1');
PREPARE cl_aw_uk_stmt FROM @cl_aw_uk;
EXECUTE cl_aw_uk_stmt;
DEALLOCATE PREPARE cl_aw_uk_stmt;
