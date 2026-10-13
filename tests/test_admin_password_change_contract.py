"""后台账号修改密码接口契约测试。"""

from app.api.routes import matchmaker_admin
from app.services.admin_content import ALLOWED_DOMAINS


def test_change_password_route_registered() -> None:
    routes = {
        (route.path, method)
        for route in matchmaker_admin.router.routes
        for method in getattr(route, "methods", set())
    }
    assert ("/admin/matchmaker/auth/change-password", "POST") in routes


def test_missing_content_domains_are_registered() -> None:
    assert {
        "free_pay_item",
        "point_gift",
        "point_exchange",
        "econtract_record",
        "econtract_template",
    } <= ALLOWED_DOMAINS
