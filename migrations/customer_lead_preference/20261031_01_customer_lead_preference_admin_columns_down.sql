-- =============================================================================
-- 客源线索择偶要求暂存表：回滚「后台单选口径」字符串列（down）
-- 幂等：列不存在时跳过。Run with the intended database selected (MySQL 8+).
-- =============================================================================

SET SESSION group_concat_max_len = 4194304;
SET NAMES utf8mb4;

SET @clp_drop = (
    SELECT GROUP_CONCAT(CONCAT('DROP COLUMN `', w.column_name, '`') ORDER BY w.ord SEPARATOR ', ')
    FROM (
        SELECT 1 AS ord, 'income_range' AS column_name
        UNION ALL SELECT 2, 'education_requirement'
        UNION ALL SELECT 3, 'marriage_requirement'
        UNION ALL SELECT 4, 'housing_expectation'
        UNION ALL SELECT 5, 'smoking_expectation'
        UNION ALL SELECT 6, 'drinking_expectation'
        UNION ALL SELECT 7, 'marriage_timeline'
        UNION ALL SELECT 8, 'preferred_occupation'
    ) AS w
    JOIN INFORMATION_SCHEMA.TABLES t
      ON t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = 'customer_lead_preference'
    JOIN INFORMATION_SCHEMA.COLUMNS c
      ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'customer_lead_preference' AND c.COLUMN_NAME = w.column_name
);

SET @clp_ddl = IF(
    @clp_drop IS NULL,
    'SELECT 1',
    CONCAT('ALTER TABLE `customer_lead_preference` ', @clp_drop)
);
PREPARE clp_drop_stmt FROM @clp_ddl;
EXECUTE clp_drop_stmt;
DEALLOCATE PREPARE clp_drop_stmt;
