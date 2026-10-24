-- =============================================================================
-- 客源线索性别列迁移（A13）（down）
--
-- 回滚 20261024_02_lead_gender_up.sql：删除 customer_lead.gender 列。
--
-- 警告：DROP COLUMN 会永久丢弃已登记的客源性别数据。可重复执行：列不存在时跳过。
-- =============================================================================

SET NAMES utf8mb4;

SET @cl_gender_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customer_lead' AND COLUMN_NAME = 'gender'
);
SET @cl_gender_drop = IF(@cl_gender_exists > 0,
    'ALTER TABLE `customer_lead` DROP COLUMN `gender`', 'SELECT 1');
PREPARE cl_gender_drop_stmt FROM @cl_gender_drop;
EXECUTE cl_gender_drop_stmt;
DEALLOCATE PREPARE cl_gender_drop_stmt;
