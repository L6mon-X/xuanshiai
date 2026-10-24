-- 后台第三方适配模块新表迁移（A1/A2/A3/A6）校验（verify）。
-- 在执行 up.sql 后运行：任何一条查询结果与注释中的期望不符，即迁移未完成或被跳过。
-- Run with the intended database selected (MySQL 8+).

-- 1) 新表齐备性：期望返回 16 行（不缺表）。
SELECT t.table_name
FROM (
    SELECT 'admin_sms_signature' AS table_name
    UNION ALL     SELECT 'admin_sms_template' AS table_name
    UNION ALL     SELECT 'admin_sms_message' AS table_name
    UNION ALL     SELECT 'admin_outbound_number' AS table_name
    UNION ALL     SELECT 'admin_outbound_task' AS table_name
    UNION ALL     SELECT 'admin_outbound_record' AS table_name
    UNION ALL     SELECT 'admin_outbound_account' AS table_name
    UNION ALL     SELECT 'admin_wechat_fan_group' AS table_name
    UNION ALL     SELECT 'admin_wechat_fan' AS table_name
    UNION ALL     SELECT 'admin_wechat_autoreply_rule' AS table_name
    UNION ALL     SELECT 'admin_wechat_template' AS table_name
    UNION ALL     SELECT 'admin_wechat_message' AS table_name
    UNION ALL     SELECT 'admin_econtract_template' AS table_name
    UNION ALL     SELECT 'admin_econtract_seal' AS table_name
    UNION ALL     SELECT 'admin_econtract' AS table_name
    UNION ALL     SELECT 'admin_econtract_event' AS table_name
) AS t
JOIN INFORMATION_SCHEMA.TABLES s
  ON s.TABLE_SCHEMA = DATABASE() AND s.TABLE_NAME = t.table_name
ORDER BY t.table_name;

-- 2) 缺表检查：期望返回 0 行。
SELECT t.table_name AS missing_table
FROM (
    SELECT 'admin_sms_signature' AS table_name
    UNION ALL     SELECT 'admin_sms_template' AS table_name
    UNION ALL     SELECT 'admin_sms_message' AS table_name
    UNION ALL     SELECT 'admin_outbound_number' AS table_name
    UNION ALL     SELECT 'admin_outbound_task' AS table_name
    UNION ALL     SELECT 'admin_outbound_record' AS table_name
    UNION ALL     SELECT 'admin_outbound_account' AS table_name
    UNION ALL     SELECT 'admin_wechat_fan_group' AS table_name
    UNION ALL     SELECT 'admin_wechat_fan' AS table_name
    UNION ALL     SELECT 'admin_wechat_autoreply_rule' AS table_name
    UNION ALL     SELECT 'admin_wechat_template' AS table_name
    UNION ALL     SELECT 'admin_wechat_message' AS table_name
    UNION ALL     SELECT 'admin_econtract_template' AS table_name
    UNION ALL     SELECT 'admin_econtract_seal' AS table_name
    UNION ALL     SELECT 'admin_econtract' AS table_name
    UNION ALL     SELECT 'admin_econtract_event' AS table_name
) AS t
LEFT JOIN INFORMATION_SCHEMA.TABLES s
  ON s.TABLE_SCHEMA = DATABASE() AND s.TABLE_NAME = t.table_name
WHERE s.TABLE_NAME IS NULL;

-- 3) 关键索引：期望返回 0 行（缺索引的项）。
SELECT t.table_name AS missing_index
FROM (
    SELECT 'admin_sms_message' AS table_name, 'idx_admin_sms_message_batch' AS index_name
    UNION ALL SELECT 'admin_outbound_task', 'idx_admin_outbound_task_batch'
    UNION ALL SELECT 'admin_outbound_record', 'idx_admin_outbound_record_time'
    UNION ALL SELECT 'admin_wechat_fan', 'idx_admin_wechat_fan_status'
    UNION ALL SELECT 'admin_wechat_message', 'idx_admin_wechat_message_batch'
    UNION ALL SELECT 'admin_econtract', 'idx_admin_econtract_status'
    UNION ALL SELECT 'admin_econtract_event', 'idx_admin_econtract_event_contract'
) AS t
LEFT JOIN INFORMATION_SCHEMA.STATISTICS s
  ON s.TABLE_SCHEMA = DATABASE() AND s.TABLE_NAME = t.table_name
     AND s.INDEX_NAME = t.index_name
WHERE s.INDEX_NAME IS NULL;

-- 4) 敏感字段未入库检查：期望返回 0 行。
-- 公众号 app_secret / 电子签 SecretKey / 外呼密码一律走环境变量，不得出现在配置域。
SELECT namespace, config_json
FROM `admin_config_snapshot`
WHERE namespace IN ('wechat_mp', 'sys_outbound', 'econtract_config')
  AND (
      config_json LIKE '%app_secret%:%"%'
      OR config_json LIKE '%secret_key%:%"%'
      OR config_json LIKE '%access_secret%:%"%'
  )
  AND config_json NOT LIKE '%app_secret":"%'
ORDER BY namespace;
