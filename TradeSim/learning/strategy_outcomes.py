"""Track strategy switch outcomes — did the change help vs hold?"""

from __future__ import annotations

import time
from typing import Any


async def log_switch(
    logger_db,
    *,
    symbol: str,
    old_type: str,
    new_type: str,
    vs_hold_at: float,
    pnl_at: float,
    reason: str,
) -> None:
    if old_type == new_type:
        return
    await logger_db.log_strategy_switch(
        symbol=symbol,
        old_type=old_type,
        new_type=new_type,
        vs_hold_at=vs_hold_at,
        pnl_at=pnl_at,
        reason=reason,
    )


async def evaluate_pending(logger_db, sessions: dict) -> list[dict[str, Any]]:
    """Fill vs_hold_after for switches older than evaluation window."""
    import config

    pending = await logger_db.pending_strategy_switches(config.STRATEGY_OUTCOME_EVAL_SEC)
    updated: list[dict[str, Any]] = []
    for row in pending:
        sym = row["symbol"]
        session = sessions.get(sym)
        if not session:
            continue
        price = session.feed.price or session.demo_price
        snap = session.engine.snapshot(price)
        vs_now = float(snap.get("vs_hold_pct", 0))
        vs_at = float(row.get("vs_hold_at") or 0)
        outcome_pp = vs_now - vs_at
        await logger_db.complete_strategy_switch(row["id"], vs_now, outcome_pp)
        updated.append({
            **row,
            "vs_hold_after": vs_now,
            "outcome_pp": round(outcome_pp, 2),
            "label": session.label,
        })
    return updated
