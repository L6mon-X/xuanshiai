-- 红娘菜单权限「已配置」标记（F15）（up）。
--
-- 背景：列表接口的 menu_permission_count = COUNT(matchmaker_menu_permission)，
-- 「新建红娘默认全部菜单」与「手动清空成无权限」都返回 0，前端拿不到区分信号，
-- 表现为「清空保存后仍显示全部菜单」。
--
-- 口径：保存过菜单权限（即使保存为空数组）才写一行 state，接口据此下发
-- menu_permission_configured。存量已赋过菜单的红娘回填成「已配置」，
-- 避免升级后权限被误当成「未配置 = 全部菜单」。
--
-- 幂等：CREATE TABLE IF NOT EXISTS + INSERT IGNORE，可重复执行。
-- 开发/测试环境（AUTO_INIT_DB=true）由 app/db/business_schema.py 同名条目补齐。
-- Run with the intended database selected (MySQL 8+).

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `matchmaker_menu_permission_state` (
    `matchmaker_user_id` bigint unsigned NOT NULL COMMENT '红娘 users.id',
    `configured_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '最近一次保存菜单权限的时间',
    PRIMARY KEY (`matchmaker_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='红娘菜单权限已配置标记（F15：区分未配置与清空）';

-- 存量回填：已有菜单行的红娘视为「人工配置过」，清空后仍保留标记。
SET @has_permission_table = (
    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'matchmaker_menu_permission'
);

SET @backfill_sql = IF(
    @has_permission_table > 0,
    CONCAT(
        'INSERT IGNORE INTO `matchmaker_menu_permission_state` (matchmaker_user_id, configured_at) ',
        'SELECT DISTINCT mmp.matchmaker_user_id, MIN(mmp.created_at) ',
        'FROM `matchmaker_menu_permission` mmp GROUP BY mmp.matchmaker_user_id'
    ),
    'SELECT 1'
);
PREPARE backfill_stmt FROM @backfill_sql;
EXECUTE backfill_stmt;
DEALLOCATE PREPARE backfill_stmt;
