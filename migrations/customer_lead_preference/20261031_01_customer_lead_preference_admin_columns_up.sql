-- =============================================================================
-- 客源线索择偶要求暂存表：补「后台单选口径」字符串列（up）
--
-- 背景：PreferenceUpdateRequest 自 2026-10-27 起新增一套与后台会员管理一致的单选字符串
-- 字段（income_range / education_requirement / marriage_requirement / housing_expectation /
-- smoking_expectation / drinking_expectation / marriage_timeline / preferred_occupation），
-- 但 customer_lead_preference 建表（20261027_02）时只包含 C 端列（_LEAD_PREF_COLUMNS）。
-- 未入库客源写择偶要求时 _upsert_lead_preference 用 model_dump(exclude_unset=True) 把
-- income_range 等列拼进 UPDATE/INSERT，线上直接 500：
--   (1054, "Unknown column 'income_range' in 'field list'")
--
-- 幂等约定：INFORMATION_SCHEMA 检查 + PREPARE/EXECUTE 动态 DDL；表缺失或列已存在时跳过。
-- Run with the intended database selected (MySQL 8+).
-- =============================================================================

SET SESSION group_concat_max_len = 4194304;
SET NAMES utf8mb4;

SET @clp_missing = (
    SELECT GROUP_CONCAT(CONCAT('ADD COLUMN ', w.column_ddl) ORDER BY w.ord SEPARATOR ', ')
    FROM (
        SELECT 1 AS ord, 'income_range' AS column_name,
               '`income_range` varchar(32) DEFAULT NULL COMMENT ''期望年收入（后台单选口径）''' AS column_ddl
        UNION ALL SELECT 2, 'education_requirement',
               '`education_requirement` varchar(32) DEFAULT NULL COMMENT ''期望学历（后台单选口径）'''
        UNION ALL SELECT 3, 'marriage_requirement',
               '`marriage_requirement` varchar(32) DEFAULT NULL COMMENT ''婚况要求（后台单选口径）'''
        UNION ALL SELECT 4, 'housing_expectation',
               '`housing_expectation` varchar(32) DEFAULT NULL COMMENT ''住房期望（后台单选口径）'''
        UNION ALL SELECT 5, 'smoking_expectation',
               '`smoking_expectation` varchar(32) DEFAULT NULL COMMENT ''吸烟期望（后台单选口径）'''
        UNION ALL SELECT 6, 'drinking_expectation',
               '`drinking_expectation` varchar(32) DEFAULT NULL COMMENT ''喝酒期望（后台单选口径）'''
        UNION ALL SELECT 7, 'marriage_timeline',
               '`marriage_timeline` varchar(32) DEFAULT NULL COMMENT ''结婚计划（后台单选口径）'''
        UNION ALL SELECT 8, 'preferred_occupation',
               '`preferred_occupation` varchar(128) DEFAULT NULL COMMENT ''期望职业（后台单选口径）'''
    ) AS w
    JOIN INFORMATION_SCHEMA.TABLES t
      ON t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = 'customer_lead_preference'
    LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
      ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'customer_lead_preference' AND c.COLUMN_NAME = w.column_name
    WHERE c.COLUMN_NAME IS NULL
);

SET @clp_ddl = IF(
    @clp_missing IS NULL,
    'SELECT 1',
    CONCAT('ALTER TABLE `customer_lead_preference` ', @clp_missing)
);
PREPARE clp_cols_stmt FROM @clp_ddl;
EXECUTE clp_cols_stmt;
DEALLOCATE PREPARE clp_cols_stmt;
