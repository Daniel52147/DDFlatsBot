"""Persistent trade log and strategy version history for learning."""

from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

import config
from simulator.engine import Trade


class LearningLogger:
  def __init__(self, db_path: Path | None = None):
    self.db_path = db_path or config.DB_PATH

  @asynccontextmanager
  async def _connect(self):
    db = await aiosqlite.connect(self.db_path, timeout=30.0)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=30000")
    try:
      yield db
    finally:
      await db.close()

  async def _migrate(self, db: aiosqlite.Connection):
    for stmt in (
      "ALTER TABLE trades ADD COLUMN symbol TEXT DEFAULT ''",
      "ALTER TABLE snapshots ADD COLUMN symbol TEXT DEFAULT ''",
      "ALTER TABLE strategy_versions ADD COLUMN symbol TEXT DEFAULT ''",
      "ALTER TABLE sessions ADD COLUMN cost_basis REAL DEFAULT 0",
      "ALTER TABLE sessions ADD COLUMN last_dip_ts REAL DEFAULT 0",
      "ALTER TABLE sessions ADD COLUMN last_spike_ts REAL DEFAULT 0",
      "ALTER TABLE sessions ADD COLUMN last_stop_loss_ts REAL DEFAULT 0",
      "ALTER TABLE sessions ADD COLUMN start_price REAL DEFAULT 0",
      "ALTER TABLE sessions ADD COLUMN strategy_type TEXT DEFAULT 'dca'",
      "ALTER TABLE sessions ADD COLUMN bot_state TEXT DEFAULT '{}'",
      "ALTER TABLE total_snapshots ADD COLUMN hold_value REAL DEFAULT 0",
      "ALTER TABLE total_snapshots ADD COLUMN hold_pnl_pct REAL DEFAULT 0",
      "ALTER TABLE sessions ADD COLUMN benchmark_hold_price REAL DEFAULT 0",
      "ALTER TABLE sessions ADD COLUMN benchmark_hold_anchor TEXT DEFAULT ''",
    ):
      try:
        await db.execute(stmt)
      except aiosqlite.OperationalError:
        pass

  async def init(self):
    async with self._connect() as db:
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
          bot_enabled INTEGER, trades_json TEXT, updated_ts REAL,
          bot_state TEXT DEFAULT '{}'
        )
      """)
      await db.execute("""
        CREATE TABLE IF NOT EXISTS total_snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL, total_value REAL, pnl_pct REAL,
          hold_value REAL DEFAULT 0, hold_pnl_pct REAL DEFAULT 0
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
      await db.execute("""
        CREATE TABLE IF NOT EXISTS strategy_switches (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL, symbol TEXT,
          old_type TEXT, new_type TEXT,
          vs_hold_at REAL, pnl_at REAL,
          vs_hold_after REAL, outcome_pp REAL,
          evaluated INTEGER DEFAULT 0,
          reason TEXT
        )
      """)
      await db.execute("""
        CREATE TABLE IF NOT EXISTS exchange_snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL,
          exchange_total REAL, paper_total REAL,
          delta_usd REAL, usdt_free REAL,
          paper_vs_hold_pct REAL
        )
      """)
      await db.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts REAL, amount REAL, target TEXT, symbol TEXT DEFAULT '',
          note TEXT, total_after REAL, wallet TEXT DEFAULT 'paper'
        )
      """)
      await self._migrate(db)
      await db.commit()

  async def log_trade(self, trade: Trade, strategy_params: dict, symbol: str = ""):
    async with self._connect() as db:
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
    async with self._connect() as db:
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
    async with self._connect() as db:
      await db.execute(
        "INSERT INTO strategy_versions (ts, symbol, params, reason, avg_pnl_pct) VALUES (?,?,?,?,?)",
        (time.time(), symbol, json.dumps(params), reason, avg_pnl),
      )
      await db.commit()

  async def log_assistant(self, role: str, content: str):
    async with self._connect() as db:
      await db.execute(
        "INSERT INTO assistant_messages (ts, role, content) VALUES (?,?,?)",
        (time.time(), role, content),
      )
      await db.commit()

  async def recent_trades(self, limit: int = 50, symbol: str | None = None) -> list[dict[str, Any]]:
    return await self.all_trades(symbol=symbol, limit=limit)

  async def all_trades_for_symbol(self, symbol: str, limit: int | None = None) -> list[dict[str, Any]]:
    return await self.all_trades(symbol=symbol, limit=limit, ascending=True)

  async def all_trades(
      self,
      symbol: str | None = None,
      limit: int | None = None,
      ascending: bool = False,
  ) -> list[dict[str, Any]]:
    order = "ASC" if ascending else "DESC"
    async with self._connect() as db:
      db.row_factory = aiosqlite.Row
      if symbol:
        sql = f"SELECT * FROM trades WHERE symbol = ? ORDER BY ts {order}"
        params: tuple = (symbol,)
      else:
        sql = f"SELECT * FROM trades ORDER BY ts {order}"
        params = ()
      if limit is not None:
        sql += " LIMIT ?"
        params = (*params, limit)
      cur = await db.execute(sql, params)
      rows = await cur.fetchall()
    out = []
    for r in rows:
      d = dict(r)
      d.pop("strategy_params", None)
      out.append(d)
    if not ascending:
      return out
    return out

  async def performance_summary(self) -> dict[str, Any]:
    async with self._connect() as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute("SELECT COUNT(*) as c FROM trades")
      count = (await cur.fetchone())["c"]
      cur = await db.execute(
        """SELECT symbol, portfolio_value, pnl_pct, vs_hold_pct
           FROM snapshots ORDER BY ts DESC LIMIT 12"""
      )
      snapshots = [dict(r) for r in await cur.fetchall()]
      cur = await db.execute(
        "SELECT ts, symbol, params, reason, avg_pnl_pct FROM strategy_versions ORDER BY ts DESC LIMIT 8"
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
    async with self._connect() as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        "SELECT * FROM assistant_messages ORDER BY ts DESC LIMIT ?", (limit,)
      )
      rows = await cur.fetchall()
    return list(reversed([dict(r) for r in rows]))

  async def save_session(self, symbol: str, data: dict[str, Any]):
    async with self._connect() as db:
      await db.execute(
        """INSERT INTO sessions
           (symbol, quote, base, trade_counter, start_balance, start_ts,
            bot_params, last_dca_ts, last_take_profit_ts, bot_enabled, trades_json, updated_ts,
            cost_basis, last_dip_ts, last_spike_ts, last_stop_loss_ts, start_price, strategy_type,
            bot_state, benchmark_hold_price, benchmark_hold_anchor)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(symbol) DO UPDATE SET
             quote=excluded.quote, base=excluded.base, trade_counter=excluded.trade_counter,
             start_balance=excluded.start_balance, start_ts=excluded.start_ts,
             bot_params=excluded.bot_params, last_dca_ts=excluded.last_dca_ts,
             last_take_profit_ts=excluded.last_take_profit_ts, bot_enabled=excluded.bot_enabled,
             trades_json=excluded.trades_json, updated_ts=excluded.updated_ts,
             cost_basis=excluded.cost_basis, last_dip_ts=excluded.last_dip_ts,
             last_spike_ts=excluded.last_spike_ts, last_stop_loss_ts=excluded.last_stop_loss_ts,
             start_price=excluded.start_price, strategy_type=excluded.strategy_type,
             bot_state=excluded.bot_state,
             benchmark_hold_price=excluded.benchmark_hold_price,
             benchmark_hold_anchor=excluded.benchmark_hold_anchor""",
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
          data.get("start_price", 0),
          data.get("strategy_type", "dca"),
          json.dumps(data.get("bot_state", {})),
          data.get("benchmark_hold_price", 0),
          data.get("benchmark_hold_anchor", ""),
        ),
      )
      await db.commit()

  async def load_session(self, symbol: str) -> dict[str, Any] | None:
    async with self._connect() as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute("SELECT * FROM sessions WHERE symbol = ?", (symbol,))
      row = await cur.fetchone()
    if not row:
      return None
    d = dict(row)
    d["bot_params"] = json.loads(d["bot_params"] or "{}")
    d["trades"] = json.loads(d["trades_json"] or "[]")
    d["bot_enabled"] = bool(d["bot_enabled"])
    try:
        d["bot_state"] = json.loads(d.get("bot_state") or "{}")
    except json.JSONDecodeError:
        d["bot_state"] = {}
    return d

  async def clear_sessions(self):
    async with self._connect() as db:
      await db.execute("DELETE FROM sessions")
      await db.commit()

  async def full_reset(self):
    async with self._connect() as db:
      for table in (
        "trades", "snapshots", "strategy_versions", "assistant_messages",
        "sessions", "total_snapshots", "brain_cycles", "deposits",
        "strategy_switches", "exchange_snapshots",
      ):
        await db.execute(f"DELETE FROM {table}")
      await db.commit()

  async def strategy_history(self, symbol: str | None = None, limit: int = 15) -> list[dict[str, Any]]:
    async with self._connect() as db:
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

  async def log_total_snapshot(
      self, total_value: float, pnl_pct: float,
      hold_value: float = 0, hold_pnl_pct: float = 0,
  ):
    async with self._connect() as db:
      await db.execute(
        """INSERT INTO total_snapshots (ts, total_value, pnl_pct, hold_value, hold_pnl_pct)
           VALUES (?,?,?,?,?)""",
        (time.time(), total_value, pnl_pct, hold_value, hold_pnl_pct),
      )
      await db.commit()

  async def equity_curve(self, hours: int = 48) -> list[dict[str, Any]]:
    since = time.time() - hours * 3600
    async with self._connect() as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        """SELECT ts, total_value, pnl_pct, hold_value, hold_pnl_pct
           FROM total_snapshots WHERE ts >= ? ORDER BY ts ASC""",
        (since,),
      )
      rows = [dict(r) for r in await cur.fetchall()]
    if rows:
      return [{
        "time": int(r["ts"]),
        "value": r["total_value"],
        "hold_value": r.get("hold_value") or r["total_value"],
        "pnl_pct": r["pnl_pct"],
        "hold_pnl_pct": r.get("hold_pnl_pct", 0),
      } for r in rows]
    async with self._connect() as db:
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
    async with self._connect() as db:
      await db.execute(
        "INSERT INTO brain_cycles (ts, decision, verdict) VALUES (?,?,?)",
        (time.time(), decision, verdict),
      )
      await db.commit()

  async def brain_history(self, limit: int = 8) -> list[dict[str, Any]]:
    async with self._connect() as db:
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
    async with self._connect() as db:
      await db.execute(
        "INSERT INTO deposits (ts, amount, target, symbol, note, total_after) VALUES (?,?,?,?,?,?)",
        (time.time(), amount, target, symbol or "", note, total_after),
      )
      await db.commit()

  async def deposit_history(self, limit: int = 20) -> list[dict[str, Any]]:
    async with self._connect() as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        "SELECT * FROM deposits ORDER BY ts DESC LIMIT ?", (limit,),
      )
      return [dict(r) for r in await cur.fetchall()]

  async def log_withdrawal(
      self, amount: float, target: str, symbol: str, note: str, total_after: float,
      wallet: str = "paper",
  ):
    async with self._connect() as db:
      await db.execute(
        "INSERT INTO withdrawals (ts, amount, target, symbol, note, total_after, wallet) VALUES (?,?,?,?,?,?,?)",
        (time.time(), amount, target, symbol or "", note, total_after, wallet),
      )
      await db.commit()

  async def withdrawal_history(self, limit: int = 20) -> list[dict[str, Any]]:
    async with self._connect() as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        "SELECT * FROM withdrawals ORDER BY ts DESC LIMIT ?", (limit,),
      )
      return [dict(r) for r in await cur.fetchall()]

  async def wallet_movements(self, limit: int = 30) -> list[dict[str, Any]]:
    deposits = await self.deposit_history(limit)
    withdrawals = await self.withdrawal_history(limit)
    rows: list[dict[str, Any]] = []
    for d in deposits:
      rows.append({
        "ts": d["ts"],
        "kind": "deposit",
        "amount": d["amount"],
        "target": d.get("target", ""),
        "symbol": d.get("symbol", ""),
        "note": d.get("note", ""),
        "wallet": "paper",
      })
    for w in withdrawals:
      rows.append({
        "ts": w["ts"],
        "kind": "withdraw",
        "amount": w["amount"],
        "target": w.get("target", ""),
        "symbol": w.get("symbol", ""),
        "note": w.get("note", ""),
        "wallet": w.get("wallet", "paper"),
      })
    rows.sort(key=lambda r: r["ts"], reverse=True)
    return rows[:limit]

  async def learning_stats(self) -> dict[str, Any]:
    async with self._connect() as db:
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

  async def fee_summary(self, hours: int = 168) -> dict[str, Any]:
    since = time.time() - hours * 3600
    async with self._connect() as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        "SELECT COALESCE(SUM(fee), 0) as total, COUNT(*) as n FROM trades WHERE ts >= ?",
        (since,),
      )
      row = dict(await cur.fetchone())
      cur = await db.execute(
        """SELECT symbol, COALESCE(SUM(fee), 0) as fees, COUNT(*) as trades
           FROM trades WHERE ts >= ? GROUP BY symbol ORDER BY fees DESC LIMIT 10""",
        (since,),
      )
      per = [dict(r) for r in await cur.fetchall()]
    return {
      "hours": hours,
      "total_fees": round(float(row.get("total") or 0), 4),
      "trade_count": int(row.get("n") or 0),
      "per_symbol": per,
    }

  async def trades_since(self, since_ts: float, limit: int = 500) -> list[dict[str, Any]]:
    async with self._connect() as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        "SELECT * FROM trades WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
        (since_ts, limit),
      )
      return [dict(r) for r in await cur.fetchall()]

  async def log_strategy_switch(
      self,
      *,
      symbol: str,
      old_type: str,
      new_type: str,
      vs_hold_at: float,
      pnl_at: float,
      reason: str,
  ):
    async with self._connect() as db:
      await db.execute(
        """INSERT INTO strategy_switches
           (ts, symbol, old_type, new_type, vs_hold_at, pnl_at, reason, evaluated)
           VALUES (?,?,?,?,?,?,?,0)""",
        (time.time(), symbol, old_type, new_type, vs_hold_at, pnl_at, reason),
      )
      await db.commit()

  async def pending_strategy_switches(self, min_age_sec: float) -> list[dict[str, Any]]:
    cutoff = time.time() - min_age_sec
    async with self._connect() as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        """SELECT * FROM strategy_switches
           WHERE evaluated = 0 AND ts <= ? ORDER BY ts ASC LIMIT 20""",
        (cutoff,),
      )
      return [dict(r) for r in await cur.fetchall()]

  async def complete_strategy_switch(
      self, switch_id: int, vs_hold_after: float, outcome_pp: float,
  ):
    async with self._connect() as db:
      await db.execute(
        """UPDATE strategy_switches
           SET vs_hold_after = ?, outcome_pp = ?, evaluated = 1 WHERE id = ?""",
        (vs_hold_after, outcome_pp, switch_id),
      )
      await db.commit()

  async def strategy_switch_history(self, limit: int = 30) -> list[dict[str, Any]]:
    async with self._connect() as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        """SELECT * FROM strategy_switches ORDER BY ts DESC LIMIT ?""",
        (limit,),
      )
      return [dict(r) for r in await cur.fetchall()]

  async def log_exchange_snapshot(
      self,
      exchange_total: float,
      paper_total: float,
      usdt_free: float,
      paper_vs_hold_pct: float,
  ):
    async with self._connect() as db:
      await db.execute(
        """INSERT INTO exchange_snapshots
           (ts, exchange_total, paper_total, delta_usd, usdt_free, paper_vs_hold_pct)
           VALUES (?,?,?,?,?,?)""",
        (
          time.time(), exchange_total, paper_total,
          exchange_total - paper_total, usdt_free, paper_vs_hold_pct,
        ),
      )
      await db.commit()

  async def exchange_pnl_curve(self, hours: int = 48) -> list[dict[str, Any]]:
    since = time.time() - hours * 3600
    async with self._connect() as db:
      db.row_factory = aiosqlite.Row
      cur = await db.execute(
        """SELECT ts, exchange_total, paper_total, delta_usd, paper_vs_hold_pct
           FROM exchange_snapshots WHERE ts >= ? ORDER BY ts ASC""",
        (since,),
      )
      return [dict(r) for r in await cur.fetchall()]
