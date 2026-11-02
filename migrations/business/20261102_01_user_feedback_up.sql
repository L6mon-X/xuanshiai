-- 20261102_01_user_feedback
-- C 端用户反馈/意见箱。不复用 admin_ticket：后者的 submitter_user_id 语义是
-- 后台管理员，混用会污染管理端工单列表。
-- Run with the intended database selected (MySQL 8+).

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS `user_feedback` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `user_id` bigint unsigned NOT NULL COMMENT '提交人 user_id',
    `category` varchar(16) NOT NULL DEFAULT '咨询' COMMENT '咨询 / BUG / 建议 / 投诉',
    `content` varchar(2000) NOT NULL COMMENT '反馈内容',
    `images_json` json DEFAULT NULL COMMENT '截图 URL 列表（最多 9 张）',
    `contact_phone` varchar(20) DEFAULT NULL COMMENT '联系手机号（可选）',
    `status` tinyint NOT NULL DEFAULT 0 COMMENT '0待处理 / 1处理中 / 2已回复 / 3已关闭',
    `reply_content` varchar(2000) DEFAULT NULL COMMENT '客服回复内容',
    `replied_by` bigint unsigned DEFAULT NULL COMMENT '回复人 matchmaker_admin_account.id',
    `replied_at` datetime DEFAULT NULL COMMENT '回复时间',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_user_feedback_user` (`user_id`, `created_at`),
    KEY `idx_user_feedback_status` (`status`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='C 端用户反馈/意见箱';
