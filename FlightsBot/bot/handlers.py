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
)
from search.kiwi import search_flights, get_cheapest_dates
from bot.keyboards import (
    main_menu_kb, origins_kb, destinations_kb, date_range_kb,
    flight_card_kb, hot_deal_kb, alerts_list_kb, favorites_kb,
    vip_kb, vip_manual_kb, cancel_kb, share_kb,
)
from config import (
    ADMIN_IDS, VIP_PRICE_PLN, VIP_PRICE_STARS,
    FREE_SEARCHES, CHANNEL_LINK, BOT_NAME,
)

router = Router()


# ── FSM States ─────────────────────────────────────────────────────────────────

class SearchFlight(StatesGroup):
    origin      = State()
    destination = State()
    dest_manual = State()
    dates       = State()


class SetAlert(StatesGroup):
    origin      = State()
    destination = State()
    price_max   = State()


# ── Helpers ────────────────────────────────────────────────────────────────────

AIRLINE_ICONS = {
    "FR": "🟡", "W6": "🟣", "VY": "🟠", "U2": "�",
    "LO": "�", "LH": "�", "BA": "🔵", "AF": "🔵",
    "KL": "🔵", "TP": "🟢", "EK": "�", "QR": "🟤",
}

def _airline_icon(airline: str) -> str:
    code = airline[:2].upper() if airline else ""
    return AIRLINE_ICONS.get(code, "✈️")


def _flight_text(f: dict, idx: int = None, total: int = None) -> str:
    flag = _dest_flag(f.get("destination", ""))
    icon = _airline_icon(f.get("airline", ""))
    header = f"✈️ <b>{f['origin_city']} → {f['dest_city']}</b> {flag}"
    if idx is not None and total:
        header += f"  <i>({idx+1}/{total})</i>"
    lines = [
        header,
        f"💰 <b>{f['price']} {f['currency']}</b>",
        f"{icon} {f['airline']}",
    ]
    if f.get("depart_at"):
        dep = f"📅 {f['depart_at']}"
        if f.get("arrive_at"):
            dep += f" → {f['arrive_at']}"
        lines.append(dep)
    details = []
    if f.get("duration"):
        details.append(f"⏱ {f['duration']}")
    if f.get("stops"):
        details.append(f"🔀 {f['stops']}")
    if details:
        lines.append("  ".join(details))
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
    user = get_or_create_user(
        msg.from_user.id,
        msg.from_user.username or "",
        msg.from_user.first_name or "",
    )
    vip_badge = " ⭐" if is_vip(msg.from_user.id) else ""
    left = searches_left(msg.from_user.id)
    left_str = "∞" if left >= 999 else str(left)

    name = msg.from_user.first_name or "друг"
    await msg.answer(
        f"✈️ <b>{BOT_NAME}{vip_badge}</b>\n\n"
        f"Привет, {name}! Нахожу самые дешёвые авиабилеты из Польши.\n\n"
        f"🔎 Поисков сегодня: <b>{left_str}</b> из {FREE_SEARCHES}\n"
        f"🔥 Горящие билеты обновляются каждые 2 часа\n\n"
        f"Выбери действие 👇",
        reply_markup=main_menu_kb(),
    )


# ── /help ──────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        f"✈️ <b>{BOT_NAME} — команды:</b>\n\n"
        "/search — 🔎 найти билет\n"
        "/hot — 🔥 горящие билеты\n"
        "/popular — 🌍 популярные маршруты\n"
        "/alert — 🔔 создать алерт на маршрут\n"
        "/alerts — 📋 мои алерты\n"
        "/favorites — ❤️ избранное\n"
        "/vip — ⭐ VIP подписка\n"
        "/stats — 📊 моя статистика\n\n"
        f"📢 Канал с горящими: {CHANNEL_LINK}"
    )


# ── Search flow ────────────────────────────────────────────────────────────────

@router.message(F.text == "🔎 Найти билет")
@router.message(Command("search"))
async def start_search(msg: Message, state: FSMContext):
    await state.clear()
    if not can_search(msg.from_user.id):
        await msg.answer(
            f"⚠️ <b>Лимит поисков исчерпан</b> ({FREE_SEARCHES}/день).\n\n"
            f"⭐ <b>VIP</b> — безлимитный поиск + алерты\n"
            f"💰 Всего {VIP_PRICE_PLN} zł/мес\n\n"
            f"👉 /vip",
            reply_markup=vip_kb(),
        )
        return
    await state.set_state(SearchFlight.origin)
    await msg.answer("🛫 <b>Откуда летим?</b>", reply_markup=origins_kb())


@router.callback_query(SearchFlight.origin, F.data.startswith("origin:"))
async def pick_origin(call: CallbackQuery, state: FSMContext):
    origin = call.data.split(":")[1]
    await state.update_data(origin=origin)
    await state.set_state(SearchFlight.destination)
    await call.message.edit_text("🛬 <b>Куда летим?</b>", reply_markup=destinations_kb())
    await call.answer()


@router.callback_query(SearchFlight.destination, F.data.startswith("dest:"))
async def pick_destination(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    if parts[1] == "manual":
        await state.set_state(SearchFlight.dest_manual)
        await call.message.edit_text(
            "✏️ Введи <b>IATA-код</b> аэропорта назначения\n\n"
            "Примеры: <code>BCN</code> (Barcelona), <code>DXB</code> (Dubai), <code>BKK</code> (Bangkok)",
            reply_markup=cancel_kb(),
        )
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
        await msg.answer(
            "❌ Нужен 3-буквенный IATA-код.\n"
            "Например: <code>BCN</code>, <code>DXB</code>, <code>BKK</code>"
        )
        return
    await state.update_data(destination=code, dest_city=code)
    await state.set_state(SearchFlight.dates)
    await msg.answer("📅 <b>Когда летим?</b>", reply_markup=date_range_kb())


@router.callback_query(SearchFlight.dates, F.data.startswith("dates:"))
async def pick_dates(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    date_from, date_to = parts[1], parts[2]
    data = await state.get_data()
    await state.clear()

    origin = data.get("origin", "WAW")
    destination = data.get("destination", "BCN")
    dest_city = data.get("dest_city", destination)

    await call.message.edit_text(
        f"🔍 Ищу билеты <b>{origin} → {dest_city}</b>...\n⏳ Обычно 3–5 секунд"
    )
    await call.answer()

    loop = asyncio.get_event_loop()
    flights = await loop.run_in_executor(
        None,
        lambda: search_flights(origin, destination, date_from, date_to, limit=10),
    )

    # Save search to DB
    save_search(call.from_user.id, origin, destination, date_from, date_to, len(flights))
    increment_searches(call.from_user.id)

    if not flights:
        await call.message.edit_text(
            f"😔 Билеты <b>{origin} → {dest_city}</b> не найдены.\n\n"
            f"Попробуй:\n"
            f"• Другие даты\n"
            f"• Другой аэропорт вылета\n"
            f"• Соседний аэропорт назначения",
            reply_markup=cancel_kb(),
        )
        return

    await state.update_data(flights=flights, idx=0, origin=origin, destination=destination)
    f = flights[0]
    await call.message.edit_text(
        _flight_text(f, 0, len(flights)),
        reply_markup=flight_card_kb(f, 0, len(flights)),
    )


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
    await call.message.edit_text(
        _flight_text(f, new_idx, len(flights)),
        reply_markup=flight_card_kb(f, new_idx, len(flights)),
    )
    await call.answer()


@router.callback_query(F.data == "search:new")
async def new_search_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    if not can_search(call.from_user.id):
        await call.answer("Лимит поисков исчерпан. Попробуй завтра или купи VIP.", show_alert=True)
        return
    await state.set_state(SearchFlight.origin)
    await call.message.edit_text("🛫 <b>Откуда летим?</b>", reply_markup=origins_kb())
    await call.answer()


# ── Popular routes ─────────────────────────────────────────────────────────────

@router.message(F.text == "🌍 Популярные")
@router.message(Command("popular"))
async def cmd_popular(msg: Message):
    from config import POPULAR_DESTINATIONS
    lines = ["🌍 <b>Популярные маршруты из Варшавы:</b>\n"]
    for city, code in POPULAR_DESTINATIONS[:8]:
        lines.append(f"✈️ WAW → {code}  {city}")
    lines.append(
        "\n💡 Нажми <b>🔎 Найти билет</b> чтобы найти цены на любой маршрут"
    )
    await msg.answer("\n".join(lines), reply_markup=main_menu_kb())


# ── Hot deals ──────────────────────────────────────────────────────────────────

@router.message(F.text == "🔥 Горящие")
@router.message(Command("hot"))
async def cmd_hot(msg: Message):
    deals = get_recent_hot_deals(limit=5)
    if not deals:
        await msg.answer(
            "🔥 <b>Горящие билеты</b>\n\n"
            "Пока нет актуальных предложений.\n"
            "Обновляем каждые 2 часа!\n\n"
            f"📢 Подпишись на канал: {CHANNEL_LINK}",
            reply_markup=main_menu_kb(),
        )
        return
    await msg.answer(f"🔥 <b>Горящие билеты — {len(deals)} предложений:</b>")
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
            f"💰 <b>{deal['price']} EUR</b>\n"
            f"✈️ {deal.get('airline', '')}"
        )
        await call.message.answer(text, reply_markup=hot_deal_kb(deal))
        await asyncio.sleep(0.2)


# ── Alerts ─────────────────────────────────────────────────────────────────────

@router.message(F.text == "🔔 Алерты")
@router.message(Command("alerts"))
async def cmd_alerts(msg: Message):
    alerts = get_user_alerts(msg.from_user.id)
    if not alerts:
        await msg.answer(
            "🔔 <b>Алерты</b>\n\n"
            "Нет активных алертов.\n\n"
            "Алерт — уведомление когда цена на маршрут упадёт ниже нужной суммы.\n\n"
            "Нажми ➕ чтобы добавить:",
            reply_markup=alerts_list_kb([]),
        )
        return
    await msg.answer(
        f"🔔 <b>Твои алерты ({len(alerts)}):</b>\n\nНажми на алерт чтобы удалить:",
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
    await state.set_state(SetAlert.origin)
    await msg.answer("🛫 <b>Откуда?</b>\n\nВыбери аэропорт вылета:", reply_markup=origins_kb("alert_origin"))


@router.callback_query(SetAlert.origin, F.data.startswith("alert_origin:"))
async def alert_pick_origin(call: CallbackQuery, state: FSMContext):
    origin = call.data.split(":")[1]
    await state.update_data(origin=origin)
    await state.set_state(SetAlert.destination)
    await call.message.edit_text("🛬 <b>Куда?</b>", reply_markup=destinations_kb("alert_dest"))
    await call.answer()


@router.callback_query(SetAlert.destination, F.data.startswith("alert_dest:"))
async def alert_pick_dest(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    if parts[1] == "manual":
        await call.message.edit_text("✏️ Введи IATA-код:", reply_markup=cancel_kb())
        await call.answer()
        return
    dest = parts[1]
    await state.update_data(destination=dest)
    await state.set_state(SetAlert.price_max)
    await call.message.edit_text(
        "💰 <b>Максимальная цена (EUR)?</b>\n\n"
        "Введи число, например: <code>50</code>\n"
        "Или <code>0</code> — получать все предложения:",
        reply_markup=cancel_kb(),
    )
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
        f"✅ <b>Алерт создан!</b>\n\n"
        f"✈️ {origin} → {destination}\n"
        f"💰 {price_str}\n\n"
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
@router.message(Command("favorites"))
async def cmd_favorites(msg: Message):
    favs = get_favorites(msg.from_user.id)
    if not favs:
        await msg.answer(
            "❤️ <b>Избранное пусто</b>\n\n"
            "Сохраняй билеты кнопкой ❤️ при поиске или в горящих."
        )
        return
    await msg.answer(f"❤️ <b>Избранное ({len(favs)}):</b>", reply_markup=favorites_kb(favs))


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
    """Save a hot deal to favorites."""
    deal_id = int(call.data.split(":")[2])
    deals = get_recent_hot_deals(limit=20)
    deal = next((d for d in deals if d.get("id") == deal_id), None)
    if not deal:
        await call.answer("Предложение устарело", show_alert=True)
        return
    flight = {
        "origin": deal.get("origin", ""),
        "destination": deal.get("destination", ""),
        "price": deal.get("price", 0),
        "airline": deal.get("airline", ""),
        "depart_at": deal.get("depart_at", ""),
        "arrive_at": "",
        "link": deal.get("link", ""),
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
        f"💰 {fav['price']} EUR\n"
        f"✈️ {fav.get('airline', '')}\n"
        f"📅 {fav.get('depart_at', '')}",
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
    if is_vip(msg.from_user.id):
        await msg.answer(
            f"⭐ <b>У тебя уже есть VIP!</b>\n\n"
            f"✅ Безлимитный поиск\n"
            f"✅ Алерты на маршруты\n"
            f"✅ Уведомления о горящих билетах\n"
            f"✅ Ранний доступ к акциям\n\n"
            f"Спасибо за поддержку! 🙏"
        )
        return
    await msg.answer(
        f"⭐ <b>VIP — {BOT_NAME}</b>\n\n"
        f"🆓 Бесплатно: {FREE_SEARCHES} поисков/день\n"
        f"⭐ VIP: безлимитный поиск + алерты\n\n"
        f"💰 <b>{VIP_PRICE_PLN} zł/мес</b> или <b>{VIP_PRICE_STARS} Telegram Stars</b>\n\n"
        f"Выбери способ оплаты:",
        reply_markup=vip_kb(),
    )


@router.callback_query(F.data == "vip:pay:stars")
async def vip_pay_stars(call: CallbackQuery):
    await call.answer()
    await call.message.answer_invoice(
        title=f"⭐ VIP {BOT_NAME} — 30 дней",
        description="Безлимитный поиск + алерты на маршруты + уведомления о горящих",
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
    # Notify admin
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
            f"✅ Безлимитный поиск\n"
            f"✅ Алерты на маршруты\n\n"
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


# ── Admin ──────────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    stats = get_stats()
    await msg.answer(
        f"🔧 <b>Админ-панель {BOT_NAME}</b>\n\n"
        f"👥 Пользователей: <b>{stats['users']}</b>\n"
        f"⭐ VIP: <b>{stats['vip']}</b>\n"
        f"🔎 Поисков всего: <b>{stats['searches']}</b>\n"
        f"🔔 Активных алертов: <b>{stats['alerts']}</b>\n\n"
        f"Команды:\n"
        f"/givevip &lt;id&gt; [days] — выдать VIP\n"
        f"/broadcast &lt;текст&gt; — рассылка всем"
    )


@router.message(Command("givevip"))
async def cmd_givevip(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
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
        try:
            from bot.bot import bot as _bot
            await _bot.send_message(
                uid,
                f"🎉 <b>VIP активирован на {days} дней!</b>\n\n"
                f"✅ Безлимитный поиск\n✅ Алерты\n\n/search — начать поиск",
                parse_mode="HTML",
            )
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
        await msg.answer("Использование: /broadcast &lt;текст&gt;")
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
    await call.message.edit_text("❌ Отменено.")
    await call.message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.callback_query(F.data == "noop")
async def noop_cb(call: CallbackQuery):
    await call.answer()


# ── Fallback ───────────────────────────────────────────────────────────────────

@router.message()
async def fallback(msg: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        return  # Let FSM handle it
    await msg.answer(
        "Не понял команду. Используй кнопки меню или /help",
        reply_markup=main_menu_kb(),
    )
