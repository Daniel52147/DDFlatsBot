from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import CHANNEL_LINK, CHANNEL_ID, ADMIN_IDS
from typing import Callable, Awaitable, Any
from collections import defaultdict
import time

# ── Rate limit config ─────────────────────────────────────────
# Adjust these to tune anti-spam behaviour
RATE_LIMIT_MESSAGES  = 5    # max messages per window
RATE_LIMIT_CALLBACKS = 12   # callbacks are cheaper — allow more
RATE_WINDOW          = 10   # seconds
RATE_STORE_MAX       = 8000 # max users tracked in memory

_msg_store:  dict[int, list] = defaultdict(list)
_cb_store:   dict[int, list] = defaultdict(list)
_store_order: list[int] = []


def _check_rate(store: dict, user_id: int, limit: int) -> bool:
    """Returns True if user is rate-limited. Thread-safe enough for asyncio."""
    now = time.monotonic()
    # Evict oldest entry if store is full
    if len(store) >= RATE_STORE_MAX and user_id not in store:
        try:
            oldest = _store_order.pop(0)
            store.pop(oldest, None)
        except (IndexError, KeyError):
            pass
    if user_id not in store:
        _store_order.append(user_id)
    # Drop timestamps outside window
    store[user_id] = [t for t in store[user_id] if now - t < RATE_WINDOW]
    if len(store[user_id]) >= limit:
        return True
    store[user_id].append(now)
    return False


async def is_subscribed(bot, user_id: int) -> bool:
    """
    Check channel subscription. Bot must be admin of the channel.
    Returns True on any error to avoid blocking users.
    """
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status not in ("left", "kicked", "banned")
    except Exception as e:
        err = str(e).lower()
        if "not found" not in err and "deactivated" not in err:
            print(f"[Sub check] Error for {user_id}: {e}")
        return True  # fail open — don't block on error


# Callbacks always allowed regardless of subscription
ALLOWED_CALLBACKS = {
    "check_sub",
    "open_filter", "open_favorites", "open_alerts", "open_stats", "open_subscribe",
    "open_ref", "open_today", "cancel", "reset_filters",
    "open_hot", "open_drops", "open_map", "open_cheap", "open_notes", "open_digest",
    "open_compare", "open_leaderboard", "open_menu", "open_daily", "open_platforms",
    "open_advanced", "open_lang", "open_today", "adv_apply", "adv_reset",
    "adv_district", "adv_price", "adv_rooms_min", "adv_rooms_max",
    "adv_area", "adv_ppm", "adv_floor",
    "daily_loc_custom",
    "next", "skip", "prev", "alert_create", "noop",
    "accept_disclaimer",
}

# Callback prefixes always allowed
ALLOWED_PREFIXES = (
    "admin_", "fav_", "fav_page:", "alert_del:", "alert_d:", "alert_pmax:", "alert_rooms:",
    "filter_d:", "filter_pmax:", "filter_rooms:", "filter_furn:",
    "onboard_", "share:", "sub:", "lang:", "rate:", "report_reason:",
    "note:", "similar:", "mod_", "seen:", "hide:", "found:", "scam:",
    "toggle_hide_seen", "toggle_search_radius", "open_settings", "open_city_pick",
    "daily_days:", "city_select:", "quick:",
    "adv_", "adv_d:", "adv_p:", "adv_rmin:", "adv_rmax:", "adv_a:",
    "adv_pm:", "adv_fl:", "adv_toggle:",
    "daily_loc:", "daily_ci:", "daily_co:", "daily_g:", "daily_t:",
)


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        # Determine user and bot
        if isinstance(event, Message):
            user = event.from_user
            bot  = event.bot
            if event.text and event.text.startswith("/start"):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            bot  = event.bot
            cb   = event.data or ""
            if cb in ALLOWED_CALLBACKS or any(cb.startswith(p) for p in ALLOWED_PREFIXES):
                return await handler(event, data)
        else:
            return await handler(event, data)

        # Admins bypass everything
        if user.id in ADMIN_IDS:
            return await handler(event, data)

        # ── Rate limiting ─────────────────────────────────────
        if isinstance(event, Message):
            if _check_rate(_msg_store, user.id, RATE_LIMIT_MESSAGES):
                # Silent drop for messages — no reply to avoid feedback loop
                return
        elif isinstance(event, CallbackQuery):
            if _check_rate(_cb_store, user.id, RATE_LIMIT_CALLBACKS):
                from database.db import get_user_lang
                from bot.i18n import t
                _lg = get_user_lang(user.id) or "ru"
                await event.answer(t(_lg, "mw_rate_limit"), show_alert=False)
                return

        # ── Ban check ─────────────────────────────────────────
        try:
            from database.db import get_conn
            conn = get_conn()
            row  = conn.execute("SELECT vip FROM users WHERE user_id=?", (user.id,)).fetchone()
            conn.close()
            if row and row["vip"] == -1:
                from database.db import get_user_lang
                from bot.i18n import t
                _lg = get_user_lang(user.id) or "ru"
                if isinstance(event, Message):
                    await event.answer(t(_lg, "mw_banned"))
                elif isinstance(event, CallbackQuery):
                    await event.answer(t(_lg, "mw_banned_cb"), show_alert=True)
                return
        except Exception:
            pass

        # ── Subscription check ────────────────────────────────
        if not await is_subscribed(bot, user.id):
            from database.db import get_user_lang
            from bot.i18n import t
            _lg = get_user_lang(user.id) or "ru"
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=t(_lg, "mw_subscribe_btn"),
                    url=CHANNEL_LINK,
                )],
                [InlineKeyboardButton(
                    text=t(_lg, "mw_sub_check"),
                    callback_data="check_sub",
                )],
            ])
            text = t(_lg, "mw_sub_title") + t(_lg, "mw_sub_body")
            if isinstance(event, Message):
                await event.answer(text, reply_markup=kb, parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer(t(_lg, "mw_sub_first"), show_alert=True)
                await event.message.answer(text, reply_markup=kb, parse_mode="HTML")
            return

        return await handler(event, data)
