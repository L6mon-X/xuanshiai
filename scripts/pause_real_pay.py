#!/usr/bin/env python
"""真实微信支付的“安全暂停”检查器（只读）。

出于安全考虑，本脚本不会修改 ``.env``，也不会重启 systemd 服务；它只读取
当前模式并打印需要人工执行的精确命令。服务器配置变更应由运维人员在确认
窗口内手动执行。

关键提醒：`WECHAT_PAY_MODE=disabled` 只对包含 943f73b 守卫的代码有效。
若回滚到该提交之前的版本，development 环境仍可调用
``/api/v1/payments/test/pay`` 免费履约，必须同时在 nginx 阻断该路径。

用法：
    python scripts/pause_real_pay.py
    python scripts/pause_real_pay.py --env-file /home/xuanshiai/.env
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

DEFAULT_SERVICES = (
    "xuanshiai.service",
    "xuanshiai-payment-worker.service",
    "xuanshiai-reconcile-worker.service",
)
_MODE_LINE = re.compile(r"^\s*(?:export\s+)?WECHAT_PAY_MODE\s*=\s*(?P<value>\S*)", re.M)


def main() -> int:
    parser = argparse.ArgumentParser(description="只读检查并输出真实支付暂停步骤")
    parser.add_argument("--env-file", default=".env", help="环境变量文件路径")
    args = parser.parse_args()

    env_file = Path(args.env_file).expanduser()
    if not env_file.exists():
        print(f"FAIL 找不到环境变量文件：{env_file}")
        return 2

    text = env_file.read_text(encoding="utf-8")
    matches = list(_MODE_LINE.finditer(text))
    current = matches[-1].group("value") if matches else "<未配置>"
    print(f"env_file={env_file}")
    print(f"current_WECHAT_PAY_MODE={current}")

    if current == "disabled":
        print("RESULT already paused（预支付应返回 503；新代码 test/pay 应返回 403）")
        return 0

    print()
    print("人工执行步骤：")
    print("1) 备份 .env：")
    print(f"   cp -a {env_file} {env_file}.bak.pause-real-pay.$(date +%Y%m%d-%H%M%S)")
    print("2) 只把 WECHAT_PAY_MODE 改为 disabled；保留 WECHAT_PAYMENT_MODE=real：")
    print(
        "   python - <<'PY'\n"
        "import re\n"
        "from pathlib import Path\n"
        f"p = Path({str(env_file)!r})\n"
        "lines = p.read_text(encoding='utf-8').splitlines(keepends=True)\n"
        "out = []\n"
        "for line in lines:\n"
        "    body = line.rstrip('\\r\\n')\n"
        "    if re.match(r'^\\s*(export\\s+)?WECHAT_PAY_MODE\\s*=', body):\n"
        "        out.append('WECHAT_PAY_MODE=disabled\\n')\n"
        "    else:\n"
        "        out.append(line)\n"
        "p.write_text(''.join(out), encoding='utf-8')\n"
        "PY"
    )
    print("3) 重启支付相关服务：")
    print(f"   systemctl restart {' '.join(DEFAULT_SERVICES)}")
    print("4) 验证：")
    print("   - POST /api/v1/payments/orders/{order_no}/prepay 应返回 503")
    print("   - 新代码 POST /api/v1/payments/test/pay 应返回 403")
    print()
    print("若回滚到 943f73b 之前，额外在 nginx 增加：")
    print("   location = /api/v1/payments/test/pay { return 403; }")
    print("   location = /api/v1/payments/wechat/callback { return 403; }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
