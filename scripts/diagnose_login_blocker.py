#!/usr/bin/env python
"""登录被拒根因体检（只读）。

背景
    ``POST /api/v1/auth/test-login``（以及 ``/auth/phone/login``、``/auth/wechat/login``）
    在账号 ``users.status != 1`` 时统一返回 403 ``账号当前不可用``，且这道门禁排在
    **密码校验之前**（``app/services/auth.py`` 的 ``login_existing_account`` 第 390-393 行）。
    于是"密码对不对"完全不参与判定，联调侧只能看到 403，分不清是被冻结、被注销、
    还是账号根本不存在（后者是 404）。本脚本把这条判定链在库里逐项摊开。

本脚本做什么
    对一个或多个手机号只读查询：users 主表状态、注销时间戳、密码是否存在、
    注销申请记录、角色、最近登录。并对每个账号直接给出"当前会命中哪一条分支"的结论，
    以及把它恢复为可登录状态所需的最小 SQL（**只打印，不执行**）。

    ``ENVIRONMENT`` 不是 development/testing 时额外告警：此时 test-login 会被
    第一道门禁直接 403（文案不同：``已有账号测试登录仅允许在 development/testing 环境使用``）。

用法
    python scripts/diagnose_login_blocker.py
    python scripts/diagnose_login_blocker.py --phone 19730552884 --phone 13000000000

退出码
    0 = 至少一个账号当前可登录；1 = 有账号被状态/密码阻断；2 = 账号不存在（仅单号查询时返回）；
    3 = 数据库连接失败。
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402

from database_setup_marriage import get_db_config  # noqa: E402

DEFAULT_PHONES = (
    "19730552884",
    "13000000000",
    "13100000000",
    "13200000000",
    "13300000000",
    "13400000000",
)
STATUS_LABEL = {1: "正常", 2: "冻结", 3: "注销"}


def _environment() -> str:
    """Resolve the runtime environment the same way the app does, best effort."""
    try:
        from app.core.config import settings

        return settings.environment
    except Exception:
        return (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "development").lower()


def _table_exists(cur: Any, name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s LIMIT 1",
        (name,),
    )
    return cur.fetchone() is not None


def _fetch_user(cur: Any, phone: str) -> dict[str, Any] | None:
    cur.execute(
        """SELECT id, phone, nickname, `status`, password, openid, last_login_at, created_at,
                  deletion_requested_at, deletion_scheduled_at, deletion_cancelled_at
           FROM users WHERE phone = %s LIMIT 1""",
        (phone,),
    )
    return cur.fetchone()


def _cancellations(cur: Any, user_id: int) -> list[dict[str, Any]]:
    if not _table_exists(cur, "user_cancellation"):
        return []
    cur.execute(
        """SELECT id, `status`, reason, review_note, reviewed_by, reviewed_at, created_at
           FROM user_cancellation WHERE user_id = %s ORDER BY id DESC LIMIT 5""",
        (user_id,),
    )
    return list(cur.fetchall())


def _roles(cur: Any, user_id: int) -> list[str]:
    if not _table_exists(cur, "user_role"):
        return []
    cur.execute(
        "SELECT role_code FROM user_role WHERE user_id = %s AND status = 1 ORDER BY role_code",
        (user_id,),
    )
    return [str(row["role_code"]) for row in cur.fetchall()]


def _verdict(user: dict[str, Any]) -> tuple[str, str]:
    """Mirror login_existing_account so the report matches the wire behaviour."""
    status = user.get("status")
    status_value = int(status) if status is not None else -1
    if status_value != 1:
        label = STATUS_LABEL.get(status_value, f"未知({status_value})")
        return (
            "BLOCKED",
            f"403 账号当前不可用 —— users.status={status_value}（{label}），"
            "该判断在密码校验之前，所以密码正确也一样 403",
        )
    if not user.get("password"):
        return ("BLOCKED", "401 手机号或密码错误 —— users.password 为空，账号从未设置密码")
    return ("OK", "状态与密码字段都满足，可登录（前提是密码哈希与输入的明文匹配）")


def _fix_sql(user: dict[str, Any]) -> str:
    user_id = int(user["id"])
    lines = [
        f"-- 账号 {user['phone']}（user_id={user_id}）恢复为可登录",
        "UPDATE users SET `status` = 1, deletion_requested_at = NULL,",
        "       deletion_scheduled_at = NULL, deletion_cancelled_at = NULL,",
        "       updated_at = UTC_TIMESTAMP()",
        f" WHERE id = {user_id} AND (`status` IS NULL OR `status` <> 1);",
        "UPDATE user_cancellation SET `status` = 'cancelled',",
        "       review_note = '联调恢复：账号状态手工复位',",
        "       reviewed_at = UTC_TIMESTAMP(), updated_at = UTC_TIMESTAMP()",
        f" WHERE user_id = {user_id} AND `status` = 'approved';",
    ]
    if not user.get("password"):
        lines.append(
            "-- 该账号没有密码，先本地生成哈希再替换（密码明文由联调方约定）："
        )
        lines.append(
            "--   python -c \"from app.core.security import hash_password;"
            " print(hash_password('你要的密码'))\""
        )
        lines.append(f"-- UPDATE users SET password = '<bcrypt-hash>' WHERE id = {user_id};")
    return "\n".join(lines)


def diagnose(phones: tuple[str, ...]) -> int:
    environment = _environment()
    print(f"环境 ENVIRONMENT={environment}")
    if environment not in {"development", "testing"}:
        print(
            "  ⚠ 非 development/testing：test-login 会在第一道门禁直接 403"
            "（文案「已有账号测试登录仅允许在 development/testing 环境使用」），"
            "本脚本的状态结论仍然有效，但该通道本身已关闭。"
        )
    print("状态语义：1 正常 / 2 冻结 / 3 注销\n")

    try:
        connection = pymysql.connect(
            **get_db_config(), cursorclass=pymysql.cursors.DictCursor, autocommit=True
        )
    except Exception as exc:  # 连接失败要和账号问题区分开
        print(f"数据库连接失败：{exc}")
        return 3

    exit_code = 2
    try:
        cur = connection.cursor()
        for phone in phones:
            print("=" * 72)
            print(f"手机号 {phone}")
            user = _fetch_user(cur, phone)
            if user is None:
                print("  结果：404 账号不存在 —— 该库里没有这个手机号，")
                print("        需要先注册（手机号验证码登录会自动建号，status 默认 1）。")
                continue
            exit_code = min(exit_code, 1)
            print(
                f"  user_id={user['id']}  昵称={user['nickname']}  "
                f"status={user['status']}（{STATUS_LABEL.get(int(user['status'] or -1), '未知')}）"
            )
            print(f"  密码已设置：{'是' if user.get('password') else '否'}   "
                  f"最近登录：{user['last_login_at']}   建号：{user['created_at']}")
            if any(
                user.get(key)
                for key in ("deletion_requested_at", "deletion_scheduled_at", "deletion_cancelled_at")
            ):
                print(
                    "  注销时间戳：requested={} scheduled={} cancelled={}".format(
                        user["deletion_requested_at"],
                        user["deletion_scheduled_at"],
                        user["deletion_cancelled_at"],
                    )
                )
            roles = _roles(cur, int(user["id"]))
            if roles:
                print(f"  角色：{', '.join(roles)}")
            cancellations = _cancellations(cur, int(user["id"]))
            for item in cancellations:
                print(
                    "  注销申请 #{id} status={status} reviewed_at={reviewed_at} "
                    "review_note={review_note}".format(**item)
                )
            kind, reason = _verdict(user)
            print(f"  结论：{reason}")
            if kind == "OK":
                exit_code = 0
            else:
                print("\n  恢复 SQL（请先备份、再按实际情况确认后执行）：")
                for line in _fix_sql(user).splitlines():
                    print(f"    {line}")
    finally:
        connection.close()
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="登录 403 根因体检（只读）")
    parser.add_argument(
        "--phone",
        action="append",
        dest="phones",
        metavar="PHONE",
        help="待检查手机号，可重复；缺省检查测试服两个联调账号",
    )
    args = parser.parse_args()
    phones = tuple(args.phones) if args.phones else DEFAULT_PHONES
    return diagnose(phones)


if __name__ == "__main__":
    raise SystemExit(main())
