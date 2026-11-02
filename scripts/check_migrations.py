#!/usr/bin/env python
"""Check this repository's SQL migration layout before committing.

This project does not use Alembic.  The reviewed migration source of truth is
``migrations/<domain>/``: up/down SQL files plus optional ``manifest.json``
entries with LF-normalised SHA-256 checksums.  The schema sources live in
``app/db/*_schema.py`` and ``database_setup_marriage.py``.

The checker is intentionally database-free so it can run in a local hook, CI,
or at the end of an Agent task:

1. Each manifest entry points at an existing up/down (and optionally verify)
   file and its recorded checksum matches.
2. Every SQL migration has a matching up/down partner.
3. A changed schema source is accompanied by a changed migration in the same
   worktree; a changed up file in a manifest-managed domain is registered.

Exit codes:
    0  layout and diff are consistent
    1  at least one discrepancy was found
    2  the repository could not be inspected
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_ROOT = ROOT / "migrations"
SCHEMA_SOURCES = (
    "app/db/business_schema.py",
    "app/db/ai_schema.py",
    "app/db/derivation_schema.py",
    "database_setup_marriage.py",
)
SCHEMA_PREFIXES = ("app/models/",)
MANIFEST_KEYS = ("up", "down", "verify", "verify_previous")


class CheckError(RuntimeError):
    """A layout or diff inconsistency."""


def _norm(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _sha256(path: Path) -> str:
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def _manifest_files() -> list[Path]:
    if not MIGRATION_ROOT.is_dir():
        raise CheckError("migrations/ directory is missing")
    return sorted(MIGRATION_ROOT.glob("*/manifest.json"))


def _check_manifest(path: Path, errors: list[str]) -> set[str]:
    """Validate one manifest and return its registered up-file names."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{_norm(path)}: cannot read manifest: {exc}")
        return set()
    if not isinstance(data, dict):
        errors.append(f"{_norm(path)}: manifest root must be an object")
        return set()
    versions = data.get("versions")
    if not isinstance(versions, list) or not versions:
        errors.append(f"{_norm(path)}: 'versions' must be a non-empty list")
        return set()

    domain = path.parent
    seen: set[str] = set()
    ups: set[str] = set()
    for index, entry in enumerate(versions, start=1):
        if not isinstance(entry, dict):
            errors.append(f"{_norm(path)}: versions[{index}] must be an object")
            continue
        version = str(entry.get("version", "")).strip()
        if not version:
            errors.append(f"{_norm(path)}: versions[{index}] has no version")
            continue
        if version in seen:
            errors.append(f"{_norm(path)}: duplicate version {version}")
        seen.add(version)

        for key in MANIFEST_KEYS:
            value = entry.get(key)
            if value is None:
                if key in {"up", "down"}:
                    errors.append(f"{_norm(path)}: {version} missing '{key}'")
                continue
            name = str(value).strip()
            if not name or Path(name).name != name:
                errors.append(f"{_norm(path)}: {version}.{key} must be a plain filename")
                continue
            target = domain / name
            if not target.is_file():
                errors.append(f"{_norm(path)}: {version}.{key} file missing: {name}")
                continue
            if key == "up":
                ups.add(name)
            expected = str(entry.get("sha256", {}).get(key, "")).strip()
            if expected and expected != _sha256(target):
                errors.append(f"{_norm(path)}: {version}.{key} checksum mismatch: {name}")
    return ups


def _check_pairs(errors: list[str]) -> int:
    pairs = 0
    for path in sorted(MIGRATION_ROOT.rglob("*.sql")):
        name = path.name
        if name.endswith("_up.sql"):
            pairs += 1
            partner = path.with_name(name[: -len("_up.sql")] + "_down.sql")
            if not partner.is_file():
                errors.append(f"{_norm(path)}: missing down partner {partner.name}")
        elif name.endswith("_down.sql"):
            partner = path.with_name(name[: -len("_down.sql")] + "_up.sql")
            if not partner.is_file():
                errors.append(f"{_norm(path)}: missing up partner {partner.name}")
    return pairs


def _git_lines(*args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise CheckError(
            f"git {' '.join(args)} failed with exit {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    return [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]


def _changed_files() -> list[str]:
    changed = set(_git_lines("diff", "--name-only"))
    changed.update(_git_lines("diff", "--cached", "--name-only"))
    changed.update(_git_lines("ls-files", "--others", "--exclude-standard"))
    return sorted(changed)


def _is_schema_source(path: str) -> bool:
    return path in SCHEMA_SOURCES or path.startswith(SCHEMA_PREFIXES)


def _check_diff(errors: list[str], manifests: dict[str, set[str]]) -> tuple[int, int, int]:
    changed = _changed_files()
    schema_changed = [path for path in changed if _is_schema_source(path)]
    migration_sql_changed = [
        path for path in changed if path.startswith("migrations/") and path.endswith(".sql")
    ]
    migration_manifest_changed = [
        path
        for path in changed
        if path.startswith("migrations/") and path.endswith("manifest.json")
    ]

    if schema_changed and not migration_sql_changed:
        errors.append(
            "schema source changed without a migration SQL change: "
            + ", ".join(schema_changed)
        )

    for path in changed:
        if not path.startswith("migrations/") or not path.endswith("_up.sql"):
            continue
        domain = path.split("/")[1] if len(path.split("/")) > 2 else ""
        registered = manifests.get(domain)
        if registered is not None and Path(path).name not in registered:
            errors.append(f"{path}: changed migration is not registered in {domain}/manifest.json")

    return len(schema_changed), len(migration_sql_changed), len(migration_manifest_changed)


def _run(check_diff: bool) -> int:
    errors: list[str] = []
    manifests: dict[str, set[str]] = {}
    manifest_files = _manifest_files()
    for path in manifest_files:
        manifests[path.parent.name] = _check_manifest(path, errors)
    pairs = _check_pairs(errors)

    schema_changes = 0
    migration_sql_changes = 0
    migration_manifest_changes = 0
    if check_diff:
        schema_changes, migration_sql_changes, migration_manifest_changes = _check_diff(
            errors, manifests
        )

    if errors:
        for message in errors:
            print(f"migration check: FAIL: {message}", file=sys.stderr)
        return 1

    if check_diff:
        print(
            "migration check: OK "
            f"manifests={len(manifest_files)} pairs={pairs} "
            f"schema_changes={schema_changes} migration_sql_changes={migration_sql_changes} "
            f"migration_manifest_changes={migration_manifest_changes}"
        )
    else:
        print(f"migration check: OK manifests={len(manifest_files)} pairs={pairs} git_diff=skipped")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check SQL migration manifests and worktree diff")
    parser.add_argument(
        "--no-git-diff",
        action="store_true",
        help="only validate manifests and up/down pairing; skip schema/migration diff",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return _run(check_diff=not args.no_git_diff)
    except CheckError as exc:
        print(f"migration check: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
