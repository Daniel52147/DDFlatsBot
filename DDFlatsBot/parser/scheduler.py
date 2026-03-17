import schedule
import time
import asyncio
import threading
import shutil
import os
from datetime import datetime, timedelta

from parser.parser_olx import parse_olx
from parser.parser_otodom import parse_otodom
from parser.parser_gratka import parse_gratka
from parser.parser_morizon import parse_morizon
from database.db import (
    save_apartment, get_latest_apartments, get_all_user_ids,
    get_all_vip_user_ids, get_subscribers_for_district, log_parse,
    match_alerts, check_vip_expiry, get_daily_digest, check_auto_vip_conditions,
    get_cheapest_apartments, get_conn,
)
from config import CHANNEL_ID, DB_PATH

_bot = None
_loop = None


def set_bot(bot, loop):
    global _bot, _loop
    _bot = bot
    _loop = loop


def parse_all():
    print(f"[Scheduler] Starting parse at {datetime.now().isoformat()}")
    before = datetime.now().isoformat()

    sources = [
        ("OLX",     parse_olx),
        ("Otodom",  parse_otodom),
        ("Gratka",  parse_gratka),
        ("Morizon", parse_morizon),
    ]

    total_new = 0
    for source_name, parser_fn in sources:
        try:
            listings = parser_fn()
            new = sum(1 for l in listings if save_apartment(l))
            log_parse(source_name, new)
            total_new += new
            print(f"[{source_name}] +{new} new")
        except Exception as e:
            print(f"[{source_name}] Error: {e}")

    print(f"[Scheduler] Done. Total new: {total_new}")
    check_vip_expiry()

    if total_new > 0 and _bot and _loop:
        new_apartments = get_latest_apartments(before)
        asyncio.run_coroutine_threadsafe(_notify(new_apartments), _loop)


def send_daily_digest():
    if _bot and _loop:
        asyncio.run_coroutine_threadsafe(_daily_digest(), _loop)


def post_to_channel():
    """Post best apartments to channel every 2 hours."""
    if _bot and _loop:
        asyncio.run_coroutine_threadsafe(_post_channel(), _loop)


def send_reminders():
    """Remind inactive users who haven't returned in 24h."""
    if _bot and _loop:
        asyncio.run_coroutine_threadsafe(_remind_inactive(), _loop)


def check_auto_vip():
    if _bot and _loop:
        asyncio.run_coroutine_threadsafe(_auto_vip_check(), _loop)


def backup_db():
    """Create a backup copy of the database."""
    try:
        if os.path.exists(DB_PATH):
            backup_path = DB_PATH + ".backup"
            shutil.copy2(DB_PATH, backup_path)
            print(f"[Backup] DB backed up to {backup_path}")
    except Exception as e:
        print(f"[Backup] Error: {e}")


async def _post_channel():
    """Post top 3 cheapest apartments to the channel."""
    try:
        apts = get_cheapest_apartments(limit=3, price_max=3000)
        if not apts:
            return
        from datetime import date
        today = date.today().strftime("%d.%m.%Y")
        header = f"🏠 <b>Лучшие квартиры на {today}:</b>\n\n"
        await _bot.send_message(CHANNEL_ID, header, parse_mode="HTML")
        for apt in apts:
            source_icons = {"OLX": "🟠", "Otodom": "🔵", "Gratka": "🟢", "Morizon": "🟣"}
            icon = source_icons.get(apt.get("source", ""), "📡")
            text = (
                f"🏠 <b>{apt['title']}</b>\n"
                f"💰 <b>{apt['price']} zł/мес</b>\n"
                f"📍 {apt.get('district', 'Warszawa')}\n"
                f"🔗 <a href=\"{apt['link']}\">Открыть объявление</a> {icon}\n\n"
                f"🤖 @DDFlatsBot — все квартиры Варшавы"
            )
            try:
                if apt.get("image"):
                    await _bot.send_photo(CHANNEL_ID, apt["image"], caption=text, parse_mode="HTML")
                else:
                    await _bot.send_message(CHANNEL_ID, text, parse_mode="HTML")
            except Exception:
                pass
    except Exception as e:
        print(f"[Channel] Error: {e}")


async def _remind_inactive():
    """Send reminder to users who were active yesterday but not today."""
    try:
        conn = get_conn()
        yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
        today = datetime.now().date().isoformat()
        rows = conn.execute("""
            SELECT DISTINCT ua.user_id FROM user_activity ua
            WHERE ua.date = ?
            AND ua.user_id NOT IN (
                SELECT user_id FROM user_activity WHERE date = ?
            )
        """, (yesterday, today)).fetchall()
        new_count = conn.execute(
            "SELECT COUNT(*) FROM apartments WHERE created_at >= ?", (today,)
        ).fetchone()[0]
        conn.close()

        for row in rows[:50]:
            uid = row["user_id"]
            try:
                from database.db import get_or_create_user
                user = get_or_create_user(uid)
                if user.get("vip") == -1:  # banned
                    continue
                await _bot.send_message(
                    uid,
                    f"👋 <b>Привет! Ты ещё ищешь квартиру?</b>\n\n"
                    f"🏠 Сегодня добавлено <b>{new_count}</b> новых квартир в Варшаве.\n\n"
                    f"Нажми /next чтобы посмотреть 👇",
                    parse_mode="HTML"
                )
            except Exception:
                pass
    except Exception as e:
        print(f"[Reminder] Error: {e}")


async def _auto_vip_check():
    user_ids = get_all_user_ids()
    for uid in user_ids:
        try:
            reason = check_auto_vip_conditions(uid)
            if reason == "fav10":
                await _bot.send_message(
                    uid,
                    "🎁 <b>Автоматический VIP!</b>\n\n"
                    "Ты сохранил 10+ квартир — дарим <b>3 дня VIP бесплатно!</b>\n\n"
                    "✅ Безлимитный просмотр\n✅ Умные алерты: /alert",
                    parse_mode="HTML"
                )
            elif reason == "loyal":
                await _bot.send_message(
                    uid,
                    "🎁 <b>Подарок за верность!</b>\n\n"
                    "Дарим <b>2 дня VIP бесплатно!</b>\n\n"
                    "✅ Безлимитный просмотр\n✅ Умные алерты: /alert",
                    parse_mode="HTML"
                )
            elif reason == "streak7":
                await _bot.send_message(
                    uid,
                    "🔥 <b>7 дней подряд!</b> Дарим <b>1 день VIP</b> за стрик!\n\n"
                    "✅ Безлимитный просмотр\n✅ Умные алерты: /alert",
                    parse_mode="HTML"
                )
        except Exception:
            pass


async def _daily_digest():
    digest = get_daily_digest()
    if not digest["new_today"]:
        return

    from database.db import get_price_drops_today
    drops = get_price_drops_today(limit=3)

    user_ids = get_all_user_ids()
    text = (
        f"☀️ <b>Доброе утро! Дайджест за сегодня:</b>\n\n"
        f"🏠 Новых квартир: <b>{digest['new_today']}</b>\n"
    )
    if digest["avg_price"]:
        text += f"💰 Средняя цена: <b>{digest['avg_price']} zł</b>\n"
    if digest["cheapest"]:
        c = digest["cheapest"]
        text += (
            f"\n🏆 <b>Самая дешёвая сегодня:</b>\n"
            f"🏠 {c['title']}\n"
            f"💰 {c['price']} zł/мес · 📍 {c['district']}\n"
            f"🔗 <a href=\"{c['link']}\">Открыть</a>\n"
        )
    if drops:
        text += f"\n📉 Снижение цен: {len(drops)} объявл. → /drops\n"
    text += "\n👇 /next — смотреть квартиры"

    for uid in user_ids:
        try:
            await _bot.send_message(uid, text, parse_mode="HTML")
        except Exception:
            pass


async def _notify(apartments: list):
    if not _bot or not apartments:
        return

    notified = set()

    for apt in apartments:
        # 1. Smart alerts
        alert_users = match_alerts(apt)
        for uid in alert_users:
            try:
                await _bot.send_message(
                    uid,
                    f"🎯 <b>Алерт сработал!</b>\n\n"
                    f"🏠 {apt['title']}\n"
                    f"💰 {apt['price']} zł/мес\n"
                    f"📍 {apt['district']}\n"
                    f"🔗 <a href=\"{apt['link']}\">Открыть</a>",
                    parse_mode="HTML"
                )
                notified.add(uid)
            except Exception:
                pass

        # 2. District subscribers
        subscribers = get_subscribers_for_district(apt.get("district", ""))
        for uid in subscribers:
            if uid in notified:
                continue
            try:
                await _bot.send_message(
                    uid,
                    f"🔔 <b>Новая квартира в {apt['district']}!</b>\n\n"
                    f"🏠 {apt['title']}\n"
                    f"💰 {apt['price']} zł/мес\n"
                    f"🔗 <a href=\"{apt['link']}\">Открыть</a>",
                    parse_mode="HTML"
                )
                notified.add(uid)
            except Exception:
                pass

    # 3. VIP notification — only if 5+ new apartments
    if len(apartments) >= 5:
        vip_ids = get_all_vip_user_ids()
        for uid in vip_ids:
            if uid not in notified:
                try:
                    await _bot.send_message(
                        uid,
                        f"🏠 Добавлено <b>{len(apartments)}</b> новых квартир!\nНажми /next",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass


def run_scheduler():
    schedule.every(10).minutes.do(parse_all)
    schedule.every(2).hours.do(post_to_channel)
    schedule.every().hour.do(check_auto_vip)
    schedule.every().hour.do(backup_db)
    schedule.every().day.at("09:00").do(send_daily_digest)
    schedule.every().day.at("18:00").do(send_reminders)
    print("[Scheduler] Running: parse 10min, channel 2h, digest 09:00, reminders 18:00")
    while True:
        schedule.run_pending()
        time.sleep(1)

