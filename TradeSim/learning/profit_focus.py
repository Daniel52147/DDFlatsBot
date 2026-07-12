"""Profit Focus — pause losers, boost winners, maximize edge vs hold."""

from __future__ import annotations

import logging
import time
from typing import Any

import config
from learning.strategy_presets import apply_strategy_preset

logger = logging.getLogger(__name__)

_BUY_KEYS: dict[str, str] = {
    "dca": "dca_amount",
    "grid": "grid_buy_amount",
    "momentum": "momentum_buy_amount",
    "rsi": "rsi_buy_amount",
    "scalper": "scalp_buy_amount",
}


class ProfitFocusEngine:
    """Auto-pause markets losing vs hold; boost leaders; re-enable on recovery."""

    def __init__(self):
        self.last_run_ts = 0.0
        self.paused: dict[str, str] = {}
        self.boosted: set[str] = set()
        self.last_actions: list[dict[str, Any]] = []

    def _should_run(self) -> bool:
        return time.time() - self.last_run_ts >= config.PROFIT_FOCUS_INTERVAL_SEC

    def review(self, sessions: dict) -> list[dict[str, Any]]:
        if not config.PROFIT_FOCUS_ENABLED or not self._should_run():
            return []
        self.last_run_ts = time.time()
        actions: list[dict[str, Any]] = []

        rows: list[tuple[str, Any, dict]] = []
        for sym, session in sessions.items():
            price = session.feed.price or session.demo_price
            snap = session.engine.snapshot(price)
            rows.append((sym, session, snap))

        ranked = sorted(rows, key=lambda x: float(x[2].get("vs_hold_pct", 0)), reverse=True)
        n = len(ranked)
        top_n = max(1, n // 4)

        for i, (sym, session, snap) in enumerate(ranked):
            vs = float(snap.get("vs_hold_pct", 0))
            trades = int(snap.get("trade_count", 0))
            pnl = float(snap.get("pnl_pct", 0))
            label = session.label

            if (
                session.bot.enabled
                and trades >= config.PROFIT_FOCUS_MIN_TRADES
                and vs <= config.PROFIT_FOCUS_PAUSE_VS_HOLD
                and pnl <= config.PROFIT_FOCUS_PAUSE_PNL_PCT
            ):
                session.bot.enabled = False
                self.paused[sym] = f"vs hold {vs:+.1f}%"
                actions.append({
                    "action": "pause",
                    "symbol": sym,
                    "label": label,
                    "vs_hold_pct": vs,
                    "reason": f"отстаёт от hold {vs:+.1f}%",
                })
                logger.info("[%s] ProfitFocus: bot paused (vs hold %.1f%%)", label, vs)

            elif not session.bot.enabled and sym in self.paused:
                if vs >= config.PROFIT_FOCUS_RESUME_VS_HOLD or pnl >= config.PROFIT_FOCUS_RESUME_PNL_PCT:
                    session.bot.enabled = True
                    del self.paused[sym]
                    actions.append({
                        "action": "resume",
                        "symbol": sym,
                        "label": label,
                        "vs_hold_pct": vs,
                        "reason": f"восстановление vs hold {vs:+.1f}%",
                    })
                    logger.info("[%s] ProfitFocus: bot resumed", label)

            if i < top_n and vs >= config.PROFIT_FOCUS_BOOST_MIN_VS_HOLD and session.bot.enabled:
                if sym not in self.boosted:
                    apply_strategy_preset(session, "aggressive")
                    self.boosted.add(sym)
                    actions.append({
                        "action": "boost",
                        "symbol": sym,
                        "label": label,
                        "vs_hold_pct": vs,
                        "reason": "лидер портфеля → aggressive",
                    })
                key = _BUY_KEYS.get(session.strategy_type, "dca_amount")
                p = dict(session.bot.get_params())
                base = float(session.base_params.get(key, p.get(key, 20)))
                target = round(base * config.PROFIT_FOCUS_LEADER_MULT, 2)
                if p.get(key, 0) < target * 0.95:
                    p[key] = target
                    session.set_params_bounded(p)

        self.last_actions = actions[-20:]
        return actions

    def status(self, sessions: dict) -> dict[str, Any]:
        leaders = []
        laggards = []
        for sym, session in sessions.items():
            price = session.feed.price or session.demo_price
            snap = session.engine.snapshot(price)
            row = {
                "symbol": sym,
                "label": session.label,
                "vs_hold_pct": round(float(snap.get("vs_hold_pct", 0)), 2),
                "pnl_pct": round(float(snap.get("pnl_pct", 0)), 2),
                "trades": snap.get("trade_count", 0),
                "bot_enabled": session.bot.enabled,
                "paused_by_focus": sym in self.paused,
            }
            if row["vs_hold_pct"] >= config.PROFIT_FOCUS_BOOST_MIN_VS_HOLD:
                leaders.append(row)
            elif row["vs_hold_pct"] <= config.PROFIT_FOCUS_PAUSE_VS_HOLD:
                laggards.append(row)
        leaders.sort(key=lambda x: -x["vs_hold_pct"])
        laggards.sort(key=lambda x: x["vs_hold_pct"])
        return {
            "enabled": config.PROFIT_FOCUS_ENABLED,
            "paused_count": len(self.paused),
            "paused": [
                {"symbol": s, "label": sessions[s].label if s in sessions else s, "reason": r}
                for s, r in self.paused.items()
            ],
            "leaders": leaders[:5],
            "laggards": laggards[:5],
            "last_actions": self.last_actions[-8:],
            "settings": {
                "pause_vs_hold": config.PROFIT_FOCUS_PAUSE_VS_HOLD,
                "resume_vs_hold": config.PROFIT_FOCUS_RESUME_VS_HOLD,
                "min_trades": config.PROFIT_FOCUS_MIN_TRADES,
            },
        }


def apply_profit_max_startup(sessions: dict) -> None:
    """One-shot profile on boot — active trading + focus-friendly defaults."""
    if not config.PROFIT_MAX_ON_START:
        return
    from learning.trade_mode import apply_active_all

    apply_active_all(sessions, reset_timers=False)
    logger.info("ProfitMax: active trading profile applied to %d markets", len(sessions))
