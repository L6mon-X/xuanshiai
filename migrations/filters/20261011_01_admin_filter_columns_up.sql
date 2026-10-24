-- 后台筛选参数补列迁移（up）。
--
-- 背景：docs/后端筛选参数缺口清单.md 中「会员资料 / 客源线索 / 内容类」三块筛选项，
-- 有一部分在 users、user_profile、customer_lead、admin_content_item 上没有对应列，
-- 不补列新版本的筛选 SQL 会直接报 Unknown column。
--
-- 幂等约定与 migrations/m4_m7/20260916_01 相同：INFORMATION_SCHEMA 检查 +
-- PREPARE/EXECUTE 动态 DDL，可重复执行；表不存在时补列与索引跳过。
-- Run with the intended database selected (MySQL 8+).

SET SESSION group_concat_max_len = 4194304;
SET NAMES utf8mb4;

-- ============ 1. users：会员资料筛选补列 ============
SET @users_missing = (
    SELECT GROUP_CONCAT(CONCAT('ADD COLUMN ', w.column_ddl) ORDER BY w.ord SEPARATOR ', ')
    FROM (
        SELECT 1 AS ord, 'source' AS column_name,
               '`source` varchar(32) DEFAULT NULL COMMENT ''会员登记来源：后台添加/红娘录入/批量导入/自己注册/落地页/父母登记/线索入库/活动入库/找搭子''' AS column_ddl
        UNION ALL SELECT 2, 'region',
               '`region` varchar(16) DEFAULT NULL COMMENT ''证件或户籍地区：mainland中国大陆/hmt港澳台/overseas国外'''
        UNION ALL SELECT 3, 'cert_status',
               '`cert_status` tinyint NOT NULL DEFAULT 0 COMMENT ''身份认证状态 0未认证 1已认证 2待审核 3认证失败'''
        UNION ALL SELECT 4, 'wechat_added',
               '`wechat_added` tinyint NOT NULL DEFAULT 0 COMMENT ''加微信结果 0未添加 1已加上 2没加上'''
        UNION ALL SELECT 5, 'promoted',
               '`promoted` tinyint NOT NULL DEFAULT 0 COMMENT ''置顶推广 0否 1是'''
        UNION ALL SELECT 6, 'newcomer',
               '`newcomer` tinyint NOT NULL DEFAULT 0 COMMENT ''新人推荐 0否 1是'''
        UNION ALL SELECT 7, 'activity_signup',
               '`activity_signup` tinyint NOT NULL DEFAULT 0 COMMENT ''活动报名 0否 1是'''
        UNION ALL SELECT 8, 'level',
               '`level` varchar(32) DEFAULT NULL COMMENT ''会员级别'''
        UNION ALL SELECT 9, 'fetched_at',
               '`fetched_at` datetime DEFAULT NULL COMMENT ''最近一次被红娘捞取的时间'''
    ) AS w
    JOIN INFORMATION_SCHEMA.TABLES t
      ON t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = 'users'
    LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
      ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'users' AND c.COLUMN_NAME = w.column_name
    WHERE c.COLUMN_NAME IS NULL
);
SET @users_ddl = IF(
    @users_missing IS NULL,
    'SELECT 1',
    CONCAT('ALTER TABLE `users` ', @users_missing)
);
PREPARE users_cols_stmt FROM @users_ddl;
EXECUTE users_cols_stmt;
DEALLOCATE PREPARE users_cols_stmt;

-- ============ 2. user_profile：会员资料「更多选项」补列 ============
SET @user_profile_missing = (
    SELECT GROUP_CONCAT(CONCAT('ADD COLUMN ', w.column_ddl) ORDER BY w.ord SEPARATOR ', ')
    FROM (
        SELECT 1 AS ord, 'car' AS column_name,
               '`car` varchar(32) DEFAULT NULL COMMENT ''购车情况''' AS column_ddl
        UNION ALL SELECT 2, 'household',
               '`household` varchar(128) DEFAULT NULL COMMENT ''户口所在地'''
    ) AS w
    JOIN INFORMATION_SCHEMA.TABLES t
      ON t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = 'user_profile'
    LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
      ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'user_profile' AND c.COLUMN_NAME = w.column_name
    WHERE c.COLUMN_NAME IS NULL
);
SET @user_profile_ddl = IF(
    @user_profile_missing IS NULL,
    'SELECT 1',
    CONCAT('ALTER TABLE `user_profile` ', @user_profile_missing)
);
PREPARE user_profile_cols_stmt FROM @user_profile_ddl;
EXECUTE user_profile_cols_stmt;
DEALLOCATE PREPARE user_profile_cols_stmt;

-- ============ 3. customer_lead：客源线索「更多选项」补列 ============
SET @customer_lead_missing = (
    SELECT GROUP_CONCAT(CONCAT('ADD COLUMN ', w.column_ddl) ORDER BY w.ord SEPARATOR ', ')
    FROM (
        SELECT  1 AS ord, 'age' AS column_name,
                '`age` int DEFAULT NULL COMMENT ''年龄''' AS column_ddl
        UNION ALL SELECT  2, 'height',
                '`height` int DEFAULT NULL COMMENT ''身高cm'''
        UNION ALL SELECT  3, 'marriage',
                '`marriage` varchar(32) DEFAULT NULL COMMENT ''婚况'''
        UNION ALL SELECT  4, 'education',
                '`education` varchar(32) DEFAULT NULL COMMENT ''学历'''
        UNION ALL SELECT  5, 'occupation',
                '`occupation` varchar(128) DEFAULT NULL COMMENT ''职业'''
        UNION ALL SELECT  6, 'residence',
                '`residence` varchar(128) DEFAULT NULL COMMENT ''现居地'''
        UNION ALL SELECT  7, 'hometown',
                '`hometown` varchar(128) DEFAULT NULL COMMENT ''家乡'''
        UNION ALL SELECT  8, 'xiangqin_status',
                '`xiangqin_status` tinyint NOT NULL DEFAULT 0 COMMENT ''相亲状态 0未填 1公开相亲 2委托红娘 3完全私密 4关闭相亲 5已经脱单'''
        UNION ALL SELECT  9, 'bind_mode',
                '`bind_mode` varchar(16) DEFAULT NULL COMMENT ''落户方式 bind绑定已有账号/auto自动生成账号/custom自定义创建'''
        UNION ALL SELECT 10, 'wechat_added',
                '`wechat_added` tinyint NOT NULL DEFAULT 0 COMMENT ''加微信结果 0未添加 1已加上 2没加上'''
        UNION ALL SELECT 11, 'assigned_at',
                '`assigned_at` datetime DEFAULT NULL COMMENT ''最近一次分派时间'''
    ) AS w
    JOIN INFORMATION_SCHEMA.TABLES t
      ON t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME = 'customer_lead'
    LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
      ON c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = 'customer_lead' AND c.COLUMN_NAME = w.column_name
    WHERE c.COLUMN_NAME IS NULL
);
SET @customer_lead_ddl = IF(
    @customer_lead_missing IS NULL,
    'SELECT 1',
    CONCAT('ALTER TABLE `customer_lead` ', @customer_lead_missing)
);
PREPARE customer_lead_cols_stmt FROM @customer_lead_ddl;
EXECUTE customer_lead_cols_stmt;
DEALLOCATE PREPARE customer_lead_cols_stmt;

-- 说明：admin_content_item 的落地页/内容单页筛选项（type、qrcode_type、
-- xiangqin_status）不在这里补列。该表的域特有字段按设计存放在 extra_json，
-- 筛选走 JSON_UNQUOTE(JSON_EXTRACT(extra_json, '$.<key>'))，不需要新增列。

-- ============ 4. 索引（表不存在或索引已存在时跳过） ============
SET @users_source_index_ddl = IF(
    EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'
    ) AND NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'
          AND INDEX_NAME = 'idx_users_source'
    ),
    'ALTER TABLE `users` ADD KEY `idx_users_source` (`source`)',
    'SELECT 1'
);
PREPARE users_source_idx_stmt FROM @users_source_index_ddl;
EXECUTE users_source_idx_stmt;
DEALLOCATE PREPARE users_source_idx_stmt;

SET @users_fetched_index_ddl = IF(
    EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'
    ) AND NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users'
          AND INDEX_NAME = 'idx_users_fetched'
    ),
    'ALTER TABLE `users` ADD KEY `idx_users_fetched` (`fetched_at`)',
    'SELECT 1'
);
PREPARE users_fetched_idx_stmt FROM @users_fetched_index_ddl;
EXECUTE users_fetched_idx_stmt;
DEALLOCATE PREPARE users_fetched_idx_stmt;

SET @customer_lead_assigned_index_ddl = IF(
    EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customer_lead'
    ) AND NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customer_lead'
          AND INDEX_NAME = 'idx_customer_lead_assigned'
    ),
    'ALTER TABLE `customer_lead` ADD KEY `idx_customer_lead_assigned` (`assigned_at`)',
    'SELECT 1'
);
PREPARE customer_lead_assigned_idx_stmt FROM @customer_lead_assigned_index_ddl;
EXECUTE customer_lead_assigned_idx_stmt;
DEALLOCATE PREPARE customer_lead_assigned_idx_stmt;

SET @customer_lead_xiangqin_index_ddl = IF(
    EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customer_lead'
    ) AND NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'customer_lead'
          AND INDEX_NAME = 'idx_customer_lead_xiangqin'
    ),
    'ALTER TABLE `customer_lead` ADD KEY `idx_customer_lead_xiangqin` (`xiangqin_status`)',
    'SELECT 1'
);
PREPARE customer_lead_xiangqin_idx_stmt FROM @customer_lead_xiangqin_index_ddl;
EXECUTE customer_lead_xiangqin_idx_stmt;
DEALLOCATE PREPARE customer_lead_xiangqin_idx_stmt;
