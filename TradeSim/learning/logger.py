"""Persistent trade log and strategy version history for learning."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

import config
from simulator.engine import Trade


class LearningLogger:
  def __init__(self, db_path: Path | None = None):
    self.db_path = db_path or config.DB_PATH

  async def _migrate(self, db: aiosqlite.Connection):
    for stmt in (
      "ALTER TABLE trades ADD COLUMN symbol TEXT DEFAULT ''",
      "ALTER TABLE snapshots ADD COLUMN symbol TEXT DEFAULT ''",
      "ALTER TABLE strategy_versions ADD COLUMN symbol TEXT DEFAULT ''",
    ):
      try:
        await db.execute(stmt)
      except aiosqlite.OperationalError:
        pass

  async def init(self):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute("""
        CREATE TABLE IF NOT EXISTS trades (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL, symbol TEXT DEFAULT '',
          side TEXT, price REAL, amount_quote REAL, amount_base REAL,
          fee REAL, reason TEXT,
          balance_quote REAL, balance_base REAL, portfolio_value REAL,
          strategy_params TEXT
        )
      """)
      await db.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL, symbol TEXT DEFAULT '',
          price REAL, portfolio_value REAL, pnl_pct REAL, vs_hold_pct REAL,
          strategy_params TEXT
        )
      """)
      await db.execute("""
        CREATE TABLE IF NOT EXISTS strategy_versions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL, symbol TEXT DEFAULT '',
          params TEXT, reason TEXT, avg_pnl_pct REAL
        )
      """)
      await db.execute("""
        CREATE TABLE IF NOT EXISTS assistant_messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL, role TEXT, content TEXT
        )
      """)
      await self._migrate(db)
      await db.commit()

  async def log_trade(self, trade: Trade, strategy_params: dict, symbol: str = ""):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        """INSERT INTO trades
           (ts, symbol, side, price, amount_quote, amount_base, fee, reason,
            balance_quote, balance_base, portfolio_value, strategy_params)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
          trade.ts, symbol, trade.side, trade.price, trade.amount_quote,
          trade.amount_base, trade.fee, trade.reason,
          trade.balance_quote, trade.balance_base, trade.portfolio_value,
          json.dumps(strategy_params),
        ),
      )
      await db.commit()

  async def log_snapshot(self, snap: dict, strategy_params: dict, symbol: str = ""):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        """INSERT INTO snapshots
           (ts, symbol, price, portfolio_value, pnl_pct, vs_hold_pct, strategy_params)
           VALUES (?,?,?,?,?,?,?)""",
        (
          time.time(), symbol, snap["price"], snap["portfolio_value"],
          snap["pnl_pct"], snap.get("vs_hold_pct", 0), json.dumps(strategy_params),
        ),
      )
      await db.commit()

  async def log_strategy_change(self, params: dict, reason: str, avg_pnl: float, symbol: str = ""):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        "INSERT INTO strategy_versions (ts, symbol, params, reason, avg_pnl_pct) VALUES (?,?,?,?,?)",
        (time.time(), symbol, json.dumps(params), reason, avg_pnl),
      )
      await db.commit()

  async def log_assistant(self, role: str, content: str):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        "INSERT INTO assistant_messages (ts, role, content) VALUES (?,?,?)",
        (time.time(), role, content),
      )
      await db.commit()

  async def recent_trades(self, limit: int = 50, symbol: str | None = None) -> list[dict[str, Any]]:
    async with aiosqlite.connect(self.db_path) as db:
      db.row_factory = aiosqlite.Row
      if symbol:
        cur = await db.execute(
          "SELECT * FROM trades WHERE symbol = ? ORDER BY ts DESC LIMIT ?",
          (symbol, limit),
        )
      else:
        cur = await db.execute("SELECT * FROM trades ORDER BY ts DESC LIMIT ?", (limit,))
      rows = await cur.fetchall()
    return [dict(r) for r in rows]

  async def performance_summary(self) -> dict[str, Any]:
    async with aiosqlite.connect(self.db_path) as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute("SELECT COUNT(*) as c FROM trades")
      count = (await cur.fetchone())["c"]
      cur = await db.execute(
        """SELECT symbol, portfolio_value, pnl_pct, vs_hold_pct
           FROM snapshots ORDER BY ts DESC LIMIT 12"""
      )
      snapshots = [dict(r) for r in await cur.fetchall()]
      cur = await db.execute(
        "SELECT symbol, params, reason, avg_pnl_pct FROM strategy_versions ORDER BY ts DESC LIMIT 8"
      )
      versions = [dict(r) for r in await cur.fetchall()]
      cur = await db.execute(
        "SELECT symbol, COUNT(*) as c FROM trades GROUP BY symbol"
      )
      per_market = {r["symbol"]: r["c"] for r in await cur.fetchall() if r["symbol"]}
    return {
      "trade_count": count,
      "per_market": per_market,
      "recent_snapshots": snapshots,
      "strategy_versions": versions,
    }

  async def recent_assistant_messages(self, limit: int = 20) -> list[dict[str, Any]]:
    async with aiosqlite.connect(self.db_path) as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        "SELECT * FROM assistant_messages ORDER BY ts DESC LIMIT ?", (limit,)
      )
      rows = await cur.fetchall()
    return list(reversed([dict(r) for r in rows]))
