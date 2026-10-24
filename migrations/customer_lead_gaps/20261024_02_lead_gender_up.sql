-- =============================================================================
-- 客源线索性别列迁移（A13）（up）
--
-- 给 customer_lead 增加 `gender`（0未知 1男 2女，默认 0），供「推广红娘获客
-- 统计」按男/女拆分客源。可重复执行：列已存在时跳过。
--
-- 与代码的关系：后端 get_lead / list_leads / create_lead / update_lead 通过
-- information_schema 探测该列是否存在，未迁移时静默降级（不报错），迁移后即生效。
-- =============================================================================

SET NAMES utf8mb4;

-- 幂等补列：gender
SET @cl_gender_missing = (
    SELECT GROUP_CONCAT(CONCAT('ADD COLUMN ', w.column_ddl) ORDER BY w.ord SEPARATOR ', ')
    FROM (
        SELECT 1 AS ord, 'gender' AS column_name,
               '`gender` tinyint NOT NULL DEFAULT 0 COMMENT ''性别 0未知 1男 2女（A13）''' AS column_ddl
    ) AS w
    JOIN INFORMATION_SCHEMA.TABLES t
      ON t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = 'customer_lead'
    LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
      ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'customer_lead' AND c.COLUMN_NAME = w.column_name
    WHERE c.COLUMN_NAME IS NULL
);
SET @cl_gender_ddl = IF(@cl_gender_missing IS NULL, 'SELECT 1',
    CONCAT('ALTER TABLE `customer_lead` ', @cl_gender_missing));
PREPARE cl_gender_stmt FROM @cl_gender_ddl;
EXECUTE cl_gender_stmt;
DEALLOCATE PREPARE cl_gender_stmt;
