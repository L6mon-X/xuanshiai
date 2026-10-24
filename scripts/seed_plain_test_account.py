"""Seed a plain (non-VIP) test account straight into the database.

背景
    部署环境没有可用的短信通道：``app/services/sms/providers.py`` 只实现了
    ``disabled`` 与 ``mock`` 两种 Provider，**没有任何真实短信 SDK 实现**，所以
    「登录页 -> 获取验证码 -> 自动建号」这条路在服务器上走不通（``/auth/sms/send``
    会直接 503「短信服务未配置」）。

    同一套代码里有一条免短信通道：``POST /api/v1/auth/test-login``
    （``app/services/auth.py::login_existing_account``），只要库里存在
    ``phone`` + ``password``(bcrypt) + ``status=1`` 的账号，就能直接换到
    access_token / refresh_token。

本脚本做什么
    绕过注册流程直接写 ``users`` 一行，并只授予 ``user`` 角色 —— 也就是一个
    **普通用户**，不带红娘/合伙人/推广身份。全程不写 ``user_membership``，因此
    ``has_active_membership()`` 对该账号恒为 False，所有会员门禁都会按"非会员"
    分支走（这正是"完全没有充值会员的普通账号"要的效果）。

    幂等：同一手机号重复执行只会重置密码与状态，不会建出第二个号。

前置条件
    ``ENVIRONMENT`` 必须是 ``development`` / ``testing``，否则 test-login 在
    第一道门禁就 403（「已有账号测试登录仅允许在 development/testing 环境使用」），
    建号也登录不进去。非测试环境需要显式加 ``--allow-non-test-env``（只建号、
    不解决登录），脚本仍会打印告警。

用法
    python scripts/seed_plain_test_account.py
    python scripts/seed_plain_test_account.py --phone 13100000000
    # 一男一女：号码:性别（1 男 / 2 女）
    python scripts/seed_plain_test_account.py --phone 13100000000:1 --phone 13200000000:2
    python scripts/seed_plain_test_account.py --phone 13100000000 --takeover   # 覆盖已存在账号

接管保护（F3）
    手机号已存在时**默认拒绝**（exit 2），不会重置密码/角色/状态 —— 测试服可能已有
    真实注册用户，静默覆盖等于接管他人账号。确认该号是废弃测试号后再加
    ``--takeover``。

退出码
    0 = 已就绪；2 = 环境或会员状态阻断了"普通非会员"语义；3 = 数据库连接失败。
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_PHONE = "13000000000"
DEFAULT_PASSWORD = "password123"
DEFAULT_NICKNAME = "普通测试账号"
TEST_ENVIRONMENTS = {"development", "testing"}


def _environment() -> str:
    from app.core.config import settings

    return str(settings.environment)


def _active_memberships(cur: Any, user_id: int) -> list[dict[str, Any]]:
    """Return membership rows that currently satisfy the VIP gate."""
    cur.execute(
        """SELECT id, package_type, status, start_at, end_at FROM user_membership
        WHERE user_id=%s AND status=1
          AND (start_at IS NULL OR start_at <= UTC_TIMESTAMP())
          AND (end_at IS NULL OR end_at > UTC_TIMESTAMP())""",
        (user_id,),
    )
    return [dict(row) for row in cur.fetchall()]


def seed_plain_test_account(
    phone: str = DEFAULT_PHONE,
    password: str = DEFAULT_PASSWORD,
    nickname: str = DEFAULT_NICKNAME,
    *,
    gender: int = 1,
    allow_non_test_env: bool = False,
    expire_membership: bool = False,
    takeover: bool = False,
) -> dict[str, Any]:
    """Create or refresh a plain non-VIP account usable by ``/auth/test-login``.

    ``gender``：1 男 / 2 女。推荐页按性别做异性推荐，测试男女视角时需要成对的号。

    ``takeover=False``（默认）时，若手机号已存在则拒绝改动 —— 测试服可能已有
    真实注册用户，静默重置密码/角色等于接管他人账号（F3 接管保护）。
    """
    if gender not in (1, 2):
        raise RuntimeError(f"gender 只能是 1（男）或 2（女），收到 {gender}")
    environment = _environment()
    if environment not in TEST_ENVIRONMENTS and not allow_non_test_env:
        raise RuntimeError(
            f"ENVIRONMENT={environment}：test-login 通道已关闭（会 403）。"
            "确认这是测试服后加 --allow-non-test-env 只建号，"
            "或把该环境 ENVIRONMENT 改为 testing 再重启后端。"
        )

    import pymysql
    from database_setup_marriage import get_db_config

    from app.core.security import hash_password

    result: dict[str, Any] = {"environment": environment, "phone": phone, "gender": gender}
    connection = pymysql.connect(
        **get_db_config(), cursorclass=pymysql.cursors.DictCursor, autocommit=False
    )
    try:
        cur = connection.cursor()
        password_hash = hash_password(password)

        cur.execute("SELECT id, nickname, status FROM users WHERE phone=%s LIMIT 1", (phone,))
        row = cur.fetchone()
        if row is None:
            cur.execute(
                """INSERT INTO users
                (phone, password, nickname, gender, status, phone_verified_at,
                 password_algo, password_updated_at, register_ip, data_complete_rate)
                VALUES (%s,%s,%s,%s,1,UTC_TIMESTAMP(),'bcrypt',UTC_TIMESTAMP(),'127.0.0.1',0)""",
                (phone, password_hash, nickname, gender),
            )
            user_id = int(cur.lastrowid)
            result["created"] = True
        else:
            user_id = int(row["id"])
            if not takeover:
                connection.rollback()
                raise RuntimeError(
                    f"手机号 {phone} 已存在（user_id={user_id} 昵称={row['nickname']} "
                    f"status={row['status']}）。默认不覆盖，避免接管真实账号；"
                    "确认这是测试号后加 --takeover 重置密码与角色。"
                )
            # 复位所有会阻断登录的状态位（冻结/注销/失败锁定），并重写密码。
            cur.execute(
                """UPDATE users SET password=%s, password_algo='bcrypt',
                password_updated_at=UTC_TIMESTAMP(), password_failed_count=0,
                password_locked_until=NULL, status=1, nickname=%s, gender=%s,
                phone_verified_at=COALESCE(phone_verified_at, UTC_TIMESTAMP()),
                frozen_at=NULL, frozen_reason=NULL, deletion_requested_at=NULL,
                deletion_scheduled_at=NULL, deletion_cancelled_at=NULL, deleted_at=NULL,
                updated_at=UTC_TIMESTAMP()
                WHERE id=%s""",
                (password_hash, nickname, gender, user_id),
            )
            result["created"] = False
        result["user_id"] = user_id

        # 只保留普通用户角色：显式撤销可能残留的红娘/合伙人/推广身份。
        cur.execute(
            """INSERT INTO user_role (user_id, role_code, status)
            VALUES (%s,'user',1)
            ON DUPLICATE KEY UPDATE status=1, revoked_at=NULL, revoke_reason=NULL""",
            (user_id,),
        )
        cur.execute(
            """UPDATE user_role SET status=3, revoked_at=UTC_TIMESTAMP(),
            revoke_reason='seed_plain_test_account'
            WHERE user_id=%s AND role_code<>'user' AND status=1""",
            (user_id,),
        )
        cur.execute(
            "SELECT role_code FROM user_role WHERE user_id=%s AND status=1 ORDER BY role_code",
            (user_id,),
        )
        result["roles"] = [str(r["role_code"]) for r in cur.fetchall()]

        # 会员态必须是"无"：脚本不会替你造会员，也不会静默保留已有会员。
        active = _active_memberships(cur, user_id)
        if active:
            if not expire_membership:
                connection.rollback()
                raise RuntimeError(
                    f"该账号存在 {len(active)} 条生效中的会员记录，不是"
                    "「完全没有充值会员」的账号。换一个手机号，"
                    "或加 --expire-membership 将其置为已过期后再建。"
                )
            cur.execute(
                """UPDATE user_membership SET status=2, end_at=UTC_TIMESTAMP(),
                updated_at=UTC_TIMESTAMP()
                WHERE user_id=%s AND status=1""",
                (user_id,),
            )
            result["membership_expired"] = cur.rowcount
        result["has_active_membership"] = False

        connection.commit()

        cur.execute(
            "SELECT id, phone, nickname, status FROM users WHERE id=%s", (user_id,)
        )
        result["user"] = dict(cur.fetchone() or {})
        return result
    finally:
        connection.close()


def _report(result: dict[str, Any], password: str) -> None:
    user = result.get("user") or {}
    print("=" * 72)
    print(f"环境 ENVIRONMENT={result['environment']}")
    print(f"账号已{'创建' if result.get('created') else '更新'}：user_id={result['user_id']}")
    print(f"  手机号：{user.get('phone')}")
    print(f"  密码：{password}")
    print(f"  昵称：{user.get('nickname')}   性别：{'男' if result.get('gender') == 1 else '女'}"
          f"   状态：{user.get('status')}（1=正常）")
    print(f"  角色：{', '.join(result.get('roles') or ['(无)'])}")
    print(f"  生效会员：{'有' if result.get('has_active_membership') else '无'}"
          + (f"（已过期 {result['membership_expired']} 条）" if result.get("membership_expired") else ""))
    print("=" * 72)
    if result["environment"] in TEST_ENVIRONMENTS:
        print("登录方式：小程序登录页勾选协议 -> 点对应「账号X」按钮（走 /auth/test-login）")
        print("          或 POST /api/v1/auth/test-login  {\"phone\": \"%s\", \"password\": \"***\"}" % user.get("phone"))
    else:
        print("⚠ 当前环境不是 development/testing：test-login 会 403，此账号暂时登不进去。")
        print("  把该环境 ENVIRONMENT 改为 testing 并重启后端，或将后端部署为测试环境后再登录。")


def _parse_phone_spec(spec: str, default_gender: int) -> tuple[str, int]:
    """解析 ``手机号`` 或 ``手机号:性别``（性别 1 男 / 2 女）。"""
    phone, sep, raw_gender = spec.partition(":")
    phone = phone.strip()
    if not phone:
        raise RuntimeError(f"手机号不能为空：{spec!r}")
    gender = default_gender
    if sep:
        try:
            gender = int(raw_gender)
        except ValueError as exc:
            raise RuntimeError(f"性别取值非法：{spec!r}（应为 号码:1 或 号码:2）") from exc
    if gender not in (1, 2):
        raise RuntimeError(f"性别只能是 1（男）或 2（女）：{spec!r}")
    return phone, gender


def main() -> int:
    parser = argparse.ArgumentParser(description="直连数据库创建普通非会员测试账号")
    parser.add_argument(
        "--phone",
        action="append",
        dest="phones",
        metavar="PHONE",
        help="手机号，可重复；支持 手机号:性别（如 13100000000:1），性别 1 男 2 女",
    )
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="登录密码（bcrypt 落库）")
    parser.add_argument("--nickname", default=DEFAULT_NICKNAME, help="昵称（多个号时自动追加 号码-性别）")
    parser.add_argument(
        "--gender",
        type=int,
        default=1,
        choices=(1, 2),
        help="缺省性别 1 男 / 2 女；逐个号可用 --phone 号码:性别 覆盖",
    )
    parser.add_argument(
        "--allow-non-test-env",
        action="store_true",
        help="非 development/testing 也建号（注意 test-login 仍会 403）",
    )
    parser.add_argument(
        "--expire-membership",
        action="store_true",
        help="该号已有生效会员时，先置为已过期再交付",
    )
    parser.add_argument(
        "--takeover",
        action="store_true",
        help="手机号已存在时允许覆盖（重置密码/状态/角色）。默认拒绝，避免接管真实账号",
    )
    args = parser.parse_args()

    specs = tuple(args.phones) if args.phones else (DEFAULT_PHONE,)
    exit_code = 0
    for spec in specs:
        try:
            phone, gender = _parse_phone_spec(spec, args.gender)
        except RuntimeError as exc:
            print(f"[{spec}] 参数错误：{exc}")
            exit_code = max(exit_code, 2)
            continue
        # 多个号共用一个 --nickname 时追加号码与性别，避免昵称重复难辨认。
        nickname = args.nickname if len(specs) == 1 else (
            f"{args.nickname}-{phone}-{'男' if gender == 1 else '女'}"
        )
        try:
            result = seed_plain_test_account(
                phone,
                args.password,
                nickname,
                gender=gender,
                allow_non_test_env=args.allow_non_test_env,
                expire_membership=args.expire_membership,
                takeover=args.takeover,
            )
        except RuntimeError as exc:
            print(f"[{phone}] 失败：{exc}")
            exit_code = max(exit_code, 2)
            continue
        except Exception as exc:  # 连接失败要和账号语义问题区分开
            print(f"[{phone}] 数据库操作失败：{exc}")
            exit_code = max(exit_code, 3)
            continue
        _report(result, args.password)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
