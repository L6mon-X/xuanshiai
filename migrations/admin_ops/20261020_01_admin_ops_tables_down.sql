-- 后台运营新表迁移（A4/A5/A7/A8/A9/A10）（down）。
--
-- up.sql 只做「表不存在才建」，执行后无法区分哪些表/行由本次迁移引入；
-- 运营数据（素材、二维码、话术、模板、联盟活动、弃海记录）一旦落库即为业务数据，
-- 自动 DROP 会造成不可逆的数据丢失，因此禁止自动 down。
--
-- 如需回滚：
--   1. 用发布前保存的对象 manifest 确认本次 up 实际新建的 8 张表；
--   2. 先导出并人工确认这些表中的业务数据不再需要；
--   3. 在备份、停写窗口执行定向 DROP TABLE，并回滚 A9 的历史回填行
--      （member_abandonment 中 abandon_type='lead_sync' AND abandoned_by=0 且无捞回记录的行）。
SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT =
    'Admin ops table rollback requires the pre-migration object manifest and a data export; automatic down is disabled';
