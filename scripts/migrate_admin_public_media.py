#!/usr/bin/env python
"""把落错目录的后台公共图片从私有 ``admin/`` 迁到公开 ``common/``（P1 403 修复配套）。

背景
    ``POST /admin/matchmaker/common/upload`` 与 ``POST /admin/common/upload-file``
    历史上把头像/封面/公众号校验文件写进 ``storage/uploads/admin/``。``admin/`` 是
    私有类媒体（``media_access`` 需要短期签名 + 管理员启用态），于是只有上传响应的
    签名 URL 能打开，其它页面拿到的未签名 URL 一律 403。

    接口侧已改为写 ``common/``（公开目录，无需签名）。存量数据不迁移的话，历史
    头像/配置图片仍是 ``admin/`` 路径，继续 403。

本脚本做什么
    1. 扫描引用 ``/storage/uploads/admin/`` 的列，只挑出「通用上传接口产物」命名
       （32 位十六进制 + ``.webp`` / ``-thumb.webp`` / ``.txt`` / ``.html``）；
       ``admin/qrcodes``、``admin/econtract-seals``、素材库等私有资源不在范围内。
    2. 把对应文件 ``copy2`` 到 ``storage/uploads/common/``（保留原文件，不删不改）。
    3. 把这些列里的路径前缀改写为 ``/storage/uploads/common/``。

用法
    python scripts/migrate_admin_public_media.py                # 只演练，不落盘不改库
    python scripts/migrate_admin_public_media.py --apply        # 实际执行

退出码
    0 = 成功（含无可迁移项）；1 = 有文件缺失导致未完整迁移；2 = 连接/参数错误。
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402

from app.core.config import settings  # noqa: E402
from database_setup_marriage import get_db_config  # noqa: E402

OLD_PREFIX = "/storage/uploads/admin/"
NEW_PREFIX = "/storage/uploads/common/"
# 通用上传接口产物：common_upload 用 uuid4().hex 命名，另含缩略图与校验文件后缀。
_PUBLIC_NAME_RE = re.compile(r"^admin/[0-9a-f]{32}(?:-thumb)?\.(?:webp|txt|html?)$")
_PATH_RE = re.compile(r"/storage/uploads/admin/[A-Za-z0-9._\-]+")

# (表, 列, 主键列)；都是「对外展示」的 URL 载体，不含私有素材字段。
REFERENCE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("users", "avatar", "id"),
    ("organization", "logo", "id"),
    ("admin_config_snapshot", "config_json", "id"),
    ("admin_config_audit_log", "before_config_json", "id"),
    ("admin_config_audit_log", "after_config_json", "id"),
)


def _existing_columns(cursor) -> list[tuple[str, str, str]]:
    """只保留库里真实存在的表/列，避免历史库缺表直接中断。"""
    available: list[tuple[str, str, str]] = []
    for table, column, pk in REFERENCE_COLUMNS:
        cursor.execute(
            "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE()"
            " AND TABLE_NAME = %s AND COLUMN_NAME = %s",
            (table, column),
        )
        if cursor.fetchone():
            available.append((table, column, pk))
    return available


def _collect_targets(cursor, columns: list[tuple[str, str, str]]) -> tuple[set[str], dict[str, int]]:
    """返回 (待迁移文件名集合, {列键: 受影响行数})。"""
    names: set[str] = set()
    hits: dict[str, int] = {}
    for table, column, _pk in columns:
        cursor.execute(
            f"SELECT COUNT(*) FROM `{table}` WHERE `{column}` LIKE %s",
            (f"%{OLD_PREFIX}%",),
        )
        total = int(cursor.fetchone()[0] or 0)
        if not total:
            continue
        hits[f"{table}.{column}"] = total
        cursor.execute(f"SELECT `{column}` FROM `{table}` WHERE `{column}` LIKE %s", (f"%{OLD_PREFIX}%",))
        for (value,) in cursor.fetchall():
            if value is None:
                continue
            text = value.decode("utf-8", "ignore") if isinstance(value, bytes) else str(value)
            for path in _PATH_RE.findall(text):
                relative = path[len("/storage/uploads/") :]
                if _PUBLIC_NAME_RE.match(relative):
                    names.add(relative)
    return names, hits


def _copy_files(names: set[str], upload_dir: Path, apply: bool) -> tuple[list[str], list[str]]:
    copied: list[str] = []
    missing: list[str] = []
    destination_dir = upload_dir / "common"
    for relative in sorted(names):
        source = upload_dir / relative
        target = destination_dir / Path(relative).name
        if not source.is_file():
            missing.append(relative)
            continue
        copied.append(relative)
        if apply:
            destination_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return copied, missing


def _rewrite(cursor, columns: list[tuple[str, str, str]], names: list[str], apply: bool) -> dict[str, int]:
    changed: dict[str, int] = {}
    for relative in names:
        old = OLD_PREFIX + Path(relative).name
        new = NEW_PREFIX + Path(relative).name
        for table, column, _pk in columns:
            if not apply:
                cursor.execute(
                    f"SELECT COUNT(*) FROM `{table}` WHERE `{column}` LIKE %s", (f"%{old}%",)
                )
                affected = int(cursor.fetchone()[0] or 0)
            else:
                affected = cursor.execute(
                    f"UPDATE `{table}` SET `{column}` = REPLACE(`{column}`, %s, %s) WHERE `{column}` LIKE %s",
                    (old, new, f"%{old}%"),
                )
            if affected:
                key = f"{table}.{column}"
                changed[key] = changed.get(key, 0) + int(affected)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移后台公共媒体：admin/ -> common/")
    parser.add_argument("--apply", action="store_true", help="实际复制文件并改写数据库（默认只演练）")
    parser.add_argument("--upload-dir", default=settings.upload_dir, help="上传根目录，默认取 UPLOAD_DIR")
    args = parser.parse_args()

    upload_dir = Path(args.upload_dir)
    if not upload_dir.is_dir():
        print(f"上传目录不存在：{upload_dir}", file=sys.stderr)
        return 2

    config = get_db_config()
    try:
        connection = pymysql.connect(
            host=config["host"],
            port=int(config["port"]),
            user=config["user"],
            password=config["password"],
            database=config["database"],
            charset="utf8mb4",
            autocommit=False,
            cursorclass=pymysql.cursors.Cursor,
        )
    except Exception as exc:  # 连接失败按参数/环境问题退出
        print(f"数据库连接失败：{exc}", file=sys.stderr)
        return 2

    try:
        with connection.cursor() as cursor:
            columns = _existing_columns(cursor)
            if not columns:
                print("没有可检查的引用列，跳过")
                return 0
            names, hits = _collect_targets(cursor, columns)
            print(f"引用 admin/ 的列：{hits or '无'}")
            if not names:
                print("没有需要迁移的通用上传文件")
                return 0

            copied, missing = _copy_files(names, upload_dir, args.apply)
            changed = _rewrite(cursor, columns, copied, args.apply)
            if args.apply:
                connection.commit()
            else:
                connection.rollback()

            action = "已迁移" if args.apply else "演练：将迁移"
            print(f"{action} 文件 {len(copied)} 个 -> {upload_dir / 'common'}")
            for relative in copied:
                print(f"  {relative}")
            if missing:
                print(f"源文件缺失 {len(missing)} 个（对应行保持原状，需人工确认）：")
                for relative in missing:
                    print(f"  {relative}")
            print(f"{'已改写' if args.apply else '演练：将改写'} 数据库行：{changed or '无'}")
            if not args.apply:
                print("以上为演练结果，加 --apply 才会真正复制文件与改库")
            return 0 if not missing else 1
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
