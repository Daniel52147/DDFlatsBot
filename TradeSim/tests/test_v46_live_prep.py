"""v46 — live prep path and live micro mode."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from learning.live_micro_mode import apply_live_micro_trading, is_live_micro_active, set_live_micro_active
from learning.live_prep import REALISM_WARNINGS, build_live_prep
from simulator.market_session import MarketSession
import config


class TestLiveMicro(unittest.TestCase):
    def test_dca_interval_at_least_12h(self):
        m = config.MARKETS[0]
        s = MarketSession(m)
        info = apply_live_micro_trading(s, reset_timers=True)
        self.assertGreaterEqual(
            info["params"]["dca_interval_hours"],
            config.LIVE_MICRO_DCA_HOURS,
        )

    def test_live_micro_flag(self):
        set_live_micro_active(True)
        self.assertTrue(is_live_micro_active())
        set_live_micro_active(False)
        self.assertFalse(is_live_micro_active())


class TestLivePrep(unittest.IsolatedAsyncioTestCase):
    async def test_build_has_phases_and_warnings(self):
        logger = MagicMock()
        logger.stability_summary = AsyncMock(return_value={
            "success_rate_pct": 100, "exchange_orders": 0, "sync_failures": 0,
        })
        logger.fee_summary = AsyncMock(return_value={"total_fees": 1, "trade_count": 10})
        mode = MagicMock()
        mode.mode = "testnet"
        mode.milestones = MagicMock(return_value={"testnet_since": 0})
        result = await build_live_prep(
            {},
            MagicMock(enabled=False),
            logger,
            mode,
            readiness={"stats": {"paper_days": 1, "testnet_days": 0, "trade_count": 5}, "score_pct": 30, "ready_for_live": False},
            benchmark={},
            verify={"ok": False},
        )
        self.assertEqual(len(result["phases"]), 5)
        self.assertGreaterEqual(len(result["realism_warnings"]), 4)
        self.assertIn("summary", result)


class TestRealismContent(unittest.TestCase):
    def test_warnings_cover_fees_and_sync(self):
        ids = {w["id"] for w in REALISM_WARNINGS}
        self.assertIn("fees", ids)
        self.assertIn("sync", ids)


if __name__ == "__main__":
    unittest.main()
