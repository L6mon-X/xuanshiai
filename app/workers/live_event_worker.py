"""Publish pending live outbox events to Redis."""

from __future__ import annotations

import argparse
import asyncio
import logging
from uuid import uuid4

from app.db.session import session_factory
from app.services.live import claim_pending_events, publish_outbox_event

logger = logging.getLogger(__name__)


async def run_round(batch_size: int) -> tuple[int, int]:
    if session_factory is None:
        raise RuntimeError("database is not configured")
    async with session_factory() as db:
        events = await claim_pending_events(db, batch_size)
        published = 0
        for event in events:
            if await publish_outbox_event(db, event):
                published += 1
        return len(events), published


async def run_forever(batch_size: int, idle_seconds: float) -> None:
    worker_id = f"live-event-{uuid4().hex[:8]}"
    while True:
        claimed, published = await run_round(batch_size)
        logger.info(
            "live_event_worker_round worker=%s claimed=%d published=%d",
            worker_id,
            claimed,
            published,
        )
        if claimed == 0:
            await asyncio.sleep(idle_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="直播 Outbox 事件发布 Worker")
    parser.add_argument("--once", action="store_true", help="运行一轮后退出")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--idle-seconds", type=float, default=2.0)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if not 1 <= args.batch_size <= 500:
        raise SystemExit("--batch-size must be between 1 and 500")
    if args.once:
        claimed, published = await run_round(args.batch_size)
        # stdout 摘要保持机器可解析（CLI 契约），同时补结构化日志（FIX-08）。
        print(f"claimed={claimed} published={published}")
        logger.info(
            "live_event_worker_once_summary claimed=%d published=%d",
            claimed,
            published,
        )
        return
    await run_forever(args.batch_size, max(0.1, args.idle_seconds))


if __name__ == "__main__":
    asyncio.run(main())
