-- =============================================================================
-- 模拟登录会话标记列迁移（A12）（up）
--
-- 给 user_session 增加 `impersonated_by`（bigint unsigned 可空，NULL=正常登录会话），
-- 记录发起本次模拟登录的后台管理员 id，供安全审计与只读守卫回溯。可重复执行：
-- 列已存在时跳过。
--
-- 与代码的关系：模拟登录（app/services/auth.py:create_impersonation_session）写入
-- 该列并在签发的短时 access token 里带上 imp 声明；只读中间件（app/main.py）据此
-- 拒绝写方法。普通登录不写该列，行为完全不变。
-- =============================================================================

SET NAMES utf8mb4;

-- 幂等补列：impersonated_by
SET @u_impersonated_missing = (
    SELECT GROUP_CONCAT(CONCAT('ADD COLUMN ', w.column_ddl) ORDER BY w.ord SEPARATOR ', ')
    FROM (
        SELECT 1 AS ord, 'impersonated_by' AS column_name,
               '`impersonated_by` bigint unsigned DEFAULT NULL COMMENT ''模拟登录发起管理员 id（A12，NULL=正常登录会话）''' AS column_ddl
    ) AS w
    JOIN INFORMATION_SCHEMA.TABLES t
      ON t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = 'user_session'
    LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
      ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'user_session' AND c.COLUMN_NAME = w.column_name
    WHERE c.COLUMN_NAME IS NULL
);
SET @u_impersonated_ddl = IF(@u_impersonated_missing IS NULL, 'SELECT 1',
    CONCAT('ALTER TABLE `user_session` ', @u_impersonated_missing));
PREPARE u_impersonated_stmt FROM @u_impersonated_ddl;
EXECUTE u_impersonated_stmt;
DEALLOCATE PREPARE u_impersonated_stmt;

-- 幂等补索引：idx_session_impersonated_by（审计按管理员回溯模拟会话）
SET @u_imp_index_exists = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_session'
      AND INDEX_NAME = 'idx_session_impersonated_by'
);
SET @u_imp_index_ddl = IF(@u_imp_index_exists > 0, 'SELECT 1',
    'CREATE INDEX `idx_session_impersonated_by` ON `user_session` (`impersonated_by`)');
PREPARE u_imp_index_stmt FROM @u_imp_index_ddl;
EXECUTE u_imp_index_stmt;
DEALLOCATE PREPARE u_imp_index_stmt;
