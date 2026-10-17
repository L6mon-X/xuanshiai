"""会员 CRM 列表筛选条件构造（会员资料页 `GET /admin/matchmaker/members`）。

与路由解耦，便于单测直接覆盖枚举映射、多值展开、日期边界和缺列降级；路由只负责
参数校验与数据范围收口。

缺列降级：本模块只产出 SQL 片段与绑定参数，是否引用某列由调用方传入的
`available` 列集合决定。迁移（migrations/filters/20261011_01）未执行时对应筛选
会被静默跳过而不是拼出 Unknown column，保证「先发版后迁移」不会让整页 500。
"""

from __future__ import annotations

from typing import Any

# 会员编号口径与线下VIP关键词搜索一致：G + 会员ID 左补零到 6 位。
MEMBER_CODE_EXPR = "CONCAT('G', LPAD(u.id, 6, '0'))"

# 搜索方式 -> 命中列。`smart` 保持原有「智能搜索」行为（昵称 / 手机 / ID / 编号）。
SEARCH_TYPE_SQL: dict[str, str] = {
    "smart": (
        "(u.nickname LIKE CONCAT('%', :search, '%') OR u.phone LIKE CONCAT('%', :search, '%')"
        " OR u.id = :search_id OR {code} = :search)"
    ),
    "phone": "u.phone LIKE CONCAT('%', :search, '%')",
    "wechat": "p.wechat LIKE CONCAT('%', :search, '%')",
    "code": "{code} LIKE CONCAT('%', :search, '%')",
    "id": "u.id = :search_id",
    "nickname": "u.nickname LIKE CONCAT('%', :search, '%')",
    "realname": (
        "EXISTS (SELECT 1 FROM user_auth sa WHERE sa.user_id = u.id"
        " AND sa.real_name LIKE CONCAT('%', :search, '%'))"
    ),
}

# 线上行为类型 -> EXISTS 谓词（u 为主表 users 的别名）。
BEHAVIOR_TYPE_SQL: dict[str, str] = {
    "viewed": "EXISTS (SELECT 1 FROM user_browse_history bh WHERE bh.user_id = u.id)",
    "viewed_by": "EXISTS (SELECT 1 FROM user_browse_history bh WHERE bh.target_user_id = u.id)",
    "favorited": "EXISTS (SELECT 1 FROM user_favorite bv WHERE bv.user_id = u.id AND bv.type = 2)",
    "boosted": "EXISTS (SELECT 1 FROM user_boost bo WHERE bo.user_id = u.id)",
    "boosted_by": "EXISTS (SELECT 1 FROM user_boost bo WHERE bo.target_user_id = u.id)",
    "gift_sent": "EXISTS (SELECT 1 FROM user_gift_record gr WHERE gr.user_id = u.id)",
    "gift_received": "EXISTS (SELECT 1 FROM user_gift_record gr WHERE gr.target_user_id = u.id)",
}

# 证件/户籍地区 -> users.region 取值。
REGION_VALUES: frozenset[str] = frozenset({"mainland", "hmt", "overseas"})

# 排序白名单：值全部由服务端写死，不拼接用户输入。
SORT_SQL: dict[str, str] = {
    "created_at": "u.created_at DESC, u.id DESC",
    "entered_at": "u.created_at DESC, u.id DESC",
    "last_login_at": "COALESCE(u.last_login_at, '1970-01-01') DESC, u.id DESC",
    "last_follow_at": "COALESCE(f.last_follow_at, '1970-01-01') DESC, u.id DESC",
    "next_follow_at": "COALESCE(f.next_follow_at, '9999-12-31') ASC, u.id DESC",
    "assigned_at": "COALESCE(a.assigned_at, '1970-01-01') DESC, u.id DESC",
    "fetched_at": "COALESCE(u.fetched_at, '1970-01-01') DESC, u.id DESC",
    "id": "u.id DESC",
}

# 记录排序（order）与 sort_by 互斥；同时传时 order 优先。
ORDER_SQL: dict[str, str] = {
    "latest": "u.id DESC",
    "earliest": "u.id ASC",
    "smart": "u.created_at DESC, u.id DESC",
}


def split_values(raw: str | None, limit: int = 50) -> list[str]:
    """把「多选」参数按英文逗号拆成去重后的取值列表，空值返回空列表。"""
    if not raw:
        return []
    return [item.strip() for item in dict.fromkeys(raw.split(",")) if item.strip()][:limit]


def _placeholders(prefix: str, values: list[str], params: dict[str, Any]) -> str:
    """为多值 IN 生成命名占位符并写回 params，避免拼接用户输入。"""
    names = []
    for index, value in enumerate(values):
        key = f"{prefix}_{index}"
        params[key] = value
        names.append(f":{key}")
    return ", ".join(names)


def build_member_filter(
    values: dict[str, Any],
    available: frozenset[tuple[str, str]],
) -> tuple[str, dict[str, Any]]:
    """按传入的筛选值构造 WHERE 片段与绑定参数。

    `values` 的键名与接口的 query 参数同名；未传或为 None 的键表示该条件不生效。
    `available` 为 `(表名, 列名)` 集合，用于缺列降级。
    """
    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    def column(table: str, name: str) -> bool:
        return (table, name) in available

    # ---- 搜索 ----
    search = values.get("search")
    if search:
        search_type = values.get("search_type") or "smart"
        sql = SEARCH_TYPE_SQL.get(search_type, SEARCH_TYPE_SQL["smart"]).format(code=MEMBER_CODE_EXPR)
        where.append(sql)
        params["search"] = search
        if search.isdigit():
            params["search_id"] = int(search)
        else:
            params["search_id"] = -1

    # ---- 基础枚举 ----
    if values.get("gender") is not None:
        where.append("u.gender = :gender")
        params["gender"] = values["gender"]
    if values.get("status") is not None:
        where.append("u.status = :status")
        params["status"] = values["status"]
    if values.get("vip") is True:
        where.append("v.user_id IS NOT NULL AND (v.vip_end_at IS NULL OR v.vip_end_at > UTC_TIMESTAMP())")
    elif values.get("vip") is False:
        where.append("(v.user_id IS NULL OR (v.vip_end_at IS NOT NULL AND v.vip_end_at <= UTC_TIMESTAMP()))")
    if values.get("auth_status") is not None:
        where.append("COALESCE(ua.auth_status, 0) = :auth_status")
        params["auth_status"] = values["auth_status"]
    if values.get("assigned") is True:
        where.append("a.matchmaker_id IS NOT NULL")
    elif values.get("assigned") is False:
        where.append("a.matchmaker_id IS NULL")
    follow_state = values.get("follow_state")
    if follow_state == "never":
        where.append("f.last_follow_at IS NULL")
    elif follow_state == "due_today":
        where.append("f.next_follow_at >= CURDATE() AND f.next_follow_at < DATE_ADD(CURDATE(), INTERVAL 1 DAY)")
    elif follow_state == "overdue":
        where.append("f.next_follow_at < CURDATE()")

    # ---- 新增筛选项 ----
    if values.get("source"):
        if column("users", "source"):
            where.append("u.source = :source")
            params["source"] = values["source"]
    if values.get("region") in REGION_VALUES:
        if column("users", "region"):
            where.append("u.region = :region")
            params["region"] = values["region"]
    if values.get("xiangqin_status") is not None:
        # 相亲状态落在 user_privacy.match_status（1公开 2委托 3私密 4停止 5脱单）
        where.append("COALESCE(pr.match_status, 1) = :xiangqin_status")
        params["xiangqin_status"] = values["xiangqin_status"]
    if values.get("realname") is True:
        where.append("u.is_real_name = 1")
    elif values.get("realname") is False:
        where.append("COALESCE(u.is_real_name, 0) = 0")
    if values.get("cert_status") is not None:
        if column("users", "cert_status"):
            where.append("u.cert_status = :cert_status")
            params["cert_status"] = values["cert_status"]
    if values.get("wechat_added") is not None:
        if column("users", "wechat_added"):
            where.append("u.wechat_added = :wechat_added")
            params["wechat_added"] = values["wechat_added"]
    for flag in ("promoted", "newcomer", "activity_signup"):
        value = values.get(flag)
        if value is True and column("users", flag):
            where.append(f"u.{flag} = 1")
        elif value is False and column("users", flag):
            where.append(f"u.{flag} = 0")
    if values.get("offline_vip") is True:
        where.append(
            "EXISTS (SELECT 1 FROM offline_vip ov WHERE ov.user_id = u.id AND ov.deleted_at IS NULL)"
        )
    elif values.get("offline_vip") is False:
        where.append(
            "NOT EXISTS (SELECT 1 FROM offline_vip ov WHERE ov.user_id = u.id AND ov.deleted_at IS NULL)"
        )

    # ---- 归属 / 红娘 ----
    if values.get("organization_id") is not None:
        where.append("a.organization_id = :organization_id")
        params["organization_id"] = values["organization_id"]
    if values.get("matchmaker_id") is not None:
        where.append("a.matchmaker_id = :matchmaker_id")
        params["matchmaker_id"] = values["matchmaker_id"]
    if values.get("promoter_id") is not None:
        where.append(
            "EXISTS (SELECT 1 FROM promotion_attribution pa"
            " WHERE pa.user_id = u.id AND pa.promoter_id = :promoter_id AND pa.status = 1)"
        )
        params["promoter_id"] = values["promoter_id"]

    # ---- 区间 ----
    if values.get("age_min") is not None:
        where.append("u.birthday IS NOT NULL AND TIMESTAMPDIFF(YEAR, u.birthday, CURDATE()) >= :age_min")
        params["age_min"] = values["age_min"]
    if values.get("age_max") is not None:
        where.append("u.birthday IS NOT NULL AND TIMESTAMPDIFF(YEAR, u.birthday, CURDATE()) <= :age_max")
        params["age_max"] = values["age_max"]
    if values.get("height_min") is not None:
        where.append("p.height >= :height_min")
        params["height_min"] = values["height_min"]
    if values.get("height_max") is not None:
        where.append("p.height <= :height_max")
        params["height_max"] = values["height_max"]

    # ---- 多选维度 ----
    marriage = split_values(values.get("marriage"))
    if marriage:
        where.append(f"u.is_married IN ({_placeholders('marriage', marriage, params)})")
    education = split_values(values.get("education"))
    if education:
        where.append(f"ua.education IN ({_placeholders('education', education, params)})")
    occupation = split_values(values.get("occupation"))
    if occupation:
        where.append(f"ua.job IN ({_placeholders('occupation', occupation, params)})")
    income = split_values(values.get("income"))
    if income:
        where.append(f"p.income IN ({_placeholders('income', income, params)})")
    # 界面把收入做成区间下拉（3000以下 / 3000-8000 / 8000以上），精确匹配选不中任何值。
    if values.get("income_min") is not None:
        where.append("p.income >= :income_min")
        params["income_min"] = values["income_min"]
    if values.get("income_max") is not None:
        where.append("p.income <= :income_max")
        params["income_max"] = values["income_max"]
    # 级别 / 房子 / 民族 / 车子在界面上都标注为「多选」，取值与其它多选维度同口径
    # （英文逗号分隔 + 绑定占位符），只受理单值会让多选控件选第二个值就查不到。
    level = split_values(values.get("level"))
    if level and column("users", "level"):
        where.append(f"u.level IN ({_placeholders('level', level, params)})")
    house = split_values(values.get("house"))
    if house and column("user_profile", "house"):
        where.append(f"p.house IN ({_placeholders('house', house, params)})")
    ethnicity = split_values(values.get("ethnicity"))
    if ethnicity and column("user_profile", "ethnicity"):
        where.append(f"p.ethnicity IN ({_placeholders('ethnicity', ethnicity, params)})")
    car = split_values(values.get("car"))
    if car and column("user_profile", "car"):
        where.append(f"p.car IN ({_placeholders('car', car, params)})")

    # ---- 单值维度（与 _member_query 的 SELECT 展示列一一对应，否则「看得见筛不了」） ----
    if values.get("intention_level") is not None:
        if column("user_profile", "intention_level"):
            where.append("p.intention_level = :intention_level")
            params["intention_level"] = values["intention_level"]
    for key in ("constellation", "zodiac"):
        if values.get(key):
            if column("user_profile", key):
                where.append(f"p.{key} = :{key}")
                params[key] = values[key]

    # ---- 文本维度 ----
    for key, column_name in (("residence", "residence"), ("hometown", "hometown")):
        if values.get(key):
            where.append(f"p.{column_name} LIKE CONCAT('%', :{key}, '%')")
            params[key] = values[key]
    if values.get("hukou"):
        if column("user_profile", "household"):
            where.append("p.household LIKE CONCAT('%', :hukou, '%')")
            params["hukou"] = values["hukou"]
    if values.get("religion"):
        if column("user_profile", "religion"):
            where.append("p.religion = :religion")
            params["religion"] = values["religion"]

    # ---- 标签（JSON 数组，任一命中） ----
    tags = split_values(values.get("tags"))
    if tags:
        clauses = []
        for index, tag in enumerate(tags):
            key = f"tag_{index}"
            params[key] = f'"{tag}"'
            clauses.append(f"JSON_CONTAINS(p.tags, :{key})")
        where.append(f"({' OR '.join(clauses)})")

    # ---- 线上行为 ----
    behavior = values.get("behavior_type")
    if behavior in BEHAVIOR_TYPE_SQL:
        where.append(BEHAVIOR_TYPE_SQL[behavior])

    # ---- 时间范围 ----
    if values.get("created_start"):
        where.append("u.created_at >= :created_start")
        params["created_start"] = values["created_start"]
    if values.get("created_end"):
        # 结束日按「含当日」处理，补到次日 00:00 前。
        where.append("u.created_at < DATE_ADD(:created_end, INTERVAL 1 DAY)")
        params["created_end"] = values["created_end"]
    # 分派时间取 resource_assignment 生效记录的 effective_at，由派生表 a 提供。
    if values.get("assigned_start"):
        where.append("a.assigned_at >= :assigned_start")
        params["assigned_start"] = values["assigned_start"]
    if values.get("assigned_end"):
        where.append("a.assigned_at < DATE_ADD(:assigned_end, INTERVAL 1 DAY)")
        params["assigned_end"] = values["assigned_end"]

    return " AND ".join(where), params


def member_sort_sql(sort_by: str | None, order: str | None) -> str:
    """解析排序：order 与 sort_by 互斥，order 优先；未知值回落默认排序。"""
    if order in ORDER_SQL:
        return ORDER_SQL[order]
    return SORT_SQL.get(str(sort_by), SORT_SQL["created_at"])
