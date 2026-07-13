"""Walk-forward validation — out-of-sample backtest before promoting params."""

from __future__ import annotations

from typing import Any

import config
from simulator.backtest import Backtester


def _candle_dicts(candles: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for c in candles or []:
        if isinstance(c, dict):
            out.append(c)
        else:
            out.append(c.to_dict() if hasattr(c, "to_dict") else dict(c))
    return out


def walkforward_validate(
    candles: list[Any],
    strategy_type: str,
    live_params: dict[str, Any],
    candidate_params: dict[str, Any],
    *,
    train_ratio: float | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """
    Split candles into train/test; candidate must beat live on OOS test window.
    Returns (ok, note, metrics).
    """
    if not config.SHADOW_WALKFORWARD_ENABLED:
        return True, "", {}

    rows = _candle_dicts(candles)
    min_len = config.SHADOW_WALKFORWARD_MIN_CANDLES
    if len(rows) < min_len:
        return True, "мало свечей для walk-forward", {"candles": len(rows)}

    ratio = train_ratio if train_ratio is not None else config.SHADOW_WALKFORWARD_TRAIN_RATIO
    split = max(min_len // 2, int(len(rows) * ratio))
    if split >= len(rows) - 10:
        split = len(rows) - 10
    test = rows[split:]
    if len(test) < 10:
        return True, "короткий OOS окно", {"test_candles": len(test)}

    bal = config.SHADOW_BALANCE
    live_bt = Backtester(
        initial_balance=bal,
        strategy_type=strategy_type,
        params=live_params,
    ).run(test)
    cand_bt = Backtester(
        initial_balance=bal,
        strategy_type=strategy_type,
        params=candidate_params,
    ).run(test)

    live_vs = float(live_bt.get("vs_hold_pct") or -999)
    cand_vs = float(cand_bt.get("vs_hold_pct") or -999)
    edge = cand_vs - live_vs
    metrics = {
        "oos_live_vs_hold": round(live_vs, 2),
        "oos_candidate_vs_hold": round(cand_vs, 2),
        "oos_edge_pp": round(edge, 2),
        "test_candles": len(test),
    }

    if edge < config.SHADOW_WALKFORWARD_MIN_EDGE:
        return False, (
            f"walk-forward OOS: клон {cand_vs:+.2f}% vs live {live_vs:+.2f}% "
            f"(Δ {edge:+.2f}pp < {config.SHADOW_WALKFORWARD_MIN_EDGE})"
        ), metrics

    return True, f"walk-forward OOS OK: {cand_vs:+.2f}% vs live {live_vs:+.2f}%", metrics
