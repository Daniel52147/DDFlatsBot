import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import (
    get_or_create_user, is_vip, set_vip, can_search, increment_searches,
    searches_left, save_alert, get_user_alerts, delete_alert, get_all_active_alerts,
    save_favorite, get_favorites, delete_favorite, get_recent_hot_deals, get_stats,
)
from search.kiwi import search_flights, search_one_way, get_cheapest_dates
from bot.keyboards import (
    main_menu_kb, origins_kb, destinations_kb, date_range_kb,
    flight_card_kb, hot_deal_kb, alerts_list_kb, favorites_kb, vip_kb, cancel_kb,
)
from config import ADMIN_IDS, VIP_PRICE_PLN, VIP_PRICE_STARS, FREE_SEARCHES, CHANNEL_LINK

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

def _flight_text(f: dict) -> str:
    flag = _country_flag(f.get("destination", ""))
    return (
        f"✈️ <b>{f['origin_city']} → {f['dest_city']}</b> {flag}\n"
        f"💰 <b>{f['price']} {f['currency']}</b>\n"
        f"🛫 {f['airline']}\n"
        f"📅 {f['depart_at']}"
        + (f" → {f['arrive_at']}" if f.get("arrive_at") else "") + "\n"
        + (f"⏱ {f['duration']}  " if f.get("duration") else "")
        + (f"🔀 {f['stops']}" if f.get("stops") else "")
    )


def _country_flag(iata: str) -> str:
    flags = {
        "BCN": "🇪🇸", "MAD": "🇪🇸", "FCO": "🇮🇹", "MXP": "🇮🇹",
        "LTN": "🇬🇧", "LHR": "🇬🇧", "STN": "🇬🇧",
        "CDG": "🇫🇷", "ORY": "🇫🇷",
        "DXB": "🇦🇪", "AMS": "🇳🇱", "LIS": "🇵🇹",
        "ATH": "🇬🇷", "TFS": "🇪🇸", "PMI": "🇪🇸",
        "PRG": "🇨🇿", "BUD": "🇭🇺", "VIE": "🇦🇹",
        "BER": "🇩🇪", "MUC": "🇩🇪", "FRA": "🇩🇪",
        "WAW": "🇵🇱", "KRK": "🇵🇱",
    }
    return flags.get(iata.upper(), "🌍")


# ── /start ─────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    user = get_or_create_user(msg.from_user.id, msg.from_user.username or "", msg.from_user.first_name or "")
    vip_badge = " ⭐" if is_vip(msg.from_user.id) else ""
    left = searches_left(msg.from_user.id)
    await msg.answer(
        f"✈️ <b>FlightsBot{vip_badge}</b>\n\n"
        f"Нахожу самые дешёвые авиабилеты из Польши.\n\n"
        f"🔎 Поисков сегодня осталось: <b>{left if left < 999 else '∞'}</b>\n\n"
        f"Выбери действие 👇",
        reply_markup=main_menu_kb(),
    )


# ── /help ──────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📖 <b>Команды:</b>\n\n"
        "/start — главное меню\n"
        "/search — найти билет\n"
        "/hot — горящие билеты\n"
        "/alert — настроить алерт\n"
        "/alerts — мои алерты\n"
        "/favorites — избранное\n"
        "/vip — VIP подписка\n"
        "/stats — моя статистика\n\n"
        f"💬 Канал с горящими: {CHANNEL_LINK}"
    )


# ── Search flow ────────────────────────────────────────────────────────────────

@router.message(F.text == "🔎 Найти билет")
@router.message(Command("search"))
async def start_search(msg: Message, state: FSMContext):
    if not can_search(msg.from_user.id):
        await msg.answer(
            f"⚠️ Лимит поисков на сегодня исчерпан ({FREE_SEARCHES}/день).\n\n"
            f"⭐ <b>VIP</b> — безлимитный поиск за 19 zł/мес\n\n"
            f"👉 /vip",
            reply_markup=vip_kb(),
        )
        return
    await state.set_state(SearchFlight.origin)
    await msg.answer("🛫 <b>Откуда летим?</b>\n\nВыбери аэропорт:", reply_markup=origins_kb())


@router.callback_query(SearchFlight.origin, F.data.startswith("origin:"))
async def pick_origin(call: CallbackQuery, state: FSMContext):
    origin = call.data.split(":")[1]
    await state.update_data(origin=origin)
    await state.set_state(SearchFlight.destination)
    await call.message.edit_text("🛬 <b>Куда летим?</b>\n\nВыбери направление:", reply_markup=destinations_kb())


@router.callback_query(SearchFlight.destination, F.data.startswith("dest:"))
async def pick_destination(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    if parts[1] == "manual":
        await state.set_state(SearchFlight.dest_manual)
        await call.message.edit_text(
            "✏️ Введи IATA-код города назначения (например: <code>BCN</code>, <code>ROM</code>, <code>DXB</code>):",
            reply_markup=cancel_kb(),
        )
        return
    dest_code = parts[1]
    dest_city = parts[2] if len(parts) > 2 else dest_code
    await state.update_data(destination=dest_code, dest_city=dest_city)
    await state.set_state(SearchFlight.dates)
    await call.message.edit_text("📅 <b>Когда летим?</b>", reply_markup=date_range_kb())


@router.message(SearchFlight.dest_manual)
async def manual_destination(msg: Message, state: FSMContext):
    code = msg.text.strip().upper()
    if len(code) != 3 or not code.isalpha():
        await msg.answer("❌ Введи 3-буквенный IATA-код, например: <code>BCN</code>")
        return
    await state.update_data(destination=code, dest_city=code)
    await state.set_state(SearchFlight.dates)
    await msg.answer("📅 <b>Когда летим?</b>", reply_markup=date_range_kb())


@router.callback_query(SearchFlight.dates, F.data.startswith("dates:"))
async def pick_dates(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    date_from = parts[1]
    date_to = parts[2]
    data = await state.get_data()
    await state.clear()

    origin = data.get("origin", "WAW")
    destination = data.get("destination", "BCN")
    dest_city = data.get("dest_city", destination)

    await call.message.edit_text(
        f"🔍 Ищу билеты <b>{origin} → {dest_city}</b>...\n⏳ Подожди секунду"
    )

    increment_searches(call.from_user.id)
    flights = await asyncio.get_event_loop().run_in_executor(
        None, lambda: search_flights(origin, destination, date_from, date_to, limit=8)
    )

    if not flights:
        await call.message.edit_text(
            f"😔 Билеты <b>{origin} → {dest_city}</b> не найдены.\n\n"
            f"Попробуй другие даты или направление.",
            reply_markup=cancel_kb(),
        )
        return

    # Store results in state for navigation
    await state.update_data(flights=flights, idx=0)
    f = flights[0]
    await call.message.edit_text(
        _flight_text(f),
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
        await call.answer("Сессия истекла. Начни новый поиск.")
        return
    new_idx = current_idx - 1 if direction == "prev" else current_idx + 1
    new_idx = max(0, min(new_idx, len(flights) - 1))
    await state.update_data(idx=new_idx)
    f = flights[new_idx]
    await call.message.edit_text(
        _flight_text(f),
        reply_markup=flight_card_kb(f, new_idx, len(flights)),
    )


@router.callback_query(F.data == "search:new")
async def new_search(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("🛫 <b>Откуда летим?</b>", reply_markup=origins_kb())
    await state.set_state(SearchFlight.origin)


# ── Hot deals ──────────────────────────────────────────────────────────────────

@router.message(F.text == "🔥 Горящие билеты")
@router.message(Command("hot"))
async def cmd_hot(msg: Message):
    deals = get_recent_hot_deals(limit=5)
    if not deals:
        await msg.answer(
            "🔥 <b>Горящие билеты</b>\n\n"
            "Пока нет актуальных горящих предложений.\n"
            "Проверь позже — обновляем каждые 2 часа!\n\n"
            f"📢 Подпишись на канал: {CHANNEL_LINK}"
        )
        return
    await msg.answer(f"🔥 <b>Горящие билеты — {len(deals)} предложений:</b>")
    for deal in deals:
        text = (
            f"🔥 <b>{deal.get('origin', '?')} → {deal.get('destination', '?')}</b>\n"
            f"💰 <b>{deal['price']} EUR</b>\n"
            f"🛫 {deal.get('airline', '')}\n"
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
    await call.message.answer(f"🔥 Показываю все {len(deals)} горящих предложений:")
    for deal in deals:
        text = (
            f"🔥 <b>{deal.get('origin', '?')} → {deal.get('destination', '?')}</b>\n"
            f"💰 <b>{deal['price']} EUR</b>\n"
            f"🛫 {deal.get('airline', '')}"
        )
        await call.message.answer(text, reply_markup=hot_deal_kb(deal))
        await asyncio.sleep(0.2)


# ── Alerts ─────────────────────────────────────────────────────────────────────

@router.message(F.text == "🔔 Мои алерты")
@router.message(Command("alerts"))
async def cmd_alerts(msg: Message):
    alerts = get_user_alerts(msg.from_user.id)
    if not alerts:
        await msg.answer(
            "🔔 <b>Алерты</b>\n\n"
            "У тебя нет активных алертов.\n\n"
            "Алерт — это уведомление когда цена на маршрут упадёт ниже нужной суммы.\n\n"
            "Нажми ➕ чтобы добавить:",
            reply_markup=alerts_list_kb([]),
        )
        return
    await msg.answer(
        f"🔔 <b>Твои алерты ({len(alerts)}):</b>\n\nНажми на алерт чтобы удалить:",
        reply_markup=alerts_list_kb(alerts),
    )


@router.message(Command("alert"))
@router.callback_query(F.data == "alert:new")
async def start_alert(event, state: FSMContext):
    msg = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()
    await state.set_state(SetAlert.origin)
    await msg.answer("🛫 <b>Откуда?</b>\n\nВыбери аэропорт вылета:", reply_markup=origins_kb())


@router.callback_query(SetAlert.origin, F.data.startswith("origin:"))
async def alert_origin(call: CallbackQuery, state: FSMContext):
    origin = call.data.split(":")[1]
    await state.update_data(origin=origin)
    await state.set_state(SetAlert.destination)
    await call.message.edit_text("🛬 <b>Куда?</b>", reply_markup=destinations_kb())


@router.callback_query(SetAlert.destination, F.data.startswith("dest:"))
async def alert_destination(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    if parts[1] == "manual":
        await call.message.edit_text("✏️ Введи IATA-код:", reply_markup=cancel_kb())
        return
    dest = parts[1]
    await state.update_data(destination=dest)
    await state.set_state(SetAlert.price_max)
    await call.message.edit_text(
        "💰 <b>Максимальная цена (EUR)?</b>\n\n"
        "Введи число, например: <code>50</code>\n"
        "Или напиши <code>0</code> чтобы получать все предложения:",
        reply_markup=cancel_kb(),
    )


@router.message(SetAlert.price_max)
async def alert_price(msg: Message, state: FSMContext):
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
        f"Уведомлю когда найду подходящий билет 🔔",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data.startswith("alert:del:"))
async def delete_alert_cb(call: CallbackQuery):
    alert_id = int(call.data.split(":")[2])
    delete_alert(alert_id, call.from_user.id)
    alerts = get_user_alerts(call.from_user.id)
    await call.answer("🗑 Алерт удалён")
    await call.message.edit_text(
        f"🔔 <b>Твои алерты ({len(alerts)}):</b>" if alerts else "🔔 Алертов нет.",
        reply_markup=alerts_list_kb(alerts),
    )


@router.callback_query(F.data == "alert:delall")
async def delete_all_alerts(call: CallbackQuery):
    alerts = get_user_alerts(call.from_user.id)
    for a in alerts:
        delete_alert(a["id"], call.from_user.id)
    await call.answer("🗑 Все алерты удалены")
    await call.message.edit_text("🔔 Алертов нет.", reply_markup=alerts_list_kb([]))


@router.callback_query(F.data.startswith("alert:route:"))
async def alert_from_route(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    origin = parts[2]
    destination = parts[3]
    await state.update_data(origin=origin, destination=destination)
    await state.set_state(SetAlert.price_max)
    await call.message.answer(
        f"🔔 Алерт для <b>{origin} → {destination}</b>\n\n"
        f"💰 Введи максимальную цену (EUR) или <code>0</code> для любой:",
        reply_markup=cancel_kb(),
    )


# ── Favorites ──────────────────────────────────────────────────────────────────

@router.message(F.text == "❤️ Избранное")
@router.message(Command("favorites"))
async def cmd_favorites(msg: Message):
    favs = get_favorites(msg.from_user.id)
    if not favs:
        await msg.answer("❤️ <b>Избранное пусто</b>\n\nСохраняй билеты кнопкой ❤️ при поиске.")
        return
    await msg.answer(
        f"❤️ <b>Избранное ({len(favs)}):</b>",
        reply_markup=favorites_kb(favs),
    )


@router.callback_query(F.data.startswith("fav:save:"))
async def save_fav(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":")[2])
    data = await state.get_data()
    flights = data.get("flights", [])
    if not flights or idx >= len(flights):
        await call.answer("Сессия истекла", show_alert=True)
        return
    flight = flights[idx]
    saved = save_favorite(call.from_user.id, flight)
    await call.answer("❤️ Сохранено!" if saved else "Уже в избранном")


@router.callback_query(F.data.startswith("fav:open:"))
async def open_fav(call: CallbackQuery):
    fav_id = int(call.data.split(":")[2])
    favs = get_favorites(call.from_user.id)
    fav = next((f for f in favs if f["id"] == fav_id), None)
    if not fav:
        await call.answer("Не найдено")
        return
    from aiogram.types import InlineKeyboardMarkup
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    if fav.get("link"):
        builder.button(text="🛒 Купить", url=fav["link"])
    builder.button(text="🗑 Удалить", callback_data=f"fav:del:{fav_id}")
    builder.button(text="◀️ Назад", callback_data="fav:back")
    builder.adjust(2)
    await call.message.edit_text(
        f"✈️ <b>{fav['origin']} → {fav['destination']}</b>\n"
        f"💰 {fav['price']} EUR\n"
        f"🛫 {fav.get('airline', '')}\n"
        f"📅 {fav.get('depart_at', '')}",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data.startswith("fav:del:"))
async def del_fav(call: CallbackQuery):
    fav_id = int(call.data.split(":")[2])
    delete_favorite(fav_id, call.from_user.id)
    await call.answer("🗑 Удалено")
    favs = get_favorites(call.from_user.id)
    if not favs:
        await call.message.edit_text("❤️ Избранное пусто.")
        return
    await call.message.edit_text(f"❤️ <b>Избранное ({len(favs)}):</b>", reply_markup=favorites_kb(favs))


@router.callback_query(F.data == "fav:back")
async def fav_back(call: CallbackQuery):
    favs = get_favorites(call.from_user.id)
    await call.message.edit_text(
        f"❤️ <b>Избранное ({len(favs)}):</b>",
        reply_markup=favorites_kb(favs),
    )


@router.callback_query(F.data == "fav:clear")
async def fav_clear(call: CallbackQuery):
    favs = get_favorites(call.from_user.id)
    for f in favs:
        delete_favorite(f["id"], call.from_user.id)
    await call.answer("🗑 Очищено")
    await call.message.edit_text("❤️ Избранное пусто.")


# ── VIP ────────────────────────────────────────────────────────────────────────

@router.message(F.text == "⭐ VIP")
@router.message(Command("vip"))
async def cmd_vip(msg: Message):
    if is_vip(msg.from_user.id):
        await msg.answer(
            "⭐ <b>У тебя уже есть VIP!</b>\n\n"
            "✅ Безлимитный поиск\n"
            "✅ Алерты на маршруты\n"
            "✅ Уведомления о горящих билетах\n"
            "✅ Ранний доступ к акциям"
        )
        return
    await msg.answer(
        "⭐ <b>VIP подписка</b>\n\n"
        f"🔎 Бесплатно: {FREE_SEARCHES} поисков/день\n"
        f"⭐ VIP: безлимитный поиск\n\n"
        f"💰 Цена: <b>19 zł/мес</b> или <b>50 Stars</b>\n\n"
        "Выбери способ оплаты:",
        reply_markup=vip_kb(),
    )


@router.callback_query(F.data == "vip:pay:stars")
async def vip_pay_stars(call: CallbackQuery):
    await call.answer()
    await call.message.answer_invoice(
        title="⭐ VIP FlightsBot — 30 дней",
        description="Безлимитный поиск билетов + алерты на маршруты",
        payload="vip_30d",
        currency="XTR",
        prices=[LabeledPrice(label="VIP 30 дней", amount=VIP_PRICE_STARS)],
    )


@router.message(F.successful_payment)
async def successful_payment(msg: Message):
    payload = msg.successful_payment.invoice_payload
    if payload == "vip_30d":
        set_vip(msg.from_user.id, days=30)
        await msg.answer(
            "🎉 <b>VIP активирован на 30 дней!</b>\n\n"
            "✅ Безлимитный поиск\n"
            "✅ Алерты на маршруты\n\n"
            "Начни поиск: /search",
            reply_markup=main_menu_kb(),
        )


@router.message(F.pre_checkout_query)
async def pre_checkout(msg: Message):
    pass


@router.pre_checkout_query()
async def pre_checkout_query(query: PreCheckoutQuery):
    await query.answer(ok=True)


# ── Stats ──────────────────────────────────────────────────────────────────────

@router.message(F.text == "📊 Статистика")
@router.message(Command("stats"))
async def cmd_stats(msg: Message):
    left = searches_left(msg.from_user.id)
    vip_status = "⭐ VIP" if is_vip(msg.from_user.id) else "Бесплатный"
    favs = get_favorites(msg.from_user.id)
    alerts = get_user_alerts(msg.from_user.id)
    await msg.answer(
        f"📊 <b>Твоя статистика:</b>\n\n"
        f"👤 Статус: <b>{vip_status}</b>\n"
        f"🔎 Поисков сегодня осталось: <b>{left if left < 999 else '∞'}</b>\n"
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
        f"🔧 <b>Админ-панель</b>\n\n"
        f"👥 Пользователей: <b>{stats['users']}</b>\n"
        f"⭐ VIP: <b>{stats['vip']}</b>\n"
        f"🔎 Поисков всего: <b>{stats['searches']}</b>\n"
        f"🔔 Активных алертов: <b>{stats['alerts']}</b>"
    )


@router.message(Command("givevip"))
async def cmd_givevip(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("Использование: /givevip <user_id> [days]")
        return
    try:
        uid = int(parts[1])
        days = int(parts[2]) if len(parts) > 2 else 30
        set_vip(uid, days)
        await msg.answer(f"✅ VIP выдан пользователю {uid} на {days} дней")
    except ValueError:
        await msg.answer("❌ Неверный формат")


# ── Cancel / noop ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel")
async def cancel_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer("Отменено")
    await call.message.edit_text("❌ Отменено. Выбери действие:", reply_markup=None)
    await call.message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()
