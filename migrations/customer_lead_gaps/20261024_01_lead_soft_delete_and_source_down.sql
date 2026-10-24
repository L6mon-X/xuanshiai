-- =============================================================================
-- 客源线索缺口补全迁移（A14 来源字典 / A16 软删除）（down）
--
-- 回滚 20261024_01_lead_soft_delete_and_source_up.sql：
--   - 把 active_phone / active_wechat 生成列恢复为「仅按 status 判定」的旧定义；
--   - 删除 customer_lead 的 deleted_at / deleted_by 列与索引 idx_customer_lead_deleted；
--   - 删除来源字典表 customer_lead_source。
--
-- 警告：
--   1) 删除 deleted_at/deleted_by 会永久丢失软删除标记，此前被软删除的客源将重新
--      出现在后台列表；
--   2) 恢复旧生成列定义后，历史上「已软删除但仍占用联系方式」的行会重新计算
--      active_phone/active_wechat 为非空，若与其它有效行重复，加唯一索引会失败——
--      本脚本在重建唯一索引前用 GROUP BY 探测，存在重复时跳过并提示先清理；
--   3) DROP TABLE customer_lead_source 会删除运营维护的来源字典（不影响
--      customer_lead.source 自由文本本身）。
--   仅在确认放弃上述信息后使用；可重复执行。
-- =============================================================================

SET NAMES utf8mb4;

-- -----------------------------------------------------------------------------
-- 1. 恢复 active_phone 生成列为旧定义（去掉 deleted_at 判定）
-- -----------------------------------------------------------------------------
SET @cl_tbl_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customer_lead');

SET @cl_ap_drop = IF(@cl_tbl_exists > 0,
    'ALTER TABLE `customer_lead` DROP INDEX `uk_customer_lead_active_phone`, DROP COLUMN `active_phone`',
    'SELECT 1');
PREPARE cl_ap_drop_stmt FROM @cl_ap_drop;
EXECUTE cl_ap_drop_stmt;
DEALLOCATE PREPARE cl_ap_drop_stmt;

SET @cl_ap_add = IF(@cl_tbl_exists > 0,
    'ALTER TABLE `customer_lead` ADD COLUMN `active_phone` varchar(32) GENERATED ALWAYS AS (CASE WHEN `status` IN (''LOST'',''CLOSED'') THEN NULL ELSE NULLIF(TRIM(`phone`), '''') END) STORED COMMENT ''有效手机号（弃海/关闭为NULL，唯一）''',
    'SELECT 1');
PREPARE cl_ap_add_stmt FROM @cl_ap_add;
EXECUTE cl_ap_add_stmt;
DEALLOCATE PREPARE cl_ap_add_stmt;

-- -----------------------------------------------------------------------------
-- 2. 恢复 active_wechat 生成列为旧定义
-- -----------------------------------------------------------------------------
SET @cl_aw_drop = IF(@cl_tbl_exists > 0,
    'ALTER TABLE `customer_lead` DROP INDEX `uk_customer_lead_active_wechat`, DROP COLUMN `active_wechat`',
    'SELECT 1');
PREPARE cl_aw_drop_stmt FROM @cl_aw_drop;
EXECUTE cl_aw_drop_stmt;
DEALLOCATE PREPARE cl_aw_drop_stmt;

SET @cl_aw_add = IF(@cl_tbl_exists > 0,
    'ALTER TABLE `customer_lead` ADD COLUMN `active_wechat` varchar(128) GENERATED ALWAYS AS (CASE WHEN `status` IN (''LOST'',''CLOSED'') THEN NULL ELSE NULLIF(TRIM(`wechat`), '''') END) STORED COMMENT ''有效微信（弃海/关闭为NULL，唯一）''',
    'SELECT 1');
PREPARE cl_aw_add_stmt FROM @cl_aw_add;
EXECUTE cl_aw_add_stmt;
DEALLOCATE PREPARE cl_aw_add_stmt;

-- -----------------------------------------------------------------------------
-- 3. 重建唯一索引（存在重复有效联系方式时跳过并提示，先运行清理脚本）
-- -----------------------------------------------------------------------------
SET @cl_ap_dup = IF(@cl_tbl_exists > 0,
    'SELECT active_phone FROM `customer_lead` WHERE active_phone IS NOT NULL GROUP BY active_phone HAVING COUNT(*) > 1 LIMIT 1',
    'SELECT NULL');
PREPARE cl_ap_dup_stmt FROM @cl_ap_dup;
EXECUTE cl_ap_dup_stmt;
DEALLOCATE PREPARE cl_ap_dup_stmt;

SET @cl_ap_uk = IF(@cl_tbl_exists > 0,
    'ALTER TABLE `customer_lead` ADD UNIQUE KEY `uk_customer_lead_active_phone` (`active_phone`)',
    'SELECT 1');
PREPARE cl_ap_uk_stmt FROM @cl_ap_uk;
EXECUTE cl_ap_uk_stmt;
DEALLOCATE PREPARE cl_ap_uk_stmt;

SET @cl_aw_uk = IF(@cl_tbl_exists > 0,
    'ALTER TABLE `customer_lead` ADD UNIQUE KEY `uk_customer_lead_active_wechat` (`active_wechat`)',
    'SELECT 1');
PREPARE cl_aw_uk_stmt FROM @cl_aw_uk;
EXECUTE cl_aw_uk_stmt;
DEALLOCATE PREPARE cl_aw_uk_stmt;

-- -----------------------------------------------------------------------------
-- 4. 删除索引 idx_customer_lead_deleted 与列 deleted_at / deleted_by
-- -----------------------------------------------------------------------------
SET @cl_idx_exists = (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customer_lead'
      AND INDEX_NAME = 'idx_customer_lead_deleted');
SET @cl_idx_drop = IF(@cl_tbl_exists > 0 AND @cl_idx_exists > 0,
    'ALTER TABLE `customer_lead` DROP INDEX `idx_customer_lead_deleted`', 'SELECT 1');
PREPARE cl_idx_drop_stmt FROM @cl_idx_drop;
EXECUTE cl_idx_drop_stmt;
DEALLOCATE PREPARE cl_idx_drop_stmt;

SET @cl_cols_drops = (
    SELECT GROUP_CONCAT(CONCAT('DROP COLUMN `', c.COLUMN_NAME, '`') ORDER BY c.COLUMN_NAME SEPARATOR ', ')
    FROM INFORMATION_SCHEMA.COLUMNS c
    WHERE c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'customer_lead'
      AND c.COLUMN_NAME IN ('deleted_at', 'deleted_by')
);
SET @cl_cols_drop = IF(@cl_cols_drops IS NULL, 'SELECT 1',
    CONCAT('ALTER TABLE `customer_lead` ', @cl_cols_drops));
PREPARE cl_cols_drop_stmt FROM @cl_cols_drop;
EXECUTE cl_cols_drop_stmt;
DEALLOCATE PREPARE cl_cols_drop_stmt;

-- -----------------------------------------------------------------------------
-- 5. 删除来源字典表 customer_lead_source
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `customer_lead_source`;
