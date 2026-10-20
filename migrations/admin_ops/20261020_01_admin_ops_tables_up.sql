-- 后台运营新表迁移（A4/A5/A7/A8/A9/A10）（up）。
--
-- 背景：后端接口缺失清单.md 的 A 类新增接口需要持久化载体。7 张运营表 + 1 张
-- 会员弃海表由 app/db/business_schema.py::BUSINESS_TABLES 以 CREATE TABLE IF NOT
-- EXISTS 幂等定义，本脚本逐条镜像同一 DDL，供 AUTO_INIT_DB=false 的生产/预发布库
-- 显式执行（先迁移、后发版）。
--
-- 幂等：全部 CREATE TABLE IF NOT EXISTS，可重复执行，不会覆盖已有表或数据。
-- Run with the intended database selected (MySQL 8+).

SET NAMES utf8mb4;

-- ============ A4 云端素材库 ============
CREATE TABLE IF NOT EXISTS `admin_material_category` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `parent_id` bigint unsigned DEFAULT NULL COMMENT '父分类 ID；空为一级',
    `name` varchar(64) NOT NULL COMMENT '分类名称',
    `sort` int NOT NULL DEFAULT 0 COMMENT '排序，越小越靠前',
    `enabled` tinyint NOT NULL DEFAULT 1 COMMENT '是否启用 1是 0否',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_admin_material_category_name` (`tenant_id`, `parent_id`, `name`),
    KEY `idx_admin_material_category_parent` (`tenant_id`, `parent_id`, `sort`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='后台素材库分类';

CREATE TABLE IF NOT EXISTS `admin_material` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `category_id` bigint unsigned NOT NULL COMMENT '所属分类 admin_material_category.id',
    `name` varchar(128) NOT NULL COMMENT '素材名称',
    `url` varchar(500) NOT NULL COMMENT '原图 WebP 相对路径（/storage/uploads/...）',
    `thumbnail_url` varchar(500) NOT NULL COMMENT '缩略图 WebP 相对路径',
    `mime_type` varchar(64) NOT NULL COMMENT '原文件 MIME 类型',
    `size` bigint unsigned NOT NULL DEFAULT 0 COMMENT '原图字节数（转码后）',
    `width` int unsigned DEFAULT NULL COMMENT '图片宽度',
    `height` int unsigned DEFAULT NULL COMMENT '图片高度',
    `uploaded_by` bigint unsigned DEFAULT NULL COMMENT '上传者（matchmaker_admin_account.id）',
    `deleted_at` datetime DEFAULT NULL COMMENT '软删除时间；空为有效',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_material_category` (`tenant_id`, `category_id`, `deleted_at`),
    KEY `idx_admin_material_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='后台素材库文件';

-- ============ A5 二维码管理 ============
CREATE TABLE IF NOT EXISTS `admin_qrcode` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `name` varchar(128) NOT NULL COMMENT '二维码名称',
    `scene` varchar(32) NOT NULL COMMENT '场景：h5 落地页 / follow 关注公众号',
    `type` varchar(16) NOT NULL DEFAULT 'h5' COMMENT '编码载体：h5 / miniprogram 小程序码',
    `target_url` varchar(500) NOT NULL COMMENT '指向地址（小程序码为小程序 path）',
    `description` varchar(500) DEFAULT NULL COMMENT '用途描述',
    `expire_at` datetime NOT NULL COMMENT '失效时间（生成时 now + days，续期累加）',
    `status` tinyint NOT NULL DEFAULT 1 COMMENT '1有效 0已失效',
    `image_url` varchar(500) NOT NULL COMMENT '二维码 PNG 相对路径',
    `renew_count` int NOT NULL DEFAULT 0 COMMENT '续期次数',
    `last_renewed_at` datetime DEFAULT NULL COMMENT '最近一次续期时间',
    `created_by` bigint unsigned DEFAULT NULL COMMENT '创建人（matchmaker_admin_account.id）',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_qrcode_status` (`status`, `expire_at`),
    KEY `idx_admin_qrcode_scene` (`scene`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='后台二维码管理';

-- ============ A7 销售话术库 ============
CREATE TABLE IF NOT EXISTS `admin_sales_category` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `name` varchar(64) NOT NULL COMMENT '话术分类名称',
    `sort` int NOT NULL DEFAULT 0 COMMENT '排序',
    `enabled` tinyint NOT NULL DEFAULT 1 COMMENT '是否启用',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_admin_sales_category_name` (`tenant_id`, `name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='销售话术库分类';

CREATE TABLE IF NOT EXISTS `admin_sales_item` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `category_id` bigint unsigned NOT NULL COMMENT '分类 admin_sales_category.id',
    `title` varchar(128) NOT NULL COMMENT '话术标题',
    `content` text NOT NULL COMMENT '话术正文',
    `media_url` varchar(500) DEFAULT NULL COMMENT '配套素材（图片/语音）相对路径，可空',
    `pick_limit` int NOT NULL DEFAULT 0 COMMENT '每日可取用次数上限，0 不限制',
    `status` tinyint NOT NULL DEFAULT 1 COMMENT '1上架 0下架',
    `sort` int NOT NULL DEFAULT 0 COMMENT '排序',
    `created_by` bigint unsigned DEFAULT NULL COMMENT '创建人（matchmaker_admin_account.id）',
    `deleted_at` datetime DEFAULT NULL COMMENT '软删除时间；空为有效',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_sales_item_category` (`tenant_id`, `category_id`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='销售话术库条目';

CREATE TABLE IF NOT EXISTS `admin_sales_push` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `item_id` bigint unsigned NOT NULL COMMENT '话术条目 admin_sales_item.id',
    `matchmaker_id` bigint unsigned NOT NULL COMMENT '下发目标（users.id，有效服务红娘）',
    `note` varchar(500) DEFAULT NULL COMMENT '下发备注',
    `pushed_by` bigint unsigned NOT NULL COMMENT '下发人（matchmaker_admin_account.id）',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_sales_push_item` (`item_id`, `created_at`),
    KEY `idx_admin_sales_push_matchmaker` (`matchmaker_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='销售话术下发记录';

-- ============ A8 相亲卡模板 ============
CREATE TABLE IF NOT EXISTS `admin_lovecard_template` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `name` varchar(128) NOT NULL COMMENT '模板名称',
    `style` int NOT NULL DEFAULT 1 COMMENT '卡片样式编号 1–25',
    `activity_id` bigint unsigned DEFAULT NULL COMMENT '关联线下活动 offline_activity.id，可空',
    `register_start` datetime DEFAULT NULL COMMENT '报名开始时间（可空）',
    `register_end` datetime DEFAULT NULL COMMENT '报名结束时间（可空）',
    `region_code` varchar(64) DEFAULT NULL COMMENT '地区筛选',
    `native_place` varchar(64) DEFAULT NULL COMMENT '籍贯筛选',
    `height_min` int DEFAULT NULL COMMENT '身高下限（cm）',
    `height_max` int DEFAULT NULL COMMENT '身高上限（cm）',
    `age_min` int DEFAULT NULL COMMENT '年龄下限',
    `age_max` int DEFAULT NULL COMMENT '年龄上限',
    `promoter_id` bigint unsigned DEFAULT NULL COMMENT '推广红娘（users.id）',
    `matchmaker_id` bigint unsigned DEFAULT NULL COMMENT '服务红娘（users.id）',
    `qrcode_desc` varchar(500) DEFAULT NULL COMMENT '卡片内二维码说明文案',
    `qrcode_expire_at` datetime DEFAULT NULL COMMENT '卡片二维码失效时间',
    `limit_latest` int NOT NULL DEFAULT 5 COMMENT '取最新会员前 N 条生成',
    `tags_json` text COMMENT '标签 JSON 数组字符串',
    `enabled` tinyint NOT NULL DEFAULT 1 COMMENT '是否启用 1是 0否',
    `created_by` bigint unsigned DEFAULT NULL COMMENT '创建人（matchmaker_admin_account.id）',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_lovecard_template_enabled` (`enabled`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='相亲卡模板';

CREATE TABLE IF NOT EXISTS `admin_lovecard_generation` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `template_id` bigint unsigned NOT NULL COMMENT '模板 admin_lovecard_template.id',
    `batch_no` varchar(32) DEFAULT NULL COMMENT '批次号（一次 generate 一个批次）',
    `user_id` bigint unsigned NOT NULL COMMENT '会员 users.id',
    `image_url` varchar(500) DEFAULT NULL COMMENT '生成图片相对路径',
    `status` varchar(16) NOT NULL DEFAULT 'pending' COMMENT 'pending / success / failed',
    `error` varchar(500) DEFAULT NULL COMMENT '失败原因',
    `generated_by` bigint unsigned DEFAULT NULL COMMENT '操作人（matchmaker_admin_account.id）',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_lovecard_generation_batch` (`template_id`, `batch_no`),
    KEY `idx_admin_lovecard_generation_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='相亲卡生成记录';

-- ============ A9 会员弃海 ============
CREATE TABLE IF NOT EXISTS `member_abandonment` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `user_id` bigint unsigned NOT NULL COMMENT '会员 users.id',
    `reason` varchar(500) NOT NULL COMMENT '放弃原因',
    `abandon_type` varchar(16) NOT NULL DEFAULT 'manual' COMMENT 'manual 手工弃海 / lead_sync 客源同步 / auto 系统判定',
    `abandoned_by` bigint unsigned NOT NULL COMMENT '弃海操作人（matchmaker_admin_account.id）',
    `abandoned_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '弃海时间',
    `restored_by` bigint unsigned DEFAULT NULL COMMENT '捞回操作人；空为未捞回',
    `restored_at` datetime DEFAULT NULL COMMENT '捞回时间；空为仍弃海',
    `restore_reason` varchar(500) DEFAULT NULL COMMENT '捞回备注',
    `assigned_matchmaker_id` bigint unsigned DEFAULT NULL COMMENT '捞回时分派的服务红娘（users.id）',
    PRIMARY KEY (`id`),
    KEY `idx_member_abandonment_user` (`user_id`, `restored_at`),
    KEY `idx_member_abandonment_time` (`abandoned_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会员弃海和捞回记录（A9/B3）';

-- ============ A10 联盟活动 ============
CREATE TABLE IF NOT EXISTS `admin_alliance_activity` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `title` varchar(128) NOT NULL COMMENT '活动标题',
    `cover` varchar(500) DEFAULT NULL COMMENT '封面图相对路径',
    `store_id` bigint unsigned DEFAULT NULL COMMENT '主办门店 organization.id，可空',
    `start_time` datetime NOT NULL COMMENT '活动开始时间',
    `end_time` datetime NOT NULL COMMENT '活动结束时间',
    `address` varchar(255) DEFAULT NULL COMMENT '活动地址',
    `fee` decimal(10,2) NOT NULL DEFAULT 0.00 COMMENT '活动费用，0 免费',
    `capacity` int NOT NULL DEFAULT 0 COMMENT '人数上限，0 不限制',
    `intro` text COMMENT '活动介绍',
    `status` tinyint NOT NULL DEFAULT 1 COMMENT '1报名中 2已结束 3已取消 4草稿',
    `sort` int NOT NULL DEFAULT 0 COMMENT '排序',
    `created_by` bigint unsigned DEFAULT NULL COMMENT '创建人（matchmaker_admin_account.id）',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_alliance_activity_status` (`status`, `start_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='联盟活动（活动联盟页面）';

-- ============ A9 历史口径回填 ============
-- 「弃海会员」历史定义是「来源客源 status=LOST」。为保持列表与计数连续，
-- 把尚无有效弃海记录的此类会员回填成 abandon_type='lead_sync'。
-- 幂等：NOT EXISTS 保证重复执行不会重复插入；abandoned_by=0 表示系统回填。
INSERT INTO `member_abandonment` (user_id, reason, abandon_type, abandoned_by)
SELECT cl.converted_user_id, '历史客源弃海（迁移回填）', 'lead_sync', 0
FROM `customer_lead` cl
WHERE cl.status = 'LOST'
  AND cl.converted_user_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM `member_abandonment` ma
      WHERE ma.user_id = cl.converted_user_id AND ma.restored_at IS NULL
  );
