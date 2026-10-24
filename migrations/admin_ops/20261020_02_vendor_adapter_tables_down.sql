-- 后台第三方适配模块新表迁移（A1/A2/A3/A6）（down）。
--
-- up.sql 只做「表不存在才建」，执行后无法区分哪些表由本次迁移引入；短信发送记录、
-- 外呼名单与通话记录、公众号粉丝与发送记录、电子合同与签署流水一旦落库即为业务
-- 数据（含对账凭据），自动 DROP 会造成不可逆的数据丢失，因此禁止自动 down。
--
-- 如需回滚：
--   1. 用发布前保存的对象 manifest 确认本次 up 实际新建的 16 张表；
--   2. 先导出并人工确认这些表中的业务数据不再需要（短信/外呼/合同记录通常需保留）；
--   3. 在备份、停写窗口执行定向 DROP TABLE；同时把 .env 中的
--      SMS_TEMPLATE_PROVIDER / WECHAT_MP_* / TENCENT_ESIGN_* / OUTBOUND_CALL_*
--      置回 disabled，避免回滚后接口仍尝试调用外部服务。
SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT =
    'Vendor adapter table rollback requires the pre-migration object manifest and a data export; automatic down is disabled';
