-- =============================================================================
-- 实名 / 人脸双写一致性回填（verify）—— D-14
--
-- 在 up 之后执行。第一条查询期望返回 0 行（不存在「已过人脸核验但实名未通过」
-- 的记录）；第二条用于确认 user_auth 表存在时被检查到。
-- =============================================================================

SET NAMES utf8mb4;

-- 1. 期望 0 行：已通过人脸核验但 realname_status 未置为通过
SELECT '期望 0 行：人脸已通过但实名未同步' AS check_item,
       ua.`id`,
       ua.`user_id`,
       ua.`realname_status`,
       ua.`face_verified`
FROM `user_auth` ua
WHERE ua.`face_verified` = 1
  AND (ua.`realname_status` IS NULL OR ua.`realname_status` <> 2);

-- 2. 表存在性确认：期望 1 行
SELECT '期望 1 行：user_auth 表存在' AS check_item, COUNT(*) AS table_present
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_auth';
