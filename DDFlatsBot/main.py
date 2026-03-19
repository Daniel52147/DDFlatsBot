import asyncio
import threading
import sys
import os
from datetime import datetime
from aiohttp import web

from bot.bot import bot, dp
from bot.handlers import router
from bot.middleware import SubscriptionMiddleware
from database.db import init_db, get_stats
from parser.scheduler import run_scheduler, set_bot, parse_all
from config import ADMIN_IDS

LOCK_FILE = "bot.lock"
_START_TIME = datetime.now()

# Webhook settings — set WEBHOOK_HOST env var on Render (e.g. https://your-app.onrender.com)
WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", "")
WEBHOOK_PATH = f"/webhook/{os.environ.get('BOT_TOKEN', '').split(':')[0]}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}" if WEBHOOK_HOST else ""
WEBAPP_PORT = int(os.environ.get("PORT", 8080))


def check_lock():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                pid = int(f.read().strip())
            try:
                import psutil
                if psutil.pid_exists(pid):
                    print(f"⚠️  Bot already running (PID {pid}). Close it first.")
                    sys.exit(1)
            except ImportError:
                pass
        except Exception:
            pass
        os.remove(LOCK_FILE)
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)


async def notify_admin_startup():
    """Notify admin that bot started successfully."""
    try:
        stats = get_stats()
        text = (
            f"✅ <b>DDFlatsBot запущен</b>\n\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"🏠 Квартир в базе: <b>{stats['apartments']}</b>\n"
            f"👥 Пользователей: <b>{stats['users']}</b>\n"
            f"💎 VIP: <b>{stats['vip']}</b>"
        )
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, text, parse_mode="HTML")
            except Exception:
                pass
    except Exception as e:
        print(f"[Startup] Notify error: {e}")


async def main():
    check_lock()
    try:
        init_db()

        dp.message.middleware(SubscriptionMiddleware())
        dp.callback_query.middleware(SubscriptionMiddleware())
        dp.include_router(router)

        loop = asyncio.get_running_loop()
        set_bot(bot, loop)

        await notify_admin_startup()

        threading.Thread(target=parse_all, daemon=True).start()
        threading.Thread(target=run_scheduler, daemon=True).start()

        if WEBHOOK_URL:
            # Webhook mode (Render / production)
            from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
            await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
            app = web.Application()
            SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
            setup_application(app, dp, bot=bot)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", WEBAPP_PORT)
            await site.start()
            print(f"🤖 DDFlatsBot started (webhook on port {WEBAPP_PORT})")
            await asyncio.Event().wait()  # run forever
        else:
            # Polling mode (local dev)
            await bot.delete_webhook(drop_pending_updates=True)
            print("🤖 DDFlatsBot started (polling)")
            await dp.start_polling(
                bot,
                allowed_updates=["message", "callback_query", "pre_checkout_query"],
                drop_pending_updates=True,
            )
    finally:
        remove_lock()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
