import asyncio
import threading
import schedule
import time
from datetime import datetime
from aiohttp import web

from bot.bot import bot, dp
from bot.handlers import router
from database.db import init_db, get_stats, get_all_active_alerts, get_all_user_ids
from search.kiwi import search_one_way
from search.hot_deals import scan_hot_deals
from database.db import mark_deal_notified, get_unnotified_hot_deals
from config import ADMIN_IDS, CHANNEL_ID, WEBHOOK_URL, WEBHOOK_PATH, WEBAPP_PORT


_loop = None


def set_loop(loop):
    global _loop
    _loop = loop


# ── Scheduler jobs ─────────────────────────────────────────────────────────────

def job_scan_hot_deals():
    """Scan for hot deals every 2 hours and notify users."""
    new_deals = scan_hot_deals()
    if new_deals and _loop:
        asyncio.run_coroutine_threadsafe(_notify_hot_deals(new_deals), _loop)


def job_check_alerts():
    """Check all active alerts every hour."""
    if _loop:
        asyncio.run_coroutine_threadsafe(_check_alerts(), _loop)


def job_post_channel():
    """Post best deals to channel every 6 hours."""
    if _loop:
        asyncio.run_coroutine_threadsafe(_post_to_channel(), _loop)


def run_scheduler():
    schedule.every(2).hours.do(job_scan_hot_deals)
    schedule.every(1).hours.do(job_check_alerts)
    schedule.every(6).hours.do(job_post_channel)
    print("[Scheduler] Running: hot deals 2h, alerts 1h, channel 6h")
    while True:
        schedule.run_pending()
        time.sleep(30)


# ── Async notification tasks ───────────────────────────────────────────────────

async def _notify_hot_deals(deals: list):
    """Send hot deals to all users and channel."""
    user_ids = get_all_user_ids()
    for deal in deals[:3]:  # max 3 per cycle to avoid spam
        text = (
            f"🔥 <b>Горящий билет!</b>\n\n"
            f"✈️ <b>{deal['origin']} → {deal['destination']}</b>\n"
            f"💰 <b>{deal['price']} EUR</b>\n"
            f"🛫 {deal.get('airline', '')}\n"
            f"📅 {deal.get('depart_at', '')}\n\n"
            f"👉 <a href=\"{deal['link']}\">Купить билет</a>"
        )
        # Post to channel
        try:
            await bot.send_message(CHANNEL_ID, text, parse_mode="HTML")
        except Exception as e:
            print(f"[Channel] Error: {e}")

        # Notify users with matching alerts
        alerts = get_all_active_alerts()
        notified = set()
        for alert in alerts:
            if (alert["origin"] == deal["origin"] and
                    alert["destination"] == deal["destination"]):
                price_ok = not alert["price_max"] or deal["price"] <= alert["price_max"]
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
    """Check all active alerts against current prices."""
    alerts = get_all_active_alerts()
    if not alerts:
        return
    print(f"[Alerts] Checking {len(alerts)} active alerts...")
    checked = set()
    for alert in alerts:
        route_key = f"{alert['origin']}:{alert['destination']}"
        if route_key in checked:
            continue
        checked.add(route_key)
        try:
            flights = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda a=alert: search_one_way(
                    a["origin"], a["destination"],
                    price_max=a.get("price_max"),
                    limit=3,
                )
            )
            for flight in flights:
                if alert.get("price_max") and flight["price"] > alert["price_max"]:
                    continue
                try:
                    await bot.send_message(
                        alert["user_id"],
                        f"🎯 <b>Алерт!</b> Нашёл билет по твоему маршруту:\n\n"
                        f"✈️ <b>{flight['origin_city']} → {flight['dest_city']}</b>\n"
                        f"💰 <b>{flight['price']} EUR</b>\n"
                        f"🛫 {flight['airline']}\n"
                        f"📅 {flight['depart_at']}\n\n"
                        f"👉 <a href=\"{flight['link']}\">Купить</a>",
                        parse_mode="HTML",
                    )
                    break
                except Exception:
                    pass
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"[Alerts] Error checking {route_key}: {e}")


async def _post_to_channel():
    """Post hot deals to channel."""
    from database.db import get_recent_hot_deals
    deals = get_recent_hot_deals(limit=3)
    if not deals:
        return
    for deal in deals:
        text = (
            f"✈️ <b>{deal.get('origin', '?')} → {deal.get('destination', '?')}</b>\n"
            f"💰 <b>{deal['price']} EUR</b>\n"
            f"🛫 {deal.get('airline', '')}\n\n"
            f"🤖 @FlightsBot — дешёвые билеты из Польши"
        )
        try:
            await bot.send_message(CHANNEL_ID, text, parse_mode="HTML")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"[Channel] Post error: {e}")


# ── Startup ────────────────────────────────────────────────────────────────────

async def setup_commands():
    from aiogram.types import BotCommand, BotCommandScopeDefault
    commands = [
        BotCommand(command="start",     description="✈️ Главная"),
        BotCommand(command="search",    description="🔎 Найти билет"),
        BotCommand(command="hot",       description="🔥 Горящие билеты"),
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
    text = (
        f"✅ <b>FlightsBot запущен</b>\n\n"
        f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"👥 Пользователей: <b>{stats['users']}</b>\n"
        f"⭐ VIP: <b>{stats['vip']}</b>\n"
        f"🔔 Алертов: <b>{stats['alerts']}</b>"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception:
            pass


async def main():
    init_db()
    dp.include_router(router)

    loop = asyncio.get_running_loop()
    set_loop(loop)

    await setup_commands()
    await notify_admin_start()

    # Start scheduler in background
    threading.Thread(target=run_scheduler, daemon=True).start()

    # Initial hot deals scan
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
        print(f"✈️ FlightsBot started (webhook port {WEBAPP_PORT})")
        await asyncio.Event().wait()
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        print("✈️ FlightsBot started (polling)")
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "pre_checkout_query"],
            drop_pending_updates=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
