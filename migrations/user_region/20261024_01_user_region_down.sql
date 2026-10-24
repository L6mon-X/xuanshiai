-- =============================================================================
-- 平台用户属地列迁移（A12）（down）
--
-- 回滚 20261024_01_user_region_up.sql：删除 users.ip_region / phone_region 两列。
--
-- 警告：DROP COLUMN 会永久丢弃已回填的属地数据。可重复执行：列不存在时跳过。
-- =============================================================================

SET NAMES utf8mb4;

SET @u_region_drop = (
    SELECT GROUP_CONCAT(CONCAT('DROP COLUMN `', c.COLUMN_NAME, '`') ORDER BY c.COLUMN_NAME SEPARATOR ', ')
    FROM INFORMATION_SCHEMA.COLUMNS c
    WHERE c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'users'
      AND c.COLUMN_NAME IN ('ip_region', 'phone_region')
);
SET @u_region_ddl = IF(@u_region_drop IS NULL, 'SELECT 1',
    CONCAT('ALTER TABLE `users` ', @u_region_drop));
PREPARE u_region_drop_stmt FROM @u_region_ddl;
EXECUTE u_region_drop_stmt;
DEALLOCATE PREPARE u_region_drop_stmt;
