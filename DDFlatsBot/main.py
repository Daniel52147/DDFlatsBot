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

_START_TIME = datetime.now()

# Lock file on persistent disk so it survives restarts
_LOCK_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
LOCK_FILE = os.path.join(_LOCK_DIR, "bot.lock")

# Webhook — set WEBHOOK_HOST env var on Render: https://your-app.onrender.com
WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", "")
WEBHOOK_PATH = f"/webhook/{os.environ.get('BOT_TOKEN', '').split(':')[0]}"
WEBHOOK_URL  = f"{WEBHOOK_HOST}{WEBHOOK_PATH}" if WEBHOOK_HOST else ""
WEBAPP_PORT  = int(os.environ.get("PORT", 8080))


def check_lock():
    """Prevent duplicate instances. Handles stale locks gracefully."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                pid = int(f.read().strip())
            alive = False
            try:
                import psutil
                alive = psutil.pid_exists(pid) and pid != os.getpid()
            except ImportError:
                # Linux fallback
                alive = os.path.exists(f"/proc/{pid}") and pid != os.getpid()
            if alive:
                print(f"⚠️  Bot already running (PID {pid}). Exiting.")
                sys.exit(1)
        except Exception:
            pass
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass
    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
    except OSError as e:
        print(f"[Lock] Cannot write lock: {e} — continuing")


def remove_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except OSError:
        pass


async def notify_admin_startup():
    try:
        stats = get_stats()
        mode = "webhook" if WEBHOOK_URL else "polling"
        from config import DB_PATH
        text = (
            f"✅ <b>DDFlatsBot запущен</b>\n\n"
            f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"⚙️ Режим: <b>{mode}</b>\n"
            f"💾 БД: <code>{DB_PATH}</code>\n"
            f"🏠 Квартир в базе: <b>{stats['apartments']}</b>\n"
            f"👥 Пользователей: <b>{stats['users']}</b>\n"
            f"👥 Активных: <b>{stats.get('active_yesterday', 0)}</b> вчера"
        )
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, text, parse_mode="HTML")
            except Exception:
                pass
    except Exception as e:
        print(f"[Startup] Notify error: {e}")


async def setup_bot_commands():
    from aiogram.types import BotCommand, BotCommandScopeDefault

    commands_by_lang = {
        "ru": [
            BotCommand(command="start", description="🏠 Главная"),
            BotCommand(command="next", description="➡️ Следующая квартира"),
            BotCommand(command="filter", description="🔍 Фильтры"),
            BotCommand(command="favorites", description="❤️ Избранное"),
            BotCommand(command="alert", description="🔔 Алерты"),
            BotCommand(command="daily", description="🏖 Посуточно"),
            BotCommand(command="settings", description="⚙️ Настройки"),
            BotCommand(command="city", description="🏙 Сменить город"),
            BotCommand(command="subscribe", description="🔔 Подписка на район"),
            BotCommand(command="map", description="🗺 Карта цен"),
            BotCommand(command="ask", description="💬 Умный поиск"),
            BotCommand(command="menu", description="📋 Меню"),
            BotCommand(command="help", description="📖 Все команды"),
        ],
        "uk": [
            BotCommand(command="start", description="🏠 Головна"),
            BotCommand(command="next", description="➡️ Наступна квартира"),
            BotCommand(command="filter", description="🔍 Фільтри"),
            BotCommand(command="favorites", description="❤️ Обране"),
            BotCommand(command="alert", description="🔔 Алерти"),
            BotCommand(command="daily", description="🏖 Подобово"),
            BotCommand(command="settings", description="⚙️ Налаштування"),
            BotCommand(command="city", description="🏙 Змінити місто"),
            BotCommand(command="subscribe", description="🔔 Підписка на район"),
            BotCommand(command="map", description="🗺 Карта цін"),
            BotCommand(command="ask", description="💬 Розумний пошук"),
            BotCommand(command="menu", description="📋 Меню"),
            BotCommand(command="help", description="📖 Команди"),
        ],
        "pl": [
            BotCommand(command="start", description="🏠 Start"),
            BotCommand(command="next", description="➡️ Następne mieszkanie"),
            BotCommand(command="filter", description="🔍 Filtry"),
            BotCommand(command="favorites", description="❤️ Ulubione"),
            BotCommand(command="alert", description="🔔 Alerty"),
            BotCommand(command="daily", description="🏖 Na doby"),
            BotCommand(command="settings", description="⚙️ Ustawienia"),
            BotCommand(command="city", description="🏙 Zmień miasto"),
            BotCommand(command="subscribe", description="🔔 Subskrypcja dzielnicy"),
            BotCommand(command="map", description="🗺 Mapa cen"),
            BotCommand(command="ask", description="💬 Inteligentne szukanie"),
            BotCommand(command="menu", description="📋 Menu"),
            BotCommand(command="help", description="📖 Komendy"),
        ],
        "en": [
            BotCommand(command="start", description="🏠 Home"),
            BotCommand(command="next", description="➡️ Next listing"),
            BotCommand(command="filter", description="🔍 Filters"),
            BotCommand(command="favorites", description="❤️ Favorites"),
            BotCommand(command="alert", description="🔔 Alerts"),
            BotCommand(command="daily", description="🏖 Short-term"),
            BotCommand(command="settings", description="⚙️ Settings"),
            BotCommand(command="city", description="🏙 Change city"),
            BotCommand(command="subscribe", description="🔔 District alerts"),
            BotCommand(command="map", description="🗺 Price map"),
            BotCommand(command="ask", description="💬 Smart search"),
            BotCommand(command="menu", description="📋 Menu"),
            BotCommand(command="help", description="📖 All commands"),
        ],
    }
    for lang, cmds in commands_by_lang.items():
        await bot.set_my_commands(cmds, scope=BotCommandScopeDefault(), language_code=lang)
    await bot.set_my_commands(commands_by_lang["ru"], scope=BotCommandScopeDefault())

    try:
        await bot.set_my_description(
            "🏙 DDFlatsBot — квартиры Польши в одном месте!\n\n"
            "✅ OLX · Otodom · Gratka · Morizon · Adresowo\n"
            "✅ Обновление каждые 10 минут\n"
            "✅ 10 городов: Warszawa, Kraków, Wrocław, Gdańsk, Poznań, Łódź, Katowice, Lublin, Szczecin, Białystok\n"
            "✅ Бесплатно · безлимит · 10 городов · радиус 100 км\n"
            "✅ Посуточно, алерты, подписка на районы\n\n"
            "Нажми START 👇",
            language_code="ru"
        )
        await bot.set_my_description(
            "🏙 DDFlatsBot — apartments across Poland!\n\n"
            "✅ OLX · Otodom · Gratka · Morizon\n"
            "✅ Updates every 10 minutes · 10 cities\n"
            "✅ Free unlimited · 10 cities · 100 km radius\n"
            "✅ Short-term, alerts, district subscriptions\n\n"
            "Tap START 👇",
            language_code="en"
        )
        await bot.set_my_description(
            "🏙 DDFlatsBot — mieszkania Polski w jednym miejscu!\n\n"
            "✅ OLX · Otodom · Gratka · Morizon · Adresowo\n"
            "✅ Aktualizacja co 10 minut · 10 miast\n"
            "✅ Darmowo · bez limitu · promień 100 km\n"
            "✅ Krótkoterminowo, alerty, subskrypcja dzielnic\n\n"
            "Naciśnij START 👇",
            language_code="pl"
        )
        await bot.set_my_description(
            "🏙 DDFlatsBot — квартири Польщі в одному місці!\n\n"
            "✅ OLX · Otodom · Gratka · Morizon · Adresowo\n"
            "✅ Оновлення кожні 10 хвилин · 10 міст\n"
            "✅ Безкоштовно · безліміт · радіус 100 км\n"
            "✅ Подобово, алерти, підписка на райони\n\n"
            "Натисни START 👇",
            language_code="uk"
        )
        short_desc = {
            "ru": "🏠 Квартиры Польши — 10 городов, бесплатно, радиус 100 км",
            "uk": "🏠 Квартири Польщі — 10 міст, безкоштовно, радіус 100 км",
            "pl": "🏠 Mieszkania Polski — 10 miast, za darmo, promień 100 km",
            "en": "🏠 Poland apartments — 10 cities, free, 100 km radius",
        }
        for lang, desc in short_desc.items():
            await bot.set_my_short_description(desc, language_code=lang)
        await bot.set_my_short_description(short_desc["ru"])
    except Exception as e:
        print(f"[Bot] Description error (non-critical): {e}")

    print("[Bot] Commands menu updated ✅")


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
        await setup_bot_commands()

        # Start parser and scheduler in background threads
        threading.Thread(target=parse_all,      daemon=True).start()
        threading.Thread(target=run_scheduler,  daemon=True).start()

        if WEBHOOK_URL:
            # ── Webhook mode (Render production) ─────────────
            from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
            import json as _json
            from database.db import get_apartments, get_stats as _get_stats

            async def api_apartments(request):
                try:
                    district  = request.rel_url.query.get("district", "")
                    price_max = int(request.rel_url.query.get("price_max", 0) or 0)
                    rooms     = int(request.rel_url.query.get("rooms", 0) or 0)
                    limit     = min(int(request.rel_url.query.get("limit", 10) or 10), 20)
                    filters = {}
                    if district:  filters["district"]  = district
                    if price_max: filters["price_max"] = price_max
                    if rooms:     filters["rooms"]     = rooms
                    apts = get_apartments(filters=filters, offset=0, limit=limit, vip=True)
                    result = [{
                        "id": a["id"], "title": a["title"], "price": a["price"],
                        "district": a.get("district", ""), "rooms": a.get("rooms"),
                        "area": a.get("area"), "source": a.get("source", ""),
                        "link": a["link"], "image": a.get("image", ""),
                        "created_at": a.get("created_at", ""),
                    } for a in apts]
                    hdrs = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
                    return web.Response(text=_json.dumps(result, ensure_ascii=False), headers=hdrs)
                except Exception as e:
                    return web.Response(
                        text=_json.dumps({"error": str(e)}), status=500,
                        headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
                    )

            async def api_stats(request):
                try:
                    s = _get_stats()
                    hdrs = {"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
                    return web.Response(text=_json.dumps({
                        "apartments": s["apartments"],
                        "new_today":  s.get("new_today", 0),
                        "users":      s["users"],
                        "last_parse": s.get("last_parse", ""),
                    }, ensure_ascii=False), headers=hdrs)
                except Exception as e:
                    return web.Response(
                        text=_json.dumps({"error": str(e)}), status=500,
                        headers={"Access-Control-Allow-Origin": "*", "Content-Type": "application/json"}
                    )

            async def healthcheck(request):
                return web.Response(text="ok")

            await bot.set_webhook(
                WEBHOOK_URL,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "pre_checkout_query", "inline_query"],
            )
            app = web.Application()
            SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
            setup_application(app, dp, bot=bot)
            app.router.add_get("/api/apartments", api_apartments)
            app.router.add_get("/api/stats",      api_stats)
            app.router.add_get("/health",         healthcheck)
            app.router.add_get("/",               healthcheck)

            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", WEBAPP_PORT)
            await site.start()
            print(f"🤖 DDFlatsBot started (webhook, port {WEBAPP_PORT})")
            await asyncio.Event().wait()  # run forever

        else:
            # ── Polling mode (local dev) ──────────────────────
            await bot.delete_webhook(drop_pending_updates=True)
            print("🤖 DDFlatsBot started (polling)")
            await dp.start_polling(
                bot,
                allowed_updates=["message", "callback_query", "pre_checkout_query", "inline_query"],
                drop_pending_updates=True,
            )
    finally:
        remove_lock()
        try:
            await bot.session.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
