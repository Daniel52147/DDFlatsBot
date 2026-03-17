from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import CHANNEL_LINK, CHANNEL_ID, ADMIN_IDS
from typing import Callable, Awaitable, Any


async def is_subscribed(bot, user_id: int) -> bool:
    """
    Check if user is subscribed to the channel.
    Bot MUST be admin of the channel for this to work.
    Returns True if subscribed, False if not.
    On error (bot not admin, etc.) — returns True to not block users.
    """
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status not in ("left", "kicked", "banned")
    except Exception as e:
        print(f"[Sub check] Error for {user_id}: {e}")
        # If bot is not admin of channel — allow access (fail open)
        # To fix: add bot as admin of @ddflots channel
        return True


# Callbacks that are always allowed (subscription/payment flow)
ALLOWED_CALLBACKS = {
    "check_sub", "open_vip", "vip_how_to_pay", "vip_request", "vip_stars",
    "open_filter", "open_favorites", "open_subs", "open_stats",
    "open_ref", "open_alerts", "open_prices", "open_today", "cancel",
}


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
            # Allow admin_approve/reject callbacks
            if event.data and (
                event.data.startswith("admin_") or
                event.data.startswith("fav_") or
                event.data.startswith("alert_del:")
            ):
                return await handler(event, data)
        else:
            return await handler(event, data)

        # Admins bypass subscription check
        if user.id in ADMIN_IDS:
            return await handler(event, data)

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
