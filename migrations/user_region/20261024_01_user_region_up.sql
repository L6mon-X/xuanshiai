-- =============================================================================
-- 平台用户属地列迁移（A12）（up）
--
-- 给 users 增加 `ip_region`（IP 属地）与 `phone_region`（手机号归属地）两列，
-- 供账号管理列表/详情展示。可重复执行：列已存在时跳过。
--
-- 口径说明（本轮「先补列 + 展示」）：本轮只做**存储与展示**，不接入 IP→属地 /
-- 号码归属地的自动解析（全项目当前无解析器，属外部依赖，待选型后再接线）。
-- 两列可为空，由后续解析任务或人工回填；列表/详情按缺列降级为 NULL。
-- =============================================================================

SET NAMES utf8mb4;

SET @u_region_missing = (
    SELECT GROUP_CONCAT(CONCAT('ADD COLUMN ', w.column_ddl) ORDER BY w.ord SEPARATOR ', ')
    FROM (
        SELECT 1 AS ord, 'ip_region' AS column_name,
               '`ip_region` varchar(64) DEFAULT NULL COMMENT ''IP 属地（A12，展示用，待解析回填）''' AS column_ddl
        UNION ALL
        SELECT 2 AS ord, 'phone_region' AS column_name,
               '`phone_region` varchar(64) DEFAULT NULL COMMENT ''手机号归属地（A12，展示用，待解析回填）''' AS column_ddl
    ) AS w
    JOIN INFORMATION_SCHEMA.TABLES t
      ON t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = 'users'
    LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
      ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'users' AND c.COLUMN_NAME = w.column_name
    WHERE c.COLUMN_NAME IS NULL
);
SET @u_region_ddl = IF(@u_region_missing IS NULL, 'SELECT 1',
    CONCAT('ALTER TABLE `users` ', @u_region_missing));
PREPARE u_region_stmt FROM @u_region_ddl;
EXECUTE u_region_stmt;
DEALLOCATE PREPARE u_region_stmt;
