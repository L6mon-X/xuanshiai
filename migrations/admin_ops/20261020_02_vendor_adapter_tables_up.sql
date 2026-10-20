-- 后台第三方适配模块新表迁移（A1 短信 / A6 外呼 / A2 公众号 / A3 电子合同）（up）。
--
-- 背景：后端接口缺失清单.md 的 A1/A2/A3/A6 需要持久化载体。16 张表由
-- app/db/business_schema.py::BUSINESS_TABLES 以 CREATE TABLE IF NOT EXISTS 幂等定义，
-- 本脚本逐条镜像同一 DDL，供 AUTO_INIT_DB=false 的生产/预发布库显式执行
-- （先迁移、后发版）。
--
-- 幂等：全部 CREATE TABLE IF NOT EXISTS，可重复执行，不会覆盖已有表或数据。
-- Run with the intended database selected (MySQL 8+).

SET NAMES utf8mb4;


-- ============ A1 短信管理 ============

CREATE TABLE IF NOT EXISTS `admin_sms_signature` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `name` varchar(64) NOT NULL COMMENT '签名内容（不含【】）',
    `provider_ref` varchar(128) DEFAULT NULL COMMENT '供应商侧签名 ID',
    `status` varchar(16) NOT NULL DEFAULT 'pending' COMMENT 'pending 待报备 / approved 已通过 / rejected 未通过',
    `audit_remark` varchar(255) DEFAULT NULL COMMENT '报备备注',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_admin_sms_signature_name` (`tenant_id`, `name`),
    KEY `idx_admin_sms_signature_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='短信签名报备';

CREATE TABLE IF NOT EXISTS `admin_sms_template` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `name` varchar(64) NOT NULL COMMENT '模板名称',
    `code` varchar(64) NOT NULL COMMENT '供应商模板编码（发送时使用）',
    `content` varchar(1000) NOT NULL COMMENT '模板正文，变量用 {name} 占位',
    `signature_id` bigint unsigned DEFAULT NULL COMMENT '关联签名 admin_sms_signature.id',
    `scene` varchar(32) NOT NULL DEFAULT 'notice' COMMENT '场景标识',
    `status` tinyint NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_admin_sms_template_code` (`tenant_id`, `code`),
    KEY `idx_admin_sms_template_scene` (`scene`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='短信通知模板';

CREATE TABLE IF NOT EXISTS `admin_sms_message` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `batch_no` varchar(32) NOT NULL COMMENT '群发批次号',
    `template_id` bigint unsigned DEFAULT NULL COMMENT '模板 admin_sms_template.id；自由文本为空',
    `phone` varchar(32) NOT NULL COMMENT '接收手机号',
    `user_id` bigint unsigned DEFAULT NULL COMMENT '关联会员 users.id，可空',
    `content` varchar(1000) NOT NULL COMMENT '实际发送内容（变量已替换）',
    `status` varchar(16) NOT NULL DEFAULT 'queued' COMMENT 'queued 待发 / sent 已发 / failed 失败',
    `provider_ref` varchar(128) DEFAULT NULL COMMENT '供应商流水号',
    `error` varchar(500) DEFAULT NULL COMMENT '失败原因',
    `sent_at` datetime DEFAULT NULL COMMENT '发送成功时间',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_sms_message_batch` (`batch_no`, `id`),
    KEY `idx_admin_sms_message_status` (`status`, `created_at`),
    KEY `idx_admin_sms_message_phone` (`phone`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='短信发送记录（A1）';


-- ============ A6 电话外呼 ============

CREATE TABLE IF NOT EXISTS `admin_outbound_number` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `phone` varchar(32) NOT NULL COMMENT '外显号码',
    `area` varchar(64) DEFAULT NULL COMMENT '归属地（展示用）',
    `status` tinyint NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
    `bound_matchmaker_id` bigint unsigned DEFAULT NULL COMMENT '绑定红娘 matchmaker.id，可空',
    `remark` varchar(255) DEFAULT NULL,
    `created_by` bigint unsigned DEFAULT NULL,
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_admin_outbound_number_phone` (`tenant_id`, `phone`),
    KEY `idx_admin_outbound_number_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='外呼外显号码池（A6）';

CREATE TABLE IF NOT EXISTS `admin_outbound_task` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `batch_no` varchar(32) NOT NULL COMMENT '导入批次号',
    `member_id` bigint unsigned DEFAULT NULL COMMENT '关联会员 users.id，可空',
    `name` varchar(64) DEFAULT NULL COMMENT '名单姓名（导入原值）',
    `phone` varchar(32) NOT NULL COMMENT '被叫号码',
    `matchmaker_id` bigint unsigned DEFAULT NULL COMMENT '跟进红娘 matchmaker.id',
    `status` varchar(16) NOT NULL DEFAULT 'pending' COMMENT 'pending 待呼 / calling 呼叫中 / done 已完成 / failed 呼叫失败 / canceled 已取消',
    `result` varchar(32) DEFAULT NULL COMMENT '外呼结果：connected / no_answer / busy / reject / invalid',
    `remark` varchar(500) DEFAULT NULL,
    `call_count` int NOT NULL DEFAULT 0 COMMENT '已呼叫次数',
    `last_called_at` datetime DEFAULT NULL,
    `provider_call_id` varchar(128) DEFAULT NULL COMMENT '供应商通话 ID',
    `created_by` bigint unsigned DEFAULT NULL,
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_outbound_task_batch` (`batch_no`, `id`),
    KEY `idx_admin_outbound_task_status` (`status`, `created_at`),
    KEY `idx_admin_outbound_task_matchmaker` (`matchmaker_id`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='外呼名单（A6）';

CREATE TABLE IF NOT EXISTS `admin_outbound_record` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `task_id` bigint unsigned DEFAULT NULL COMMENT '关联 admin_outbound_task.id，可空',
    `phone` varchar(32) NOT NULL COMMENT '号码（回显脱敏）',
    `matchmaker_id` bigint unsigned DEFAULT NULL,
    `direction` varchar(16) NOT NULL DEFAULT 'outbound' COMMENT 'outbound 呼出 / inbound 呼入',
    `result` varchar(32) DEFAULT NULL COMMENT 'connected / no_answer / busy / reject / invalid',
    `duration` int NOT NULL DEFAULT 0 COMMENT '通话时长（秒）',
    `recording_url` varchar(500) DEFAULT NULL COMMENT '录音地址',
    `provider_call_id` varchar(128) DEFAULT NULL COMMENT '供应商通话 ID',
    `started_at` datetime DEFAULT NULL,
    `ended_at` datetime DEFAULT NULL,
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_outbound_record_time` (`created_at`),
    KEY `idx_admin_outbound_record_task` (`task_id`),
    KEY `idx_admin_outbound_record_matchmaker` (`matchmaker_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='外呼通话记录（A6）';

CREATE TABLE IF NOT EXISTS `admin_outbound_account` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `provider` varchar(32) NOT NULL DEFAULT 'disabled' COMMENT '供应商标识',
    `account_name` varchar(128) DEFAULT NULL COMMENT '账户名称',
    `balance` decimal(12,2) NOT NULL DEFAULT 0.00 COMMENT '账户余额',
    `currency` varchar(8) NOT NULL DEFAULT 'CNY',
    `checked_at` datetime DEFAULT NULL COMMENT '最近一次余额同步时间',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_outbound_account_provider` (`provider`, `checked_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='外呼账户余额快照（A6）';


-- ============ A2 微信公众号 ============

CREATE TABLE IF NOT EXISTS `admin_wechat_fan_group` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `name` varchar(64) NOT NULL COMMENT '分组名称',
    `provider_group_id` bigint DEFAULT NULL COMMENT '微信侧分组 id',
    `sort` int NOT NULL DEFAULT 0,
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_admin_wechat_fan_group_name` (`tenant_id`, `name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='公众号粉丝分组（A2）';

CREATE TABLE IF NOT EXISTS `admin_wechat_fan` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `openid` varchar(64) NOT NULL COMMENT '微信 openid',
    `unionid` varchar(64) DEFAULT NULL,
    `nickname` varchar(128) DEFAULT NULL,
    `avatar_url` varchar(500) DEFAULT NULL,
    `gender` tinyint NOT NULL DEFAULT 0 COMMENT '0未知 1男 2女',
    `city` varchar(64) DEFAULT NULL,
    `province` varchar(64) DEFAULT NULL,
    `subscribe_status` tinyint NOT NULL DEFAULT 1 COMMENT '1已关注 0已取关',
    `subscribe_at` datetime DEFAULT NULL,
    `unsubscribe_at` datetime DEFAULT NULL,
    `group_id` bigint unsigned DEFAULT NULL COMMENT 'admin_wechat_fan_group.id',
    `user_id` bigint unsigned DEFAULT NULL COMMENT '关联会员 users.id，可空',
    `remark` varchar(255) DEFAULT NULL,
    `synced_at` datetime DEFAULT NULL,
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_admin_wechat_fan_openid` (`tenant_id`, `openid`),
    KEY `idx_admin_wechat_fan_status` (`subscribe_status`, `subscribe_at`),
    KEY `idx_admin_wechat_fan_group` (`group_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='公众号粉丝（A2）';

CREATE TABLE IF NOT EXISTS `admin_wechat_autoreply_rule` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `name` varchar(64) NOT NULL COMMENT '规则名称',
    `match_type` varchar(16) NOT NULL DEFAULT 'keyword' COMMENT 'keyword 关键词 / subscribe 关注 / default 默认',
    `keyword` varchar(128) DEFAULT NULL COMMENT '关键词（逗号分隔），subscribe/default 为空',
    `reply_type` varchar(16) NOT NULL DEFAULT 'text' COMMENT 'text 文本 / image 图片 / news 图文',
    `content` text NOT NULL COMMENT '回复内容（text 为正文，image/news 为素材 URL 列表说明）',
    `status` tinyint NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
    `sort` int NOT NULL DEFAULT 0,
    `created_by` bigint unsigned DEFAULT NULL,
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_wechat_autoreply_type` (`match_type`, `status`, `sort`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='公众号自动回复规则（A2）';

CREATE TABLE IF NOT EXISTS `admin_wechat_template` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `template_id` varchar(64) NOT NULL COMMENT '微信模板消息 template_id',
    `title` varchar(128) NOT NULL COMMENT '模板标题（微信侧返回）',
    `primary_industry` varchar(64) DEFAULT NULL,
    `deputy_industry` varchar(64) DEFAULT NULL,
    `content` varchar(1000) DEFAULT NULL COMMENT '模板内容示例',
    `status` tinyint NOT NULL DEFAULT 1,
    `synced_at` datetime DEFAULT NULL,
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_admin_wechat_template_id` (`tenant_id`, `template_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='公众号模板消息（A2）';

CREATE TABLE IF NOT EXISTS `admin_wechat_message` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `batch_no` varchar(32) NOT NULL COMMENT '发送批次号',
    `send_type` varchar(16) NOT NULL DEFAULT 'broadcast' COMMENT 'broadcast 群发 / template 模板消息',
    `template_id` bigint unsigned DEFAULT NULL COMMENT 'admin_wechat_template.id，模板消息时有值',
    `group_id` bigint unsigned DEFAULT NULL COMMENT '群发目标分组，可空=全部',
    `title` varchar(128) DEFAULT NULL,
    `content` varchar(2000) DEFAULT NULL,
    `url` varchar(500) DEFAULT NULL,
    `target_count` int NOT NULL DEFAULT 0 COMMENT '目标粉丝数',
    `sent_count` int NOT NULL DEFAULT 0 COMMENT '成功数',
    `failed_count` int NOT NULL DEFAULT 0 COMMENT '失败数',
    `status` varchar(16) NOT NULL DEFAULT 'queued' COMMENT 'queued 待发 / sent 已发 / failed 失败',
    `error` varchar(500) DEFAULT NULL,
    `provider_msg_id` varchar(128) DEFAULT NULL COMMENT '微信侧 msg_id',
    `created_by` bigint unsigned DEFAULT NULL,
    `sent_at` datetime DEFAULT NULL,
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_wechat_message_batch` (`batch_no`, `id`),
    KEY `idx_admin_wechat_message_status` (`status`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='公众号消息发送记录（A2）';


-- ============ A3 电子合同 ============

CREATE TABLE IF NOT EXISTS `admin_econtract_template` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `name` varchar(128) NOT NULL COMMENT '模板名称',
    `contract_type` varchar(64) NOT NULL DEFAULT '红娘服务协议' COMMENT '合同类型',
    `provider_template_id` varchar(128) DEFAULT NULL COMMENT '电子签平台模板 ID',
    `content` mediumtext COMMENT '模板正文（富文本），发起时可覆盖',
    `file_url` varchar(500) DEFAULT NULL COMMENT '模板文件 URL',
    `status` tinyint NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
    `usage_count` int NOT NULL DEFAULT 0 COMMENT '使用次数',
    `created_by` bigint unsigned DEFAULT NULL,
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_econtract_template_type` (`contract_type`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='电子合同模板（A3）';

CREATE TABLE IF NOT EXISTS `admin_econtract_seal` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `name` varchar(128) NOT NULL COMMENT '印章名称',
    `seal_type` varchar(16) NOT NULL DEFAULT 'company' COMMENT 'company 企业章 / personal 个人章',
    `image_url` varchar(500) NOT NULL COMMENT '印章图片地址',
    `authorized_person` varchar(64) DEFAULT NULL COMMENT '授权人',
    `provider_seal_id` varchar(128) DEFAULT NULL COMMENT '电子签平台印章 ID',
    `status` tinyint NOT NULL DEFAULT 1 COMMENT '1启用 0停用',
    `created_by` bigint unsigned DEFAULT NULL,
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_econtract_seal_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='电子印章（A3）';

CREATE TABLE IF NOT EXISTS `admin_econtract` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `contract_no` varchar(64) NOT NULL COMMENT '合同编号',
    `template_id` bigint unsigned DEFAULT NULL COMMENT 'admin_econtract_template.id',
    `seal_id` bigint unsigned DEFAULT NULL COMMENT 'admin_econtract_seal.id',
    `title` varchar(128) NOT NULL COMMENT '合同标题',
    `contract_type` varchar(64) NOT NULL DEFAULT '红娘服务协议',
    `member_id` bigint unsigned DEFAULT NULL COMMENT '签署会员 users.id',
    `member_name` varchar(64) DEFAULT NULL COMMENT '签署人姓名',
    `member_phone` varchar(32) DEFAULT NULL COMMENT '签署人手机号（回显脱敏）',
    `amount` decimal(12,2) DEFAULT NULL COMMENT '合同金额，可空',
    `content` mediumtext COMMENT '合同正文快照',
    `status` varchar(16) NOT NULL DEFAULT 'draft' COMMENT 'draft 草稿 / signing 签署中 / signed 已签署 / voided 已作废 / expired 已过期',
    `provider_flow_id` varchar(128) DEFAULT NULL COMMENT '电子签平台流程 ID',
    `sign_url` varchar(1000) DEFAULT NULL COMMENT '签署链接',
    `signed_at` datetime DEFAULT NULL,
    `expire_at` datetime DEFAULT NULL COMMENT '签署截止时间',
    `voided_at` datetime DEFAULT NULL,
    `void_reason` varchar(500) DEFAULT NULL,
    `created_by` bigint unsigned DEFAULT NULL,
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_admin_econtract_no` (`tenant_id`, `contract_no`),
    KEY `idx_admin_econtract_status` (`status`, `created_at`),
    KEY `idx_admin_econtract_member` (`member_id`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='电子合同（A3）';

CREATE TABLE IF NOT EXISTS `admin_econtract_event` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `tenant_id` int NOT NULL DEFAULT 1 COMMENT '租户（预留多租户）',
    `contract_id` bigint unsigned NOT NULL COMMENT 'admin_econtract.id',
    `event` varchar(32) NOT NULL COMMENT 'created / sent / viewed / signed / voided / expired / callback',
    `actor` varchar(64) DEFAULT NULL COMMENT '触发方：admin / member / provider',
    `detail` varchar(500) DEFAULT NULL COMMENT '事件说明',
    `payload_json` json DEFAULT NULL COMMENT '供应商回调原文（已脱敏）',
    `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_admin_econtract_event_contract` (`contract_id`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='电子合同签署流水（A3）';
