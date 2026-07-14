"""Telegram alerts and remote control via Bot API."""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

import httpx

import config

logger = logging.getLogger(__name__)

CommandHandler = Callable[[str, list[str], int], Awaitable[str]]


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


class TelegramService:
    def __init__(self):
        self._offset = 0
        self._last_daily_ts = 0.0
        self._handlers: dict[str, CommandHandler] = {}
        self._free_text_handler: CommandHandler | None = None

    @property
    def enabled(self) -> bool:
        return bool(
            config.TELEGRAM_ENABLED
            and config.TELEGRAM_BOT_TOKEN
            and config.TELEGRAM_CHAT_ID
        )

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}"

    def register_command(self, name: str, handler: CommandHandler) -> None:
        self._handlers[name.lower()] = handler

    def register_free_text(self, handler: CommandHandler) -> None:
        """Handler for non-command messages: (cmd, args, user_id) -> reply."""
        self._free_text_handler = handler

    def _allowed_user(self, user_id: int) -> bool:
        allowed = config.TELEGRAM_ALLOWED_USER_IDS
        if not allowed:
            return True
        return user_id in allowed

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID),
            "token_set": bool(config.TELEGRAM_BOT_TOKEN),
            "chat_id": config.TELEGRAM_CHAT_ID or None,
            "commands": config.TELEGRAM_COMMANDS_ENABLED,
            "alert_trades": config.TELEGRAM_ALERT_TRADES,
            "allowed_user_ids": config.TELEGRAM_ALLOWED_USER_IDS,
            "bot_username": "TradeSimbot_bot",
        }

    async def verify_api(self) -> dict[str, Any]:
        if not config.TELEGRAM_BOT_TOKEN:
            return {"ok": False, "error": "no token"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(self._api_url("getMe"))
                data = r.json()
                return {"ok": bool(data.get("ok")), "bot": data.get("result", {})}
        except Exception as e:
            return {"ok": False, "error": str(e)[:120]}

    async def send_message(
        self,
        text: str,
        chat_id: str | None = None,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
    ) -> bool:
        if not self.enabled:
            return False
        cid = chat_id or config.TELEGRAM_CHAT_ID
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                payload: dict[str, Any] = {
                    "chat_id": cid,
                    "text": text[:4000],
                    "disable_web_page_preview": False,
                }
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                r = await client.post(self._api_url("sendMessage"), json=payload)
                if r.status_code != 200:
                    if parse_mode == "HTML":
                        return await self.send_message(
                            text, chat_id=cid, parse_mode="", reply_markup=reply_markup,
                        )
                    logger.warning("Telegram send failed: %s", r.text[:200])
                    return False
                return True
        except Exception as e:
            logger.warning("Telegram send error: %s", e)
            return False

    async def send_open_dashboard(self, chat_id: str | None = None, extra: str = "") -> bool:
        url = config.TRADESIM_PUBLIC_URL or "http://127.0.0.1:8765"
        text = extra or f"📊 TradeSim v{config.APP_VERSION}"
        if not config.TRADESIM_PUBLIC_URL:
            text += "\n\n<i>Задай TRADESIM_PUBLIC_URL в .env для ссылки Render.</i>"
        markup = {
            "inline_keyboard": [[{"text": "📊 Открыть TradeSim", "url": url}]],
        }
        return await self.send_message(text, chat_id=chat_id, reply_markup=markup)

    async def notify_trade(self, label: str, symbol: str, trade: Any, portfolio: dict | None = None) -> None:
        if not self.enabled or not config.TELEGRAM_ALERT_TRADES:
            return
        side = getattr(trade, "side", "")
        reason = getattr(trade, "reason", "")
        price = getattr(trade, "price", 0)
        amt = getattr(trade, "amount_quote", 0)
        pnl = portfolio.get("pnl_pct", 0) if portfolio else 0
        emoji = "🟢" if side == "buy" else "🔴"
        text = (
            f"{emoji} <b>{_escape_html(str(label))}</b> {side.upper()}\n"
            f"${amt:.2f} @ {price:.6g}\n"
            f"<i>{_escape_html(str(reason)[:120])}</i>\n"
            f"P&L портфеля: {pnl:+.2f}%"
        )
        await self.send_message(text)

    async def notify_event(self, title: str, detail: str, level: str = "info") -> None:
        if not self.enabled:
            return
        icons = {"info": "ℹ️", "warn": "⚠️", "error": "🚨", "halt": "🛑"}
        icon = icons.get(level, "ℹ️")
        await self.send_message(f"{icon} <b>{title}</b>\n{detail}")

    async def send_daily_summary(self, summary: str) -> None:
        if not self.enabled or not config.TELEGRAM_DAILY_SUMMARY:
            return
        await self.send_message(f"📊 <b>TradeSim — итог дня</b>\n{summary}")

    async def poll_once(self) -> None:
        if not self.enabled or not config.TELEGRAM_COMMANDS_ENABLED:
            return
        try:
            async with httpx.AsyncClient(timeout=35) as client:
                r = await client.get(
                    self._api_url("getUpdates"),
                    params={"offset": self._offset, "timeout": 25},
                )
                if r.status_code != 200:
                    return
                data = r.json()
                for upd in data.get("result", []):
                    self._offset = max(self._offset, upd["update_id"] + 1)
                    msg = upd.get("message") or {}
                    text = (msg.get("text") or "").strip()
                    if not text:
                        continue
                    user = msg.get("from") or {}
                    user_id = int(user.get("id", 0))
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if not self._allowed_user(user_id):
                        await self.send_message("⛔ Команды запрещены для этого user_id", chat_id=chat_id)
                        continue
                    if not text.startswith("/"):
                        if config.TELEGRAM_FREE_CHAT and self._free_text_handler:
                            try:
                                reply = await self._free_text_handler("ask", [text], user_id)
                            except Exception as e:
                                logger.exception("Telegram free text: %s", e)
                                reply = f"Ошибка: {e}"
                            await self.send_message(reply[:4000], chat_id=chat_id)
                        continue
                    parts = text.split()
                    cmd = parts[0].lstrip("/").split("@")[0].lower()
                    args = parts[1:]
                    handler = self._handlers.get(cmd)
                    if handler:
                        try:
                            reply = await handler(cmd, args, user_id)
                        except Exception as e:
                            logger.exception("Telegram cmd %s: %s", cmd, e)
                            reply = f"Ошибка: {e}"
                        if cmd == "open":
                            await self.send_open_dashboard(chat_id=chat_id, extra=reply)
                        else:
                            await self.send_message(reply, chat_id=chat_id)
                    else:
                        reply = (
                            "Команды:\n"
                            "/brain /mozg — весь мозг\n"
                            "/live — путь к Live\n"
                            "/open — открыть сайт\n"
                            "/status /balance\n"
                            "/pause /resume\n"
                            "/help"
                        )
                        await self.send_message(reply, chat_id=chat_id)
        except httpx.ReadTimeout:
            pass
        except Exception as e:
            logger.warning("Telegram poll: %s", e)

    async def run_loop(self, running: Callable[[], bool]) -> None:
        if not self.enabled:
            return
        await self.send_message(
            f"✅ TradeSim v{config.APP_VERSION} — Telegram подключён\n"
            "Команды: /status /balance /pause /resume /help"
        )
        while running():
            await self.poll_once()
            await _sleep(1)

    def should_send_daily(self, interval_sec: float = 86400) -> bool:
        now = time.time()
        if now - self._last_daily_ts >= interval_sec:
            self._last_daily_ts = now
            return True
        return False


async def _sleep(sec: float) -> None:
    import asyncio
    await asyncio.sleep(sec)


telegram_service = TelegramService()
