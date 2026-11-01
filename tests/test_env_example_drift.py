"""`.env.example` 与 `Settings` 的漂移检查。

两层保护：
1. 键集合：`Settings` 的每个字段都必须在模板中出现（启用或注释）。
2. 关键值：模板中启用的值必须与字段默认值一致；有意偏离必须登记原因，
   且登记项重新对齐后测试会失败，避免白名单腐化。

新增配置项忘记写模板、或在模板里写错值时，这些用例会直接失败。
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

from dotenv import dotenv_values

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"

ASSIGNMENT_RE = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=", re.M)
ENABLED_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=", re.M)

# 不经过 Settings，由引导/迁移脚本和集成测试直接读取的变量。
NON_SETTINGS_KEYS = frozenset(
    {
        "AI_TEST_DATABASE_URL",
        "AI_TEST_MYSQL_DATABASE",
        "AI_TEST_MYSQL_PORT",
        "AI_TEST_REDIS_PORT",
        "AI_TEST_REDIS_URL",
        "ALLOW_AI_ADVISOR_SEED",
        "BUSINESS_MIGRATION_ALLOW_DOWN",
        "BUSINESS_TEST_DATABASE_URL",
        "COMMUNITY_TEST_DATABASE_URL",
        "DB_HOST",
        "DB_NAME",
        "DB_PASSWORD",
        "DB_PORT",
        "DB_USER",
        "LIVE_API_BASE",
        "LIVE_PHONE",
        "LIVE_UNSET_CITY_PHONE",
        "SCHEMA_BOOTSTRAP_ALLOW_WARNINGS",
    }
)

# 模板有意偏离代码默认值：键 -> 原因。新增项必须写明原因。
INTENTIONAL_VALUE_DEVIATIONS = {
    "AI_GATEWAY_TIMEOUT_SECONDS": "示例为推理类 provider 留余量；字段默认 30 秒。",
}


def _text() -> str:
    return ENV_EXAMPLE.read_text(encoding="utf-8")


def _field_keys() -> set[str]:
    return {name.upper() for name in Settings.model_fields}


def _enabled_values() -> dict[str, str]:
    values = dotenv_values(ENV_EXAMPLE, interpolate=False)
    return {key: value for key, value in values.items() if value is not None}


def _matches_default(raw: str, default: object) -> bool:
    if isinstance(default, bool):
        return (raw.strip().lower() in {"true", "1", "yes", "on"}) is default
    if isinstance(default, (int, float)):
        try:
            return float(raw) == float(default)
        except ValueError:
            return False
    return raw.strip() == str(default)


def test_env_example_covers_every_settings_field() -> None:
    missing = _field_keys() - set(ASSIGNMENT_RE.findall(_text()))
    assert not missing, f".env.example 缺少配置项：{sorted(missing)}"


def test_env_example_has_no_unknown_keys() -> None:
    unknown = set(ASSIGNMENT_RE.findall(_text())) - _field_keys() - NON_SETTINGS_KEYS
    assert not unknown, f".env.example 含未登记键：{sorted(unknown)}"


def test_env_example_has_no_duplicate_enabled_keys() -> None:
    enabled = ENABLED_RE.findall(_text())
    duplicates = sorted(key for key, count in Counter(enabled).items() if count > 1)
    assert not duplicates, f".env.example 重复定义：{duplicates}"


def test_enabled_values_match_settings_defaults() -> None:
    mismatches = []
    for key, raw in _enabled_values().items():
        field = Settings.model_fields.get(key.lower())
        if field is None or field.is_required() or field.default is None:
            continue
        if key in INTENTIONAL_VALUE_DEVIATIONS:
            continue
        if not _matches_default(raw, field.default):
            mismatches.append(f"{key}: 模板={raw!r} 默认={field.default!r}")
    assert not mismatches, (
        "模板值与默认值不一致（如为有意偏离，请登记 INTENTIONAL_VALUE_DEVIATIONS）：\n"
        + "\n".join(mismatches)
    )


def test_intentional_value_deviations_are_still_needed() -> None:
    values = _enabled_values()
    stale = []
    for key, reason in INTENTIONAL_VALUE_DEVIATIONS.items():
        assert reason.strip(), f"{key} 的偏离原因不能为空"
        field = Settings.model_fields.get(key.lower())
        assert field is not None, f"白名单项 {key} 不是有效字段"
        raw = values.get(key)
        assert raw is not None, f"白名单项 {key} 在模板中没有启用"
        if _matches_default(raw, field.default):
            stale.append(key)
    assert not stale, f"以下白名单项已与默认值对齐，请移除：{stale}"


def test_realtime_asr_ws_url_uses_hyphen_domain() -> None:
    values = _enabled_values()
    assert values["AI_ALIYUN_VOICE_ASR_WS_URL"] == (
        "wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1"
    )
    for key, value in values.items():
        assert "nls-gateway.cn-shanghai" not in value, (
            f"{key} 使用了点分域名：能握手但引擎不产出识别结果"
        )


def test_deepseek_max_tokens_covers_long_json_outputs() -> None:
    # config.py 注释：2048 装不下用心度评审的长 JSON，截断会导致 parse_json 503。
    assert int(_enabled_values()["AI_DEEPSEEK_MAX_TOKENS"]) >= 4096


def test_enabled_values_are_loadable_by_settings() -> None:
    kwargs = {
        key.lower(): value
        for key, value in _enabled_values().items()
        if key.lower() in Settings.model_fields
    }
    Settings(_env_file=None, **kwargs)
