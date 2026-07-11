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
      "ALTER TABLE sessions ADD COLUMN cost_basis REAL DEFAULT 0",
      "ALTER TABLE sessions ADD COLUMN last_dip_ts REAL DEFAULT 0",
      "ALTER TABLE sessions ADD COLUMN last_spike_ts REAL DEFAULT 0",
      "ALTER TABLE sessions ADD COLUMN last_stop_loss_ts REAL DEFAULT 0",
    ):
      try:
        await db.execute(stmt)
      except aiosqlite.OperationalError:
        pass

  async def init(self):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute("PRAGMA journal_mode=WAL")
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
      await db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
          symbol TEXT PRIMARY KEY,
          quote REAL, base REAL, trade_counter INTEGER,
          start_balance REAL, start_ts REAL,
          bot_params TEXT, last_dca_ts REAL, last_take_profit_ts REAL,
          bot_enabled INTEGER, trades_json TEXT, updated_ts REAL
        )
      """)
      await db.execute("""
        CREATE TABLE IF NOT EXISTS total_snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL, total_value REAL, pnl_pct REAL
        )
      """)
      await db.execute("""
        CREATE TABLE IF NOT EXISTS brain_cycles (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL, decision TEXT, verdict TEXT
        )
      """)
      await db.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL, amount REAL, target TEXT, symbol TEXT DEFAULT '',
          note TEXT, total_after REAL
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

  async def save_session(self, symbol: str, data: dict[str, Any]):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        """INSERT INTO sessions
           (symbol, quote, base, trade_counter, start_balance, start_ts,
            bot_params, last_dca_ts, last_take_profit_ts, bot_enabled, trades_json, updated_ts,
            cost_basis, last_dip_ts, last_spike_ts, last_stop_loss_ts)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(symbol) DO UPDATE SET
             quote=excluded.quote, base=excluded.base, trade_counter=excluded.trade_counter,
             start_balance=excluded.start_balance, start_ts=excluded.start_ts,
             bot_params=excluded.bot_params, last_dca_ts=excluded.last_dca_ts,
             last_take_profit_ts=excluded.last_take_profit_ts, bot_enabled=excluded.bot_enabled,
             trades_json=excluded.trades_json, updated_ts=excluded.updated_ts,
             cost_basis=excluded.cost_basis, last_dip_ts=excluded.last_dip_ts,
             last_spike_ts=excluded.last_spike_ts, last_stop_loss_ts=excluded.last_stop_loss_ts""",
        (
          symbol, data["quote"], data["base"], data["trade_counter"],
          data["start_balance"], data["start_ts"],
          json.dumps(data["bot_params"]), data["last_dca_ts"], data["last_take_profit_ts"],
          1 if data["bot_enabled"] else 0,
          json.dumps(data.get("trades", [])),
          time.time(),
          data.get("cost_basis", 0),
          data.get("last_dip_ts", 0),
          data.get("last_spike_ts", 0),
          data.get("last_stop_loss_ts", 0),
        ),
      )
      await db.commit()

  async def load_session(self, symbol: str) -> dict[str, Any] | None:
    async with aiosqlite.connect(self.db_path) as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute("SELECT * FROM sessions WHERE symbol = ?", (symbol,))
      row = await cur.fetchone()
    if not row:
      return None
    d = dict(row)
    d["bot_params"] = json.loads(d["bot_params"] or "{}")
    d["trades"] = json.loads(d["trades_json"] or "[]")
    d["bot_enabled"] = bool(d["bot_enabled"])
    return d

  async def clear_sessions(self):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute("DELETE FROM sessions")
      await db.commit()

  async def full_reset(self):
    async with aiosqlite.connect(self.db_path) as db:
      for table in (
        "trades", "snapshots", "strategy_versions", "assistant_messages",
        "sessions", "total_snapshots", "brain_cycles",
      ):
        await db.execute(f"DELETE FROM {table}")
      await db.commit()

  async def strategy_history(self, symbol: str | None = None, limit: int = 15) -> list[dict[str, Any]]:
    async with aiosqlite.connect(self.db_path) as db:
      db.row_factory = aiosqlite.Row
      if symbol:
        cur = await db.execute(
          """SELECT ts, symbol, params, reason, avg_pnl_pct
             FROM strategy_versions WHERE symbol = ? ORDER BY ts DESC LIMIT ?""",
          (symbol, limit),
        )
      else:
        cur = await db.execute(
          """SELECT ts, symbol, params, reason, avg_pnl_pct
             FROM strategy_versions ORDER BY ts DESC LIMIT ?""",
          (limit,),
        )
      rows = await cur.fetchall()
    out = []
    for r in rows:
      d = dict(r)
      try:
        d["params"] = json.loads(d.get("params") or "{}")
      except json.JSONDecodeError:
        d["params"] = {}
      out.append(d)
    return out

  async def log_total_snapshot(self, total_value: float, pnl_pct: float):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        "INSERT INTO total_snapshots (ts, total_value, pnl_pct) VALUES (?,?,?)",
        (time.time(), total_value, pnl_pct),
      )
      await db.commit()

  async def equity_curve(self, hours: int = 48) -> list[dict[str, Any]]:
    since = time.time() - hours * 3600
    async with aiosqlite.connect(self.db_path) as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        """SELECT ts, total_value, pnl_pct FROM total_snapshots
           WHERE ts >= ? ORDER BY ts ASC""",
        (since,),
      )
      rows = [dict(r) for r in await cur.fetchall()]
    if rows:
      return [{"time": int(r["ts"]), "value": r["total_value"], "pnl_pct": r["pnl_pct"]} for r in rows]
    async with aiosqlite.connect(self.db_path) as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        """SELECT CAST(ts / 300 AS INT) * 300 as bucket,
                  SUM(portfolio_value) as total_value
           FROM snapshots WHERE ts >= ?
           GROUP BY bucket ORDER BY bucket ASC""",
        (since,),
      )
      rows = await cur.fetchall()
    return [{"time": int(r["bucket"]), "value": round(r["total_value"], 2)} for r in rows]

  async def log_brain_cycle(self, decision: str, verdict: str):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        "INSERT INTO brain_cycles (ts, decision, verdict) VALUES (?,?,?)",
        (time.time(), decision, verdict),
      )
      await db.commit()

  async def brain_history(self, limit: int = 8) -> list[dict[str, Any]]:
    async with aiosqlite.connect(self.db_path) as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        "SELECT ts, decision, verdict FROM brain_cycles ORDER BY ts DESC LIMIT ?",
        (limit,),
      )
      rows = await cur.fetchall()
    return list(reversed([dict(r) for r in rows]))

  async def log_deposit(
      self, amount: float, target: str, symbol: str, note: str, total_after: float,
  ):
    async with aiosqlite.connect(self.db_path) as db:
      await db.execute(
        "INSERT INTO deposits (ts, amount, target, symbol, note, total_after) VALUES (?,?,?,?,?,?)",
        (time.time(), amount, target, symbol or "", note, total_after),
      )
      await db.commit()

  async def deposit_history(self, limit: int = 20) -> list[dict[str, Any]]:
    async with aiosqlite.connect(self.db_path) as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        "SELECT * FROM deposits ORDER BY ts DESC LIMIT ?", (limit,),
      )
      return [dict(r) for r in await cur.fetchall()]

  async def learning_stats(self) -> dict[str, Any]:
    async with aiosqlite.connect(self.db_path) as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute("SELECT COUNT(*) as c FROM trades")
      trades = (await cur.fetchone())["c"]
      cur = await db.execute("SELECT COUNT(*) as c FROM strategy_versions")
      tunes = (await cur.fetchone())["c"]
      cur = await db.execute(
        "SELECT COUNT(*) as c FROM strategy_versions WHERE reason LIKE '%Shadow%'"
      )
      shadow = (await cur.fetchone())["c"]
      cur = await db.execute("SELECT COUNT(*) as c FROM brain_cycles")
      brain = (await cur.fetchone())["c"]
      cur = await db.execute("SELECT COUNT(*) as c FROM deposits")
      deposits = (await cur.fetchone())["c"]
    return {
      "trades_logged": trades,
      "strategy_tunes": tunes,
      "shadow_promotions": shadow,
      "brain_cycles": brain,
      "deposits": deposits,
    }
