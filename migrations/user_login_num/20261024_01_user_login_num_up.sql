-- =============================================================================
-- 平台用户登录次数列迁移（A12）（up）
--
-- 给 users 增加 `login_num`（累计登录次数，int 默认 0），供账号管理列表展示
-- 「登录次数」列并按其排序。可重复执行：列已存在时跳过。
--
-- 与代码的关系：登录链路（app/services/auth.py）在写 last_login_at 时，通过
-- information_schema 探测该列是否存在，未迁移时静默不计数（不报错）；迁移后
-- 每次登录自增 1。会员列表/详情的 login_num 出参同样按缺列降级为 NULL。
-- =============================================================================

SET NAMES utf8mb4;

-- 幂等补列：login_num
SET @u_login_num_missing = (
    SELECT GROUP_CONCAT(CONCAT('ADD COLUMN ', w.column_ddl) ORDER BY w.ord SEPARATOR ', ')
    FROM (
        SELECT 1 AS ord, 'login_num' AS column_name,
               '`login_num` int NOT NULL DEFAULT 0 COMMENT ''累计登录次数（A12）''' AS column_ddl
    ) AS w
    JOIN INFORMATION_SCHEMA.TABLES t
      ON t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = 'users'
    LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
      ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'users' AND c.COLUMN_NAME = w.column_name
    WHERE c.COLUMN_NAME IS NULL
);
SET @u_login_num_ddl = IF(@u_login_num_missing IS NULL, 'SELECT 1',
    CONCAT('ALTER TABLE `users` ', @u_login_num_missing));
PREPARE u_login_num_stmt FROM @u_login_num_ddl;
EXECUTE u_login_num_stmt;
DEALLOCATE PREPARE u_login_num_stmt;
