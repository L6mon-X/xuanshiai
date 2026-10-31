-- 红娘菜单权限「已配置」标记（F15）（down）。
--
-- 该表只承载「是否保存过菜单权限」的标记，回滚不影响业务数据；
-- 代码在表缺失时降级为 menu_permission_configured=false / configured=false。
-- Run with the intended database selected (MySQL 8+).

SET NAMES utf8mb4;

DROP TABLE IF EXISTS `matchmaker_menu_permission_state`;
