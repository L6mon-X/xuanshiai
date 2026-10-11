-- 后台筛选参数补列迁移校验（verify）。
-- 在执行 up.sql 后运行：任何一条查询的结果与注释中的期望不符，即迁移未完成或被跳过。
-- Run with the intended database selected (MySQL 8+).

-- 1) 补列齐备性：期望返回 0 行；任何返回行都是缺失的列
--    （共 22 列：users 9 + user_profile 2 + customer_lead 11）。
SELECT w.table_name AS missing_table, w.column_name AS missing_column
FROM (
    SELECT 'users' AS table_name, 'source' AS column_name
    UNION ALL SELECT 'users', 'region'
    UNION ALL SELECT 'users', 'cert_status'
    UNION ALL SELECT 'users', 'wechat_added'
    UNION ALL SELECT 'users', 'promoted'
    UNION ALL SELECT 'users', 'newcomer'
    UNION ALL SELECT 'users', 'activity_signup'
    UNION ALL SELECT 'users', 'level'
    UNION ALL SELECT 'users', 'fetched_at'
    UNION ALL SELECT 'user_profile', 'car'
    UNION ALL SELECT 'user_profile', 'household'
    UNION ALL SELECT 'customer_lead', 'age'
    UNION ALL SELECT 'customer_lead', 'height'
    UNION ALL SELECT 'customer_lead', 'marriage'
    UNION ALL SELECT 'customer_lead', 'education'
    UNION ALL SELECT 'customer_lead', 'occupation'
    UNION ALL SELECT 'customer_lead', 'residence'
    UNION ALL SELECT 'customer_lead', 'hometown'
    UNION ALL SELECT 'customer_lead', 'xiangqin_status'
    UNION ALL SELECT 'customer_lead', 'bind_mode'
    UNION ALL SELECT 'customer_lead', 'wechat_added'
    UNION ALL SELECT 'customer_lead', 'assigned_at'
) AS w
LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
  ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = w.table_name
     AND c.COLUMN_NAME = w.column_name
WHERE c.COLUMN_NAME IS NULL;

-- 2) 列定义明细：期望返回 22 行，且类型与默认值与 up.sql 一致。
SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND ((TABLE_NAME = 'users' AND COLUMN_NAME IN ('source','region','cert_status','wechat_added','promoted','newcomer','activity_signup','level','fetched_at'))
    OR (TABLE_NAME = 'user_profile' AND COLUMN_NAME IN ('car','household'))
    OR (TABLE_NAME = 'customer_lead' AND COLUMN_NAME IN ('age','height','marriage','education','occupation','residence','hometown','xiangqin_status','bind_mode','wechat_added','assigned_at')))
ORDER BY TABLE_NAME, COLUMN_NAME;

-- 3) 索引：期望 4 行，NON_UNIQUE=1，列序与 up.sql 一致，且无前缀。
SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME, SUB_PART
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND INDEX_NAME IN ('idx_users_source','idx_users_fetched',
                     'idx_customer_lead_assigned','idx_customer_lead_xiangqin')
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;

-- 4) 存量数据不受影响：补列前已存在的会员行不得因为补列产生 NULL 之外的副作用。
--    期望返回 0 行（新增的 NOT NULL 列必须有默认值，存量行全部落到默认值）。
SELECT TABLE_NAME, COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND COLUMN_DEFAULT IS NULL AND IS_NULLABLE = 'NO'
  AND ((TABLE_NAME = 'users' AND COLUMN_NAME IN ('cert_status','wechat_added','promoted','newcomer','activity_signup'))
    OR (TABLE_NAME = 'customer_lead' AND COLUMN_NAME IN ('xiangqin_status','wechat_added')));
