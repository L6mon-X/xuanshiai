-- =============================================================================
-- 平台用户登录次数列迁移（A12）（down）
--
-- 回滚 20261024_01_user_login_num_up.sql：删除 users.login_num 列。
--
-- 警告：DROP COLUMN 会永久丢弃累计登录次数数据（可由 user_login_log 重新统计回填，
-- 但非原值）。可重复执行：列不存在时跳过。
-- =============================================================================

SET NAMES utf8mb4;

SET @u_login_num_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'login_num'
);
SET @u_login_num_drop = IF(@u_login_num_exists > 0,
    'ALTER TABLE `users` DROP COLUMN `login_num`', 'SELECT 1');
PREPARE u_login_num_drop_stmt FROM @u_login_num_drop;
EXECUTE u_login_num_drop_stmt;
DEALLOCATE PREPARE u_login_num_drop_stmt;
