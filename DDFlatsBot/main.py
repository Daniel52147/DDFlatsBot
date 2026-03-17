import asyncio
import threading
import sys
import os

from bot.bot import bot, dp
from bot.handlers import router
from bot.middleware import SubscriptionMiddleware
from database.db import init_db
from parser.scheduler import run_scheduler, set_bot, parse_all

LOCK_FILE = "bot.lock"


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
                pass  # psutil not installed — skip check
        except Exception:
            pass
        os.remove(LOCK_FILE)
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)


async def main():
    check_lock()
    try:
        init_db()

        dp.message.middleware(SubscriptionMiddleware())
        dp.callback_query.middleware(SubscriptionMiddleware())
        dp.include_router(router)

        loop = asyncio.get_event_loop()
        set_bot(bot, loop)

        # Kill any other bot sessions on Telegram side
        await bot.delete_webhook(drop_pending_updates=True)
        # Small delay to let Telegram close other connections
        await asyncio.sleep(2)

        threading.Thread(target=parse_all, daemon=True).start()
        threading.Thread(target=run_scheduler, daemon=True).start()

        print("🤖 DDFlatsBot started...")
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
