"""
Auto-tactics — brain picks strategy per coin from market stats + trader signals.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import config
from learning.strategy_presets import apply_strategy_preset
from simulator.strategies import STRATEGY_META

logger = logging.getLogger(__name__)

# Trader public style → our strategy type
STYLE_TO_STRATEGY: dict[str, str] = {
    "orderflow": "scalper",
    "macro_s2f": "dca",
    "meme_momentum": "momentum",
    "scalp": "scalper",
    "swing": "momentum",
    "contrarian": "rsi",
    "macro_contrarian": "dca",
    "nft_defi": "grid",
}

STYLE_PRESET: dict[str, str] = {
    "meme_momentum": "aggressive",
    "scalp": "aggressive",
    "macro_s2f": "conservative",
    "macro_contrarian": "conservative",
    "contrarian": "balanced",
    "swing": "balanced",
    "orderflow": "aggressive",
    "nft_defi": "balanced",
}

BIAS_SCORE: dict[str, float] = {
    "bullish": 1.0,
    "accumulate": 0.9,
    "neutral": 0.2,
    "caution": -0.5,
    "defensive": -0.7,
}


class AutoTacticsEngine:
    """Automatically select and switch strategy per market."""

    def __init__(self):
        self.last_switch_ts: dict[str, float] = {}
        self.last_reasons: dict[str, dict[str, Any]] = {}
        self.total_switches = 0

    def score_strategies(self, ctx: dict[str, Any]) -> dict[str, float]:
        """Heuristic scores from live market context (no trader input)."""
        scores = {k: 0.0 for k in STRATEGY_META}
        vol = float(ctx.get("volatility_pct") or 0)
        vs = float(ctx["portfolio"].get("vs_hold_pct", 0))
        pnl = float(ctx["portfolio"].get("pnl_pct", 0))
        price = float(ctx.get("price") or 0)
        sma = ctx.get("sma")
        candles = ctx.get("candles") or []

        momentum_5 = 0.0
        if len(candles) >= 5:
            first, last = candles[0], candles[-1]
            c0 = first.get("close") if isinstance(first, dict) else getattr(first, "close", None)
            c1 = last.get("close") if isinstance(last, dict) else getattr(last, "close", None)
            if c0:
                momentum_5 = (c1 - c0) / c0 * 100

        sma_diff = 0.0
        if sma and price and sma > 0:
            sma_diff = (price - sma) / sma * 100

        if ctx.get("viral"):
            scores["scalper"] += 2.5
            scores["momentum"] += 2.0
        elif ctx.get("volatile"):
            scores["momentum"] += 2.0
            scores["rsi"] += 1.5
            scores["scalper"] += 1.0
        elif ctx.get("growth"):
            scores["grid"] += 1.5
            scores["momentum"] += 1.0
        else:
            scores["dca"] += 2.0

        if vol >= 10:
            scores["scalper"] += 1.5
            scores["momentum"] += 1.0
        elif vol <= 3:
            scores["grid"] += 1.5
            scores["dca"] += 1.0

        if sma_diff >= 2 and momentum_5 >= 0.5:
            scores["momentum"] += 2.5
        elif sma_diff <= -2 and momentum_5 <= -0.5:
            scores["dca"] += 2.0
            scores["rsi"] += 1.5
        elif abs(sma_diff) < 1:
            scores["grid"] += 2.0

        if vs < -1.5:
            scores["rsi"] += 1.5
            scores["dca"] += 0.5
        elif vs > 2:
            scores["momentum"] += 1.0

        if pnl < -5:
            scores["dca"] += 1.0
            scores["grid"] += 0.5

        return scores

    def pick_from_scores(self, scores: dict[str, float], current: str) -> tuple[str, float]:
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        best, best_score = ranked[0]
        cur_score = scores.get(current, 0)
        margin = best_score - cur_score
        return best, margin

    def decide(
        self,
        ctx: dict[str, Any],
        market_play: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """
        Return switch proposal or None.
        Trader signal wins when confidence >= threshold and bias is positive.
        """
        sym = ctx["symbol"]
        label = ctx["label"]
        current = ctx.get("strategy_type", "dca")
        now = time.time()

        if now - self.last_switch_ts.get(sym, 0) < config.AUTO_TACTICS_MIN_INTERVAL_SEC:
            return None

        # --- Trader copy (popular trader idea the brain likes) ---
        if (
            config.AUTO_TRADER_COPY_ENABLED
            and market_play
            and market_play.get("confidence", 0) >= config.AUTO_TRADER_MIN_CONFIDENCE
            and market_play.get("strategy") in STRATEGY_META
            and market_play.get("strategy") != current
        ):
            return {
                "symbol": sym,
                "label": label,
                "strategy_type": market_play["strategy"],
                "preset": market_play.get("preset"),
                "source": "trader",
                "trader": market_play.get("trader", "?"),
                "confidence": market_play["confidence"],
                "reason": market_play.get("reason", f"копируем стиль {market_play.get('trader')}"),
                "margin": market_play["confidence"],
            }

        if not config.AUTO_TACTICS_ENABLED:
            return None

        scores = self.score_strategies(ctx)
        best, margin = self.pick_from_scores(scores, current)

        if best == current or margin < config.AUTO_TACTICS_MIN_MARGIN:
            return None

        trade_count = int(ctx.get("trade_count") or 0)
        if trade_count < config.AUTO_TACTICS_MIN_TRADES:
            return None

        return {
            "symbol": sym,
            "label": label,
            "strategy_type": best,
            "preset": None,
            "source": "auto",
            "trader": None,
            "confidence": min(0.95, 0.5 + margin * 0.1),
            "reason": f"авто-выбор: {best} (margin {margin:.1f}) vs {current}",
            "margin": margin,
            "scores": {k: round(v, 2) for k, v in sorted(scores.items(), key=lambda x: -x[1])[:3]},
        }

    def apply_preset_multipliers(self, session, preset_name: str | None) -> bool:
        return self._apply_preset(session, preset_name) if preset_name else False

    async def apply_all(
        self,
        sessions: dict,
        contexts: list[dict],
        market_plays: dict[str, dict],
        shadow_lab,
        logger_db,
    ) -> list[dict[str, Any]]:
        """Apply auto tactics to all markets; returns list of changes."""
        changes: list[dict[str, Any]] = []

        for ctx in contexts:
            sym = ctx["symbol"]
            if sym not in sessions:
                continue
            session = sessions[sym]
            play = market_plays.get(ctx["label"]) or market_plays.get(sym)
            proposal = self.decide(ctx, play)
            if not proposal:
                continue

            old_type = session.strategy_type
            session.switch_strategy(proposal["strategy_type"])
            if proposal.get("preset"):
                self._apply_preset(session, proposal["preset"])
            if shadow_lab:
                shadow_lab.reset_clones(sym)

            self.last_switch_ts[sym] = time.time()
            self.last_reasons[sym] = proposal
            self.total_switches += 1

            price = session.feed.price or session.demo_price
            snap = session.engine.snapshot(price)
            reason = (
                f"{'👁️' if proposal['source'] == 'trader' else '🤖'} "
                f"{proposal['reason']} ({old_type}→{proposal['strategy_type']})"
            )
            await session.persist()
            await logger_db.log_strategy_change(
                session.bot.get_params(), reason, snap.get("pnl_pct", 0), symbol=sym,
            )
            changes.append({**proposal, "old_strategy": old_type, "params": session.bot.get_params()})
            logger.info("[%s] Auto-tactics: %s", session.label, reason)

        return changes

    def _apply_preset(self, session, preset_name: str) -> bool:
        return apply_strategy_preset(session, preset_name)

    def status(self, sessions: dict) -> dict[str, Any]:
        markets = []
        for sym, session in sessions.items():
            last = self.last_reasons.get(sym)
            markets.append({
                "symbol": sym,
                "label": session.label,
                "strategy_type": session.strategy_type,
                "last_auto": last,
                "cooldown_sec": max(
                    0,
                    int(config.AUTO_TACTICS_MIN_INTERVAL_SEC - (time.time() - self.last_switch_ts.get(sym, 0))),
                ),
            })
        return {
            "enabled": config.AUTO_TACTICS_ENABLED,
            "trader_copy": config.AUTO_TRADER_COPY_ENABLED,
            "total_switches": self.total_switches,
            "markets": markets,
        }
