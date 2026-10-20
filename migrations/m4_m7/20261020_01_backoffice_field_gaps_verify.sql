-- 后台运营补列迁移（B1 门店 / B2 互选活动）校验（verify）。
-- 在执行 up.sql 后运行：任何一条查询结果与注释中的期望不符，即迁移未完成或被跳过。
-- Run with the intended database selected (MySQL 8+).

-- 1) 补列齐备性：期望返回 0 行；任何返回行都是缺失的列（共 12 列：organization 5 + mutual 7）。
SELECT w.table_name AS missing_table, w.column_name AS missing_column
FROM (
    SELECT 'organization' AS table_name, 'logo' AS column_name
    UNION ALL SELECT 'organization', 'address'
    UNION ALL SELECT 'organization', 'commission_mode'
    UNION ALL SELECT 'organization', 'commission_value'
    UNION ALL SELECT 'organization', 'intro'
    UNION ALL SELECT 'mutual_selection_activity', 'signup_start_time'
    UNION ALL SELECT 'mutual_selection_activity', 'signup_end_time'
    UNION ALL SELECT 'mutual_selection_activity', 'mutual_start_time'
    UNION ALL SELECT 'mutual_selection_activity', 'mutual_end_time'
    UNION ALL SELECT 'mutual_selection_activity', 'activity_fee'
    UNION ALL SELECT 'mutual_selection_activity', 'show_wechat_direct'
    UNION ALL SELECT 'mutual_selection_activity', 'show_matchmaker_push'
) AS w
LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
  ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = w.table_name
     AND c.COLUMN_NAME = w.column_name
WHERE c.COLUMN_NAME IS NULL;

-- 2) 列定义明细：期望返回 12 行，类型与默认值与 up.sql 一致。
SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND (
    (TABLE_NAME = 'organization'
      AND COLUMN_NAME IN ('logo', 'address', 'commission_mode', 'commission_value', 'intro'))
    OR (TABLE_NAME = 'mutual_selection_activity'
      AND COLUMN_NAME IN ('signup_start_time', 'signup_end_time', 'mutual_start_time',
                          'mutual_end_time', 'activity_fee', 'show_wechat_direct',
                          'show_matchmaker_push'))
  )
ORDER BY TABLE_NAME, COLUMN_NAME;

-- 3) NOT NULL 列必须带默认值：期望返回 0 行（存量行才能自动落默认值）。
SELECT TABLE_NAME, COLUMN_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND (
    (TABLE_NAME = 'organization'
      AND COLUMN_NAME IN ('logo', 'address', 'commission_mode', 'commission_value', 'intro'))
    OR (TABLE_NAME = 'mutual_selection_activity'
      AND COLUMN_NAME IN ('signup_start_time', 'signup_end_time', 'mutual_start_time',
                          'mutual_end_time', 'activity_fee', 'show_wechat_direct',
                          'show_matchmaker_push'))
  )
  AND IS_NULLABLE = 'NO'
  AND COLUMN_DEFAULT IS NULL;
