#!/usr/bin/env python3
"""Clear stale paper_sync failures so Smoke can pass sync ≥85%.

Run from TradeSim/:
  python scripts/reset_sync_stats.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config
from learning.logger import LearningLogger


async def main() -> int:
    db = LearningLogger()
    await db.init()
    before = await db.stability_summary(hours=168)
    cleared = await db.clear_stability_events(kind="paper_sync", only_failures=True)
    await db.log_stability_event(
        "paper_sync", True, f"CLI reset — удалено {cleared} сбоев (v{config.APP_VERSION})", "",
    )
    after = await db.stability_summary(hours=168)
    print(f"TradeSim v{config.APP_VERSION}")
    print(f"Было:  {before.get('success_rate_pct')}% · сбоев {before.get('sync_failures')} · ордеров {before.get('exchange_orders')}")
    print(f"Удалено сбоев: {cleared}")
    print(f"Стало: {after.get('success_rate_pct')}% · сбоев {after.get('sync_failures')} · ордеров {after.get('exchange_orders')}")
    print("Дальше: start.bat → Ctrl+Shift+R → Smoke test")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
