"""2026-10-31 后端问题清单修复回归测试（可离线验证的契约部分）。

覆盖清单中不依赖真实库的断言：
- P0-3 活动创建/更新接受前端驼峰 ``startDate`` / ``endDate``；
- P1-5 线下 VIP 删除接口、P1-6 ``/love-users/{id}`` 删除接口已注册；
- P1-8 推广红娘创建接受 ``display_name``；
- P1-9 牵线列表 ``search_type`` 白名单与 SQL 片段选择；
- P1-11 门店成员列表支持 ``role_code`` / ``status``；
- P2-14 积分明细带 ``reason``；
- P2-16 服务端音频时长解析（wav / mp3 / m4a / amr / 未知容器）。
"""

from __future__ import annotations

import struct

import pytest
from fastapi.testclient import TestClient

from app.api.routes.matchmaker_crm_admin import _apply_match_search
from app.main import app
from app.schemas.activity_admin import ActivityAdminCreate, ActivityAdminUpdate
from app.schemas.promoter_staff_admin import PromoterStaffCreate
from app.services.audio_duration import parse_audio_duration

client = TestClient(app)
SPEC = client.get("/openapi.json").json()


# ── P0-3 活动时间字段兼容驼峰 ──────────────────────────────────


def test_activity_create_accepts_camel_case_start_date() -> None:
    body = ActivityAdminCreate.model_validate(
        {
            "title": "秋日脱单局",
            "startDate": "2026-11-01T19:00:00",
            "endDate": "2026-11-01T21:30:00",
            "signupDeadline": "2026-10-31T12:00:00",
        }
    )
    # 曾经忽略 startDate 导致落库 start=end：这里必须解析出不同的开始时间。
    assert body.start_time.isoformat() == "2026-11-01T19:00:00"
    assert body.end_time.isoformat() == "2026-11-01T21:30:00"
    assert body.start_time != body.end_time
    assert body.signup_deadline is not None


def test_activity_update_accepts_snake_case_still() -> None:
    body = ActivityAdminUpdate.model_validate(
        {"startDate": "2026-11-01T19:00:00", "endDate": "2026-11-01T21:30:00"}
    )
    assert body.start_time is not None and body.end_time is not None
    legacy = ActivityAdminUpdate.model_validate(
        {"start_time": "2026-11-02T19:00:00", "end_time": "2026-11-02T20:00:00"}
    )
    assert legacy.start_time is not None and legacy.start_time.day == 2


def test_activity_create_rejects_end_before_start() -> None:
    with pytest.raises(ValueError):
        ActivityAdminCreate.model_validate(
            {"title": "x", "startDate": "2026-11-02T19:00:00", "endDate": "2026-11-01T19:00:00"}
        )


# ── P1-5 / P1-6 新增删除入口 ────────────────────────────────────


def test_offline_vip_delete_route_registered() -> None:
    assert "delete" in SPEC["paths"]["/api/v1/admin/offline-vips/{vip_id}"]


def test_love_users_delete_route_registered() -> None:
    assert "delete" in SPEC["paths"]["/api/v1/admin/love-users/{member_id}"]


# ── P1-8 推广红娘展示名 ────────────────────────────────────────


def test_promoter_create_schema_accepts_display_name() -> None:
    assert "display_name" in SPEC["components"]["schemas"]["PromoterStaffCreate"]["properties"]
    body = PromoterStaffCreate.model_validate({"user_id": 5, "display_name": "探针推广红娘S8A"})
    assert body.display_name == "探针推广红娘S8A"


# ── P1-9 牵线列表搜索类型 ──────────────────────────────────────


def test_match_records_accepts_keyword_and_search_type() -> None:
    params = {item["name"] for item in SPEC["paths"]["/api/v1/admin/matchmaker/match-records"]["get"]["parameters"]}
    assert {"keyword", "search_type", "search"} <= params
    stats = {
        item["name"] for item in SPEC["paths"]["/api/v1/admin/matchmaker/match-records/statistics"]["get"]["parameters"]
    }
    assert {"keyword", "search_type"} <= stats


def test_apply_match_search_uses_requested_type() -> None:
    where: list[str] = []
    params: dict[str, object] = {}
    _apply_match_search(where, params, "13800138000", "phone")
    assert "fu.phone LIKE :kw" in where[0]
    assert "fu.nickname" not in where[0]
    assert params["kw"] == "%13800138000%"

    where.clear()
    params.clear()
    _apply_match_search(where, params, "阿明", "unknown-type")
    # 未知类型回退 smart（双方昵称/手机号/编号），不再静默返回全量。
    assert "fu.nickname LIKE :kw" in where[0] and "tu.nickname LIKE :kw" in where[0]


# ── P1-11 门店红娘列表过滤 ─────────────────────────────────────


def test_store_members_accepts_role_and_status() -> None:
    params = {
        item["name"]
        for item in SPEC["paths"]["/api/v1/admin/matchmaker/stores/{store_id}/members"]["get"]["parameters"]
    }
    assert {"role_code", "status"} <= params


# ── P2-14 积分明细原因 ────────────────────────────────────────


def test_credit_record_item_has_reason() -> None:
    props = SPEC["components"]["schemas"]["CreditRecordItem"]["properties"]
    assert "reason" in props


# ── P2-16 服务端音频时长解析 ───────────────────────────────────


def _wav(seconds: float, sample_rate: int = 8000) -> bytes:
    byte_rate = sample_rate * 2  # 16bit 单声道
    payload = b"\x00\x00" * int(byte_rate / 2 * seconds)
    fmt = struct.pack("<HHIIHH", 1, 1, sample_rate, byte_rate, 2, 16)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    chunks += b"data" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks


def _mp3_cbr(seconds: float, bitrate_kbps: int = 128) -> bytes:
    # MPEG1 Layer III、44.1kHz、立体声，无 Xing/Info 头 → 走 CBR 估算分支。
    header = bytes((0xFF, 0xFB, 0x90, 0x00))
    body = header + b"\x00" * (int(bitrate_kbps * 1000 / 8 * seconds) - len(header))
    return body


def _m4a(seconds: float, timescale: int = 1000) -> bytes:
    mvhd_body = b"\x00" * 12 + struct.pack(">I", timescale) + struct.pack(">I", int(timescale * seconds)) + b"\x00" * 80
    mvhd = struct.pack(">I", 8 + len(mvhd_body)) + b"mvhd" + mvhd_body
    moov = struct.pack(">I", 8 + len(mvhd)) + b"moov" + mvhd
    return struct.pack(">I", 8) + b"ftyp" + moov


def _amr(frames: int) -> bytes:
    # AMR-NB：TOC 高 4 位是 mode，mode=7 时帧长 1+31 字节，TOC 与载荷逐帧交替。
    return b"#!AMR\n" + (bytes(((7 << 3),)) + b"\x00" * 31) * frames


# 显式 ids：默认 id 会把二进制字节塞进 PYTEST_CURRENT_TEST 环境变量，超长直接报错。
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (_wav(1.0), 1),
        (_wav(3.4), 3),
        (_mp3_cbr(2.0), 2),
        (_m4a(2.5), 2),
        (_amr(100), 2),
    ],
    ids=["wav-1.0s", "wav-3.4s", "mp3-cbr-2.0s", "m4a-2.5s", "amr-2.0s"],
)
def test_parse_audio_duration_known_containers(payload: bytes, expected: int) -> None:
    assert parse_audio_duration(payload) == expected


def test_parse_audio_duration_unknown_returns_none() -> None:
    assert parse_audio_duration(b"") is None
    assert parse_audio_duration(b"\x00" * 64) is None
    # 截断的 wav 头不应抛异常，交给调用方回退前端传值。
    assert parse_audio_duration(b"RIFF\x00\x00\x00\x00WAVEfmt ") is None
