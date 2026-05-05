import schedule
import time
import asyncio
import threading
import shutil
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timedelta

from parser.parser_olx import parse_olx
from parser.parser_otodom import parse_otodom
from parser.parser_gratka import parse_gratka
from parser.parser_morizon import parse_morizon
from parser.parser_adresowo import parse_adresowo
from parser.parser_nieruch import parse_nieruch_online, parse_domiporta
from parser.parser_lento import parse_lento
from database.db import (
    save_apartment, get_latest_apartments, get_all_user_ids,
    get_all_vip_user_ids, get_subscribers_for_district, log_parse,
    match_alerts, check_vip_expiry, get_daily_digest, check_auto_vip_conditions,
    get_cheapest_apartments, get_conn, get_morning_push_apts,
)
from config import CHANNEL_ID, DB_PATH, ADMIN_IDS

_bot = None
_loop = None
_parse_lock = threading.Lock()  # Prevent overlapping parse cycles

PARSER_TIMEOUT = 120  # seconds per source


def set_bot(bot, loop):
    global _bot, _loop
    _bot = bot
    _loop = loop


def _run_parser_with_timeout(parser_fn, source_name: str) -> list:
    """Run a parser function with a hard timeout."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(parser_fn)
        try:
            return future.result(timeout=PARSER_TIMEOUT)
        except FuturesTimeout:
            print(f"[{source_name}] ⏰ Timeout after {PARSER_TIMEOUT}s — skipping")
            return []
        except Exception as e:
            print(f"[{source_name}] Error: {e}")
            return []


def parse_all():
    # Prevent overlapping cycles — if previous parse is still running, skip
    if not _parse_lock.acquire(blocking=False):
        print("[Scheduler] Previous parse still running — skipping this cycle")
        return
    try:
        print(f"[Scheduler] Starting parse at {datetime.now().isoformat()}")
        before = datetime.now().isoformat()

        sources = [
            ("OLX",            parse_olx),
            ("Otodom",         parse_otodom),
            ("Gratka",         parse_gratka),
            ("Morizon",        parse_morizon),
            ("Adresowo",        parse_adresowo),
            ("Nieruch-online", parse_nieruch_online),
            ("Domiporta",      parse_domiporta),
            ("Lento",          parse_lento),
        ]

        total_new = 0
        for source_name, parser_fn in sources:
            listings = _run_parser_with_timeout(parser_fn, source_name)
            new = sum(1 for l in listings if save_apartment(l))
            log_parse(source_name, new)
            total_new += new
            print(f"[{source_name}] +{new} new")

        print(f"[Scheduler] Done. Total new: {total_new}")
        check_vip_expiry()

        if total_new > 0 and _bot and _loop:
            new_apartments = get_latest_apartments(before)
            asyncio.run_coroutine_threadsafe(_notify(new_apartments), _loop)
    finally:
        _parse_lock.release()


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


def cleanup_old_listings():
    """Auto-delete apartments older than 14 days — they're likely already rented."""
    try:
        from database.db import get_conn
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=14)).isoformat()
        conn = get_conn()
        deleted = conn.execute(
            "DELETE FROM apartments WHERE created_at < ?", (cutoff,)
        ).rowcount
        conn.commit()
        conn.close()
        if deleted > 0:
            print(f"[Cleanup] Removed {deleted} listings older than 14 days")
    except Exception as e:
        print(f"[Cleanup] Error: {e}")


def send_vip_expiry_reminders():
    """Remind users whose VIP expires in 1-3 days."""
    if _bot and _loop:
        asyncio.run_coroutine_threadsafe(_vip_expiry_reminders(), _loop)


def backup_db():
    """Create a local backup and send to admin via Telegram."""
    try:
        if not os.path.exists(DB_PATH):
            return
        backup_path = DB_PATH + ".backup"
        shutil.copy2(DB_PATH, backup_path)
        size_kb = os.path.getsize(DB_PATH) // 1024
        print(f"[Backup] DB backed up ({size_kb} KB)")
        # Send to admin via Telegram
        if _bot and _loop:
            asyncio.run_coroutine_threadsafe(_send_backup_to_admin(backup_path, size_kb), _loop)
    except Exception as e:
        print(f"[Backup] Error: {e}")


async def _send_backup_to_admin(backup_path: str, size_kb: int):
    """Send DB backup file to all admins."""
    try:
        from aiogram.types import FSInputFile
        for admin_id in ADMIN_IDS:
            try:
                await _bot.send_document(
                    admin_id,
                    FSInputFile(backup_path, filename="Flats.db"),
                    caption=(
                        f"💾 <b>Авто-бэкап БД</b>\n"
                        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                        f"📦 {size_kb} KB"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"[Backup] Failed to send to admin {admin_id}: {e}")
    except Exception as e:
        print(f"[Backup] Send error: {e}")


async def _post_channel():
    """Post top 3 cheapest apartments to the channel."""
    try:
        apts = get_cheapest_apartments(limit=3, price_max=3000)
        if not apts:
            return
        from datetime import date
        today = date.today().strftime("%d.%m.%Y")
        header = f"🏠 <b>Лучшие квартиры на {today}:</b>\n\n"
        try:
            await _bot.send_message(CHANNEL_ID, header, parse_mode="HTML")
        except Exception as e:
            print(f"[Channel] Cannot post — bot not admin or channel not found: {e}")
            return
        for apt in apts:
            source_icons = {"OLX": "🟠", "Otodom": "🔵", "Gratka": "🟢", "Morizon": "🟣", "Adresowo": "🟡", "Domiporta": "🔴", "Lento": "🟤"}
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
                await asyncio.sleep(0.05)
            except Exception:
                pass
    except Exception as e:
        print(f"[Reminder] Error: {e}")


async def _auto_vip_check():
    """Check auto-VIP conditions. Uses batch SQL to avoid N+1 queries."""
    # Only check users who are NOT already VIP and have enough activity
    conn = get_conn()
    try:
        candidates = conn.execute("""
            SELECT u.user_id,
                   u.views,
                   u.created_at,
                   (SELECT COUNT(*) FROM favorites f WHERE f.user_id = u.user_id) as fav_count
            FROM users u
            WHERE u.vip = 0
              AND (
                  (SELECT COUNT(*) FROM favorites f WHERE f.user_id = u.user_id) >= 10
                  OR u.views >= 20
              )
        """).fetchall()
    except Exception as e:
        print(f"[AutoVIP] Query error: {e}")
        conn.close()
        return
    conn.close()

    for row in candidates:
        uid = row["user_id"]
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
    top_apts = get_morning_push_apts(limit=3)
    user_ids = get_all_user_ids()

    if not digest["new_today"] and not top_apts:
        return

    from database.db import get_price_drops_today
    drops = get_price_drops_today(limit=2)

    header = (
        f"☀️ <b>Доброе утро! Дайджест за сегодня:</b>\n\n"
        f"🏠 Новых квартир: <b>{digest['new_today']}</b>\n"
    )
    if digest.get("avg_price"):
        header += f"💰 Средняя цена: <b>{digest['avg_price']} zł</b>\n"
    if drops:
        header += f"📉 Снижений цен: <b>{len(drops)}</b> → /drops\n"
    if top_apts:
        header += f"\n🏆 <b>Топ-{len(top_apts)} дешёвых за последние 24ч:</b>"

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    header_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏠 Смотреть все", callback_data="next"),
        InlineKeyboardButton(text="📉 Снижения",     callback_data="open_drops"),
    ]])

    source_icons = {
        "OLX": "🟠", "Otodom": "🔵", "Gratka": "🟢",
        "Morizon": "🟣", "Szybko": "🔷", "Lento": "🟤",
    }

    # Rate-limited batch send
    for i, uid in enumerate(user_ids):
        try:
            await _safe_send(uid, header, parse_mode="HTML", reply_markup=header_kb)
            for apt in top_apts:
                icon = source_icons.get(apt.get("source", ""), "📡")
                rooms_str = f" · {apt['rooms']} комн." if apt.get("rooms") else ""
                area_str  = f" · {apt['area']} м²" if apt.get("area") else ""
                card = (
                    f"🏠 <b>{apt['title'][:60]}</b>\n"
                    f"💰 <b>{apt['price']} zł/мес</b>{rooms_str}{area_str}\n"
                    f"📍 {apt.get('district', 'Warszawa')}  {icon} {apt.get('source','')}\n"
                    f"🔗 <a href=\"{apt['link']}\">Открыть объявление</a>"
                )
                card_kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="❤️ Сохранить", callback_data=f"fav_add:{apt['id']}"),
                    InlineKeyboardButton(text="➡️ Следующая", callback_data="next"),
                ]])
                if apt.get("image"):
                    try:
                        await _bot.send_photo(uid, apt["image"], caption=card, reply_markup=card_kb, parse_mode="HTML")
                    except Exception:
                        await _safe_send(uid, card, reply_markup=card_kb, parse_mode="HTML")
                else:
                    await _safe_send(uid, card, reply_markup=card_kb, parse_mode="HTML")
                await asyncio.sleep(0.03)
        except Exception:
            pass

        # Rate limit: 1 sec pause every 25 users
        if (i + 1) % 25 == 0:
            await asyncio.sleep(1.0)
        else:
            await asyncio.sleep(0.05)


async def _safe_send(uid: int, text: str, **kwargs) -> bool:
    """Send message with error handling. Returns True on success."""
    try:
        await _bot.send_message(uid, text, **kwargs)
        return True
    except Exception as e:
        err = str(e).lower()
        # Silently skip blocked/deactivated users
        if any(x in err for x in ("blocked", "deactivated", "not found", "forbidden", "kicked")):
            return False
        print(f"[Notify] send error uid={uid}: {e}")
        return False


async def _batch_send(user_ids: list, text: str, rate: float = 0.05, **kwargs):
    """
    Send message to a list of users with rate limiting.
    rate = seconds between sends (0.05 = 20 msg/sec, safe for Telegram).
    Telegram limit: 30 msg/sec globally, 1 msg/sec per chat.
    """
    sent = 0
    for i, uid in enumerate(user_ids):
        ok = await _safe_send(uid, text, **kwargs)
        if ok:
            sent += 1
        # Rate limit: pause every 25 sends to stay under Telegram limits
        if (i + 1) % 25 == 0:
            await asyncio.sleep(1.0)
        else:
            await asyncio.sleep(rate)
    return sent


async def _notify(apartments: list):
    if not _bot or not apartments:
        return

    notified = set()
    from database.db import evaluate_price

    for apt in apartments:
        # 1. Smart alerts — highest priority
        alert_users = match_alerts(apt)
        for uid in alert_users:
            ev = evaluate_price(apt.get("price", 0), apt.get("district", ""), apt.get("rooms"))
            price_badge = ""
            if ev.get("verdict") == "cheap":
                price_badge = "\n🟢 <b>Очень дёшево!</b>"
            elif ev.get("verdict") == "below_avg":
                price_badge = "\n🟡 Ниже среднего"
            ok = await _safe_send(
                uid,
                f"🎯 <b>Алерт сработал!</b>\n\n"
                f"🏠 {apt['title']}\n"
                f"💰 {apt['price']} zł/мес{price_badge}\n"
                f"📍 {apt.get('district', 'Warszawa')}\n"
                f"🔗 <a href=\"{apt['link']}\">Открыть</a>",
                parse_mode="HTML"
            )
            if ok:
                notified.add(uid)
            await asyncio.sleep(0.05)

        # 2. District subscribers
        subscribers = get_subscribers_for_district(apt.get("district", ""))
        for uid in subscribers:
            if uid in notified:
                continue
            ok = await _safe_send(
                uid,
                f"🔔 <b>Новая квартира в {apt.get('district', 'Warszawa')}!</b>\n\n"
                f"🏠 {apt['title']}\n"
                f"💰 {apt['price']} zł/мес\n"
                f"🔗 <a href=\"{apt['link']}\">Открыть</a>",
                parse_mode="HTML"
            )
            if ok:
                notified.add(uid)
            await asyncio.sleep(0.05)

    # 3. VIP — notify about cheap new apartments only (avoid spam)
    cheap_apts = [
        a for a in apartments
        if a.get("price") and evaluate_price(
            a["price"], a.get("district", ""), a.get("rooms")
        ).get("verdict") in ("cheap", "below_avg")
    ]
    if cheap_apts:
        best = cheap_apts[0]
        extra = f"\n+ ещё {len(cheap_apts)-1} дешёвых → /next" if len(cheap_apts) > 1 else ""
        vip_ids = [uid for uid in get_all_vip_user_ids() if uid not in notified]
        await _batch_send(
            vip_ids,
            f"🟢 <b>Дешёвая квартира!</b>\n\n"
            f"🏠 {best['title']}\n"
            f"💰 <b>{best['price']} zł/мес</b> — ниже среднего!\n"
            f"📍 {best.get('district', 'Warszawa')}\n"
            f"🔗 <a href=\"{best['link']}\">Открыть</a>{extra}",
            parse_mode="HTML",
            rate=0.05,
        )
    elif len(apartments) >= 10:
        # Only notify VIP if 10+ new apartments — avoid spam on small batches
        vip_ids = [uid for uid in get_all_vip_user_ids() if uid not in notified]
        await _batch_send(
            vip_ids,
            f"🏠 Добавлено <b>{len(apartments)}</b> новых квартир!\nНажми /next",
            parse_mode="HTML",
            rate=0.05,
        )


async def _vip_expiry_reminders():
    """Notify users whose VIP expires in 1-3 days."""
    try:
        conn = get_conn()
        now = datetime.now()
        in_3_days = (now + timedelta(days=3)).isoformat()
        rows = conn.execute("""
            SELECT user_id, vip_until FROM users
            WHERE vip=1 AND vip_until IS NOT NULL AND vip_until > ? AND vip_until <= ?
        """, (now.isoformat(), in_3_days)).fetchall()
        conn.close()

        for row in rows:
            uid = row["user_id"]
            try:
                vip_until = datetime.fromisoformat(row["vip_until"])
                days_left = (vip_until - now).days + 1
                await _bot.send_message(
                    uid,
                    f"⚠️ <b>Твой VIP заканчивается через {days_left} дн.!</b>\n\n"
                    f"Продли за 19 zł/мес чтобы не потерять:\n"
                    f"✅ Безлимитный просмотр\n"
                    f"✅ Умные алерты\n"
                    f"✅ Уведомления о снижении цен\n\n"
                    f"👉 /vip — продлить сейчас",
                    parse_mode="HTML"
                )
                await asyncio.sleep(0.05)
            except Exception:
                pass
    except Exception as e:
        print(f"[VIP Reminder] Error: {e}")


def run_scheduler():
    schedule.every(10).minutes.do(parse_all)
    schedule.every(2).hours.do(post_to_channel)
    schedule.every().hour.do(check_auto_vip)
    schedule.every().day.at("03:00").do(backup_db)
    schedule.every().day.at("04:00").do(cleanup_old_listings)
    schedule.every().day.at("09:00").do(send_daily_digest)
    schedule.every().day.at("12:00").do(send_vip_expiry_reminders)
    schedule.every().day.at("18:00").do(send_reminders)
    print("[Scheduler] Running: parse 10min, channel 2h, digest 09:00, vip-reminder 12:00, reminders 18:00, cleanup 04:00, backup 03:00")
    while True:
        schedule.run_pending()
        time.sleep(1)

