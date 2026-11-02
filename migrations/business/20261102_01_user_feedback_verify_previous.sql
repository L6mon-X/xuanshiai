-- 20261102_01_user_feedback (verify_previous)
-- 期望：升级前 user_feedback 表不存在。
SELECT COUNT(*) AS table_count
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_feedback';
