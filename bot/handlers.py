import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import (
    get_or_create_user, is_vip, set_vip, can_search, increment_searches,
    searches_left, save_alert, get_user_alerts, delete_alert,
    save_favorite, get_favorites, delete_favorite,
    get_recent_hot_deals, get_stats, save_search,
    get_full_stats, get_recent_users, get_top_users, get_early_adopters,
    get_user_info, revoke_vip, ban_user, unban_user, is_banned,
    get_user_lang, set_user_lang,
)
from search.flights import search_flights, get_cheapest_dates, search_round_trip, get_week_prices
from bot.keyboards import (
    main_menu_kb, origins_kb, destinations_kb, date_range_kb,
    flight_card_kb, hot_deal_kb, alerts_list_kb, favorites_kb,
    vip_kb, vip_manual_kb, cancel_kb, trip_type_kb, filters_kb,
    admin_kb, admin_user_kb, lang_kb, MENU_LABELS,
)
from bot.i18n import t
from config import (
    ADMIN_IDS, VIP_PRICE_PLN, VIP_PRICE_STARS,
    FREE_SEARCHES, CHANNEL_LINK, BOT_NAME,
)

router = Router()


# ── FSM States ─────────────────────────────────────────────────────────────────

class SearchFlight(StatesGroup):
    trip_type   = State()
    origin      = State()
    destination = State()
    dest_manual = State()
    dates       = State()
    return_date = State()


class SetAlert(StatesGroup):
    origin      = State()
    destination = State()
    price_max   = State()


class LangSelect(StatesGroup):
    waiting = State()


class AdminState(StatesGroup):
    broadcast   = State()
    find_user   = State()
    msg_user    = State()
    msg_user_id = State()


# ── Helpers ────────────────────────────────────────────────────────────────────

AIRLINE_ICONS = {
    "FR": "🟡", "W6": "🟣", "VY": "🟠", "U2": "🟠",
    "LO": "🔵", "LH": "🟡", "BA": "🔵", "AF": "🔵",
    "KL": "🔵", "TP": "🟢", "EK": "🔴", "QR": "🟤",
    "TK": "🔴", "SU": "🔴", "PS": "🔵",
}

def _airline_icon(airline: str) -> str:
    code = airline[:2].upper() if airline else ""
    return AIRLINE_ICONS.get(code, "✈️")


def _flight_text(f: dict, idx: int = None, total: int = None) -> str:
    flag = _dest_flag(f.get("destination", ""))
    icon = _airline_icon(f.get("airline_code") or f.get("airline", ""))
    price = f.get("price", 0)
    is_fallback = f.get("_is_fallback", False)

    header = f"✈️ <b>{f['origin_city']} → {f['dest_city']}</b> {flag}"
    if idx is not None and total:
        header += f"  <i>({idx+1}/{total})</i>"

    if is_fallback:
        # Нет точной цены — показываем ссылку для поиска
        lines = [
            header,
            f"🔍 <b>Нажми чтобы найти цену</b>",
            f"{icon} {f['airline']}",
        ]
    else:
        # Hot badge
        if price <= 35:
            badge = "🔥 <b>ГОРЯЩИЙ!</b>  "
        elif price <= 60:
            badge = "💚 <b>Дёшево</b>  "
        else:
            badge = ""
        lines = [
            header,
            f"{badge}💰 <b>{price} {f.get('currency','EUR')}</b>",
            f"{icon} {f['airline']}",
        ]

    if f.get("depart_at"):
        dep = f"📅 {f['depart_at']}"
        if f.get("arrive_at"):
            dep += f" → {f['arrive_at']}"
        lines.append(dep)
    if f.get("return_at"):
        lines.append(f"🔄 Обратно: {f['return_at']}")
    details = []
    if f.get("duration"):
        details.append(f"⏱ {f['duration']}")
    if f.get("stops"):
        details.append(f"🔀 {f['stops']}")
    if details:
        lines.append("  ".join(details))
    if is_fallback:
        lines.append("\n💡 <i>Точная цена — на сайте авиакомпании</i>")
    return "\n".join(lines)


def _dest_flag(iata: str) -> str:
    flags = {
        "BCN": "🇪🇸", "MAD": "🇪🇸", "TFS": "🇪🇸", "PMI": "🇪🇸", "AGP": "🇪🇸",
        "FCO": "🇮🇹", "MXP": "🇮🇹", "NAP": "🇮🇹", "VCE": "🇮🇹",
        "LTN": "🇬🇧", "LHR": "🇬🇧", "STN": "🇬🇧", "MAN": "🇬🇧",
        "CDG": "🇫🇷", "ORY": "🇫🇷", "NCE": "🇫🇷",
        "DXB": "🇦🇪", "AUH": "🇦🇪",
        "AMS": "🇳🇱", "LIS": "🇵🇹", "ATH": "🇬🇷",
        "PRG": "🇨🇿", "BUD": "🇭🇺", "VIE": "🇦🇹",
        "BER": "🇩🇪", "MUC": "🇩🇪", "FRA": "🇩🇪", "HAM": "🇩🇪",
        "WAW": "🇵🇱", "KRK": "🇵🇱", "WRO": "🇵🇱",
        "BKK": "🇹🇭", "HKT": "🇹🇭", "CMB": "🇱🇰",
        "JFK": "🇺🇸", "LAX": "🇺🇸", "MIA": "🇺🇸",
        "IST": "🇹🇷", "SAW": "🇹🇷",
        "TLV": "🇮🇱", "CAI": "🇪🇬", "HRG": "🇪🇬",
    }
    return flags.get(iata.upper(), "🌍")


# ── /start ─────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    if is_banned(msg.from_user.id):
        await msg.answer("🚫 Ваш аккаунт заблокирован. / Konto zablokowane. / Account banned.")
        return
    user = get_or_create_user(msg.from_user.id, msg.from_user.username or "", msg.from_user.first_name or "")
    lang = get_user_lang(msg.from_user.id)

    # Новый пользователь — предлагаем выбрать язык
    if user.get("total_searches", 0) == 0 and not user.get("lang") or user.get("lang") == "ru":
        is_new = user.get("total_searches", 0) == 0
        if is_new:
            await msg.answer(
                t("choose_lang", "ru"),
                reply_markup=lang_kb(),
            )
            return

    await _show_main_menu(msg, lang, user)


async def _show_main_menu(msg: Message, lang: str, user: dict):
    vip_status = is_vip(msg.from_user.id)
    early = user.get("is_early_adopter", 0)
    badge = " 🌟" if early else (" ⭐" if vip_status else "")
    left = searches_left(msg.from_user.id)
    left_str = "∞" if left >= 999 else str(left)
    name = msg.from_user.first_name or ("друг" if lang == "ru" else ("przyjacielu" if lang == "pl" else "friend"))
    vip_str = "(∞ VIP)" if vip_status else (f"из {FREE_SEARCHES}" if lang == "ru" else (f"z {FREE_SEARCHES}" if lang == "pl" else f"of {FREE_SEARCHES}"))
    extra = ""
    if early and user.get("total_searches", 0) == 0:
        extra = t("early_badge", lang)
    await msg.answer(
        t("welcome", lang, bot=BOT_NAME, badge=badge, name=name,
          left=left_str, vip_str=vip_str, channel=CHANNEL_LINK, extra=extra),
        reply_markup=main_menu_kb(lang),
    )


@router.callback_query(F.data.startswith("lang:"))
async def set_lang_cb(call: CallbackQuery, state: FSMContext):
    lang = call.data.split(":")[1]
    set_user_lang(call.from_user.id, lang)
    await call.answer(t("lang_set", lang))
    user = get_or_create_user(call.from_user.id, call.from_user.username or "", call.from_user.first_name or "")
    await call.message.edit_reply_markup(reply_markup=None)
    await _show_main_menu(call.message, lang, user)


@router.message(Command("lang"))
async def cmd_lang(msg: Message):
    await msg.answer(t("choose_lang", get_user_lang(msg.from_user.id)), reply_markup=lang_kb())


# ── /help ──────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        f"✈️ <b>{BOT_NAME} — команды:</b>\n\n"
        "/search — 🔎 найти билет (туда)\n"
        "/roundtrip — 🔄 туда-обратно\n"
        "/price — 💰 быстрая проверка цены (/price WAW BCN)\n"
        "/week — 📆 цены на неделю (/week WAW BCN)\n"
        "/hot — 🔥 горящие билеты\n"
        "/popular — 🌍 популярные маршруты\n"
        "/cheapdates — 📅 самые дешёвые даты\n"
        "/alert — 🔔 создать алерт на маршрут\n"
        "/alerts — 📋 мои алерты\n"
        "/favorites — ❤️ избранное\n"
        "/vip — ⭐ VIP подписка\n"
        "/stats — 📊 моя статистика\n\n"
        f"📢 Канал с горящими: {CHANNEL_LINK}"
    )


# ── /price — quick price check ────────────────────────────────────────────────

@router.message(Command("price"))
async def cmd_price(msg: Message):
    """Usage: /price WAW BCN  or  /price WAW BCN 2025-05-01"""
    parts = msg.text.split()
    if len(parts) < 3:
        await msg.answer(
            "📌 <b>Быстрая проверка цены</b>\n\n"
            "Использование:\n"
            "<code>/price WAW BCN</code> — ближайший месяц\n"
            "<code>/price KRK DXB</code> — из Кракова в Дубай\n\n"
            "IATA коды: WAW, KRK, WRO, GDN, KTW, POZ"
        )
        return
    origin = parts[1].upper()
    dest   = parts[2].upper()
    wait   = await msg.answer(f"🔍 Проверяю цену <b>{origin} → {dest}</b>...")
    loop   = asyncio.get_event_loop()
    from datetime import datetime, timedelta
    d_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    d_to   = (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y")
    flights = await loop.run_in_executor(
        None, lambda: search_flights(origin, dest, d_from, d_to, limit=3)
    )
    try:
        await wait.delete()
    except Exception:
        pass
    if not flights:
        await msg.answer(f"😔 Рейсы <b>{origin} → {dest}</b> не найдены.\nПроверь IATA коды.")
        return
    f = flights[0]
    flag = _dest_flag(dest)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛒 Купить", url=f["link"]))
    if f.get("link_aviasales"):
        builder.row(InlineKeyboardButton(text="✈️ Aviasales", url=f["link_aviasales"]))
    builder.row(InlineKeyboardButton(text="🔎 Полный поиск", callback_data="search:new"))
    await msg.answer(
        f"💰 <b>Минимальная цена {origin} → {dest}</b> {flag}\n\n"
        f"<b>{f['price']} EUR</b>  {_airline_icon(f.get('airline_code') or f.get('airline',''))} {f['airline']}\n"
        f"📅 {f.get('depart_at','')}  ⏱ {f.get('duration','')}\n"
        f"🔀 {f.get('stops','')}\n\n"
        + (f"💚 Дёшево!" if f['price'] <= 60 else "") +
        (f"🔥 Горящий!" if f['price'] <= 35 else ""),
        reply_markup=builder.as_markup(),
    )




# ── /week — prices for next 7 days ────────────────────────────────────────────

@router.message(Command("week"))
async def cmd_week(msg: Message):
    parts = msg.text.split()
    if len(parts) < 3:
        await msg.answer(
            "📆 <b>Цены на неделю</b>\n\n"
            "Использование: <code>/week WAW BCN</code>\n"
            "Показывает минимальную цену на каждый день следующих 7 дней."
        )
        return
    origin = parts[1].upper()
    dest   = parts[2].upper()
    wait   = await msg.answer(f"📆 Загружаю цены на неделю <b>{origin} → {dest}</b>...")
    loop   = asyncio.get_event_loop()
    days   = await loop.run_in_executor(None, lambda: get_week_prices(origin, dest))
    try:
        await wait.delete()
    except Exception:
        pass

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    flag = _dest_flag(dest)
    lines = [f"📆 <b>{origin} → {dest}</b> {flag}  — цены на 7 дней:\n"]
    builder = InlineKeyboardBuilder()
    min_price = min((d["price"] for d in days if d.get("price")), default=None)

    for d in days:
        price = d.get("price")
        if price is None:
            lines.append(f"  {d['weekday']} {d['date']}  —  нет рейсов")
        else:
            badge = " 🔥" if min_price and price == min_price else ""
            lines.append(f"  {d['weekday']} {d['date']}  💰 <b>{price}€</b>{badge}")
            builder.button(
                text=f"{d['weekday']} {d['date']} — {price}€{badge}",
                url=d["link"],
            )

    builder.button(text="✈️ Aviasales", url=days[0]["link_aviasales"] if days else "https://aviasales.ru")
    builder.button(text="🔎 Полный поиск", callback_data="search:new")
    builder.adjust(1)
    await msg.answer("\n".join(lines), reply_markup=builder.as_markup())


@router.message(F.text == "🔎 Найти билет")
@router.message(F.text == "🔎 Szukaj biletu")
@router.message(F.text == "🔎 Find flight")
@router.message(Command("search"))
async def start_search(msg: Message, state: FSMContext):
    await state.clear()
    lang = get_user_lang(msg.from_user.id)
    if not can_search(msg.from_user.id):
        await msg.answer(
            t("limit_reached", lang) + f"\n\n👉 /vip",
            reply_markup=vip_kb(),
        )
        return
    await state.update_data(mode="oneway")
    await state.set_state(SearchFlight.origin)
    await msg.answer(t("search_from", lang), reply_markup=origins_kb())


@router.message(Command("roundtrip"))
@router.message(F.text == "🔄 Туда-обратно")
@router.message(F.text == "🔄 W obie strony")
@router.message(F.text == "🔄 Round trip")
async def start_roundtrip(msg: Message, state: FSMContext):
    await state.clear()
    lang = get_user_lang(msg.from_user.id)
    if not can_search(msg.from_user.id):
        await msg.answer(t("limit_reached", lang) + "\n\n👉 /vip", reply_markup=vip_kb())
        return
    await state.update_data(mode="roundtrip")
    await state.set_state(SearchFlight.origin)
    await msg.answer(t("trip_type", lang), reply_markup=origins_kb())


@router.callback_query(SearchFlight.origin, F.data.startswith("origin:"))
async def pick_origin(call: CallbackQuery, state: FSMContext):
    lang = get_user_lang(call.from_user.id)
    origin = call.data.split(":")[1]
    await state.update_data(origin=origin)
    await state.set_state(SearchFlight.destination)
    await call.message.edit_text(t("search_to", lang), reply_markup=destinations_kb())
    await call.answer()


@router.callback_query(SearchFlight.destination, F.data.startswith("dest:"))
async def pick_destination(call: CallbackQuery, state: FSMContext):
    lang = get_user_lang(call.from_user.id)
    parts = call.data.split(":")
    if parts[1] == "manual":
        await state.set_state(SearchFlight.dest_manual)
        await call.message.edit_text(t("manual_iata", lang), reply_markup=cancel_kb())
        await call.answer()
        return
    dest_code = parts[1]
    dest_city = parts[2] if len(parts) > 2 else dest_code
    await state.update_data(destination=dest_code, dest_city=dest_city)
    await state.set_state(SearchFlight.dates)
    await call.message.edit_text("📅 <b>Когда летим?</b>", reply_markup=date_range_kb())
    await call.answer()


@router.message(SearchFlight.dest_manual)
async def manual_destination(msg: Message, state: FSMContext):
    code = msg.text.strip().upper()
    if len(code) != 3 or not code.isalpha():
        await msg.answer("❌ Нужен 3-буквенный IATA-код.\nНапример: <code>BCN</code>, <code>DXB</code>")
        return
    await state.update_data(destination=code, dest_city=code)
    await state.set_state(SearchFlight.dates)
    await msg.answer("📅 <b>Когда летим?</b>", reply_markup=date_range_kb())


@router.callback_query(SearchFlight.dates, F.data.startswith("dates:"))
async def pick_dates(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    date_from, date_to = parts[1], parts[2]
    data = await state.get_data()
    mode = data.get("mode", "oneway")

    origin = data.get("origin", "WAW")
    destination = data.get("destination", "BCN")
    dest_city = data.get("dest_city", destination)

    await call.answer()

    # ── Round-trip: ask for return date ───────────────────────────────────────
    if mode == "roundtrip":
        await state.update_data(date_from=date_from, date_to=date_to)
        await state.set_state(SearchFlight.return_date)
        await call.message.edit_text(
            f"🔄 <b>Туда-обратно: {origin} → {dest_city}</b>\n\n"
            f"📅 Вылет: {date_from} — {date_to}\n\n"
            f"🔙 Когда возвращаемся?",
            reply_markup=date_range_kb(label_prefix="return"),
        )
        return

    # ── Cheapest dates mode ───────────────────────────────────────────────────
    if mode == "cheapdates":
        await state.clear()
        await call.message.edit_text(
            f"📅 Ищу самые дешёвые даты <b>{origin} → {dest_city}</b>...\n⏳ Секунду"
        )
        loop = asyncio.get_event_loop()
        flights = await loop.run_in_executor(None, lambda: get_cheapest_dates(origin, destination, months=3))
        save_search(call.from_user.id, origin, destination, date_from, date_to, len(flights))
        increment_searches(call.from_user.id)
        if not flights:
            await call.message.edit_text(
                f"😔 Не нашёл дешёвых дат для <b>{origin} → {dest_city}</b>.\nПопробуй другой маршрут.",
                reply_markup=cancel_kb(),
            )
            return
        flag = _dest_flag(destination)
        lines = [f"📅 <b>Топ-{len(flights)} дешёвых дат: {origin} → {dest_city}</b> {flag}\n"]
        for i, f in enumerate(flights, 1):
            icon = _airline_icon(f.get("airline", ""))
            lines.append(
                f"{i}. 💰 <b>{f['price']} EUR</b>  {icon} {f['airline']}\n"
                f"   📅 {f['depart_at']}  ⏱ {f.get('duration', '')}\n"
                f"   🔀 {f.get('stops', '')}"
            )
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        builder = InlineKeyboardBuilder()
        for i, f in enumerate(flights):
            builder.button(text=f"#{i+1} {f['price']}€ — {f['depart_at'][:5]}", url=f["link"])
        builder.button(text="🔎 Обычный поиск", callback_data="search:new")
        builder.adjust(1)
        await call.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())
        return

    # ── Normal one-way search ─────────────────────────────────────────────────
    await state.clear()
    await call.message.edit_text(f"🔍 Ищу билеты <b>{origin} → {dest_city}</b>...\n⏳ Обычно 5–10 секунд")
    loop = asyncio.get_event_loop()
    flights = await loop.run_in_executor(
        None, lambda: search_flights(origin, destination, date_from, date_to, limit=15)
    )
    save_search(call.from_user.id, origin, destination, date_from, date_to, len(flights))
    increment_searches(call.from_user.id)
    if not flights:
        await call.message.edit_text(
            f"😔 Билеты <b>{origin} → {dest_city}</b> не найдены.\n\n"
            f"Попробуй:\n• Другие даты\n• Другой аэропорт вылета\n• Соседний аэропорт",
            reply_markup=cancel_kb(),
        )
        return
    await state.update_data(flights=flights, idx=0, origin=origin, destination=destination)
    f = flights[0]
    await call.message.edit_text(_flight_text(f, 0, len(flights)), reply_markup=flight_card_kb(f, 0, len(flights)))


@router.callback_query(SearchFlight.return_date, F.data.startswith("return:"))
async def pick_return_date(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    ret_from, ret_to = parts[1], parts[2]
    data = await state.get_data()
    await state.clear()

    origin = data.get("origin", "WAW")
    destination = data.get("destination", "BCN")
    dest_city = data.get("dest_city", destination)
    date_from = data.get("date_from")
    date_to = data.get("date_to")

    await call.answer()
    await call.message.edit_text(
        f"🔄 Ищу билеты туда-обратно\n"
        f"<b>{origin} → {dest_city} → {origin}</b>...\n⏳ Секунду"
    )
    loop = asyncio.get_event_loop()
    flights = await loop.run_in_executor(
        None, lambda: search_round_trip(origin, destination, date_from, date_to, ret_from, ret_to, limit=8)
    )
    save_search(call.from_user.id, origin, destination, date_from, ret_to, len(flights))
    increment_searches(call.from_user.id)
    if not flights:
        await call.message.edit_text(
            f"😔 Рейсы туда-обратно <b>{origin} ↔ {dest_city}</b> не найдены.\nПопробуй другие даты.",
            reply_markup=cancel_kb(),
        )
        return
    await state.update_data(flights=flights, idx=0, origin=origin, destination=destination)
    f = flights[0]
    await call.message.edit_text(_flight_text(f, 0, len(flights)), reply_markup=flight_card_kb(f, 0, len(flights)))


# ── Flight navigation ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("flight:"))
async def navigate_flights(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    direction = parts[1]
    current_idx = int(parts[2])
    data = await state.get_data()
    flights = data.get("flights", [])
    if not flights:
        await call.answer("⏰ Сессия истекла. Начни новый поиск.", show_alert=True)
        return
    new_idx = current_idx - 1 if direction == "prev" else current_idx + 1
    new_idx = max(0, min(new_idx, len(flights) - 1))
    await state.update_data(idx=new_idx)
    f = flights[new_idx]
    try:
        await call.message.edit_text(
            _flight_text(f, new_idx, len(flights)),
            reply_markup=flight_card_kb(f, new_idx, len(flights)),
        )
    except Exception:
        pass
    await call.answer()


@router.callback_query(F.data == "search:new")
async def new_search_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if not can_search(call.from_user.id):
        await call.answer("Лимит поисков исчерпан. Попробуй завтра или купи VIP.", show_alert=True)
        return
    await state.update_data(mode="oneway")
    await state.set_state(SearchFlight.origin)
    await call.message.edit_text("🛫 <b>Откуда летим?</b>", reply_markup=origins_kb())
    await call.answer()


# ── Popular routes ─────────────────────────────────────────────────────────────

@router.message(F.text == "🌍 Популярные")
@router.message(Command("popular"))
async def cmd_popular(msg: Message, state: FSMContext):
    from config import POPULAR_DESTINATIONS
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from datetime import datetime, timedelta

    wait = await msg.answer("🌍 <b>Загружаю популярные маршруты...</b>\n⏳ Ищу актуальные цены")
    builder = InlineKeyboardBuilder()
    lines = ["🌍 <b>Популярные маршруты из Варшавы (WAW):</b>\n"]
    loop = asyncio.get_event_loop()

    for city, code in POPULAR_DESTINATIONS[:6]:
        try:
            d_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
            d_to = (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y")
            from search.flights import search_flights as _sf
            flights = await loop.run_in_executor(None, lambda c=code, df=d_from, dt=d_to: _sf("WAW", c, df, dt, limit=1))
            price_str = f"от {flights[0]['price']}€" if flights else "—"
        except Exception:
            price_str = "—"
        flag = _dest_flag(code)
        lines.append(f"✈️ WAW → {code} {flag}  {city}  <b>{price_str}</b>")
        builder.button(text=f"{city.split()[0]} {price_str}", callback_data=f"popular:WAW:{code}:{city.split()[0]}")

    lines.append("\n💡 Нажми на направление чтобы найти билеты:")
    builder.adjust(2)
    try:
        await wait.delete()
    except Exception:
        pass
    await msg.answer("\n".join(lines), reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("popular:"))
async def popular_search(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    origin, dest, city = parts[1], parts[2], parts[3]
    await call.answer()
    if not can_search(call.from_user.id):
        await call.answer("Лимит поисков исчерпан. Купи VIP.", show_alert=True)
        return
    await state.update_data(origin=origin, destination=dest, dest_city=city, mode="oneway")
    await state.set_state(SearchFlight.dates)
    await call.message.answer(f"📅 <b>Когда летим в {city}?</b>", reply_markup=date_range_kb())


# ── Cheapest dates ─────────────────────────────────────────────────────────────

@router.message(Command("cheapdates"))
@router.message(F.text == "📅 Дешёвые даты")
@router.message(F.text == "📅 Najtańsze daty")
@router.message(F.text == "📅 Cheapest dates")
async def cmd_cheapdates(msg: Message, state: FSMContext):
    await state.clear()
    lang = get_user_lang(msg.from_user.id)
    await state.update_data(mode="cheapdates")
    await state.set_state(SearchFlight.origin)
    await msg.answer(t("search_from", lang), reply_markup=origins_kb())


# ── Hot deals ──────────────────────────────────────────────────────────────────

@router.message(F.text == "🔥 Горящие")
@router.message(F.text == "🔥 Gorące oferty")
@router.message(F.text == "🔥 Hot deals")
@router.message(Command("hot"))
async def cmd_hot(msg: Message):
    lang = get_user_lang(msg.from_user.id)
    deals = get_recent_hot_deals(limit=10)
    if not deals:
        await msg.answer(
            t("hot_empty", lang, channel=CHANNEL_LINK),
            reply_markup=main_menu_kb(lang),
        )
        return
    await msg.answer(t("hot_title", lang, n=len(deals)))
    for deal in deals:
        flag = _dest_flag(deal.get("destination", ""))
        text = (
            f"🔥 <b>{deal.get('origin', '?')} → {deal.get('destination', '?')}</b> {flag}\n"
            f"💰 <b>{deal['price']} EUR</b>\n"
            f"✈️ {deal.get('airline', '')}\n"
            f"📅 {deal.get('depart_at', '')}"
        )
        await msg.answer(text, reply_markup=hot_deal_kb(deal))
        await asyncio.sleep(0.3)


@router.callback_query(F.data == "hot:more")
async def hot_more(call: CallbackQuery):
    await call.answer()
    deals = get_recent_hot_deals(limit=10)
    if not deals:
        await call.answer("Нет новых горящих билетов", show_alert=True)
        return
    await call.message.answer(f"🔥 <b>Все горящие ({len(deals)}):</b>")
    for deal in deals:
        flag = _dest_flag(deal.get("destination", ""))
        text = (
            f"🔥 <b>{deal.get('origin', '?')} → {deal.get('destination', '?')}</b> {flag}\n"
            f"💰 <b>{deal['price']} EUR</b>\n✈️ {deal.get('airline', '')}"
        )
        await call.message.answer(text, reply_markup=hot_deal_kb(deal))
        await asyncio.sleep(0.2)


# ── Alerts ─────────────────────────────────────────────────────────────────────

@router.message(F.text == "🔔 Алерты")
@router.message(F.text == "🔔 Alerty")
@router.message(F.text == "🔔 Alerts")
@router.message(Command("alerts"))
async def cmd_alerts(msg: Message):
    lang = get_user_lang(msg.from_user.id)
    alerts = get_user_alerts(msg.from_user.id)
    if not alerts:
        await msg.answer(t("alerts_empty", lang), reply_markup=alerts_list_kb([]))
        return
    await msg.answer(
        f"🔔 <b>{'Твои алерты' if lang=='ru' else ('Twoje alerty' if lang=='pl' else 'Your alerts')} ({len(alerts)}):</b>",
        reply_markup=alerts_list_kb(alerts),
    )


@router.message(Command("alert"))
async def cmd_alert(msg: Message, state: FSMContext):
    await _start_alert_flow(msg, state)


@router.callback_query(F.data == "alert:new")
async def alert_new_cb(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _start_alert_flow(call.message, state)


async def _start_alert_flow(msg: Message, state: FSMContext):
    lang = get_user_lang(msg.from_user.id if hasattr(msg, 'from_user') and msg.from_user else 0)
    await state.set_state(SetAlert.origin)
    await msg.answer(t("alert_origin", lang), reply_markup=origins_kb("alert_origin"))


@router.callback_query(SetAlert.origin, F.data.startswith("alert_origin:"))
async def alert_pick_origin(call: CallbackQuery, state: FSMContext):
    lang = get_user_lang(call.from_user.id)
    origin = call.data.split(":")[1]
    await state.update_data(origin=origin)
    await state.set_state(SetAlert.destination)
    await call.message.edit_text(t("alert_dest", lang), reply_markup=destinations_kb("alert_dest"))
    await call.answer()


@router.callback_query(SetAlert.destination, F.data.startswith("alert_dest:"))
async def alert_pick_dest(call: CallbackQuery, state: FSMContext):
    lang = get_user_lang(call.from_user.id)
    parts = call.data.split(":")
    if parts[1] == "manual":
        await call.message.edit_text(t("manual_iata", lang), reply_markup=cancel_kb())
        await call.answer()
        return
    dest = parts[1]
    await state.update_data(destination=dest)
    await state.set_state(SetAlert.price_max)
    await call.message.edit_text(t("alert_price", lang), reply_markup=cancel_kb())
    await call.answer()


@router.message(SetAlert.price_max)
async def alert_set_price(msg: Message, state: FSMContext):
    try:
        price_max = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ Введи число, например: <code>50</code>")
        return
    data = await state.get_data()
    await state.clear()
    origin = data.get("origin", "WAW")
    destination = data.get("destination", "BCN")
    save_alert(msg.from_user.id, origin, destination, price_max or None)
    price_str = f"до {price_max}€" if price_max else "любая цена"
    await msg.answer(
        f"✅ <b>Алерт создан!</b>\n\n✈️ {origin} → {destination}\n💰 {price_str}\n\n"
        f"Уведомлю как только найду подходящий билет 🔔",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data.startswith("alert:del:"))
async def delete_alert_cb(call: CallbackQuery):
    alert_id = int(call.data.split(":")[2])
    delete_alert(alert_id, call.from_user.id)
    alerts = get_user_alerts(call.from_user.id)
    await call.answer("🗑 Алерт удалён")
    text = f"🔔 <b>Твои алерты ({len(alerts)}):</b>" if alerts else "🔔 Алертов нет."
    await call.message.edit_text(text, reply_markup=alerts_list_kb(alerts))


@router.callback_query(F.data == "alert:delall")
async def delete_all_alerts_cb(call: CallbackQuery):
    for a in get_user_alerts(call.from_user.id):
        delete_alert(a["id"], call.from_user.id)
    await call.answer("🗑 Все алерты удалены")
    await call.message.edit_text("🔔 Алертов нет.", reply_markup=alerts_list_kb([]))


@router.callback_query(F.data.startswith("alert:route:"))
async def alert_from_route(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    origin, destination = parts[2], parts[3]
    await state.update_data(origin=origin, destination=destination)
    await state.set_state(SetAlert.price_max)
    await call.message.answer(
        f"🔔 Алерт для <b>{origin} → {destination}</b>\n\n"
        f"💰 Введи максимальную цену (EUR) или <code>0</code> для любой:",
        reply_markup=cancel_kb(),
    )
    await call.answer()


# ── Favorites ──────────────────────────────────────────────────────────────────

@router.message(F.text == "❤️ Избранное")
@router.message(F.text == "❤️ Ulubione")
@router.message(F.text == "❤️ Favorites")
@router.message(Command("favorites"))
async def cmd_favorites(msg: Message):
    lang = get_user_lang(msg.from_user.id)
    favs = get_favorites(msg.from_user.id)
    empty_text = {"ru": "❤️ <b>Избранное пусто</b>\n\nСохраняй билеты кнопкой ❤️ при поиске.",
                  "pl": "❤️ <b>Ulubione jest puste</b>\n\nZapisuj bilety przyciskiem ❤️ podczas wyszukiwania.",
                  "en": "❤️ <b>Favorites is empty</b>\n\nSave flights with the ❤️ button during search."}
    if not favs:
        await msg.answer(empty_text.get(lang, empty_text["ru"]))
        return
    title = {"ru": f"❤️ <b>Избранное ({len(favs)}):</b>", "pl": f"❤️ <b>Ulubione ({len(favs)}):</b>", "en": f"❤️ <b>Favorites ({len(favs)}):</b>"}
    await msg.answer(title.get(lang, title["ru"]), reply_markup=favorites_kb(favs))


@router.callback_query(F.data.startswith("fav:save:"))
async def save_fav_cb(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":")[2])
    data = await state.get_data()
    flights = data.get("flights", [])
    if not flights or idx >= len(flights):
        await call.answer("⏰ Сессия истекла. Найди билет заново.", show_alert=True)
        return
    saved = save_favorite(call.from_user.id, flights[idx])
    await call.answer("❤️ Сохранено в избранное!" if saved else "Уже в избранном")


@router.callback_query(F.data.startswith("fav:hotdeal:"))
async def save_hotdeal_fav(call: CallbackQuery):
    deal_id = int(call.data.split(":")[2])
    deals = get_recent_hot_deals(limit=20)
    deal = next((d for d in deals if d.get("id") == deal_id), None)
    if not deal:
        await call.answer("Предложение устарело", show_alert=True)
        return
    flight = {
        "origin": deal.get("origin", ""), "destination": deal.get("destination", ""),
        "price": deal.get("price", 0), "airline": deal.get("airline", ""),
        "depart_at": deal.get("depart_at", ""), "arrive_at": "", "link": deal.get("link", ""),
    }
    saved = save_favorite(call.from_user.id, flight)
    await call.answer("❤️ Сохранено!" if saved else "Уже в избранном")


@router.callback_query(F.data.startswith("fav:open:"))
async def open_fav_cb(call: CallbackQuery):
    fav_id = int(call.data.split(":")[2])
    favs = get_favorites(call.from_user.id)
    fav = next((f for f in favs if f["id"] == fav_id), None)
    if not fav:
        await call.answer("Не найдено", show_alert=True)
        return
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    if fav.get("link"):
        builder.row(InlineKeyboardButton(text="🛒 Купить", url=fav["link"]))
    builder.row(
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"fav:del:{fav_id}"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="fav:back"),
    )
    flag = _dest_flag(fav.get("destination", ""))
    await call.message.edit_text(
        f"✈️ <b>{fav['origin']} → {fav['destination']}</b> {flag}\n"
        f"💰 {fav['price']} EUR\n✈️ {fav.get('airline', '')}\n📅 {fav.get('depart_at', '')}",
        reply_markup=builder.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("fav:del:"))
async def del_fav_cb(call: CallbackQuery):
    fav_id = int(call.data.split(":")[2])
    delete_favorite(fav_id, call.from_user.id)
    await call.answer("🗑 Удалено")
    favs = get_favorites(call.from_user.id)
    if not favs:
        await call.message.edit_text("❤️ Избранное пусто.")
        return
    await call.message.edit_text(f"❤️ <b>Избранное ({len(favs)}):</b>", reply_markup=favorites_kb(favs))


@router.callback_query(F.data == "fav:back")
async def fav_back_cb(call: CallbackQuery):
    favs = get_favorites(call.from_user.id)
    await call.message.edit_text(f"❤️ <b>Избранное ({len(favs)}):</b>", reply_markup=favorites_kb(favs))
    await call.answer()


@router.callback_query(F.data == "fav:clear")
async def fav_clear_cb(call: CallbackQuery):
    for f in get_favorites(call.from_user.id):
        delete_favorite(f["id"], call.from_user.id)
    await call.answer("🗑 Очищено")
    await call.message.edit_text("❤️ Избранное пусто.")


# ── VIP ────────────────────────────────────────────────────────────────────────

@router.message(F.text == "⭐ VIP")
@router.message(Command("vip"))
async def cmd_vip(msg: Message):
    lang = get_user_lang(msg.from_user.id)
    if is_vip(msg.from_user.id):
        already = {"ru": "⭐ <b>У тебя уже есть VIP!</b>\n\n✅ Безлимитный поиск\n✅ Алерты\n✅ Горящие уведомления\n\nСпасибо! 🙏",
                   "pl": "⭐ <b>Masz już VIP!</b>\n\n✅ Nieograniczone wyszukiwania\n✅ Alerty\n✅ Powiadomienia o gorących ofertach\n\nDziękujemy! 🙏",
                   "en": "⭐ <b>You already have VIP!</b>\n\n✅ Unlimited searches\n✅ Alerts\n✅ Hot deal notifications\n\nThank you! 🙏"}
        await msg.answer(already.get(lang, already["ru"]))
        return
    await msg.answer(
        t("vip_text", lang, price_pln=VIP_PRICE_PLN, price_stars=VIP_PRICE_STARS),
        reply_markup=vip_kb(),
    )


@router.callback_query(F.data == "vip:pay:stars")
async def vip_pay_stars(call: CallbackQuery):
    await call.answer()
    await call.message.answer_invoice(
        title=f"⭐ VIP {BOT_NAME} — 30 дней",
        description="Безлимитный поиск + алерты + туда-обратно + уведомления о горящих",
        payload="vip_30d",
        currency="XTR",
        prices=[LabeledPrice(label="VIP 30 дней", amount=VIP_PRICE_STARS)],
    )


@router.callback_query(F.data == "vip:pay:manual")
async def vip_pay_manual(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        f"💳 <b>Оплата вручную — {VIP_PRICE_PLN} zł/мес</b>\n\n"
        f"Revolut: <code>@d_yaromenka</code>\n"
        f"BLIK: <code>+48 731 359 199</code>\n\n"
        f"В комментарии укажи свой Telegram ID: <code>{call.from_user.id}</code>\n\n"
        f"После оплаты нажми кнопку ниже — активирую вручную в течение часа.",
        reply_markup=vip_manual_kb(),
    )


@router.callback_query(F.data == "vip:paid:manual")
async def vip_paid_manual(call: CallbackQuery):
    await call.answer("✅ Заявка отправлена!")
    from bot.bot import bot as _bot
    for admin_id in ADMIN_IDS:
        try:
            await _bot.send_message(
                admin_id,
                f"💳 <b>Запрос VIP (ручная оплата)</b>\n\n"
                f"👤 @{call.from_user.username or 'нет'}\n"
                f"🆔 <code>{call.from_user.id}</code>\n"
                f"💰 {VIP_PRICE_PLN} zł\n\n"
                f"Активировать: /givevip {call.from_user.id} 30",
                parse_mode="HTML",
            )
        except Exception:
            pass
    await call.message.edit_text(
        "✅ <b>Заявка отправлена!</b>\n\n"
        "Активирую VIP в течение часа после подтверждения оплаты.\n\n"
        "Если вопросы — пиши @D_ANIEL0507"
    )


@router.callback_query(F.data == "vip:back")
async def vip_back(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        f"⭐ <b>VIP — {BOT_NAME}</b>\n\n"
        f"💰 <b>{VIP_PRICE_PLN} zł/мес</b> или <b>{VIP_PRICE_STARS} Stars</b>",
        reply_markup=vip_kb(),
    )


@router.pre_checkout_query()
async def pre_checkout_query(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(msg: Message):
    if msg.successful_payment.invoice_payload == "vip_30d":
        set_vip(msg.from_user.id, days=30)
        await msg.answer(
            f"🎉 <b>VIP активирован на 30 дней!</b>\n\n"
            f"✅ Безлимитный поиск\n✅ Алерты\n✅ Туда-обратно\n\n"
            f"Начни поиск: /search",
            reply_markup=main_menu_kb(),
        )


# ── Stats ──────────────────────────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(msg: Message):
    left = searches_left(msg.from_user.id)
    left_str = "∞" if left >= 999 else str(left)
    vip_status = "⭐ VIP" if is_vip(msg.from_user.id) else "🆓 Бесплатный"
    favs = get_favorites(msg.from_user.id)
    alerts = get_user_alerts(msg.from_user.id)
    await msg.answer(
        f"📊 <b>Твоя статистика:</b>\n\n"
        f"👤 Статус: <b>{vip_status}</b>\n"
        f"🔎 Поисков сегодня осталось: <b>{left_str}</b>\n"
        f"❤️ Избранных билетов: <b>{len(favs)}</b>\n"
        f"🔔 Активных алертов: <b>{len(alerts)}</b>"
    )


# ── Admin panel ────────────────────────────────────────────────────────────────

def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(msg: Message, state: FSMContext):
    if not _is_admin(msg.from_user.id):
        return
    await state.clear()
    stats = get_full_stats()
    from config import EARLY_ADOPTERS_LIMIT
    slots_left = max(0, EARLY_ADOPTERS_LIMIT - stats["early"])
    await msg.answer(
        f"🔧 <b>Админ-панель {BOT_NAME}</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['users']}</b>\n"
        f"📅 Сегодня активных: <b>{stats['today_users']}</b>\n"
        f"⭐ VIP: <b>{stats['vip']}</b>\n"
        f"🌟 Early adopters: <b>{stats['early']}</b> / 50  (осталось мест: {slots_left})\n"
        f"🚫 Забанено: <b>{stats['banned']}</b>\n\n"
        f"🔎 Поисков всего: <b>{stats['searches']}</b>\n"
        f"📅 Поисков сегодня: <b>{stats['today_searches']}</b>\n"
        f"🔔 Активных алертов: <b>{stats['alerts']}</b>\n"
        f"🔥 Горящих в базе: <b>{stats['deals']}</b>",
        reply_markup=admin_kb(),
    )


@router.callback_query(F.data == "adm:stats")
async def adm_stats(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    stats = get_full_stats()
    from config import EARLY_ADOPTERS_LIMIT
    slots_left = max(0, EARLY_ADOPTERS_LIMIT - stats["early"])
    await call.message.edit_text(
        f"📊 <b>Статистика {BOT_NAME}</b>\n\n"
        f"👥 Всего: <b>{stats['users']}</b>  |  Сегодня: <b>{stats['today_users']}</b>\n"
        f"⭐ VIP: <b>{stats['vip']}</b>  |  🌟 Early: <b>{stats['early']}</b>/50 (мест: {slots_left})\n"
        f"🚫 Бан: <b>{stats['banned']}</b>\n\n"
        f"🔎 Поисков: <b>{stats['searches']}</b>  |  Сегодня: <b>{stats['today_searches']}</b>\n"
        f"🔔 Алертов: <b>{stats['alerts']}</b>  |  🔥 Горящих: <b>{stats['deals']}</b>",
        reply_markup=admin_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "adm:recent")
async def adm_recent(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    users = get_recent_users(10)
    lines = ["👥 <b>Последние 10 пользователей:</b>\n"]
    for u in users:
        vip_mark = "⭐" if u.get("vip") else ""
        early_mark = "🌟" if u.get("is_early_adopter") else ""
        ban_mark = "🚫" if u.get("banned") else ""
        name = u.get("first_name") or u.get("username") or "—"
        lines.append(
            f"{early_mark}{vip_mark}{ban_mark} <b>{name}</b> "
            f"(<code>{u['user_id']}</code>)  🔎{u.get('total_searches',0)}\n"
            f"   📅 {u.get('created_at','')[:10]}"
        )
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="adm:back")
    await call.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data == "adm:top")
async def adm_top(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    users = get_top_users(10)
    lines = ["🏆 <b>Топ-10 по поискам:</b>\n"]
    for i, u in enumerate(users, 1):
        vip_mark = "⭐" if u.get("vip") else ""
        name = u.get("first_name") or u.get("username") or "—"
        lines.append(f"{i}. {vip_mark} <b>{name}</b> (<code>{u['user_id']}</code>) — {u.get('total_searches',0)} поисков")
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="adm:back")
    await call.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data == "adm:early")
async def adm_early(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    users = get_early_adopters()
    lines = [f"🌟 <b>Early adopters ({len(users)}/50):</b>\n"]
    for i, u in enumerate(users, 1):
        name = u.get("first_name") or u.get("username") or "—"
        lines.append(f"{i}. <b>{name}</b> (<code>{u['user_id']}</code>)  📅 {u.get('created_at','')[:10]}")
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="adm:back")
    await call.message.edit_text("\n".join(lines) if lines else "Нет early adopters.", reply_markup=builder.as_markup())
    await call.answer()


@router.callback_query(F.data == "adm:find")
async def adm_find_start(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return
    await state.set_state(AdminState.find_user)
    await call.message.edit_text(
        "🔍 <b>Найти пользователя</b>\n\nВведи user_id или @username:",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(AdminState.find_user)
async def adm_find_user(msg: Message, state: FSMContext):
    if not _is_admin(msg.from_user.id):
        return
    await state.clear()
    query = msg.text.strip().lstrip("@")
    # Try by ID first
    user = None
    try:
        user = get_user_info(int(query))
    except ValueError:
        # Search by username
        conn = __import__('database.db', fromlist=['get_conn']).get_conn()
        row = conn.execute("SELECT * FROM users WHERE username=?", (query,)).fetchone()
        conn.close()
        user = dict(row) if row else None

    if not user:
        await msg.answer("❌ Пользователь не найден.", reply_markup=admin_kb())
        return
    await _show_user_card(msg, user)


async def _show_user_card(msg_or_call, user: dict):
    uid = user["user_id"]
    vip_status = is_vip(uid)
    ban_status = bool(user.get("banned"))
    early = bool(user.get("is_early_adopter"))
    name = user.get("first_name") or "—"
    username = f"@{user['username']}" if user.get("username") else "нет"
    vip_until = user.get("vip_until", "")[:10] if user.get("vip_until") else ("∞" if early else "нет")

    text = (
        f"👤 <b>{name}</b>  {username}\n"
        f"🆔 <code>{uid}</code>\n\n"
        f"{'🌟 Early adopter  ' if early else ''}"
        f"{'⭐ VIP' if vip_status else '🆓 Free'}  {'🚫 БАН' if ban_status else ''}\n"
        f"VIP до: <b>{vip_until}</b>\n\n"
        f"🔎 Поисков всего: <b>{user.get('total_searches', 0)}</b>\n"
        f"📅 Зарегистрирован: <b>{user.get('created_at','')[:10]}</b>\n"
        f"👁 Последний визит: <b>{user.get('last_seen','')[:10]}</b>"
    )
    kb = admin_user_kb(uid, vip_status, ban_status)
    if hasattr(msg_or_call, "edit_text"):
        await msg_or_call.edit_text(text, reply_markup=kb)
    else:
        await msg_or_call.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("adm:givevip:"))
async def adm_givevip(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    uid = int(call.data.split(":")[2])
    set_vip(uid, days=30)
    await call.answer("✅ VIP выдан на 30 дней")
    user = get_user_info(uid)
    if user:
        await _show_user_card(call.message, user)
    from bot.bot import bot as _bot
    try:
        await _bot.send_message(uid, f"🎉 <b>VIP активирован на 30 дней!</b>\n\n✅ Безлимитный поиск\n✅ Алерты\n\n/search", parse_mode="HTML")
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm:revokevip:"))
async def adm_revokevip(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    uid = int(call.data.split(":")[2])
    revoke_vip(uid)
    await call.answer("❌ VIP отозван")
    user = get_user_info(uid)
    if user:
        await _show_user_card(call.message, user)


@router.callback_query(F.data.startswith("adm:ban:"))
async def adm_ban(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    uid = int(call.data.split(":")[2])
    ban_user(uid)
    await call.answer("🚫 Пользователь забанен")
    user = get_user_info(uid)
    if user:
        await _show_user_card(call.message, user)


@router.callback_query(F.data.startswith("adm:unban:"))
async def adm_unban(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    uid = int(call.data.split(":")[2])
    unban_user(uid)
    await call.answer("✅ Разбанен")
    user = get_user_info(uid)
    if user:
        await _show_user_card(call.message, user)


@router.callback_query(F.data.startswith("adm:msg:"))
async def adm_msg_start(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return
    uid = int(call.data.split(":")[2])
    await state.set_state(AdminState.msg_user)
    await state.update_data(msg_target=uid)
    await call.message.edit_text(
        f"📢 Напиши сообщение для пользователя <code>{uid}</code>:",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(AdminState.msg_user)
async def adm_msg_send(msg: Message, state: FSMContext):
    if not _is_admin(msg.from_user.id):
        return
    data = await state.get_data()
    uid = data.get("msg_target")
    await state.clear()
    from bot.bot import bot as _bot
    try:
        await _bot.send_message(uid, msg.text, parse_mode="HTML")
        await msg.answer(f"✅ Сообщение отправлено пользователю {uid}", reply_markup=admin_kb())
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}", reply_markup=admin_kb())


@router.callback_query(F.data == "adm:broadcast")
async def adm_broadcast_start(call: CallbackQuery, state: FSMContext):
    if not _is_admin(call.from_user.id):
        return
    await state.set_state(AdminState.broadcast)
    await call.message.edit_text(
        "📢 <b>Рассылка всем пользователям</b>\n\nНапиши текст (поддерживается HTML):",
        reply_markup=cancel_kb(),
    )
    await call.answer()


@router.message(AdminState.broadcast)
async def adm_broadcast_send(msg: Message, state: FSMContext):
    if not _is_admin(msg.from_user.id):
        return
    await state.clear()
    from database.db import get_all_user_ids
    from bot.bot import bot as _bot
    user_ids = get_all_user_ids()
    sent, failed = 0, 0
    status_msg = await msg.answer(f"📢 Рассылка... 0/{len(user_ids)}")
    for i, uid in enumerate(user_ids):
        try:
            await _bot.send_message(uid, msg.text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        if i % 20 == 0:
            try:
                await status_msg.edit_text(f"📢 Рассылка... {i}/{len(user_ids)}")
            except Exception:
                pass
        await asyncio.sleep(0.05)
    await status_msg.edit_text(f"📢 Рассылка завершена:\n✅ Доставлено: {sent}\n❌ Ошибок: {failed}")


@router.callback_query(F.data == "adm:back")
async def adm_back(call: CallbackQuery):
    if not _is_admin(call.from_user.id):
        return
    stats = get_full_stats()
    from config import EARLY_ADOPTERS_LIMIT
    slots_left = max(0, EARLY_ADOPTERS_LIMIT - stats["early"])
    await call.message.edit_text(
        f"🔧 <b>Админ-панель {BOT_NAME}</b>\n\n"
        f"👥 Пользователей: <b>{stats['users']}</b>  |  Сегодня: <b>{stats['today_users']}</b>\n"
        f"⭐ VIP: <b>{stats['vip']}</b>  |  🌟 Early: <b>{stats['early']}</b>/50 (мест: {slots_left})\n"
        f"🔎 Поисков: <b>{stats['searches']}</b>  |  Сегодня: <b>{stats['today_searches']}</b>",
        reply_markup=admin_kb(),
    )
    await call.answer()


@router.message(Command("givevip"))
async def cmd_givevip(msg: Message):
    if not _is_admin(msg.from_user.id):
        return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("Использование: /givevip &lt;user_id&gt; [days]")
        return
    try:
        uid = int(parts[1])
        days = int(parts[2]) if len(parts) > 2 else 30
        set_vip(uid, days)
        await msg.answer(f"✅ VIP выдан пользователю {uid} на {days} дней")
        from bot.bot import bot as _bot
        try:
            await _bot.send_message(uid, f"🎉 <b>VIP активирован на {days} дней!</b>\n\n✅ Безлимитный поиск\n✅ Алерты\n\n/search", parse_mode="HTML")
        except Exception:
            pass
    except ValueError:
        await msg.answer("❌ Неверный формат")


@router.message(Command("broadcast"))
async def cmd_broadcast(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    text = msg.text.removeprefix("/broadcast").strip()
    if not text:
        await msg.answer("Используй /admin → 📢 Рассылка")
        return
    from database.db import get_all_user_ids
    from bot.bot import bot as _bot
    user_ids = get_all_user_ids()
    sent, failed = 0, 0
    for uid in user_ids:
        try:
            await _bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    await msg.answer(f"📢 Рассылка завершена: ✅ {sent} / ❌ {failed}")


# ── Cancel / noop ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel")
async def cancel_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer("Отменено")
    try:
        await call.message.edit_text("❌ Отменено.")
    except Exception:
        pass
    await call.message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.callback_query(F.data == "noop")
async def noop_cb(call: CallbackQuery):
    await call.answer()


# ── Fallback ───────────────────────────────────────────────────────────────────

@router.message()
async def fallback(msg: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        return
    await msg.answer("Не понял команду. Используй кнопки меню или /help", reply_markup=main_menu_kb())
