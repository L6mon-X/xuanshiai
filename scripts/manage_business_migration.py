"""Apply and verify reviewed business schema migrations without Alembic."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database_setup_marriage import get_db_config  # noqa: E402

MIGRATION_ROOT = ROOT / "migrations" / "business"
MANIFEST_PATH = MIGRATION_ROOT / "manifest.json"
MIGRATION_LOCK = "xuanshiai_business_schema_migration_v1"
IGNORABLE_MYSQL_ERRORS = {1050, 1060, 1061, 1091}
SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]{1,64}$")


class MigrationError(RuntimeError):
    """Raised for an unsafe or incomplete migration operation."""


def _checksum(path: Path, expected: str) -> None:
    raw = path.read_bytes()
    normalised = raw.replace(b"\r\n", b"\n")
    digest = hashlib.sha256(normalised).hexdigest()
    if expected and expected != digest:
        raise MigrationError(f"migration checksum mismatch: {path.name}")


def _normalize_versions(data: dict[str, Any]) -> list[dict[str, Any]]:
    versions = data.get("versions")
    if not isinstance(versions, list) or not versions:
        raise MigrationError("migration manifest has empty 'versions'")
    normalized: list[dict[str, Any]] = []
    for entry in versions:
        for key in ("version", "up", "down", "verify", "verify_previous"):
            if key not in entry:
                raise MigrationError(f"migration manifest version entry missing {key}")
        entry.setdefault("sha256", {})
        normalized.append(entry)
    return normalized


def _manifest() -> dict[str, Any]:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if "requires" not in data:
        raise MigrationError("migration manifest missing 'requires'")
    versions = _normalize_versions(data)
    for entry in versions:
        for direction in ("up", "down", "verify", "verify_previous"):
            path = MIGRATION_ROOT / str(entry[direction])
            if not path.is_file():
                raise MigrationError(f"migration file not found: {entry[direction]}")
            _checksum(path, str(entry.get("sha256", {}).get(direction, "")))
    data["versions"] = versions
    return data


def _statements(path: Path) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("--"):
            continue
        current.append(line)
        if line.rstrip().endswith(";"):
            statement = "\n".join(current).strip().rstrip(";").strip()
            if statement:
                chunks.append(statement)
            current = []
    trailing = "\n".join(current).strip()
    if trailing:
        chunks.append(trailing)
    return chunks


def _database_config_for_target(target: str) -> dict[str, Any]:
    if target == "development":
        return get_db_config()
    test_database_url = os.getenv("BUSINESS_TEST_DATABASE_URL", "").strip()
    if not test_database_url:
        raise MigrationError(
            "BUSINESS_TEST_DATABASE_URL is required for --target test; "
            "refusing to fall back to the development database"
        )
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_database_url
    try:
        return get_db_config()
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url


def _connect(target: str) -> tuple[pymysql.connections.Connection, str]:
    config = _database_config_for_target(target)
    database = str(config["database"])
    if not SAFE_IDENTIFIER.fullmatch(database):
        raise MigrationError("invalid database identifier")
    return pymysql.connect(**config, cursorclass=DictCursor, autocommit=False), database


def _ensure_history(cursor: Any) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS `business_schema_migration` (
            `id` bigint unsigned NOT NULL AUTO_INCREMENT,
            `version` varchar(128) NOT NULL,
            `checksum` char(64) NOT NULL,
            `status` varchar(24) NOT NULL,
            `started_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `finished_at` datetime DEFAULT NULL,
            `last_step` int unsigned NOT NULL DEFAULT 0,
            `error_message` varchar(1000) DEFAULT NULL,
            PRIMARY KEY (`id`),
            UNIQUE KEY `uk_business_schema_migration_version` (`version`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )


def _lock(cursor: Any) -> None:
    cursor.execute("SELECT GET_LOCK(%s, 30) AS acquired", (MIGRATION_LOCK,))
    if int(cursor.fetchone()["acquired"] or 0) != 1:
        raise MigrationError("could not acquire business migration advisory lock")


def _unlock(cursor: Any) -> None:
    cursor.execute("SELECT RELEASE_LOCK(%s)", (MIGRATION_LOCK,))


def _history(cursor: Any, version: str) -> dict[str, Any] | None:
    cursor.execute(
        "SELECT version, checksum, status, last_step, error_message FROM business_schema_migration "
        "WHERE version = %s LIMIT 1",
        (version,),
    )
    return cursor.fetchone()


def _record_start(cursor: Any, version: str, checksum: str, status: str) -> None:
    cursor.execute(
        "INSERT INTO business_schema_migration "
        "(version, checksum, status, started_at, finished_at, last_step, error_message) "
        "VALUES (%s, %s, %s, UTC_TIMESTAMP(), NULL, 0, NULL) "
        "ON DUPLICATE KEY UPDATE checksum = VALUES(checksum), status = VALUES(status), "
        "started_at = UTC_TIMESTAMP(), finished_at = NULL, last_step = 0, error_message = NULL",
        (version, checksum, status),
    )


def _record_step(cursor: Any, version: str, step: int) -> None:
    cursor.execute(
        "UPDATE business_schema_migration SET last_step = %s WHERE version = %s",
        (step, version),
    )


def _record_finish(cursor: Any, version: str, status: str, error: str | None = None) -> None:
    cursor.execute(
        "UPDATE business_schema_migration SET status = %s, finished_at = UTC_TIMESTAMP(), "
        "error_message = %s WHERE version = %s",
        (status, error, version),
    )


def _execute_file(cursor: Any, path: Path, version: str) -> None:
    for step, statement in enumerate(_statements(path), start=1):
        try:
            cursor.execute(statement)
        except pymysql.MySQLError as exc:
            code = int(exc.args[0]) if exc.args and isinstance(exc.args[0], int) else 0
            if code not in IGNORABLE_MYSQL_ERRORS:
                raise
        _record_step(cursor, version, step)


def _verify(cursor: Any, entry: dict[str, Any], expect: str, database_name: str) -> None:
    key = "verify" if expect == "current" else "verify_previous"
    if key not in {"verify", "verify_previous"}:
        raise MigrationError("verify expect must be current or previous")
    path = MIGRATION_ROOT / str(entry[key])
    statements = _statements(path)
    if len(statements) != 1:
        raise MigrationError(f"migration verification file must contain one query: {path.name}")
    cursor.execute(statements[0])
    failures = cursor.fetchall()
    if failures:
        raise MigrationError(f"{path.name} failed: {failures}")
    print(f"verified={expect} version={entry['version']} database={database_name}")


def _base_tables_required(cursor: Any, manifest: dict[str, Any]) -> None:
    cursor.execute(
        "SELECT TABLE_NAME AS table_name FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE()"
    )
    existing = {str(row["table_name"]) for row in cursor.fetchall()}
    missing = sorted({str(name) for name in manifest["requires"]} - existing)
    if missing:
        raise MigrationError(f"missing business migration dependencies: {missing}")


def _run(command: str, target: str, expect: str = "current") -> int:
    if target not in {"test", "development"}:
        raise MigrationError("business migration target must be test or development")
    if expect not in {"current", "previous"}:
        raise MigrationError("verify expect must be current or previous")
    if command == "down" and os.getenv("BUSINESS_MIGRATION_ALLOW_DOWN", "false") != "true":
        raise MigrationError(
            "refusing down; set BUSINESS_MIGRATION_ALLOW_DOWN=true after verifying backup and data impact"
        )
    manifest = _manifest()
    versions = manifest["versions"]
    connection, database_name = _connect(target)
    try:
        with connection.cursor() as cursor:
            _ensure_history(cursor)
            _lock(cursor)
            try:
                if command == "status":
                    rows = []
                    for entry in versions:
                        version = str(entry["version"])
                        rows.append(_history(cursor, version) or {"version": version, "status": "not_started"})
                    print(json.dumps(rows, default=str))
                    connection.commit()
                    return 0
                if command == "verify":
                    _base_tables_required(cursor, manifest)
                    for entry in versions:
                        _verify(cursor, entry, expect, database_name)
                    connection.commit()
                    return 0
                if command == "up":
                    _base_tables_required(cursor, manifest)
                    for entry in versions:
                        version = str(entry["version"])
                        checksum = str(entry.get("sha256", {}).get("up", ""))
                        _record_start(cursor, version, checksum, "running")
                        connection.commit()
                        try:
                            _execute_file(cursor, MIGRATION_ROOT / str(entry["up"]), version)
                            _verify(cursor, entry, "current", database_name)
                            _record_finish(cursor, version, "succeeded")
                            connection.commit()
                        except Exception as exc:
                            connection.rollback()
                            _record_finish(cursor, version, "failed", type(exc).__name__)
                            connection.commit()
                            raise
                    print(f"migration={' -> '.join(str(v['version']) for v in versions)} status=succeeded")
                    return 0
                if command == "down":
                    for entry in reversed(versions):
                        version = str(entry["version"])
                        checksum = str(entry.get("sha256", {}).get("down", ""))
                        _record_start(cursor, version, checksum, "rolling_back")
                        connection.commit()
                        try:
                            _execute_file(cursor, MIGRATION_ROOT / str(entry["down"]), version)
                            _verify(cursor, entry, "previous", database_name)
                            _record_finish(cursor, version, "rolled_back")
                            connection.commit()
                        except Exception as exc:
                            connection.rollback()
                            _record_finish(cursor, version, "rollback_failed", type(exc).__name__)
                            connection.commit()
                            raise
                    print(f"migration={' -> '.join(str(v['version']) for v in reversed(versions))} status=rolled_back")
                    return 0
                raise MigrationError(f"unknown migration command: {command}")
            finally:
                _unlock(cursor)
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage reviewed business schema migrations")
    parser.add_argument("command", choices=("status", "up", "down", "verify"))
    parser.add_argument("--target", required=True, choices=("test", "development"))
    parser.add_argument("--expect", default="current", choices=("current", "previous"))
    args = parser.parse_args(argv)
    try:
        return _run(args.command, args.target, args.expect)
    except (MigrationError, pymysql.MySQLError) as exc:
        print(f"migration failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
