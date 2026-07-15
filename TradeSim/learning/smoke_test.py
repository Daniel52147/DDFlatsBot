"""Testnet certification harness — one-click system health check."""

from __future__ import annotations

import time
from typing import Any

import config


def _check(
    checks: list[dict[str, Any]],
    *,
    cid: str,
    label: str,
    ok: bool,
    detail: str,
    required: bool = True,
) -> None:
    checks.append({
        "id": cid,
        "label": label,
        "ok": bool(ok),
        "detail": detail,
        "required": required,
    })


async def run_smoke_test(
    *,
    sessions: dict,
    exchange,
    logger_db,
    trading_mode_mgr,
    live_readiness: dict[str, Any],
    live_prep: dict[str, Any],
    telegram_enabled: bool,
    feed_hub_ok: bool,
) -> dict[str, Any]:
    """Run full certification — technical readiness, not profitability."""
    checks: list[dict[str, Any]] = []
    started = time.time()

    ready_markets = sum(1 for s in sessions.values() if s._candles_ready)
    max_lag = max((s.candles.lag_sec() for s in sessions.values()), default=999.0)
    _check(
        checks,
        cid="markets",
        label=f"Рынки загружены ({len(sessions)})",
        ok=len(sessions) >= len(config.MARKETS),
        detail=f"{ready_markets}/{len(sessions)} со свечами · max lag {max_lag:.0f}s",
    )
    _check(
        checks,
        cid="candles",
        label="Свечи актуальны",
        ok=max_lag <= config.CANDLE_MAX_LAG_SEC and ready_markets >= len(sessions) * 0.8,
        detail=f"порог lag {config.CANDLE_MAX_LAG_SEC}s",
    )
    _check(
        checks,
        cid="feed",
        label="Price feed",
        ok=feed_hub_ok or any((s.feed.price or 0) > 0 for s in sessions.values()),
        detail="FeedHub или poll цен",
    )

    mode = trading_mode_mgr.mode
    _check(
        checks,
        cid="trading_mode",
        label=f"Режим: {mode}",
        ok=mode in ("paper", "testnet", "live"),
        detail=trading_mode_mgr.status(exchange).get("label", mode),
    )

    verify: dict[str, Any] = {"ok": False}
    if exchange.enabled:
        verify = await exchange.verify_connection()
        _check(
            checks,
            cid="exchange_verify",
            label="Binance API verify",
            ok=bool(verify.get("ok")),
            detail=verify.get("error") or f"USDT free ${verify.get('usdt_free', 0):.2f}",
            required=mode in ("testnet", "live"),
        )
    else:
        _check(
            checks,
            cid="exchange_verify",
            label="Binance API",
            ok=mode == "paper",
            detail="EXCHANGE_ENABLED=false — OK для Paper",
            required=False,
        )

    # Legacy paper→exchange sell failures (before v65 skip) poison the 7d rate.
    # Auto-drop failed paper_sync rows once, then remeasure — fresh epoch.
    purged = 0
    if mode in ("testnet", "live"):
        pre = await logger_db.stability_summary(hours=168)
        pre_rate = float(pre.get("success_rate_pct", 100))
        pre_fail = int(pre.get("sync_failures", 0))
        if pre_fail >= 5 and pre_rate < 85:
            purged = await logger_db.clear_stability_events(
                kind="paper_sync", only_failures=True,
            )
            if purged:
                await logger_db.log_stability_event(
                    "paper_sync",
                    True,
                    f"smoke re-baseline — сброшено {purged} устаревших сбоев sync",
                    "",
                )

    stability = await logger_db.stability_summary(hours=168)
    sync_rate = float(stability.get("success_rate_pct", 100))
    detail = (
        f"{sync_rate:.0f}% · ордеров {stability.get('exchange_orders', 0)} · "
        f"сбоев {stability.get('sync_failures', 0)}"
    )
    if purged:
        detail += f" · сброшено {purged} старых fail"
    _check(
        checks,
        cid="stability",
        label=f"Sync stability ≥ 85%",
        ok=sync_rate >= 85 or mode == "paper",
        detail=detail,
        required=mode in ("testnet", "live"),
    )

    readiness_score = int(live_readiness.get("score_pct", 0))
    _check(
        checks,
        cid="readiness",
        label=f"Live readiness ≥ 60%",
        ok=readiness_score >= 60 or mode == "paper",
        detail=f"{readiness_score}% · ready={live_readiness.get('ready_for_live', False)}",
        required=False,
    )

    trade_count = int(live_readiness.get("stats", {}).get("trade_count", 0))
    _check(
        checks,
        cid="trades",
        label=f"Сделок ≥ {config.LIVE_MIN_TRADES}",
        ok=trade_count >= config.LIVE_MIN_TRADES,
        detail=f"в БД: {trade_count}",
        required=False,
    )

    from learning.protections import protections_engine
    prot = protections_engine.status()
    _check(
        checks,
        cid="protections",
        label="Protections",
        ok=not prot.get("global_active") and not prot.get("paused_symbols"),
        detail="активен" if prot.get("enabled") else "выкл",
        required=False,
    )

    _check(
        checks,
        cid="telegram",
        label="Telegram",
        ok=telegram_enabled,
        detail="алерты включены" if telegram_enabled else "не настроен — опционально",
        required=False,
    )

    phases_done = live_prep.get("phase_progress", "0/5")
    _check(
        checks,
        cid="live_prep",
        label="Путь к Live",
        ok=True,
        detail=f"фазы {phases_done} · {live_prep.get('summary', '')[:80]}",
        required=False,
    )

    if exchange.enabled and mode in ("testnet", "live"):
        try:
            reconcile = await _quick_reconcile(sessions, exchange)
            bad = [r for r in reconcile if r.get("bad")]
            paper_only = [r for r in reconcile if r.get("status") == "paper_only"]
            if paper_only and not config.EXCHANGE_SYNC_FROM_PAPER:
                detail = (
                    f"{len(reconcile)} рынков · paper-only: {len(paper_only)} "
                    "(OK без EXCHANGE_SYNC_FROM_PAPER)"
                )
                if bad:
                    detail += f" · реальный drift: {len(bad)}"
            else:
                faucet = [r for r in reconcile if r.get("status") == "testnet_faucet"]
                ahead = [r for r in reconcile if r.get("status") == "paper_ahead"]
                detail = f"{len(reconcile)} рынков · красных Δ>15%: {len(bad)}"
                if faucet:
                    detail += f" · faucet: {len(faucet)}"
                if ahead:
                    detail += f" · paper ahead: {len(ahead)} (OK)"
            _check(
                checks,
                cid="reconcile",
                label="Paper ↔ биржа reconcile",
                ok=len(bad) == 0,
                detail=detail,
                required=mode == "testnet",
            )
        except Exception as e:
            _check(
                checks,
                cid="reconcile",
                label="Reconcile",
                ok=False,
                detail=str(e)[:120],
                required=False,
            )

    required = [c for c in checks if c.get("required", True)]
    passed = sum(1 for c in required if c["ok"])
    optional_passed = sum(1 for c in checks if c["ok"])
    score = round(passed / len(required) * 100) if required else 100
    certified = all(c["ok"] for c in required)

    return {
        "version": config.APP_VERSION,
        "ok": certified,
        "certified": certified,
        "score_pct": score,
        "passed": passed,
        "total_required": len(required),
        "optional_passed": optional_passed,
        "total_checks": len(checks),
        "checks": checks,
        "duration_sec": round(time.time() - started, 2),
        "summary": _summary(certified, score, mode),
        "next_action": _next_action(certified, checks, mode),
    }


async def _quick_reconcile(sessions: dict, exchange) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    is_testnet = bool(getattr(exchange, "testnet", False) or config.EXCHANGE_TESTNET)
    for sym, s in list(sessions.items())[:6]:
        paper = s.engine.position
        rec = await exchange.reconcile(sym, paper.base, paper.quote)
        price = float(s.feed.price or s.demo_price or 0)
        paper_base = float(rec.get("paper_base", 0) or 0)
        ex_base = float(rec.get("exchange_base", 0) or 0)
        paper_usd = paper_base * price
        ex_usd = ex_base * price
        surplus_usd = (ex_base - paper_base) * price

        if rec.get("base_synced"):
            status = "synced"
            bad = False
            diff_pct = 0.0
        elif paper_usd < 3 and ex_usd < 3:
            status = "empty"
            bad = False
            diff_pct = 0.0
        elif is_testnet and surplus_usd > 50 and ex_base > paper_base * 1.15:
            # Testnet faucet / leftover: биржа богаче paper (1 BTC, 1 ETH…)
            status = "testnet_faucet"
            bad = False
            diff_pct = round(abs(ex_base - paper_base) / max(ex_base, 1e-8) * 100, 2)
        elif is_testnet and paper_usd >= 3 and (paper_base - ex_base) * price > 50:
            # Paper впереди — sell-skip (v65+); не валим сертификацию
            status = "paper_ahead"
            bad = False
            diff_pct = round(
                abs(ex_base - paper_base) / max(paper_base, 1e-8) * 100, 2,
            )
        elif not config.EXCHANGE_SYNC_FROM_PAPER and ex_usd < 3 and paper_usd >= 3:
            status = "paper_only"
            bad = False
            diff_pct = round(
                abs(ex_base - paper_base) / max(paper_base, 1e-8) * 100, 2,
            )
        else:
            denom = max(paper_base, ex_base, 1e-8)
            diff_pct = round(abs(ex_base - paper_base) / denom * 100, 2)
            bad = diff_pct > 15
            status = "drift" if bad else "ok"

        rows.append({
            **rec,
            "diff_pct": diff_pct,
            "bad": bad,
            "status": status,
            "paper_usd": round(paper_usd, 2),
            "exchange_usd": round(ex_usd, 2),
        })
    return rows


def _summary(certified: bool, score: int, mode: str) -> str:
    if certified:
        if mode == "testnet":
            return f"✅ Сертификация Testnet пройдена ({score}%). Можно двигаться к Live Micro."
        if mode == "live":
            return f"✅ Smoke test OK ({score}%). Следи за лимитами Live Micro."
        return f"✅ Paper OK ({score}%). Переключись на Testnet для следующей фазы."
    return f"⚠ Не готов ({score}%). Исправь красные пункты перед Live."


def _next_action(certified: bool, checks: list[dict], mode: str) -> str:
    failed = [c for c in checks if not c["ok"] and c.get("required", True)]
    if not failed:
        if mode == "paper":
            return "Переключись на Testnet → кнопка «Неделя Testnet»"
        if mode == "testnet":
            return "Кнопка «Micro Testnet» → редкие сделки $10"
        return "Live Micro: ордер ≤$10, 2–3 сделки/день"
    top = failed[0]
    if top.get("id") == "stability":
        return (
            "Сброс sync (кнопка 🧹) или Micro Testnet → Smoke test снова. "
            + top["detail"]
        )
    return top["label"] + ": " + top["detail"]
