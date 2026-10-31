-- 红娘菜单权限「已配置」标记（F15）（verify）。
--
-- 期望：1 行结果 state_table=1，state_count 等于「至少有一条菜单权限的红娘数」，
-- 即存量已配置 / 已清空前保存过的红娘都被回填。
-- Run with the intended database selected (MySQL 8+).

SET NAMES utf8mb4;

SELECT
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'matchmaker_menu_permission_state') AS state_table,
    (SELECT COUNT(*) FROM `matchmaker_menu_permission_state`) AS state_count,
    (SELECT COUNT(DISTINCT mmp.matchmaker_user_id) FROM `matchmaker_menu_permission` mmp) AS permission_user_count,
    (SELECT COUNT(*) FROM `matchmaker_menu_permission_state` st
     LEFT JOIN (SELECT DISTINCT matchmaker_user_id FROM `matchmaker_menu_permission`) u
       ON u.matchmaker_user_id = st.matchmaker_user_id
     WHERE u.matchmaker_user_id IS NULL) AS cleared_user_count;
