-- =============================================================================
-- 实名 / 人脸双写一致性回填（up）—— D-14
--
-- 背景：实名存在两条并行审核链路，写入的列不一致：
--   * 旧后台实名审核  → `user_auth.realname_status`
--   * 会员认证后台审核 → `user_auth.face_verified`
-- 而 C 端门禁 `get_realname_verified_user` / `get_face_verified_user` 读取的是
-- `realname_status == 2`，导致**在会员认证后台通过实名的用户过不了门禁**。
--
-- 本迁移把「已通过人脸核验（face_verified=1）但 realname_status 未置为通过」的
-- 历史记录补齐，使两条链路对同一事实给出一致结论。
--
-- 幂等：以 `face_verified = 1 AND realname_status <> 2` 为条件，可重复执行；
--       `user_auth` 表不存在时静默跳过。
-- 请在已选定目标数据库的会话中执行（MySQL 8+）。
-- =============================================================================

SET NAMES utf8mb4;

SET @realname_backfill_sql = (
    SELECT IF(
        COUNT(*) > 0,
        'UPDATE `user_auth` SET `realname_status` = 2, `auth_status` = 2, `auth_step` = 4, `updated_at` = UTC_TIMESTAMP() WHERE `face_verified` = 1 AND (`realname_status` IS NULL OR `realname_status` <> 2)',
        'SELECT 1'
    )
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_auth'
);
PREPARE realname_backfill_stmt FROM @realname_backfill_sql;
EXECUTE realname_backfill_stmt;
DEALLOCATE PREPARE realname_backfill_stmt;
