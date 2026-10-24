-- =============================================================================
-- 会员核验额度充值订单表迁移（A17）（up）
--
-- 背景：后端接口缺失清单.md A17——核验额度（实名/人脸、婚姻状况）「在线充值」
--   此前只有只读余量接口，无任何下单/支付/回调载体。本迁移新建 member_auth_recharge_order
--   订单表，供「充值订单骨架」落库（provider=disabled/mock/real 分档）。
--   真实额度扣减由认证厂商回调驱动，本表只记录下单与支付状态流水。
--
-- 同一 DDL 由 app/db/business_schema.py::BUSINESS_TABLES 以 CREATE TABLE IF NOT
-- EXISTS 定义，AUTO_INIT_DB=true 时自动创建；本脚本供 AUTO_INIT_DB=false 的
-- 生产/预发布库显式执行（先迁移、后发版）。
--
-- 幂等：CREATE TABLE IF NOT EXISTS，可重复执行，不覆盖已有表或数据。
-- Run with the intended database selected (MySQL 8+).
-- =============================================================================

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `member_auth_recharge_order` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `order_no` varchar(64) NOT NULL COMMENT '对外充值订单号',
    `kind` varchar(16) NOT NULL COMMENT 'realname 实名/marriage 婚姻',
    `package_id` varchar(64) NOT NULL COMMENT '套餐档 ID',
    `package_name` varchar(128) NOT NULL DEFAULT '' COMMENT '套餐名称快照',
    `quantity` int unsigned NOT NULL DEFAULT 1 COMMENT '核验次数增量（份数×每份次数）',
    `unit_price` decimal(12,2) NOT NULL DEFAULT 0.00 COMMENT '单价（元）',
    `total_amount` decimal(12,2) NOT NULL DEFAULT 0.00 COMMENT '总金额（元）',
    `currency` varchar(8) NOT NULL DEFAULT 'CNY',
    `status` varchar(16) NOT NULL DEFAULT 'pending' COMMENT 'pending/paid/failed/cancelled',
    `provider` varchar(32) NOT NULL DEFAULT 'mock' COMMENT '下单时的 provider',
    `pay_url` varchar(500) DEFAULT NULL COMMENT '支付跳转链接/二维码（mock 为占位）',
    `created_by` bigint unsigned DEFAULT NULL COMMENT '发起管理员 matchmaker_admin_account.id',
    `paid_at` datetime DEFAULT NULL COMMENT '支付完成时间',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_member_auth_recharge_order_no` (`order_no`),
    KEY `idx_member_auth_recharge_status` (`status`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会员核验额度充值订单（A17 骨架）';
