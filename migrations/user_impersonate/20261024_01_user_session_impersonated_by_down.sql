-- =============================================================================
-- 模拟登录会话标记列迁移（A12）（down）
--
-- 回滚 20261024_01_user_session_impersonated_by_up.sql：删除索引与 user_session.impersonated_by 列。
--
-- 可重复执行：列/索引不存在时跳过。删除后历史模拟登录会话的发起管理员标记将丢失，
-- 但 business_audit_log 中的 admin.impersonate.create 审计记录仍保留可回溯。
-- =============================================================================

SET NAMES utf8mb4;

-- 先删索引（存在才删）
SET @u_imp_index_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_session'
      AND INDEX_NAME = 'idx_session_impersonated_by'
);
SET @u_imp_index_drop = IF(@u_imp_index_exists > 0,
    'ALTER TABLE `user_session` DROP INDEX `idx_session_impersonated_by`', 'SELECT 1');
PREPARE u_imp_index_drop_stmt FROM @u_imp_index_drop;
EXECUTE u_imp_index_drop_stmt;
DEALLOCATE PREPARE u_imp_index_drop_stmt;

-- 再删列（存在才删）
SET @u_impersonated_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_session' AND COLUMN_NAME = 'impersonated_by'
);
SET @u_impersonated_drop = IF(@u_impersonated_exists > 0,
    'ALTER TABLE `user_session` DROP COLUMN `impersonated_by`', 'SELECT 1');
PREPARE u_impersonated_drop_stmt FROM @u_impersonated_drop;
EXECUTE u_impersonated_drop_stmt;
DEALLOCATE PREPARE u_impersonated_drop_stmt;
