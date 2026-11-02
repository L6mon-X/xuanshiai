#!/usr/bin/env python
"""微信支付 real 模式预检（不发起扣款）。

检查配置门禁、AppID 一致性、私钥/证书匹配、序列号、公钥和回调地址。
真实响应/回调验签无法在无订单、无真实回调时证明，脚本末尾会提示用一次
0.01 支付或预支付冒烟测试完成最终确认。

用法：
    python scripts/verify_wechat_pay_preflight.py
    python scripts/verify_wechat_pay_preflight.py \
        --cert-path /etc/xuanshiai/wechat-pay/apiclient_cert.pem

退出码：0=通过；1=存在失败项；2=参数错误。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402

def _mask(value: str | None, head: int = 6, tail: int = 4) -> str:
    if not value:
        return "-"
    text = value.strip()
    if len(text) <= head + tail:
        return text
    return f"{text[:head]}...{text[-tail:]}"


def _normalize_serial(value: str | None) -> str:
    return (value or "").strip().upper().lstrip("0")


def _check(condition: bool, ok: str, fail: str, failures: list[str]) -> None:
    if condition:
        print(f"PASS {ok}")
        return
    failures.append(fail)
    print(f"FAIL {fail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="微信支付 real 模式配置/证书预检")
    parser.add_argument(
        "--cert-path",
        default="/etc/xuanshiai/wechat-pay/apiclient_cert.pem",
        help="商户 API 证书路径（仅用于核对序列号和私钥匹配）",
    )
    args = parser.parse_args()

    # app.core.config 在导入时会构造全局 Settings；real 门禁失败时导入本身
    # 就会抛错，这里必须捕获，避免运维只看到 traceback。
    try:
        from app.core.config import Settings
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL 配置加载失败：{exc}")
        return 1

    try:
        settings = Settings()
    except Exception as exc:  # noqa: BLE001 - 启动校验失败要原样展示
        print(f"FAIL Settings 加载失败：{exc}")
        return 1

    failures: list[str] = []
    api_v3_key = (
        settings.wechat_pay_api_v3_key.get_secret_value().strip()
        if settings.wechat_pay_api_v3_key
        else ""
    )

    print("=== 配置摘要（已脱敏） ===")
    print(f"environment={settings.environment} mode={settings.wechat_pay_mode}")
    print(f"mch_id={settings.wechat_pay_mch_id or '-'}")
    print(f"app_id={settings.wechat_app_id or '-'} pay_app_id={settings.wechat_pay_app_id or '-'}")
    print(f"serial_no={_mask(settings.wechat_pay_serial_no)}")
    print(f"public_key_id={_mask(settings.wechat_pay_public_key_id)}")
    print(f"api_v3_key_len={len(api_v3_key.encode('utf-8'))}")
    print(f"notify_url={settings.wechat_pay_notify_url or '-'}")
    print(f"refund_notify_url={settings.wechat_pay_refund_notify_url or '-'}")

    _check(settings.wechat_pay_mode == "real", "WECHAT_PAY_MODE=real", "WECHAT_PAY_MODE 不是 real", failures)
    _check(
        (settings.wechat_app_id or "").strip() == (settings.wechat_pay_app_id or "").strip(),
        "登录 AppID 与支付 AppID 一致",
        "WECHAT_APP_ID 与 WECHAT_PAY_APP_ID 不一致",
        failures,
    )
    _check(
        bool((settings.wechat_app_secret or "").strip()),
        "WECHAT_APP_SECRET 已配置",
        "WECHAT_APP_SECRET 未配置，无法换取 openid",
        failures,
    )
    _check(len(api_v3_key.encode("utf-8")) == 32, "APIv3 密钥为 32 字节", "APIv3 密钥不是 32 字节", failures)
    _check(
        bool((settings.wechat_pay_refund_notify_url or "").startswith("https://")),
        "退款回调为 HTTPS",
        "WECHAT_PAY_REFUND_NOTIFY_URL 缺失或不是 HTTPS",
        failures,
    )
    _check(
        bool((settings.wechat_pay_notify_url or "").startswith("https://")),
        "支付回调为 HTTPS",
        "WECHAT_PAY_NOTIFY_URL 缺失或不是 HTTPS",
        failures,
    )
    if settings.wechat_pay_public_key_id:
        _check(
            settings.wechat_pay_public_key_id.startswith("PUB_KEY_ID_"),
            "公钥 ID 前缀正确",
            "WECHAT_PAY_PUBLIC_KEY_ID 必须以 PUB_KEY_ID_ 开头",
            failures,
        )

    private_pem = settings.wechat_pay_private_key_pem()
    public_pem = settings.wechat_pay_public_key_pem()
    private_key = None
    if private_pem:
        try:
            private_key = serialization.load_pem_private_key(
                private_pem.encode("utf-8"), password=None
            )
            print("PASS 商户私钥可解析")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"商户私钥无法解析：{exc}")
            print(f"FAIL 商户私钥无法解析：{exc}")
    else:
        failures.append("商户私钥未配置")
        print("FAIL 商户私钥未配置")

    if public_pem:
        try:
            serialization.load_pem_public_key(public_pem.encode("utf-8"))
            print("PASS 微信支付公钥可解析")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"微信支付公钥无法解析：{exc}")
            print(f"FAIL 微信支付公钥无法解析：{exc}")
    else:
        print("WARN 未配置微信支付公钥；平台证书模式下可忽略")

    cert_path = Path(args.cert_path)
    if not cert_path.exists():
        print(f"WARN 未找到商户证书 {cert_path}，跳过序列号/私钥匹配检查")
    else:
        try:
            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        except Exception as exc:  # noqa: BLE001
            failures.append(f"商户证书无法解析：{exc}")
            print(f"FAIL 商户证书无法解析：{exc}")
        else:
            cert_serial = format(cert.serial_number, "X")
            _check(
                _normalize_serial(cert_serial) == _normalize_serial(settings.wechat_pay_serial_no),
                f"证书序列号与配置一致（{_mask(cert_serial)}）",
                f"证书序列号与 WECHAT_PAY_SERIAL_NO 不一致：cert={_mask(cert_serial)}",
                failures,
            )
            if private_key is not None:
                cert_public = cert.public_key().public_bytes(
                    serialization.Encoding.DER,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
                private_public = private_key.public_key().public_bytes(
                    serialization.Encoding.DER,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
                _check(
                    cert_public == private_public,
                    "商户证书与私钥匹配",
                    "商户证书与私钥不匹配",
                    failures,
                )

    print()
    if failures:
        print(f"RESULT failed checks={len(failures)}")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("RESULT ok")
    print(
        "NOTE 预检只验证配置与密钥；响应/回调验签仍需一次真实 0.01 支付"
        "（或带订单的预支付冒烟测试）确认公钥 ID 与 Wechatpay-Serial。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
