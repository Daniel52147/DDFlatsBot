from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import CHANNEL_LINK, CHANNEL_ID, ADMIN_IDS
from typing import Callable, Awaitable, Any
from collections import defaultdict
import time


async def is_subscribed(bot, user_id: int) -> bool:
    """
    Check if user is subscribed to the channel.
    Bot MUST be admin of the channel for this to work.
    Returns True if subscribed, False if not.
    On error (bot not admin, chat not found, etc.) — returns True to not block users.
    """
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status not in ("left", "kicked", "banned")
    except Exception as e:
        err = str(e).lower()
        # Suppress noisy "chat not found" / "user not found" errors
        if "not found" not in err and "deactivated" not in err:
            print(f"[Sub check] Error for {user_id}: {e}")
        return True  # Don't block on error


# Callbacks that are always allowed (subscription/payment flow)
ALLOWED_CALLBACKS = {
    "check_sub", "open_vip", "vip_how_to_pay", "vip_request", "vip_stars",
    "open_filter", "open_favorites", "open_subs", "open_stats", "open_stats_pub",
    "open_ref", "open_alerts", "open_prices", "open_today", "cancel",
    "open_hot", "open_drops", "open_map", "open_cheap", "open_notes",
    "open_compare", "open_leaderboard", "open_top", "open_feedback", "open_help",
    "reset_filters", "next", "skip", "accept_disclaimer",
    "alert_create", "open_menu",
}

# Rate limiting: max N actions per window (seconds)
_RATE_LIMIT = 8        # max requests
_RATE_WINDOW = 10      # per N seconds
_RATE_STORE_MAX = 5000  # max users to track (prevents memory leak)
_rate_store: dict[int, list] = defaultdict(list)
_rate_store_order: list = []  # insertion order for eviction


def _is_rate_limited(user_id: int) -> bool:
    """Returns True if user exceeded rate limit. Caps store size to prevent memory leak."""
    now = time.monotonic()
    # Evict oldest entries if store is too large
    if len(_rate_store) >= _RATE_STORE_MAX and user_id not in _rate_store:
        try:
            oldest = _rate_store_order.pop(0)
            _rate_store.pop(oldest, None)
        except (IndexError, KeyError):
            pass
    if user_id not in _rate_store:
        _rate_store_order.append(user_id)
    # Remove old timestamps outside the window
    _rate_store[user_id] = [t for t in _rate_store[user_id] if now - t < _RATE_WINDOW]
    if len(_rate_store[user_id]) >= _RATE_LIMIT:
        return True
    _rate_store[user_id].append(now)
    return False


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        if isinstance(event, Message):
            user = event.from_user
            bot = event.bot
            # Always allow /start
            if event.text and event.text.startswith("/start"):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            bot = event.bot
            # Allow subscription/payment callbacks
            if event.data in ALLOWED_CALLBACKS:
                return await handler(event, data)
            # Allow admin/fav/alert callbacks
            if event.data and (
                event.data.startswith("admin_") or
                event.data.startswith("fav_") or
                event.data.startswith("alert_del:") or
                event.data.startswith("alert_d:") or
                event.data.startswith("alert_pmax:") or
                event.data.startswith("alert_rooms:") or
                event.data.startswith("filter_d:") or
                event.data.startswith("filter_pmax:") or
                event.data.startswith("filter_rooms:") or
                event.data.startswith("onboard_d:") or
                event.data.startswith("onboard_p:") or
                event.data.startswith("share:") or
                event.data.startswith("sub:") or
                event.data.startswith("lang:") or
                event.data.startswith("rate:") or
                event.data.startswith("report:") or
                event.data.startswith("report_reason:") or
                event.data.startswith("note:") or
                event.data.startswith("similar:") or
                event.data.startswith("mod_") or
                event.data.startswith("vip_")
            ):
                return await handler(event, data)
        else:
            return await handler(event, data)

        # Admins bypass all checks
        if user.id in ADMIN_IDS:
            return await handler(event, data)

        # Rate limiting — prevent spam
        if _is_rate_limited(user.id):
            if isinstance(event, CallbackQuery):
                await event.answer("⏳ Не так быстро!", show_alert=False)
            return

        # Check if user is banned (vip = -1)
        try:
            from database.db import get_conn
            conn = get_conn()
            row = conn.execute("SELECT vip FROM users WHERE user_id=?", (user.id,)).fetchone()
            conn.close()
            if row and row["vip"] == -1:
                if isinstance(event, Message):
                    await event.answer("🚫 Ты заблокирован.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚫 Заблокирован", show_alert=True)
                return
        except Exception:
            pass

        if not await is_subscribed(bot, user.id):
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="📢 Подписаться на @ddflots",
                    url=CHANNEL_LINK
                )],
                [InlineKeyboardButton(
                    text="✅ Я подписался — проверить",
                    callback_data="check_sub"
                )],
            ])
            text = (
                "🔒 <b>Доступ закрыт</b>\n\n"
                "Чтобы пользоваться ботом — подпишись на канал @ddflots\n\n"
                "Там публикуем:\n"
                "🏠 Лучшие квартиры дня\n"
                "📊 Статистику рынка аренды Варшавы\n"
                "💡 Советы по аренде\n\n"
                "После подписки нажми кнопку ниже 👇"
            )
            if isinstance(event, Message):
                await event.answer(text, reply_markup=kb, parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer("❌ Сначала подпишись на канал!", show_alert=True)
                await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
            return

        return await handler(event, data)
