-- 后台运营新表迁移（A4/A5/A7/A8/A9/A10）校验（verify）。
-- 在执行 up.sql 后运行：任何一条查询结果与注释中的期望不符，即迁移未完成或被跳过。
-- Run with the intended database selected (MySQL 8+).

-- 1) 新表齐备性：期望返回 8 行（不缺表）。
SELECT t.table_name
FROM (
    SELECT 'admin_material_category' AS table_name
    UNION ALL SELECT 'admin_material'
    UNION ALL SELECT 'admin_qrcode'
    UNION ALL SELECT 'admin_sales_category'
    UNION ALL SELECT 'admin_sales_item'
    UNION ALL SELECT 'admin_sales_push'
    UNION ALL SELECT 'admin_lovecard_template'
    UNION ALL SELECT 'admin_lovecard_generation'
    UNION ALL SELECT 'member_abandonment'
    UNION ALL SELECT 'admin_alliance_activity'
) AS t
JOIN INFORMATION_SCHEMA.TABLES s
  ON s.TABLE_SCHEMA = DATABASE() AND s.TABLE_NAME = t.table_name
ORDER BY t.table_name;

-- 2) 缺表检查：期望返回 0 行。
SELECT t.table_name AS missing_table
FROM (
    SELECT 'admin_material_category' AS table_name
    UNION ALL SELECT 'admin_material'
    UNION ALL SELECT 'admin_qrcode'
    UNION ALL SELECT 'admin_sales_category'
    UNION ALL SELECT 'admin_sales_item'
    UNION ALL SELECT 'admin_sales_push'
    UNION ALL SELECT 'admin_lovecard_template'
    UNION ALL SELECT 'admin_lovecard_generation'
    UNION ALL SELECT 'member_abandonment'
    UNION ALL SELECT 'admin_alliance_activity'
) AS t
LEFT JOIN INFORMATION_SCHEMA.TABLES s
  ON s.TABLE_SCHEMA = DATABASE() AND s.TABLE_NAME = t.table_name
WHERE s.TABLE_NAME IS NULL;

-- 3) 关键索引：期望返回 0 行（缺索引的项）。
SELECT t.table_name AS missing_index
FROM (
    SELECT 'admin_material' AS table_name, 'idx_admin_material_category' AS index_name
    UNION ALL SELECT 'admin_qrcode', 'idx_admin_qrcode_status'
    UNION ALL SELECT 'admin_sales_push', 'idx_admin_sales_push_matchmaker'
    UNION ALL SELECT 'admin_lovecard_generation', 'idx_admin_lovecard_generation_batch'
    UNION ALL SELECT 'member_abandonment', 'idx_member_abandonment_user'
    UNION ALL SELECT 'admin_alliance_activity', 'idx_admin_alliance_activity_status'
) AS t
LEFT JOIN INFORMATION_SCHEMA.STATISTICS s
  ON s.TABLE_SCHEMA = DATABASE() AND s.TABLE_NAME = t.table_name
     AND s.INDEX_NAME = t.index_name
WHERE s.INDEX_NAME IS NULL;

-- 4) A9 历史回填幂等性：期望返回 0 行（同一会员不存在两条有效弃海记录）。
SELECT user_id, COUNT(*) AS active_rows
FROM `member_abandonment`
WHERE restored_at IS NULL
GROUP BY user_id
HAVING COUNT(*) > 1;
