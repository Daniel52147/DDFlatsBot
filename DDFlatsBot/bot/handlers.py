from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import (
    get_or_create_user, get_apartments, count_apartments, increment_views,
    add_favorite, remove_favorite, get_favorites, set_vip,
    subscribe_district, unsubscribe_district, get_user_subscriptions,
    get_stats, apply_referral, get_ref_stats,
    create_alert, get_user_alerts, delete_alert, get_price_drop,
    rate_apartment, set_user_lang, get_user_lang,
    get_leaderboard, get_daily_digest, check_auto_vip_conditions,
)
from config import FREE_VIEWS, VIP_PRICE, DISTRICTS, ADMIN_IDS, CHANNEL_LINK
from config import REFERRAL_REQUIRED, REFERRAL_REWARD_DAYS
from bot.i18n import t

router = Router()


# ── FSM States ───────────────────────────────────────────────

class FilterState(StatesGroup):
    waiting_district = State()
    waiting_price_max = State()
    waiting_price_min = State()
    waiting_rooms = State()

class SearchState(StatesGroup):
    waiting_keyword = State()

class AlertState(StatesGroup):
    waiting_district = State()
    waiting_price_max = State()
    waiting_price_min = State()
    waiting_rooms = State()

class BroadcastState(StatesGroup):
    waiting_message = State()


# ── Helpers ──────────────────────────────────────────────────

def apt_text(apt: dict) -> str:
    rooms = f"{apt['rooms']} комн." if apt.get("rooms") else ""
    area = f"{apt['area']} м²" if apt.get("area") else ""
    floor = f"этаж {apt['floor']}" if apt.get("floor") else ""
    details = " · ".join(filter(None, [rooms, area, floor]))
    lines = [
        f"🏠 <b>{apt['title']}</b>",
        f"💰 <b>{apt['price']} zł/мес</b>" if apt.get("price") else "💰 Цена не указана",
        f"📍 {apt['district']}",
    ]
    if details:
        lines.append(f"📐 {details}")
    drop = get_price_drop(apt["id"]) if apt.get("id") else None
    if drop:
        lines.append(f"📉 Цена снижена! {drop['old']} → {drop['new']} zł (-{drop['drop']} zł)")
    lines += [f"🔗 {apt['link']}", f"📡 {apt['source']}"]
    return "\n".join(lines)


def apt_keyboard(apt_id: int, lat=None, lon=None) -> InlineKeyboardMarkup:
    row1 = [
        InlineKeyboardButton(text="❤️ Избранное", callback_data=f"fav_add:{apt_id}"),
        InlineKeyboardButton(text="➡️ Следующая", callback_data="next"),
    ]
    row2 = [
        InlineKeyboardButton(text="👍", callback_data=f"rate:1:{apt_id}"),
        InlineKeyboardButton(text="👎", callback_data=f"rate:-1:{apt_id}"),
        InlineKeyboardButton(text="🗑 Пропустить", callback_data="skip"),
    ]
    rows = [row1, row2]
    if lat and lon:
        rows.append([InlineKeyboardButton(
            text="🗺 На карте",
            url=f"https://www.google.com/maps?q={lat},{lon}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def districts_keyboard(action: str = "sub") -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i, d in enumerate(DISTRICTS):
        row.append(InlineKeyboardButton(text=d, callback_data=f"{action}:{d}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🌍 Все районы", callback_data=f"{action}:все")])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def price_keyboard(action: str) -> InlineKeyboardMarkup:
    prices = [1500, 2000, 2500, 3000, 3500, 4000]
    buttons = []
    row = []
    for p in prices:
        row.append(InlineKeyboardButton(text=f"{p} zł", callback_data=f"{action}:{p}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🚫 Без ограничений", callback_data=f"{action}:0")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def rooms_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 комн.", callback_data=f"{action}:1"),
            InlineKeyboardButton(text="2 комн.", callback_data=f"{action}:2"),
            InlineKeyboardButton(text="3 комн.", callback_data=f"{action}:3"),
            InlineKeyboardButton(text="4+ комн.", callback_data=f"{action}:4"),
        ],
        [InlineKeyboardButton(text="🚫 Любое", callback_data=f"{action}:0")],
    ])


# ── /start ───────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    user = get_or_create_user(message.from_user.id)
    name = message.from_user.first_name or "друг"

    early_adopter_msg = ""
    if user.get("vip") and user.get("vip_until"):
        from datetime import datetime
        created = user.get("created_at", "")
        if created and (datetime.now() - datetime.fromisoformat(created)).seconds < 10:
            early_adopter_msg = "\n\n🎁 <b>Ты в числе первых 50!</b> Тебе активирован VIP на 7 дней бесплатно!"

    if len(args) > 1 and args[1].startswith("ref_"):
        ref_code = args[1][4:]
        rewarded = apply_referral(message.from_user.id, ref_code)
        if rewarded:
            await message.answer("🎁 Реферальный бонус активирован! Пригласивший получил 7 дней VIP.")

    # Auto VIP check on start
    reason = check_auto_vip_conditions(message.from_user.id)
    if reason == "fav10":
        early_adopter_msg += "\n\n🎁 <b>+3 дня VIP</b> за 10 сохранённых квартир!"
        user = get_or_create_user(message.from_user.id)
    elif reason == "loyal":
        early_adopter_msg += "\n\n🎁 <b>+2 дня VIP</b> за активность!"
        user = get_or_create_user(message.from_user.id)

    # Progress bar for free users
    if not user["vip"]:
        used = user["views"]
        total = FREE_VIEWS
        filled = min(used, total)
        bar = "🟩" * filled + "⬜" * (total - filled)
        vip_badge = f"🆓 {bar} {used}/{total}"
    else:
        vip_until = user.get("vip_until", "")[:10] if user.get("vip_until") else "∞"
        vip_badge = f"💎 VIP до {vip_until}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏠 Найти квартиру", callback_data="next"),
            InlineKeyboardButton(text="🔍 Фильтры", callback_data="open_filter"),
        ],
        [
            InlineKeyboardButton(text="❤️ Избранное", callback_data="open_favorites"),
            InlineKeyboardButton(text="🔔 Алерты", callback_data="open_alerts"),
        ],
        [
            InlineKeyboardButton(text="⭐ VIP доступ", callback_data="open_vip"),
            InlineKeyboardButton(text="👥 Пригласить друга", callback_data="open_ref"),
        ],
        [
            InlineKeyboardButton(text="📊 Цены по районам", callback_data="open_prices"),
            InlineKeyboardButton(text="🆕 Сегодня", callback_data="open_today"),
        ],
        [
            InlineKeyboardButton(text="🏆 Топ квартир", callback_data="open_top"),
            InlineKeyboardButton(text="📈 Лидерборд", callback_data="open_leaderboard"),
        ],
    ])
    await message.answer(
        f"👋 Привет, {name}!\n"
        f"{vip_badge}\n\n"
        f"🏙 <b>DDFlatsBot</b> — квартиры Варшавы в одном месте.\n"
        f"Парсю OLX · Otodom · Gratka · Morizon каждые 10 минут.\n\n"
        f"<b>Команды:</b>\n"
        f"/next — следующая квартира\n"
        f"/filter — фильтры\n"
        f"/today — добавлено сегодня\n"
        f"/top — топ дешёвых\n"
        f"/prices — цены по районам\n"
        f"/favorites — избранное\n"
        f"/alert — умный алерт (VIP)\n"
        f"/ref — пригласить друга → VIP\n"
        f"/vip — VIP подписка\n"
        f"/mystats — моя статистика\n"
        f"/leaderboard — топ рефералов\n"
        f"/lang — сменить язык 🌍"
        f"{early_adopter_msg}",
        parse_mode="HTML",
        reply_markup=kb
    )


# ── /next ────────────────────────────────────────────────────

async def show_next_apartment(user_id: int, bot, state: FSMContext, chat_id: int):
    """Core logic for showing next apartment — used by both /next command and callbacks."""
    user = get_or_create_user(user_id)
    is_vip = bool(user["vip"])
    data = await state.get_data()

    if user["views"] >= FREE_VIEWS and not is_vip:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"⭐ VIP — {VIP_PRICE} zł/мес", callback_data="open_vip")
        ]])
        await bot.send_message(
            chat_id,
            f"⛔ Бесплатный лимит {FREE_VIEWS} квартир исчерпан.\n\n"
            f"💎 VIP — безлимит + алерты + уведомления о снижении цены",
            reply_markup=kb
        )
        return

    offset = data.get("offset", 0)
    filters = data.get("filters", {})
    apartments = get_apartments(filters=filters, offset=offset, vip=is_vip)

    if not apartments:
        if offset > 0:
            # Wrap around — start from beginning
            await state.update_data(offset=0)
            apartments = get_apartments(filters=filters, offset=0, vip=is_vip)
            if apartments:
                await bot.send_message(chat_id, "🔄 Показываю сначала — новых квартир пока нет.")
            else:
                await bot.send_message(
                    chat_id,
                    "😔 Квартир по твоим фильтрам не найдено.\n\n"
                    "Попробуй изменить фильтры: /filter\n"
                    "Или сбрось их: /start"
                )
                return
        else:
            await bot.send_message(
                chat_id,
                "😔 Квартир пока нет. Парсер работает каждые 10 минут.\n\n"
                "Попробуй позже или измени фильтры: /filter"
            )
            return

    apt = apartments[0]
    await state.update_data(offset=offset + 1, last_apt_id=apt["id"])
    increment_views(user_id)

    total = count_apartments(filters, vip=is_vip)
    text = apt_text(apt)
    remaining = max(0, total - offset - 1)
    if remaining > 0:
        text += f"\n\n📦 Ещё {remaining} квартир по фильтрам"

    kb = apt_keyboard(apt["id"])
    # Map button: build Google Maps link from district/title
    map_url = f"https://www.google.com/maps/search/{apt.get('district','')},+Warszawa"
    kb.inline_keyboard.append([
        InlineKeyboardButton(text="🗺 На карте", url=map_url)
    ])
    if apt.get("image"):
        try:
            await bot.send_photo(chat_id, apt["image"], caption=text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass
    await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")

@router.message(Command("next"))
async def cmd_next(message: Message, state: FSMContext):
    await show_next_apartment(message.from_user.id, message.bot, state, message.chat.id)


# ── /filter ──────────────────────────────────────────────────

@router.message(Command("filter"))
async def cmd_filter(message: Message, state: FSMContext):
    await state.set_state(FilterState.waiting_district)
    await message.answer(
        "📍 <b>Шаг 1/3: Выбери район</b>",
        parse_mode="HTML",
        reply_markup=districts_keyboard("filter_d")
    )


@router.callback_query(F.data.startswith("filter_d:"))
async def cb_filter_district(call: CallbackQuery, state: FSMContext):
    district = call.data.split(":", 1)[1]
    filters = {} if district == "все" else {"district": district}
    await state.update_data(filters=filters, offset=0)
    await call.message.edit_text(
        f"📍 Район: <b>{'Все' if district == 'все' else district}</b>\n\n"
        f"💰 <b>Шаг 2/3: Максимальная цена</b>",
        parse_mode="HTML",
        reply_markup=price_keyboard("filter_pmax")
    )
    await state.set_state(FilterState.waiting_price_max)


@router.callback_query(F.data.startswith("filter_pmax:"), FilterState.waiting_price_max)
async def cb_filter_price_max(call: CallbackQuery, state: FSMContext):
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    filters = data.get("filters", {})
    if val > 0:
        filters["price_max"] = val
    await state.update_data(filters=filters)
    await call.message.edit_text(
        f"💰 Макс. цена: <b>{'без ограничений' if val == 0 else f'{val} zł'}</b>\n\n"
        f"🛏 <b>Шаг 3/3: Количество комнат</b>",
        parse_mode="HTML",
        reply_markup=rooms_keyboard("filter_rooms")
    )
    await state.set_state(FilterState.waiting_rooms)


@router.callback_query(F.data.startswith("filter_rooms:"), FilterState.waiting_rooms)
async def cb_filter_rooms(call: CallbackQuery, state: FSMContext):
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    filters = data.get("filters", {})
    if val > 0:
        filters["rooms"] = val
    await state.update_data(filters=filters, offset=0)
    await state.set_state(None)

    user = get_or_create_user(call.from_user.id)
    total = count_apartments(filters, vip=bool(user["vip"]))
    summary = []
    if filters.get("district"):
        summary.append(f"📍 {filters['district']}")
    if filters.get("price_max"):
        summary.append(f"до {filters['price_max']} zł")
    if filters.get("rooms"):
        summary.append(f"{filters['rooms']} комн.")

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏠 Смотреть квартиры", callback_data="next")
    ]])
    await call.message.edit_text(
        f"✅ <b>Фильтры установлены!</b>\n\n"
        f"{'  ·  '.join(summary) if summary else 'Все квартиры'}\n"
        f"🏠 Найдено: <b>{total}</b> квартир",
        parse_mode="HTML",
        reply_markup=kb
    )


# ── /search ──────────────────────────────────────────────────

@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext):
    args = message.text.split(maxsplit=1)
    if len(args) >= 2:
        keyword = args[1].strip()
        await state.update_data(filters={"keyword": keyword}, offset=0)
        user = get_or_create_user(message.from_user.id)
        total = count_apartments({"keyword": keyword}, vip=bool(user["vip"]))
        await message.answer(f"🔍 «{keyword}» — найдено {total}\n\nНажми /next")
    else:
        await message.answer("✏️ Введи ключевое слово:")
        await state.set_state(SearchState.waiting_keyword)


@router.message(SearchState.waiting_keyword)
async def search_keyword(message: Message, state: FSMContext):
    keyword = message.text.strip()
    await state.update_data(filters={"keyword": keyword}, offset=0)
    await state.set_state(None)
    user = get_or_create_user(message.from_user.id)
    total = count_apartments({"keyword": keyword}, vip=bool(user["vip"]))
    await message.answer(f"🔍 «{keyword}» — найдено {total}\n\nНажми /next")


# ── /alert ───────────────────────────────────────────────────

@router.message(Command("alert"))
async def cmd_alert(message: Message, state: FSMContext):
    user = get_or_create_user(message.from_user.id)
    if not user["vip"]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"⭐ VIP — {VIP_PRICE} zł/мес", callback_data="open_vip")
        ]])
        await message.answer(
            "🔔 <b>Умный алерт</b> — VIP функция.\n\n"
            "Задай параметры и я напишу тебе <b>мгновенно</b> когда появится подходящая квартира.",
            parse_mode="HTML", reply_markup=kb
        )
        return
    alerts = get_user_alerts(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать алерт", callback_data="alert_create")],
        *[[InlineKeyboardButton(
            text=f"🗑 #{a['id']}: {a.get('district','любой')} до {a.get('price_max','∞')} zł",
            callback_data=f"alert_del:{a['id']}"
        )] for a in alerts],
    ])
    await message.answer(
        f"🔔 <b>Твои алерты ({len(alerts)}/5):</b>\n\nКогда появится квартира по параметрам — напишу сразу.",
        parse_mode="HTML", reply_markup=kb
    )


@router.callback_query(F.data == "alert_create")
async def cb_alert_create(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("📍 Район для алерта:", reply_markup=districts_keyboard("alert_d"))
    await state.set_state(AlertState.waiting_district)


@router.callback_query(F.data.startswith("alert_d:"))
async def cb_alert_district(call: CallbackQuery, state: FSMContext):
    district = call.data.split(":", 1)[1]
    await state.update_data(alert_district=None if district == "все" else district)
    await call.message.edit_text(
        "💰 Максимальная цена для алерта:",
        reply_markup=price_keyboard("alert_pmax")
    )
    await state.set_state(AlertState.waiting_price_max)


@router.callback_query(F.data.startswith("alert_pmax:"), AlertState.waiting_price_max)
async def cb_alert_price_max(call: CallbackQuery, state: FSMContext):
    val = int(call.data.split(":")[1])
    await state.update_data(alert_price_max=val if val > 0 else None)
    await call.message.edit_text(
        "🛏 Количество комнат для алерта:",
        reply_markup=rooms_keyboard("alert_rooms")
    )
    await state.set_state(AlertState.waiting_rooms)


@router.callback_query(F.data.startswith("alert_rooms:"), AlertState.waiting_rooms)
async def cb_alert_rooms(call: CallbackQuery, state: FSMContext):
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    await state.set_state(None)
    create_alert(
        call.from_user.id,
        district=data.get("alert_district"),
        price_min=data.get("alert_price_min"),
        price_max=data.get("alert_price_max"),
        rooms=val if val > 0 else None,
    )
    parts = []
    if data.get("alert_district"):
        parts.append(f"📍 {data['alert_district']}")
    if data.get("alert_price_max"):
        parts.append(f"до {data['alert_price_max']} zł")
    if val > 0:
        parts.append(f"{val} комн.")
    await call.message.edit_text(
        f"✅ Алерт создан!\n{' · '.join(parts) if parts else 'Любые квартиры'}\n\n"
        f"Напишу тебе сразу как появится подходящая квартира. 🔔"
    )


@router.callback_query(F.data.startswith("alert_del:"))
async def cb_alert_del(call: CallbackQuery):
    alert_id = int(call.data.split(":")[1])
    delete_alert(alert_id, call.from_user.id)
    await call.answer("🗑 Алерт удалён")
    await call.message.delete()


# ── /ref ─────────────────────────────────────────────────────

@router.message(Command("ref"))
async def cmd_ref(message: Message):
    stats = get_ref_stats(message.from_user.id)
    if not stats:
        return
    ref_code = stats["ref_code"]
    ref_count = stats["ref_count"]
    bot_me = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start=ref_{ref_code}"
    next_reward = REFERRAL_REQUIRED - (ref_count % REFERRAL_REQUIRED)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📤 Поделиться ссылкой", switch_inline_query=ref_link)
    ]])
    await message.answer(
        f"👥 <b>Пригласи друзей — получи VIP бесплатно!</b>\n\n"
        f"Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        f"👤 Приглашено: {ref_count} чел.\n"
        f"🎁 До следующего VIP ({REFERRAL_REWARD_DAYS} дней): ещё {next_reward} чел.\n\n"
        f"За каждые {REFERRAL_REQUIRED} приглашённых — {REFERRAL_REWARD_DAYS} дней VIP бесплатно!",
        parse_mode="HTML", reply_markup=kb
    )


# ── /favorites ───────────────────────────────────────────────

@router.message(Command("favorites"))
async def cmd_favorites(message: Message):
    favs = get_favorites(message.from_user.id)
    if not favs:
        await message.answer("❤️ Избранное пусто.\nДобавляй кнопкой под объявлением.")
        return
    await message.answer(f"❤️ <b>Избранное ({len(favs)}):</b>", parse_mode="HTML")
    for apt in favs[:10]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"fav_remove:{apt['id']}"),
            InlineKeyboardButton(text="🔗 Открыть", url=apt["link"]),
        ]])
        await message.answer(apt_text(apt), reply_markup=kb, parse_mode="HTML")


# ── /vip ─────────────────────────────────────────────────────

@router.message(Command("vip"))
async def cmd_vip(message: Message):
    user = get_or_create_user(message.from_user.id)
    if user["vip"]:
        subs = get_user_subscriptions(message.from_user.id)
        vip_until = user.get("vip_until", "")[:10] if user.get("vip_until") else "∞"
        await message.answer(
            f"💎 <b>VIP активен до: {vip_until}</b>\n\n"
            f"🔔 Подписки на районы: {', '.join(subs) if subs else 'нет'}\n\n"
            f"🛠 Управление:\n"
            f"• Добавить район: /subscribe\n"
            f"• Умные алерты: /alert\n"
            f"• Статистика: /mystats",
            parse_mode="HTML"
        )
        return

    # Show progress to free VIP
    ref = get_ref_stats(message.from_user.id)
    ref_count = ref.get("ref_count", 0)
    ref_progress = min(ref_count, REFERRAL_REQUIRED)
    ref_bar = "🟩" * ref_progress + "⬜" * (REFERRAL_REQUIRED - ref_progress)

    favs = get_favorites(message.from_user.id)
    fav_count = len(favs)
    fav_progress = min(fav_count, 10)
    fav_bar = "🟩" * fav_progress + "⬜" * (10 - fav_progress)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 Оплатить {VIP_PRICE} zł/мес", callback_data="vip_how_to_pay")],
        [InlineKeyboardButton(text="👥 Получить бесплатно (рефералы)", callback_data="open_ref")],
    ])
    await message.answer(
        f"⭐ <b>VIP — {VIP_PRICE} zł/мес</b>\n\n"
        f"✅ Безлимитный просмотр квартир\n"
        f"✅ Умные алерты — мгновенно при совпадении\n"
        f"✅ Подписка на районы\n"
        f"✅ Уведомления о снижении цены\n"
        f"✅ Ежедневный дайджест\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆓 <b>Как получить бесплатно:</b>\n\n"
        f"👥 Рефералы: {ref_bar} {ref_count}/{REFERRAL_REQUIRED}\n"
        f"   → пригласи {REFERRAL_REQUIRED} друзей = {REFERRAL_REWARD_DAYS} дней VIP\n\n"
        f"❤️ Избранное: {fav_bar} {fav_count}/10\n"
        f"   → сохрани 10 квартир = 3 дня VIP автоматически\n\n"
        f"🏆 Топ-3 реферала каждый месяц = VIP навсегда",
        parse_mode="HTML", reply_markup=kb
    )


@router.callback_query(F.data == "vip_how_to_pay")
async def cb_vip_how_to_pay(call: CallbackQuery):
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Я оплатил!", callback_data="vip_request")
    ]])
    await call.message.answer(
        f"💳 <b>Как оплатить VIP ({VIP_PRICE} zł/мес):</b>\n\n"
        f"1️⃣ Переведи <b>{VIP_PRICE} zł</b> на Revolut:\n"
        f"   👉 <code>@d_yaromenka</code>\n\n"
        f"   или BLIK:\n"
        f"   👉 <code>+48 731 359 199</code>\n\n"
        f"2️⃣ В комментарии напиши свой Telegram ID:\n"
        f"   👉 <code>{call.from_user.id}</code>\n\n"
        f"3️⃣ Нажми «Я оплатил» — активирую в течение нескольких часов.\n\n"
        f"❓ Вопросы: @D_ANIEL0507",
        parse_mode="HTML", reply_markup=kb
    )


@router.callback_query(F.data == "vip_request")
async def cb_vip_request(call: CallbackQuery):
    await call.answer("✅ Запрос отправлен!")
    for admin_id in ADMIN_IDS:
        try:
            kb_admin = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Активировать VIP", callback_data=f"admin_approve:{call.from_user.id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject:{call.from_user.id}"),
            ]])
            await call.bot.send_message(
                admin_id,
                f"💳 <b>Запрос VIP</b>\n\n"
                f"👤 {call.from_user.full_name}\n"
                f"🆔 <code>{call.from_user.id}</code>\n"
                f"📛 @{call.from_user.username or 'нет'}\n\n"
                f"Проверь перевод на Revolut @d_yaromenka\nи нажми кнопку ниже:",
                parse_mode="HTML", reply_markup=kb_admin
            )
        except Exception:
            pass
    await call.message.answer(
        "✅ Запрос отправлен!\n\n"
        "Проверю оплату и активирую VIP в течение нескольких часов.\n"
        "Получишь уведомление как только VIP будет активирован. 🙏"
    )


@router.callback_query(F.data.startswith("admin_approve:"))
async def cb_admin_approve(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    target_id = int(call.data.split(":")[1])
    set_vip(target_id, 1, days=30)
    await call.answer("✅ VIP активирован!")
    await call.message.edit_text(call.message.text + "\n\n✅ <b>VIP активирован</b>", parse_mode="HTML")
    try:
        await call.bot.send_message(
            target_id,
            "🎉 <b>VIP активирован на 30 дней!</b>\n\n"
            "✅ Безлимитный просмотр\n"
            "✅ Умные алерты: /alert\n"
            "✅ Подписка на районы: /subscribe\n\n"
            "Спасибо за поддержку! 🙏",
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_reject:"))
async def cb_admin_reject(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    target_id = int(call.data.split(":")[1])
    await call.answer("❌ Отклонено")
    await call.message.edit_text(call.message.text + "\n\n❌ <b>Отклонено</b>", parse_mode="HTML")
    try:
        await call.bot.send_message(
            target_id,
            "❌ Оплата не найдена.\n\n"
            "Убедись что перевёл на Revolut <code>@d_yaromenka</code> "
            f"или BLIK <code>+48 731 359 199</code>\n"
            "и в комментарии указал свой ID.\n\nВопросы: @D_ANIEL0507",
            parse_mode="HTML"
        )
    except Exception:
        pass


# ── /today, /top, /prices ─────────────────────────────────────

@router.message(Command("today"))
async def cmd_today(message: Message, state: FSMContext):
    from datetime import date
    today = date.today().isoformat()
    from database.db import get_conn
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM apartments WHERE created_at >= ?", (today,)
    ).fetchone()[0]
    conn.close()
    await state.update_data(filters={"today": today}, offset=0)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏠 Смотреть", callback_data="next")
    ]])
    await message.answer(
        f"🆕 Сегодня добавлено <b>{count}</b> квартир!",
        parse_mode="HTML", reply_markup=kb
    )


@router.message(Command("top"))
async def cmd_top(message: Message):
    user = get_or_create_user(message.from_user.id)
    apts = get_apartments(filters={"price_max": 2500}, offset=0, limit=5, vip=bool(user["vip"]))
    if not apts:
        await message.answer("😔 Квартир до 2500 zł не найдено.")
        return
    await message.answer("🏆 <b>Топ дешёвых квартир (до 2500 zł):</b>", parse_mode="HTML")
    for apt in apts:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❤️ Избранное", callback_data=f"fav_add:{apt['id']}"),
            InlineKeyboardButton(text="🔗 Открыть", url=apt["link"]),
        ]])
        await message.answer(apt_text(apt), reply_markup=kb, parse_mode="HTML")


@router.message(Command("prices"))
async def cmd_prices(message: Message):
    from database.db import get_conn
    conn = get_conn()
    rows = conn.execute("""
        SELECT district, COUNT(*) as cnt, AVG(price) as avg_price, MIN(price) as min_price
        FROM apartments WHERE price > 0 AND district != ''
        GROUP BY district ORDER BY avg_price ASC LIMIT 12
    """).fetchall()
    conn.close()
    if not rows:
        await message.answer("📊 Пока мало данных. Подожди первого парсинга.")
        return
    lines = ["📊 <b>Средние цены по районам:</b>\n"]
    for r in rows:
        bar = "█" * min(int(r["avg_price"] / 500), 8)
        lines.append(
            f"📍 <b>{r['district']}</b> — avg {int(r['avg_price'])} zł {bar}\n"
            f"   от {r['min_price']} zł · {r['cnt']} объявл."
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


# ── /mystats ─────────────────────────────────────────────────

@router.message(Command("mystats"))
async def cmd_mystats(message: Message):
    user = get_or_create_user(message.from_user.id)
    subs = get_user_subscriptions(message.from_user.id)
    favs = get_favorites(message.from_user.id)
    alerts = get_user_alerts(message.from_user.id)
    ref = get_ref_stats(message.from_user.id)
    vip_status = "💎 VIP" if user["vip"] else f"🆓 {user['views']}/{FREE_VIEWS}"
    vip_until = user.get("vip_until", "")[:10] if user.get("vip_until") else ""
    vip_line = f"{vip_status}" + (f" (до {vip_until})" if vip_until else "")
    await message.answer(
        f"📊 <b>Твоя статистика</b>\n\n"
        f"📌 Статус: {vip_line}\n"
        f"👁 Просмотрено: {user['views']}\n"
        f"❤️ Избранное: {len(favs)}\n"
        f"🔔 Подписки: {', '.join(subs) if subs else 'нет'}\n"
        f"🎯 Алертов: {len(alerts)}\n"
        f"👥 Приглашено: {ref.get('ref_count', 0)} чел.\n"
        f"📅 С нами с: {user['created_at'][:10]}",
        parse_mode="HTML"
    )


# ── /subscribe ───────────────────────────────────────────────

@router.message(Command("subscribe"))
async def cmd_subscribe_menu(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user["vip"]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"⭐ VIP — {VIP_PRICE} zł/мес", callback_data="open_vip")
        ]])
        await message.answer(
            "🔔 Подписка на район — VIP функция.\n"
            "Получай уведомления о новых квартирах в выбранном районе.",
            reply_markup=kb
        )
        return
    subs = get_user_subscriptions(message.from_user.id)
    await message.answer(
        f"🔔 Подписки: {', '.join(subs) if subs else 'нет'}\n\nВыбери район:",
        reply_markup=districts_keyboard("sub")
    )


@router.callback_query(F.data.startswith("sub:"))
async def cb_subscribe(call: CallbackQuery):
    user = get_or_create_user(call.from_user.id)
    if not user["vip"]:
        await call.answer("💎 Только для VIP!", show_alert=True)
        return
    district = call.data.split(":", 1)[1]
    subscribe_district(call.from_user.id, district)
    await call.answer(f"✅ Подписан на {district}!")
    subs = get_user_subscriptions(call.from_user.id)
    await call.message.edit_text(
        f"🔔 Подписки: {', '.join(subs)}\n\nВыбери ещё:",
        reply_markup=districts_keyboard("sub")
    )


# ── /admin ───────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    stats = get_stats()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔄 Запустить парсер", callback_data="admin_parse")],
    ])
    last = stats["last_parse"][:16] if stats["last_parse"] != "никогда" else "никогда"
    await message.answer(
        f"🛠 <b>Админ-панель</b>\n\n"
        f"🏠 Квартир: {stats['apartments']}\n"
        f"👥 Пользователей: {stats['users']}\n"
        f"💎 VIP: {stats['vip']}\n"
        f"❤️ Избранных: {stats['favorites']}\n"
        f"🕐 Последний парсинг: {last}",
        parse_mode="HTML", reply_markup=kb
    )


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.message.answer("✏️ Введи текст рассылки:")
    await state.set_state(BroadcastState.waiting_message)
    await call.answer()


@router.message(BroadcastState.waiting_message)
async def broadcast_send(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    from database.db import get_all_user_ids
    user_ids = get_all_user_ids()
    sent = 0
    for uid in user_ids:
        try:
            await message.bot.send_message(uid, f"📢 {message.text}")
            sent += 1
        except Exception:
            pass
    await state.set_state(None)
    await message.answer(f"✅ Отправлено {sent}/{len(user_ids)}")


@router.callback_query(F.data == "admin_parse")
async def cb_admin_parse(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer("🔄 Парсер запущен!", show_alert=True)
    import threading
    from parser.scheduler import parse_all
    threading.Thread(target=parse_all, daemon=True).start()


@router.message(Command("setvip"))
async def cmd_setvip(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Использование: /setvip [user_id]")
        return
    target_id = int(args[1])
    set_vip(target_id, 1, days=30)
    await message.answer(f"✅ VIP активирован для {target_id}")
    try:
        await message.bot.send_message(
            target_id,
            "🎉 Твой VIP активирован на 30 дней!\n\n"
            "• Безлимитный просмотр\n"
            "• Умные алерты: /alert\n"
            "• Подписка на районы: /subscribe\n\nСпасибо за поддержку! 🙏"
        )
    except Exception:
        pass


@router.message(Command("removevip"))
async def cmd_removevip(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Использование: /removevip [user_id]")
        return
    set_vip(int(args[1]), 0)
    await message.answer(f"✅ VIP снят с {args[1]}")


# ── Callbacks ────────────────────────────────────────────────

@router.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery, state: FSMContext):
    from bot.middleware import is_subscribed
    if await is_subscribed(call.bot, call.from_user.id):
        await call.answer("✅ Подписка подтверждена!", show_alert=True)
        await call.message.delete()
        # Send start message
        user = get_or_create_user(call.from_user.id)
        name = call.from_user.first_name or "друг"
        vip_badge = "💎 VIP" if user["vip"] else f"🆓 {user['views']}/{FREE_VIEWS} просмотров"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🏠 Найти квартиру", callback_data="next"),
                InlineKeyboardButton(text="🔍 Фильтры", callback_data="open_filter"),
            ],
            [
                InlineKeyboardButton(text="⭐ VIP доступ", callback_data="open_vip"),
                InlineKeyboardButton(text="👥 Пригласить друга", callback_data="open_ref"),
            ],
        ])
        await call.message.answer(
            f"✅ Добро пожаловать, {name}! {vip_badge}\n\n"
            f"Нажми <b>Найти квартиру</b> чтобы начать!",
            parse_mode="HTML", reply_markup=kb
        )
    else:
        await call.answer("❌ Ты ещё не подписался на @ddflots!", show_alert=True)


@router.callback_query(F.data.startswith("fav_add:"))
async def cb_fav_add(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    add_favorite(call.from_user.id, apt_id)
    await call.answer("❤️ Добавлено в избранное!")


@router.callback_query(F.data.startswith("fav_remove:"))
async def cb_fav_remove(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    remove_favorite(call.from_user.id, apt_id)
    await call.answer("🗑 Удалено")
    await call.message.delete()


@router.callback_query(F.data == "next")
async def cb_next(call: CallbackQuery, state: FSMContext):
    await call.answer()
    # Use call.from_user.id and call.message.chat.id — NOT call.message (which is bot's message)
    await show_next_apartment(call.from_user.id, call.bot, state, call.message.chat.id)


@router.callback_query(F.data == "skip")
async def cb_skip(call: CallbackQuery, state: FSMContext):
    await call.answer("⏭ Пропущено")
    await show_next_apartment(call.from_user.id, call.bot, state, call.message.chat.id)


@router.callback_query(F.data == "open_filter")
async def cb_open_filter(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(FilterState.waiting_district)
    await call.message.answer(
        "📍 <b>Шаг 1/3: Выбери район</b>",
        parse_mode="HTML",
        reply_markup=districts_keyboard("filter_d")
    )


@router.callback_query(F.data == "open_favorites")
async def cb_open_favorites(call: CallbackQuery):
    await call.answer()
    await cmd_favorites(call.message)


@router.callback_query(F.data == "open_alerts")
async def cb_open_alerts(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await cmd_alert(call.message, state)


@router.callback_query(F.data == "open_vip")
async def cb_open_vip(call: CallbackQuery):
    await call.answer()
    await cmd_vip(call.message)


@router.callback_query(F.data == "open_ref")
async def cb_open_ref(call: CallbackQuery):
    await call.answer()
    await cmd_ref(call.message)


@router.callback_query(F.data == "open_stats")
async def cb_open_stats(call: CallbackQuery):
    await call.answer()
    await cmd_mystats(call.message)


@router.callback_query(F.data == "open_prices")
async def cb_open_prices(call: CallbackQuery):
    await call.answer()
    await cmd_prices(call.message)


@router.callback_query(F.data == "open_today")
async def cb_open_today(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await cmd_today(call.message, state)


@router.callback_query(F.data == "cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer("Отменено")
    await call.message.delete()


# ── Rating ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("rate:"))
async def cb_rate(call: CallbackQuery):
    parts = call.data.split(":")
    rating = int(parts[1])
    apt_id = int(parts[2])
    rate_apartment(call.from_user.id, apt_id, rating)
    emoji = "👍 Лайк!" if rating == 1 else "👎 Дизлайк"
    await call.answer(emoji)


# ── Language selection ────────────────────────────────────────

@router.message(Command("lang"))
async def cmd_lang(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
            InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang:uk"),
            InlineKeyboardButton(text="🇵🇱 Polski", callback_data="lang:pl"),
        ]
    ])
    await message.answer("🌍 Выбери язык / Wybierz język / Оберіть мову:", reply_markup=kb)


@router.callback_query(F.data.startswith("lang:"))
async def cb_lang(call: CallbackQuery):
    lang = call.data.split(":")[1]
    set_user_lang(call.from_user.id, lang)
    labels = {"ru": "🇷🇺 Русский", "uk": "🇺🇦 Українська", "pl": "🇵🇱 Polski"}
    await call.answer(f"✅ {labels.get(lang, lang)}", show_alert=True)
    await call.message.delete()


# ── /leaderboard ──────────────────────────────────────────────

@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message):
    leaders = get_leaderboard()
    if not leaders:
        await message.answer("🏆 Пока никто не пригласил друзей.\nБудь первым! /ref")
        return
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    lines = ["🏆 <b>Топ рефералов месяца:</b>\n"]
    for i, leader in enumerate(leaders):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        uid = leader["user_id"]
        count = leader["ref_count"]
        # Mark current user
        marker = " ← ты" if uid == message.from_user.id else ""
        lines.append(f"{medal} ID{uid} — {count} чел.{marker}")
    lines.append("\n👥 Топ-3 каждый месяц получают VIP!\n/ref — твоя реферальная ссылка")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data == "open_leaderboard")
async def cb_open_leaderboard(call: CallbackQuery):
    await call.answer()
    await cmd_leaderboard(call.message)


@router.callback_query(F.data == "open_top")
async def cb_open_top(call: CallbackQuery):
    await call.answer()
    await cmd_top(call.message)


# ── /digest — manual daily digest ────────────────────────────

@router.message(Command("digest"))
async def cmd_digest(message: Message):
    digest = get_daily_digest()
    if not digest["new_today"]:
        await message.answer("📭 Сегодня новых квартир пока нет. Парсер работает каждые 10 минут.")
        return
    text = (
        f"📰 <b>Дайджест за сегодня:</b>\n\n"
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
            f"🔗 {c['link']}"
        )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏠 Смотреть все", callback_data="open_today")
    ]])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


# ── /mystats — improved ───────────────────────────────────────

@router.message(Command("mystats"))
async def cmd_mystats(message: Message):
    user = get_or_create_user(message.from_user.id)
    subs = get_user_subscriptions(message.from_user.id)
    favs = get_favorites(message.from_user.id)
    alerts = get_user_alerts(message.from_user.id)
    ref = get_ref_stats(message.from_user.id)
    ref_count = ref.get("ref_count", 0)

    if not user["vip"]:
        used = user["views"]
        bar = "🟩" * min(used, FREE_VIEWS) + "⬜" * max(0, FREE_VIEWS - used)
        vip_line = f"🆓 {bar} {used}/{FREE_VIEWS} просмотров"
    else:
        vip_until = user.get("vip_until", "")[:10] if user.get("vip_until") else "∞"
        vip_line = f"💎 VIP до {vip_until}"

    # Progress to next auto-VIP
    fav_count = len(favs)
    next_reward = ""
    if not user["vip"]:
        if fav_count < 10:
            next_reward = f"\n\n🎯 <b>До бесплатного VIP:</b>\n❤️ Сохрани ещё {10 - fav_count} квартир → 3 дня VIP\n👥 Пригласи ещё {max(0, REFERRAL_REQUIRED - ref_count % REFERRAL_REQUIRED)} друзей → {REFERRAL_REWARD_DAYS} дней VIP"
        else:
            next_reward = "\n\n✅ Ты выполнил условие для VIP! Напиши /start"

    await message.answer(
        f"📊 <b>Твоя статистика</b>\n\n"
        f"📌 Статус: {vip_line}\n"
        f"👁 Просмотрено: {user['views']} квартир\n"
        f"❤️ Избранное: {fav_count}\n"
        f"🔔 Подписки: {', '.join(subs) if subs else 'нет'}\n"
        f"🎯 Алертов: {len(alerts)}\n"
        f"👥 Приглашено: {ref_count} чел.\n"
        f"📅 С нами с: {user['created_at'][:10]}"
        f"{next_reward}",
        parse_mode="HTML"
    )
