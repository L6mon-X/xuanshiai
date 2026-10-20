-- 后台运营补列迁移（B1 门店 / B2 互选活动）（down）。
--
-- 与 migrations/m4_m7/20260916_01 同因：up.sql 只做「列不存在才 ADD」，执行后无法区分
--   * 本次 up 新增的列；
--   * 迁移执行前已经存在的同名列（例如别的环境手工补过 organization.address）。
-- 继续自动 DROP 可能误删业务在用的列，因此禁止自动 down。
--
-- 如需回滚：
--   1. 用发布前保存的对象 manifest 确认本次 up 实际新增的 12 列；
--   2. 生成只针对这些差异的定向 DDL；
--   3. 人工审核并在备份、停写窗口执行。
SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT =
    'Backoffice field gap rollback requires the pre-migration object manifest; automatic down is disabled';
