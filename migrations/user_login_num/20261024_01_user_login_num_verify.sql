-- 平台用户登录次数列迁移（A12）校验（verify）。
-- 在执行 up.sql 后运行：任何一条查询结果与注释中的期望不符，即迁移未完成或被跳过。
-- Run with the intended database selected (MySQL 8+).

-- 1) 补列齐备性：期望返回 0 行；任何返回行都是缺失的列。
SELECT w.table_name AS missing_table, w.column_name AS missing_column
FROM (
    SELECT 'users' AS table_name, 'login_num' AS column_name
) AS w
LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
  ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = w.table_name
     AND c.COLUMN_NAME = w.column_name
WHERE c.COLUMN_NAME IS NULL;

-- 2) 列定义明细：期望返回 1 行，类型 int / 非空 / 默认 0，与 up.sql 一致。
SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'users'
  AND COLUMN_NAME = 'login_num';

-- 3) NOT NULL 列必须带默认值：期望返回 0 行（存量行才能自动落 0）。
SELECT TABLE_NAME, COLUMN_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'users'
  AND COLUMN_NAME = 'login_num'
  AND IS_NULLABLE = 'NO'
  AND COLUMN_DEFAULT IS NULL;
