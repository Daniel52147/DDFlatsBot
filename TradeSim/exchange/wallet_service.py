"""Unified paper + exchange wallet — bridge, deposit info, withdrawals."""

from __future__ import annotations

import logging
import time
from typing import Any

import config

logger = logging.getLogger(__name__)


async def exchange_usdt_free(exchange) -> float:
    if not exchange.enabled:
        return 0.0
    try:
        acct = await exchange.account_balances()
        for b in acct.get("balances", []):
            if b.get("asset") == "USDT":
                return float(b.get("free", 0)) + float(b.get("locked", 0))
    except Exception as e:
        logger.warning("exchange_usdt_free: %s", e)
    return 0.0


def paper_quote_total(sessions: dict) -> float:
    return sum(float(s.engine.position.quote) for s in sessions.values())


def wallet_credit_total(sessions: dict) -> float:
    return sum(float(getattr(s.engine, "wallet_credit", 0) or 0) for s in sessions.values())


async def refresh_wallet_bridge(sessions: dict, exchange, mode_mgr) -> dict[str, Any]:
    """
    On testnet/live, expose spare exchange USDT to bots via engine.wallet_credit.
    Paper quote stays as-is; bots can spend quote + credit.
    """
    if mode_mgr.mode == "paper" or not exchange.enabled or not config.WALLET_BRIDGE_ENABLED:
        for s in sessions.values():
            s.engine.wallet_credit = 0.0
        return {
            "ok": True,
            "mode": mode_mgr.mode,
            "bridged_per_market": 0.0,
            "exchange_usdt": 0.0,
            "paper_quote": paper_quote_total(sessions),
        }

    usdt = await exchange_usdt_free(exchange)
    paper_q = paper_quote_total(sessions)
    spare = max(0.0, usdt - paper_q)
    per = round(spare / max(len(sessions), 1), 2)
    for s in sessions.values():
        s.engine.wallet_credit = per

    return {
        "ok": True,
        "mode": mode_mgr.mode,
        "exchange_usdt": round(usdt, 2),
        "paper_quote": round(paper_q, 2),
        "spare_usdt": round(spare, 2),
        "bridged_per_market": per,
        "markets": len(sessions),
    }


async def mirror_usdt_to_paper(sessions: dict, exchange, amount: float | None = None) -> dict[str, Any]:
    """Move exchange USDT into paper wallets (real deposit into virtual quote)."""
    if not exchange.enabled:
        return {"ok": False, "error": "биржа выключена — задай BINANCE_API_KEY + EXCHANGE_ENABLED=true"}

    usdt_free = await exchange_usdt_free(exchange)
    if usdt_free < 1:
        return {
            "ok": False,
            "error": "На бирже нет свободного USDT",
            "usdt_free": round(usdt_free, 2),
            "testnet_faucet": "https://testnet.binance.vision/" if exchange.testnet else None,
        }

    move = float(amount) if amount and amount > 0 else usdt_free
    move = min(move, usdt_free)
    if move < 1:
        return {"ok": False, "error": "Сумма от $1"}

    per = round(move / max(len(sessions), 1), 2)
    deposited = 0.0
    for s in sessions.values():
        s.engine.position.quote += per
        deposited += per
        await s.persist()

    return {
        "ok": True,
        "mirrored_usdt": round(deposited, 2),
        "per_market": per,
        "exchange_usdt_before": round(usdt_free, 2),
        "note": "USDT зачислен в paper quote (P&L не меняется). Баланс биржи не списан.",
    }


async def wallet_summary(sessions: dict, exchange, mode_mgr) -> dict[str, Any]:
    bridge = await refresh_wallet_bridge(sessions, exchange, mode_mgr)
    paper_q = paper_quote_total(sessions)
    credit = wallet_credit_total(sessions)
    return {
        "mode": mode_mgr.mode,
        "paper_quote_usd": round(paper_q, 2),
        "wallet_credit_usd": round(credit, 2),
        "bot_available_usd": round(paper_q + credit, 2),
        "exchange_usdt": bridge.get("exchange_usdt", 0),
        "bridge": bridge,
        "bridge_enabled": config.WALLET_BRIDGE_ENABLED,
    }


async def deposit_info(exchange) -> dict[str, Any]:
    if not exchange.enabled:
        return {
            "ok": False,
            "wallet": "paper",
            "note": "Paper: кнопка «+ Пополнить». Для биржи — BINANCE_API_KEY + EXCHANGE_ENABLED=true",
        }
    if exchange.testnet:
        return {
            "ok": True,
            "wallet": "testnet",
            "coin": "USDT",
            "faucet_url": "https://testnet.binance.vision/",
            "note": "Testnet: получи USDT на faucet testnet.binance.vision, затем «Синхр. USDT → paper».",
        }
    try:
        addr = await exchange.deposit_address(
            coin="USDT",
            network=config.EXCHANGE_DEPOSIT_NETWORK,
        )
        return {
            "ok": True,
            "wallet": "live",
            "coin": "USDT",
            "network": config.EXCHANGE_DEPOSIT_NETWORK,
            **addr,
            "note": "Переводи только USDT в выбранной сети. После зачисления нажми «Синхр. USDT → paper».",
        }
    except Exception as e:
        return {"ok": False, "wallet": "live", "error": str(e)}


async def exchange_withdraw_usdt(
    exchange,
    *,
    address: str,
    amount: float,
    network: str | None = None,
    confirm_live: bool = False,
) -> dict[str, Any]:
    if not exchange.enabled:
        return {"ok": False, "error": "биржа выключена"}
    if not exchange.testnet and not confirm_live:
        return {
            "ok": False,
            "error": "Live вывод — передай confirm_live=true и проверь адрес",
        }
    amount = float(amount)
    if amount < 1:
        return {"ok": False, "error": "Минимум $1"}
    if amount > config.EXCHANGE_MAX_WITHDRAW_USD:
        return {
            "ok": False,
            "error": f"Лимит вывода ${config.EXCHANGE_MAX_WITHDRAW_USD}",
        }
    addr = (address or "").strip()
    if len(addr) < 10:
        return {"ok": False, "error": "Некорректный адрес"}

    net = network or config.EXCHANGE_WITHDRAW_NETWORK
    try:
        result = await exchange.withdraw_usdt(amount=amount, address=addr, network=net)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def paper_withdraw(
    sessions: dict,
    amount: float,
    target: str = "split",
    symbol: str | None = None,
) -> dict[str, Any]:
    amount = float(amount)
    if amount < 1 or amount > 100_000:
        return {"ok": False, "error": "Сумма от $1 до $100,000"}

    target = (target or "split").lower()
    if target == "symbol":
        if not symbol or symbol not in sessions:
            return {"ok": False, "error": "Укажи symbol, например BTCUSDT"}
        s = sessions[symbol]
        if s.engine.position.quote < amount:
            return {
                "ok": False,
                "error": f"Недостаточно USDT на {symbol}: ${s.engine.position.quote:.2f}",
            }
        s.engine.position.quote -= amount
        s.engine.start_balance = max(0.0, s.engine.start_balance - amount)
        await s.persist()
        withdrawn = amount
        note = f"С {symbol}"
    else:
        total_q = paper_quote_total(sessions)
        if total_q < amount:
            return {"ok": False, "error": f"Недостаточно USDT на paper: ${total_q:.2f}"}
        per = amount / max(len(sessions), 1)
        withdrawn = 0.0
        for s in sessions.values():
            take = min(per, s.engine.position.quote)
            if take <= 0:
                continue
            s.engine.position.quote -= take
            s.engine.start_balance = max(0.0, s.engine.start_balance - take)
            withdrawn += take
            await s.persist()
        note = f"Со всех {len(sessions)} рынков"

    return {
        "ok": True,
        "withdrawn": round(withdrawn, 2),
        "note": note,
    }
