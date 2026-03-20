import asyncio
import threading
import schedule
import time
from datetime import datetime
from aiohttp import web

from bot.bot import bot, dp
from bot.handlers import router
from bot.middleware import RateLimitMiddleware
from database.db import (
    init_db, get_stats, get_all_active_alerts, get_all_user_ids,
    mark_deal_notified, get_unnotified_hot_deals,
)
from search.kiwi import search_one_way
from search.hot_deals import scan_hot_deals
from config import (
    ADMIN_IDS, CHANNEL_ID, WEBHOOK_URL, WEBHOOK_PATH, WEBAPP_PORT, BOT_NAME,
    RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW,
)

_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop):
    global _loop
    _loop = loop


# ── Scheduler jobs ─────────────────────────────────────────────────────────────

def job_scan_hot_deals():
    new_deals = scan_hot_deals()
    if new_deals and _loop:
        asyncio.run_coroutine_threadsafe(_notify_hot_deals(new_deals), _loop)


def job_check_alerts():
    if _loop:
        asyncio.run_coroutine_threadsafe(_check_alerts(), _loop)


def job_post_channel():
    if _loop:
        asyncio.run_coroutine_threadsafe(_post_to_channel(), _loop)


def run_scheduler():
    schedule.every(2).hours.do(job_scan_hot_deals)
    schedule.every(1).hours.do(job_check_alerts)
    schedule.every(6).hours.do(job_post_channel)
    print("[Scheduler] hot deals 2h | alerts 1h | channel 6h")
    while True:
        schedule.run_pending()
        time.sleep(30)


# ── Async tasks ────────────────────────────────────────────────────────────────

async def _notify_hot_deals(deals: list):
    """Post new hot deals to channel + notify users with matching alerts."""
    alerts = get_all_active_alerts()

    for deal in deals[:5]:
        from bot.keyboards import hot_deal_kb
        from bot.handlers import _dest_flag
        flag = _dest_flag(deal.get("destination", ""))
        text = (
            f"🔥 <b>Горящий билет!</b>\n\n"
            f"✈️ <b>{deal['origin']} → {deal['destination']}</b> {flag}\n"
            f"💰 <b>{deal['price']} EUR</b>\n"
            f"✈️ {deal.get('airline', '')}\n"
            f"📅 {deal.get('depart_at', '')}\n\n"
            f"👉 <a href=\"{deal['link']}\">Купить билет</a>\n\n"
            f"🤖 @SkyCheapBot"
        )
        try:
            await bot.send_message(CHANNEL_ID, text, parse_mode="HTML")
        except Exception as e:
            print(f"[Channel] {e}")

        # Notify users with matching alerts
        notified: set[int] = set()
        for alert in alerts:
            if alert["origin"] != deal["origin"] or alert["destination"] != deal["destination"]:
                continue
            price_ok = not alert.get("price_max") or deal["price"] <= alert["price_max"]
            if price_ok and alert["user_id"] not in notified:
                try:
                    await bot.send_message(
                        alert["user_id"],
                        f"🎯 <b>Алерт сработал!</b>\n\n{text}",
                        parse_mode="HTML",
                    )
                    notified.add(alert["user_id"])
                    await asyncio.sleep(0.05)
                except Exception:
                    pass

        mark_deal_notified(deal.get("id", 0))
        await asyncio.sleep(1)


async def _check_alerts():
    """Hourly: check all active alerts against live prices."""
    alerts = get_all_active_alerts()
    if not alerts:
        return
    print(f"[Alerts] Checking {len(alerts)} alerts...")
    checked: set[str] = set()
    loop = asyncio.get_event_loop()

    for alert in alerts:
        route_key = f"{alert['origin']}:{alert['destination']}"
        if route_key in checked:
            continue
        checked.add(route_key)
        try:
            flights = await loop.run_in_executor(
                None,
                lambda a=alert: search_one_way(
                    a["origin"], a["destination"],
                    price_max=a.get("price_max"),
                    limit=3,
                ),
            )
            for flight in flights:
                if alert.get("price_max") and flight["price"] > alert["price_max"]:
                    continue
                from bot.handlers import _dest_flag
                flag = _dest_flag(flight.get("destination", ""))
                try:
                    await bot.send_message(
                        alert["user_id"],
                        f"🎯 <b>Алерт!</b> Нашёл билет:\n\n"
                        f"✈️ <b>{flight['origin_city']} → {flight['dest_city']}</b> {flag}\n"
                        f"💰 <b>{flight['price']} EUR</b>\n"
                        f"✈️ {flight['airline']}\n"
                        f"📅 {flight['depart_at']}\n\n"
                        f"👉 <a href=\"{flight['link']}\">Купить</a>",
                        parse_mode="HTML",
                    )
                    break
                except Exception:
                    pass
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"[Alerts] {route_key}: {e}")


async def _post_to_channel():
    """Post recent hot deals to channel every 6 hours."""
    from database.db import get_recent_hot_deals
    deals = get_recent_hot_deals(limit=3)
    if not deals:
        return
    for deal in deals:
        from bot.handlers import _dest_flag
        flag = _dest_flag(deal.get("destination", ""))
        text = (
            f"✈️ <b>{deal.get('origin', '?')} → {deal.get('destination', '?')}</b> {flag}\n"
            f"💰 <b>{deal['price']} EUR</b>\n"
            f"✈️ {deal.get('airline', '')}\n\n"
            f"🤖 @SkyCheapBot — дешёвые билеты из Польши"
        )
        try:
            await bot.send_message(CHANNEL_ID, text, parse_mode="HTML")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"[Channel] {e}")


# ── Startup ────────────────────────────────────────────────────────────────────

async def setup_commands():
    from aiogram.types import BotCommand, BotCommandScopeDefault
    commands = [
        BotCommand(command="start",     description=f"✈️ {BOT_NAME} — главная"),
        BotCommand(command="search",    description="🔎 Найти билет"),
        BotCommand(command="hot",       description="🔥 Горящие билеты"),
        BotCommand(command="popular",   description="🌍 Популярные маршруты"),
        BotCommand(command="alert",     description="🔔 Создать алерт"),
        BotCommand(command="alerts",    description="📋 Мои алерты"),
        BotCommand(command="favorites", description="❤️ Избранное"),
        BotCommand(command="vip",       description="⭐ VIP подписка"),
        BotCommand(command="stats",     description="📊 Статистика"),
        BotCommand(command="help",      description="📖 Помощь"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    print("[Bot] Commands set")


async def notify_admin_start():
    stats = get_stats()
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"✅ <b>{BOT_NAME} запущен</b>\n\n"
                f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                f"👥 Пользователей: <b>{stats['users']}</b>\n"
                f"⭐ VIP: <b>{stats['vip']}</b>\n"
                f"🔔 Алертов: <b>{stats['alerts']}</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass


async def main():
    init_db()

    # Middleware
    dp.message.middleware(RateLimitMiddleware(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW))
    dp.callback_query.middleware(RateLimitMiddleware(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW))

    dp.include_router(router)

    loop = asyncio.get_running_loop()
    set_loop(loop)

    await setup_commands()
    await notify_admin_start()

    # Background threads
    threading.Thread(target=run_scheduler, daemon=True).start()
    threading.Thread(target=job_scan_hot_deals, daemon=True).start()

    if WEBHOOK_URL:
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
        app = web.Application()
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", WEBAPP_PORT)
        await site.start()
        print(f"✈️ {BOT_NAME} started (webhook port {WEBAPP_PORT})")
        await asyncio.Event().wait()
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        print(f"✈️ {BOT_NAME} started (polling)")
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "pre_checkout_query"],
            drop_pending_updates=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
