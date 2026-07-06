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

  async def init(self):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute("""
        CREATE TABLE IF NOT EXISTS trades (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL,
          side TEXT,
          price REAL,
          amount_quote REAL,
          amount_base REAL,
          fee REAL,
          reason TEXT,
          balance_quote REAL,
          balance_base REAL,
          portfolio_value REAL,
          strategy_params TEXT
        )
      """)
      await db.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL,
          price REAL,
          portfolio_value REAL,
          pnl_pct REAL,
          vs_hold_pct REAL,
          strategy_params TEXT
        )
      """)
      await db.execute("""
        CREATE TABLE IF NOT EXISTS strategy_versions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL,
          params TEXT,
          reason TEXT,
          avg_pnl_pct REAL
        )
      """)
      await db.execute("""
        CREATE TABLE IF NOT EXISTS assistant_messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL,
          role TEXT,
          content TEXT
        )
      """)
      await db.commit()

  async def log_trade(self, trade: Trade, strategy_params: dict):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        """INSERT INTO trades
           (ts, side, price, amount_quote, amount_base, fee, reason,
            balance_quote, balance_base, portfolio_value, strategy_params)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
          trade.ts, trade.side, trade.price, trade.amount_quote,
          trade.amount_base, trade.fee, trade.reason,
          trade.balance_quote, trade.balance_base, trade.portfolio_value,
          json.dumps(strategy_params),
        ),
      )
      await db.commit()

  async def log_snapshot(self, snap: dict, strategy_params: dict):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        """INSERT INTO snapshots (ts, price, portfolio_value, pnl_pct, vs_hold_pct, strategy_params)
           VALUES (?,?,?,?,?,?)""",
        (
          time.time(), snap["price"], snap["portfolio_value"],
          snap["pnl_pct"], snap["vs_hold_pct"], json.dumps(strategy_params),
        ),
      )
      await db.commit()

  async def log_strategy_change(self, params: dict, reason: str, avg_pnl: float):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        "INSERT INTO strategy_versions (ts, params, reason, avg_pnl_pct) VALUES (?,?,?,?)",
        (time.time(), json.dumps(params), reason, avg_pnl),
      )
      await db.commit()

  async def log_assistant(self, role: str, content: str):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        "INSERT INTO assistant_messages (ts, role, content) VALUES (?,?,?)",
        (time.time(), role, content),
      )
      await db.commit()

  async def recent_trades(self, limit: int = 50) -> list[dict[str, Any]]:
    async with aiosqlite.connect(self.db_path) as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        "SELECT * FROM trades ORDER BY ts DESC LIMIT ?", (limit,)
      )
      rows = await cur.fetchall()
    return [dict(r) for r in rows]

  async def performance_summary(self) -> dict[str, Any]:
    async with aiosqlite.connect(self.db_path) as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute("SELECT COUNT(*) as c FROM trades")
      count = (await cur.fetchone())["c"]
      cur = await db.execute(
        "SELECT portfolio_value, pnl_pct, vs_hold_pct FROM snapshots ORDER BY ts DESC LIMIT 1"
      )
      last = await cur.fetchone()
      cur = await db.execute(
        "SELECT params, reason, avg_pnl_pct FROM strategy_versions ORDER BY ts DESC LIMIT 5"
      )
      versions = [dict(r) for r in await cur.fetchall()]
    return {
      "trade_count": count,
      "last_snapshot": dict(last) if last else None,
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
