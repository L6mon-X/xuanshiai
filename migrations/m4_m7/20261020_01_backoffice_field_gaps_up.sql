-- 后台运营补列迁移（B1 门店 / B2 互选活动）（up）。
--
-- 背景：后端接口缺失清单.md 的 B 类字段缺口。organization 缺门店 LOGO/地址/
-- 分成配置/简介 5 列，mutual_selection_activity 缺报名与互选时间窗、活动收费、
-- 微信展示开关 7 列。不补列时新版本 SELECT/INSERT 会直接 Unknown column。
--
-- 幂等约定与 migrations/filters/20261011_01 相同：INFORMATION_SCHEMA 检查 +
-- PREPARE/EXECUTE 动态 DDL，可重复执行；表不存在时补列跳过。
-- 开发/测试环境（AUTO_INIT_DB=true）由 database_setup_marriage.py 的
-- _ensure_m5_columns / _ensure_mutual_selection_columns 幂等补齐同一批对象。
-- Run with the intended database selected (MySQL 8+).

SET SESSION group_concat_max_len = 4194304;
SET NAMES utf8mb4;

-- ============ 1. organization：门店补充字段（B1） ============
SET @organization_missing = (
    SELECT GROUP_CONCAT(CONCAT('ADD COLUMN ', w.column_ddl) ORDER BY w.ord SEPARATOR ', ')
    FROM (
        SELECT 1 AS ord, 'logo' AS column_name,
               '`logo` varchar(500) DEFAULT NULL COMMENT ''门店独立 LOGO''' AS column_ddl
        UNION ALL SELECT 2, 'address',
               '`address` varchar(255) DEFAULT NULL COMMENT ''门店地址'''
        UNION ALL SELECT 3, 'commission_mode',
               '`commission_mode` varchar(16) NOT NULL DEFAULT ''fixed'' COMMENT ''fixed 固定金额 / ratio 按比例'''
        UNION ALL SELECT 4, 'commission_value',
               '`commission_value` decimal(12,2) NOT NULL DEFAULT 0.00 COMMENT ''固定金额或比例值（ratio 时为百分比）'''
        UNION ALL SELECT 5, 'intro',
               '`intro` text COMMENT ''门店简介'''
    ) AS w
    JOIN INFORMATION_SCHEMA.TABLES t
      ON t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = 'organization'
    LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
      ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'organization' AND c.COLUMN_NAME = w.column_name
    WHERE c.COLUMN_NAME IS NULL
);
SET @organization_ddl = IF(
    @organization_missing IS NULL,
    'SELECT 1',
    CONCAT('ALTER TABLE `organization` ', @organization_missing)
);
PREPARE organization_cols_stmt FROM @organization_ddl;
EXECUTE organization_cols_stmt;
DEALLOCATE PREPARE organization_cols_stmt;

-- ============ 2. mutual_selection_activity：报名/互选时间窗与收费（B2） ============
SET @mutual_missing = (
    SELECT GROUP_CONCAT(CONCAT('ADD COLUMN ', w.column_ddl) ORDER BY w.ord SEPARATOR ', ')
    FROM (
        SELECT 1 AS ord, 'signup_start_time' AS column_name,
               '`signup_start_time` datetime DEFAULT NULL COMMENT ''活动报名开始时间''' AS column_ddl
        UNION ALL SELECT 2, 'signup_end_time',
               '`signup_end_time` datetime DEFAULT NULL COMMENT ''活动报名结束时间'''
        UNION ALL SELECT 3, 'mutual_start_time',
               '`mutual_start_time` datetime DEFAULT NULL COMMENT ''互选开始时间'''
        UNION ALL SELECT 4, 'mutual_end_time',
               '`mutual_end_time` datetime DEFAULT NULL COMMENT ''互选结束时间'''
        UNION ALL SELECT 5, 'activity_fee',
               '`activity_fee` decimal(10,2) DEFAULT NULL COMMENT ''活动收费金额；NULL 表示不收费'''
        UNION ALL SELECT 6, 'show_wechat_direct',
               '`show_wechat_direct` tinyint NOT NULL DEFAULT 1 COMMENT ''显示双方微信自己加'''
        UNION ALL SELECT 7, 'show_matchmaker_push',
               '`show_matchmaker_push` tinyint NOT NULL DEFAULT 0 COMMENT ''提示联系红娘推送微信号'''
    ) AS w
    JOIN INFORMATION_SCHEMA.TABLES t
      ON t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = 'mutual_selection_activity'
    LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
      ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'mutual_selection_activity'
         AND c.COLUMN_NAME = w.column_name
    WHERE c.COLUMN_NAME IS NULL
);
SET @mutual_ddl = IF(
    @mutual_missing IS NULL,
    'SELECT 1',
    CONCAT('ALTER TABLE `mutual_selection_activity` ', @mutual_missing)
);
PREPARE mutual_cols_stmt FROM @mutual_ddl;
EXECUTE mutual_cols_stmt;
DEALLOCATE PREPARE mutual_cols_stmt;
