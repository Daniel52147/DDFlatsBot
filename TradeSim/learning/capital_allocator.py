"""Dynamic capital allocation — tilt buy sizes toward winning markets."""

from __future__ import annotations

from typing import Any

import time

import config


_BUY_KEYS: dict[str, str] = {
    "dca": "dca_amount",
    "grid": "grid_buy_amount",
    "momentum": "momentum_buy_amount",
    "rsi": "rsi_buy_amount",
    "scalper": "scalp_buy_amount",
}


class CapitalAllocator:
    """Boost DCA/buy amounts on markets beating hold; trim laggards."""

    def __init__(self):
        self.last_apply_ts = 0.0
        self.multipliers: dict[str, float] = {}
        self.last_summary: dict[str, Any] = {}

    def compute(self, contexts: list[dict[str, Any]]) -> dict[str, float]:
        if not contexts:
            return {}
        ranked = sorted(
            contexts,
            key=lambda c: float(c["portfolio"].get("vs_hold_pct", 0)),
            reverse=True,
        )
        n = len(ranked)
        top_n = max(1, n // 4)
        bottom_n = max(1, n // 4)
        top_syms = {c["symbol"] for c in ranked[:top_n]}
        bottom_syms = {c["symbol"] for c in ranked[-bottom_n:]}

        mults: dict[str, float] = {}
        boost = config.CAPITAL_ALLOCATOR_BOOST
        cut = config.CAPITAL_ALLOCATOR_CUT
        for ctx in ranked:
            sym = ctx["symbol"]
            vs = float(ctx["portfolio"].get("vs_hold_pct", 0))
            if sym in top_syms and vs >= config.CAPITAL_ALLOCATOR_MIN_VS_HOLD:
                mults[sym] = boost
            elif sym in bottom_syms and vs < 0:
                mults[sym] = cut
            else:
                mults[sym] = 1.0
        return mults

    def apply(self, sessions: dict, contexts: list[dict[str, Any]]) -> list[str]:
        if not config.CAPITAL_ALLOCATOR_ENABLED:
            return []
        now = time.time()
        if now - self.last_apply_ts < config.CAPITAL_ALLOCATOR_INTERVAL_SEC:
            return []

        mults = self.compute(contexts)
        self.multipliers = mults
        self.last_apply_ts = now
        changed: list[str] = []

        for ctx in contexts:
            sym = ctx["symbol"]
            if sym not in sessions:
                continue
            m = mults.get(sym, 1.0)
            if abs(m - 1.0) < 0.01:
                continue
            session = sessions[sym]
            stype = getattr(session, "strategy_type", "dca")
            key = _BUY_KEYS.get(stype, "dca_amount")
            base_params = session.base_params or session.bot.get_params()
            base_val = float(base_params.get(key, 20))
            if base_val <= 0:
                continue
            new_val = round(base_val * m, 2)
            p = dict(session.bot.get_params())
            if abs(p.get(key, 0) - new_val) < 0.5:
                continue
            p[key] = new_val
            session.set_params_bounded(p)
            changed.append(sym)

        boosted = [s for s, m in mults.items() if m > 1.01]
        trimmed = [s for s, m in mults.items() if m < 0.99]
        self.last_summary = {
            "boosted": len(boosted),
            "trimmed": len(trimmed),
            "boost_symbols": boosted[:5],
            "trim_symbols": trimmed[:5],
            "boost_mult": config.CAPITAL_ALLOCATOR_BOOST,
            "cut_mult": config.CAPITAL_ALLOCATOR_CUT,
        }
        return changed

    def status(self, sessions: dict) -> dict[str, Any]:
        markets = []
        for sym, session in sessions.items():
            stype = getattr(session, "strategy_type", "dca")
            key = _BUY_KEYS.get(stype, "dca_amount")
            markets.append({
                "symbol": sym,
                "label": session.label,
                "strategy_type": stype,
                "multiplier": round(self.multipliers.get(sym, 1.0), 2),
                "buy_amount": session.bot.get_params().get(key),
            })
        return {
            "enabled": config.CAPITAL_ALLOCATOR_ENABLED,
            "interval_sec": config.CAPITAL_ALLOCATOR_INTERVAL_SEC,
            "last_apply_ts": self.last_apply_ts,
            "summary": self.last_summary,
            "markets": markets,
        }
