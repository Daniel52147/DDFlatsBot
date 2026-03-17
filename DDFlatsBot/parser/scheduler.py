import schedule
import time
import asyncio
import threading
from datetime import datetime

from parser.parser_olx import parse_olx
from parser.parser_otodom import parse_otodom
from parser.parser_gratka import parse_gratka
from parser.parser_morizon import parse_morizon
from database.db import (
    save_apartment, get_latest_apartments, get_all_user_ids,
    get_all_vip_user_ids, get_subscribers_for_district, log_parse,
    match_alerts, check_vip_expiry, get_daily_digest, check_auto_vip_conditions,
)

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
    """Send daily digest to all users at 9:00."""
    if _bot and _loop:
        asyncio.run_coroutine_threadsafe(_daily_digest(), _loop)


def check_auto_vip():
    """Check all users for auto-VIP conditions every hour."""
    if _bot and _loop:
        asyncio.run_coroutine_threadsafe(_auto_vip_check(), _loop)


async def _auto_vip_check():
    """Auto-grant VIP to users who meet conditions."""
    user_ids = get_all_user_ids()
    for uid in user_ids:
        try:
            reason = check_auto_vip_conditions(uid)
            if reason == "fav10":
                await _bot.send_message(
                    uid,
                    "🎁 <b>Автоматический VIP!</b>\n\n"
                    "Ты сохранил 10+ квартир в избранное — это говорит о том, что ты серьёзно ищешь.\n"
                    "Мы дарим тебе <b>3 дня VIP бесплатно!</b>\n\n"
                    "✅ Безлимитный просмотр\n"
                    "✅ Умные алерты: /alert\n"
                    "✅ Подписка на районы: /subscribe",
                    parse_mode="HTML"
                )
            elif reason == "loyal":
                await _bot.send_message(
                    uid,
                    "🎁 <b>Подарок за верность!</b>\n\n"
                    "Ты с нами уже больше недели и активно ищешь квартиру.\n"
                    "Дарим тебе <b>2 дня VIP бесплатно!</b>\n\n"
                    "✅ Безлимитный просмотр\n"
                    "✅ Умные алерты: /alert",
                    parse_mode="HTML"
                )
            elif reason == "streak7":
                await _bot.send_message(
                    uid,
                    "🔥 <b>7 дней подряд!</b>\n\n"
                    "Ты заходишь в бот 7 дней подряд — это серьёзно!\n"
                    "Дарим тебе <b>1 день VIP бесплатно</b> за стрик!\n\n"
                    "✅ Безлимитный просмотр\n"
                    "✅ Умные алерты: /alert",
                    parse_mode="HTML"
                )
        except Exception:
            pass


async def _daily_digest():
    """Send morning digest with today's stats."""
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
        text += f"💰 Средняя цена сегодня: <b>{digest['avg_price']} zł</b>\n"
    if digest["cheapest"]:
        c = digest["cheapest"]
        text += (
            f"\n🏆 <b>Самая дешёвая сегодня:</b>\n"
            f"🏠 {c['title']}\n"
            f"💰 {c['price']} zł/мес\n"
            f"📍 {c['district']}\n"
            f"🔗 {c['link']}\n"
        )
    if drops:
        text += f"\n📉 <b>Снижение цен ({len(drops)}):</b> /drops\n"
    text += "\nНажми /next чтобы смотреть квартиры 👇"

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
                    f"🔗 {apt['link']}",
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
                    f"🔗 {apt['link']}",
                    parse_mode="HTML"
                )
                notified.add(uid)
            except Exception:
                pass

    # 3. General VIP notification — only if 5+ new apartments
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
    schedule.every().hour.do(check_auto_vip)
    schedule.every().day.at("09:00").do(send_daily_digest)
    print("[Scheduler] Running: parse every 10min, auto-vip every hour, digest at 09:00")
    while True:
        schedule.run_pending()
        time.sleep(1)
