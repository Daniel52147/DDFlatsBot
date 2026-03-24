from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove,
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
    get_hot_apartments, get_price_drops_today, record_user_activity,
    get_user_streak_days, get_all_user_ids, get_all_vip_user_ids,
    set_user_role, get_user_role, is_moderator,
    report_apartment, get_pending_reports, verify_apartment,
    delete_apartment, get_mod_stats, get_reported_apartments,
    get_price_stats, get_cheapest_apartments, get_apartment_by_id,
    add_user_note, get_user_notes, get_similar_apartments, get_new_today_count,
    increment_apt_views, mark_seen, get_seen_ids, record_conversion, get_conversion_stats,
)
from config import FREE_VIEWS, VIP_PRICE, DISTRICTS, ADMIN_IDS, CHANNEL_LINK, MODERATOR_IDS
from config import REFERRAL_REQUIRED, REFERRAL_REWARD_DAYS
from bot.i18n import t
from datetime import datetime

# Stars price: ~50 XTR ≈ 19 zł
VIP_STARS_PRICE = 50

router = Router()


def get_lang(user_id: int) -> str:
    """Get user language, default ru."""
    try:
        return get_user_lang(user_id) or "ru"
    except Exception:
        return "ru"


def auto_detect_lang(tg_lang: str | None) -> str:
    """Detect language from Telegram locale."""
    if not tg_lang:
        return "ru"
    code = tg_lang.lower()[:2]
    if code == "uk":
        return "uk"
    if code == "pl":
        return "pl"
    return "ru"


# ── FSM States ───────────────────────────────────────────────

class FilterState(StatesGroup):
    waiting_district = State()
    waiting_price_max = State()
    waiting_price_min = State()
    waiting_rooms = State()
    waiting_furnished = State()

class SearchState(StatesGroup):
    waiting_keyword = State()

class AlertState(StatesGroup):
    waiting_district = State()
    waiting_price_max = State()
    waiting_price_min = State()
    waiting_rooms = State()

class BroadcastState(StatesGroup):
    waiting_message = State()

class AdminInputState(StatesGroup):
    give_vip_id = State()
    give_vip_days = State()
    remove_vip_id = State()
    ban_id = State()
    unban_id = State()
    find_user_id = State()

class ReportState(StatesGroup):
    waiting_reason = State()

class DisclaimerState(StatesGroup):
    waiting_accept = State()

class OnboardingState(StatesGroup):
    waiting_district = State()
    waiting_budget = State()

class NoteState(StatesGroup):
    waiting_note = State()

class FeedbackState(StatesGroup):
    waiting_text = State()


# ── Helpers ──────────────────────────────────────────────────

def apt_text(apt: dict, lang: str = "ru") -> str:
    rooms_str = f"{apt['rooms']} комн." if apt.get("rooms") else ""
    area_str = f"{apt['area']} м²" if apt.get("area") else ""
    floor_str = f"этаж {apt['floor']}" if apt.get("floor") else ""
    details = " · ".join(filter(None, [rooms_str, area_str, floor_str]))

    verified = "✅ <b>Проверено модератором</b>\n" if apt.get("verified") else ""

    source_icons = {"OLX": "🟠", "Otodom": "🔵", "Gratka": "🟢", "Morizon": "🟣", "Adresowo": "🟡", "Domiporta": "🔴", "Lento": "🟤"}
    source_icon = source_icons.get(apt.get("source", ""), "📡")

    price = apt.get("price", 0)
    if price:
        # Price per m² if area known
        price_per_m = f" · {int(price / apt['area'])} zł/м²" if apt.get("area") and apt["area"] > 0 else ""
        price_line = f"💰 <b>{price} zł/мес</b>{price_per_m}"
    else:
        price_line = "💰 <i>Цена не указана</i>"

    lines = [
        f"{verified}🏠 <b>{apt['title']}</b>",
        price_line,
        f"📍 {apt.get('district', 'Warszawa')}",
    ]
    if details:
        lines.append(f"📐 {details}")

    drop = get_price_drop(apt["id"]) if apt.get("id") else None
    if drop:
        lines.append(f"📉 <b>Цена снижена!</b> {drop['old']} → {drop['new']} zł (−{drop['drop']} zł)")

    lines.append(f"🔗 <a href=\"{apt['link']}\">Открыть объявление</a>  {source_icon} {apt.get('source','')}")
    # Views counter — creates FOMO
    apt_views = apt.get("apt_views", 0) or 0
    if apt_views >= 3:
        lines.append(f"👁 <i>Смотрели {apt_views} раз</i>")
    lines.append(f"\n<i>⚠️ {t(lang, 'warn_check')}</i>")
    return "\n".join(lines)


def apt_keyboard(apt_id: int, lat=None, lon=None, lang: str = "ru") -> InlineKeyboardMarkup:
    row1 = [
        InlineKeyboardButton(text=t(lang, "btn_fav_add"), callback_data=f"fav_add:{apt_id}"),
        InlineKeyboardButton(text=t(lang, "btn_next"), callback_data="next"),
    ]
    row2 = [
        InlineKeyboardButton(text="👍", callback_data=f"rate:1:{apt_id}"),
        InlineKeyboardButton(text="👎", callback_data=f"rate:-1:{apt_id}"),
        InlineKeyboardButton(text="🚩", callback_data=f"report:{apt_id}"),
        InlineKeyboardButton(text="📤", callback_data=f"share:{apt_id}"),
    ]
    row3 = [
        InlineKeyboardButton(text="👁 Уже смотрел", callback_data=f"seen:{apt_id}"),
        InlineKeyboardButton(text="✅ Нашёл!", callback_data=f"found:{apt_id}"),
    ]
    rows = [row1, row2, row3]
    if lat and lon:
        rows.append([InlineKeyboardButton(
            text=t(lang, "btn_on_map"),
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
    prices = [1500, 2000, 2500, 3000, 3500, 4000, 5000, 5500, 6000]
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

    # Auto-detect language for new users
    from datetime import datetime
    created = user.get("created_at", "")
    is_new = False
    if created:
        try:
            is_new = (datetime.now() - datetime.fromisoformat(created)).seconds < 30
        except Exception:
            pass

    if is_new:
        detected_lang = auto_detect_lang(message.from_user.language_code)
        set_user_lang(message.from_user.id, detected_lang)
        lang = detected_lang
    else:
        lang = get_lang(message.from_user.id)

    # Remove any old ReplyKeyboard from previous bot versions
    await message.answer(".", reply_markup=ReplyKeyboardRemove())
    await message.delete()

    if is_new:
        kb_disc = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t(lang, "btn_accept"), callback_data="accept_disclaimer"),
        ]])
        await message.answer(
            t(lang, "disclaimer"),
            parse_mode="HTML", reply_markup=kb_disc
        )
        # Store referral for after disclaimer
        if len(args) > 1:
            await state.update_data(pending_ref=args[1])
        return

    early_adopter_msg = ""
    if user.get("vip") and user.get("vip_until"):
        from datetime import datetime
        created = user.get("created_at", "")
        if created and (datetime.now() - datetime.fromisoformat(created)).seconds < 10:
            early_adopter_msg = t(lang, "early_adopter")

    if len(args) > 1 and args[1].startswith("ref_"):
        ref_code = args[1][4:]
        rewarded = apply_referral(message.from_user.id, ref_code)
        if rewarded:
            await message.answer(t(lang, "ref_bonus"))

    # Auto VIP check on start
    reason = check_auto_vip_conditions(message.from_user.id)
    if reason == "fav10":
        early_adopter_msg += t(lang, "vip_fav10")
        user = get_or_create_user(message.from_user.id)
    elif reason == "loyal":
        early_adopter_msg += t(lang, "vip_loyal")
        user = get_or_create_user(message.from_user.id)

    # Progress bar for free users
    if not user["vip"]:
        used = user["views"]
        total = FREE_VIEWS
        filled = min(used, total)
        bar = "🟩" * filled + "⬜" * (total - filled)
        vip_badge = t(lang, "free_badge", bar=bar, used=used, total=total)
    else:
        vip_until = user.get("vip_until", "")[:10] if user.get("vip_until") else "∞"
        vip_badge = t(lang, "vip_badge", until=vip_until)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "btn_find"), callback_data="next"),
            InlineKeyboardButton(text=t(lang, "btn_filter"), callback_data="open_filter"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_favorites"), callback_data="open_favorites"),
            InlineKeyboardButton(text=t(lang, "btn_alerts"), callback_data="open_alerts"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_vip"), callback_data="open_vip"),
            InlineKeyboardButton(text=t(lang, "btn_ref"), callback_data="open_ref"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_cheap"), callback_data="open_cheap"),
            InlineKeyboardButton(text=t(lang, "btn_hot"), callback_data="open_hot"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_drops"), callback_data="open_drops"),
            InlineKeyboardButton(text=t(lang, "btn_map"), callback_data="open_map"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_notes"), callback_data="open_notes"),
            InlineKeyboardButton(text=t(lang, "btn_mystats"), callback_data="open_stats"),
        ],
        [
            InlineKeyboardButton(text="🔄 Сбросить фильтры", callback_data="reset_filters"),
        ],
    ])
    await message.answer(
        t(lang, "start_greeting", name=name, badge=vip_badge) + early_adopter_msg +
        "\n\n/menu — полное меню  |  /help — все команды",
        parse_mode="HTML",
        reply_markup=kb
    )

# ── /next ────────────────────────────────────────────────────

async def show_next_apartment(user_id: int, bot, state: FSMContext, chat_id: int):
    """Core logic for showing next apartment — used by both /next command and callbacks."""
    user = get_or_create_user(user_id)
    is_vip = bool(user["vip"])
    lang = get_lang(user_id)
    data = await state.get_data()

    if user["views"] >= FREE_VIEWS and not is_vip:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"⭐ VIP — {VIP_PRICE} zł/мес", callback_data="open_vip")
        ]])
        await bot.send_message(
            chat_id,
            t(lang, "limit_reached", limit=FREE_VIEWS),
            reply_markup=kb
        )
        return

    offset = data.get("offset", 0)
    filters = data.get("filters", {})
    seen_ids = get_seen_ids(user_id)
    apartments = get_apartments(filters=filters, offset=offset, vip=is_vip, exclude_ids=seen_ids)

    if not apartments:
        if offset > 0:
            # Wrap around — start from beginning
            await state.update_data(offset=0)
            apartments = get_apartments(filters=filters, offset=0, vip=is_vip, exclude_ids=seen_ids)
            if apartments:
                await bot.send_message(chat_id, t(lang, "wrap_around"))
            else:
                await bot.send_message(chat_id, t(lang, "no_apts"))
                return
        else:
            await bot.send_message(chat_id, t(lang, "no_apts_yet"))
            return

    apt = apartments[0]
    await state.update_data(offset=offset + 1, last_apt_id=apt["id"])
    increment_views(user_id)
    increment_apt_views(apt["id"])
    record_user_activity(user_id)

    total = count_apartments(filters, vip=is_vip)
    text = apt_text(apt, lang)
    remaining = max(0, total - offset - 1)
    if remaining > 0:
        text += t(lang, "remaining", n=remaining)

    # Warn when 1 view left before hitting limit
    views_after = user["views"] + 1
    if not is_vip and views_after == FREE_VIEWS - 1:
        text += f"\n\n⚠️ <b>Осталась 1 квартира</b> из бесплатных {FREE_VIEWS}. Потом нужен VIP."

    kb = apt_keyboard(apt["id"], lang=lang)
    # Map button: build Google Maps link from district/title
    map_url = f"https://www.google.com/maps/search/{apt.get('district','')},+Warszawa"
    kb.inline_keyboard.append([
        InlineKeyboardButton(text=t(lang, "btn_on_map"), url=map_url),
        InlineKeyboardButton(text=t(lang, "btn_note"), callback_data=f"note:{apt['id']}"),
    ])
    kb.inline_keyboard.append([
        InlineKeyboardButton(text=t(lang, "btn_similar"), callback_data=f"similar:{apt['id']}"),
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
        f"💰 <b>Шаг 2/4: Максимальная цена</b>",
        parse_mode="HTML",
        reply_markup=price_keyboard("filter_pmax")
    )
    await state.set_state(FilterState.waiting_price_max)


@router.callback_query(F.data.startswith("filter_pmax:"))
async def cb_filter_price_max(call: CallbackQuery, state: FSMContext):
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    filters = data.get("filters", {})
    if val > 0:
        filters["price_max"] = val
    await state.update_data(filters=filters)
    await call.message.edit_text(
        f"💰 Макс. цена: <b>{'без ограничений' if val == 0 else f'{val} zł'}</b>\n\n"
        f"🛏 <b>Шаг 3/4: Количество комнат</b>",
        parse_mode="HTML",
        reply_markup=rooms_keyboard("filter_rooms")
    )
    await state.set_state(FilterState.waiting_rooms)


@router.callback_query(F.data.startswith("filter_rooms:"))
async def cb_filter_rooms(call: CallbackQuery, state: FSMContext):
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    filters = data.get("filters", {})
    if val > 0:
        filters["rooms"] = val
    await state.update_data(filters=filters)
    await call.message.edit_text(
        f"🛏 Комнат: <b>{'любое' if val == 0 else val}</b>\n\n"
        f"🛋 <b>Шаг 4/4: Меблированная?</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data="filter_furn:1"),
                InlineKeyboardButton(text="❌ Нет", callback_data="filter_furn:0"),
                InlineKeyboardButton(text="🚫 Любая", callback_data="filter_furn:any"),
            ]
        ])
    )
    await state.set_state(FilterState.waiting_furnished)


@router.callback_query(F.data.startswith("filter_furn:"))
async def cb_filter_furnished(call: CallbackQuery, state: FSMContext):
    val = call.data.split(":")[1]
    data = await state.get_data()
    filters = data.get("filters", {})
    if val == "1":
        filters["furnished"] = 1
    elif val == "0":
        filters["furnished"] = 0
    # "any" — don't add filter
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
    if filters.get("furnished") == 1:
        summary.append("🛋 меблированная")
    elif filters.get("furnished") == 0:
        summary.append("🚫 без мебели")

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
        [InlineKeyboardButton(text=f"⭐ Оплатить Stars ({VIP_STARS_PRICE} XTR)", callback_data="vip_stars")],
        [InlineKeyboardButton(text=f"💳 Оплатить {VIP_PRICE} zł/мес (Revolut/BLIK)", callback_data="vip_how_to_pay")],
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


@router.callback_query(F.data == "vip_stars")
async def cb_vip_stars(call: CallbackQuery):
    await call.answer()
    from aiogram.types import LabeledPrice
    await call.bot.send_invoice(
        call.message.chat.id,
        title="VIP DDFlatsBot — 30 дней",
        description="Безлимитный просмотр, алерты, уведомления о снижении цен",
        payload="vip_30days",
        currency="XTR",
        prices=[LabeledPrice(label="VIP 30 дней", amount=VIP_STARS_PRICE)],
    )


@router.pre_checkout_query()
async def pre_checkout(query):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    set_vip(message.from_user.id, 1, days=30)
    await message.answer(
        "🎉 <b>VIP активирован на 30 дней!</b>\n\n"
        "✅ Безлимитный просмотр\n"
        "✅ Умные алерты: /alert\n"
        "✅ Подписка на районы: /subscribe\n\n"
        "Спасибо за поддержку! 🙏",
        parse_mode="HTML"
    )
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                f"💰 <b>Оплата Stars!</b>\n"
                f"👤 {message.from_user.full_name} (<code>{message.from_user.id}</code>)\n"
                f"⭐ {VIP_STARS_PRICE} XTR → VIP 30 дней",
                parse_mode="HTML"
            )
        except Exception:
            pass


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

def _admin_kb(pending_count: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
            InlineKeyboardButton(text="💎 VIP список", callback_data="admin_vip_list"),
        ],
        [
            InlineKeyboardButton(text="➕ Выдать VIP", callback_data="admin_give_vip"),
            InlineKeyboardButton(text="➖ Снять VIP", callback_data="admin_remove_vip"),
        ],
        [
            InlineKeyboardButton(text="🔍 Найти юзера", callback_data="admin_find_user"),
            InlineKeyboardButton(text="💰 Финансы", callback_data="admin_finance"),
        ],
        [
            InlineKeyboardButton(text="🚫 Забанить", callback_data="admin_ban_user"),
            InlineKeyboardButton(text="✅ Разбанить", callback_data="admin_unban_user"),
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка всем", callback_data="admin_broadcast"),
            InlineKeyboardButton(text="📢 VIP рассылка", callback_data="admin_broadcast_vip"),
        ],
        [
            InlineKeyboardButton(text="📊 Парсер", callback_data="admin_parse_stats"),
            InlineKeyboardButton(text="🔄 Запустить парсер", callback_data="admin_parse"),
        ],
        [
            InlineKeyboardButton(text=f"🚩 Жалобы ({pending_count})", callback_data="admin_reports"),
            InlineKeyboardButton(text="🗑 Очистить старые", callback_data="admin_cleanup"),
        ],
        [
            InlineKeyboardButton(text="📈 Топ рефералов", callback_data="admin_top_refs"),
            InlineKeyboardButton(text="💾 Бэкап БД", callback_data="admin_backup"),
        ],
    ])


async def _send_admin_panel(target, bot=None):
    """Send admin panel. target = Message or CallbackQuery."""
    stats = get_stats()
    last = stats["last_parse"][:16] if stats["last_parse"] != "никогда" else "никогда"
    pending_reports = get_pending_reports(limit=50)
    conv = get_conversion_stats()
    text = (
        f"🛠 <b>Админ-панель DDFlatsBot</b>\n\n"
        f"🏠 Квартир: <b>{stats['apartments']}</b> (+{stats.get('new_today',0)} сегодня)\n"
        f"👥 Пользователей: <b>{stats['users']}</b> (+{stats.get('new_users_today',0)} сегодня)\n"
        f"💎 VIP активных: <b>{stats['vip']}</b>\n"
        f"❤️ Избранных: <b>{stats['favorites']}</b>\n"
        f"📊 Активных сегодня: <b>{stats.get('active_today',0)}</b> (вчера: {stats.get('active_yesterday',0)})\n"
        f"✅ Конверсий: <b>{conv['total']}</b> (+{conv['today']} сегодня)\n"
        f"🕐 Последний парсинг: <b>{last}</b>"
    )
    kb = _admin_kb(len(pending_reports))
    from aiogram.types import Message as Msg, CallbackQuery as CQ
    if isinstance(target, Msg):
        await target.answer(text, parse_mode="HTML", reply_markup=kb)
    elif isinstance(target, CQ):
        await target.answer()
        await target.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await _send_admin_panel(message)


@router.callback_query(F.data == "admin_users")
async def cb_admin_users(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer()
    from database.db import get_conn
    conn = get_conn()
    rows = conn.execute(
        "SELECT user_id, vip, views, ref_count, created_at FROM users ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    lines = ["👥 <b>Последние 20 пользователей:</b>\n"]
    for r in rows:
        vip_mark = "💎" if r["vip"] else "🆓"
        date = r["created_at"][:10] if r["created_at"] else "?"
        lines.append(f"{vip_mark} <code>{r['user_id']}</code> · 👁{r['views']} · 👥{r['ref_count']} · {date}")
    await call.message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data == "admin_vip_list")
async def cb_admin_vip_list(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer()
    from database.db import get_conn
    conn = get_conn()
    rows = conn.execute(
        "SELECT user_id, vip_until FROM users WHERE vip=1 ORDER BY vip_until DESC"
    ).fetchall()
    conn.close()
    if not rows:
        await call.message.answer("💎 VIP пользователей нет.")
        return
    lines = [f"💎 <b>VIP пользователи ({len(rows)}):</b>\n"]
    for r in rows:
        until = r["vip_until"][:10] if r["vip_until"] else "∞"
        lines.append(f"<code>{r['user_id']}</code> — до {until}")
    await call.message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data == "admin_parse_stats")
async def cb_admin_parse_stats(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer()
    from database.db import get_conn
    conn = get_conn()
    rows = conn.execute("""
        SELECT source, SUM(count) as total, MAX(logged_at) as last
        FROM parse_log GROUP BY source ORDER BY total DESC
    """).fetchall()
    src_counts = conn.execute(
        "SELECT source, COUNT(*) as cnt FROM apartments GROUP BY source"
    ).fetchall()
    conn.close()
    lines = ["📊 <b>Статистика парсера:</b>\n"]
    for r in rows:
        last = r["last"][:16] if r["last"] else "?"
        lines.append(f"📡 <b>{r['source']}</b>: всего +{r['total']} · последний: {last}")
    lines.append("\n<b>В базе сейчас:</b>")
    for r in src_counts:
        lines.append(f"  {r['source']}: {r['cnt']} объявл.")
    await call.message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data == "admin_cleanup")
async def cb_admin_cleanup(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer("🗑 Очистка запущена...")
    from database.db import get_conn
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    conn = get_conn()
    deleted = conn.execute(
        "DELETE FROM apartments WHERE created_at < ?", (cutoff,)
    ).rowcount
    conn.commit()
    conn.close()
    await call.message.answer(f"✅ Удалено {deleted} объявлений старше 30 дней.")


@router.callback_query(F.data == "admin_broadcast_vip")
async def cb_admin_broadcast_vip(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.message.answer("✏️ Введи текст рассылки для VIP пользователей:")
    await state.update_data(broadcast_target="vip")
    await state.set_state(BroadcastState.waiting_message)
    await call.answer()


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.message.answer("✏️ Введи текст рассылки (всем пользователям):")
    await state.update_data(broadcast_target="all")
    await state.set_state(BroadcastState.waiting_message)
    await call.answer()


@router.message(BroadcastState.waiting_message)
async def broadcast_send(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    target = data.get("broadcast_target", "all")
    if target == "vip":
        user_ids = get_all_vip_user_ids()
    else:
        user_ids = get_all_user_ids()
    sent = 0
    for uid in user_ids:
        try:
            await message.bot.send_message(uid, f"📢 {message.text}", parse_mode="HTML")
            sent += 1
        except Exception:
            pass
    await state.set_state(None)
    label = "VIP" if target == "vip" else "всем"
    await message.answer(f"✅ Отправлено {sent}/{len(user_ids)} ({label})")


@router.callback_query(F.data == "admin_parse")
async def cb_admin_parse(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer("🔄 Парсер запущен!", show_alert=True)
    import threading
    from parser.scheduler import parse_all
    threading.Thread(target=parse_all, daemon=True).start()


@router.callback_query(F.data == "admin_reports")
async def cb_admin_reports(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer()
    reports = get_pending_reports(limit=10)
    if not reports:
        await call.message.answer("✅ Жалоб нет!")
        return
    await call.message.answer(f"🚩 <b>Жалобы ({len(reports)}):</b>", parse_mode="HTML")
    for r in reports:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Проверено", callback_data=f"mod_verify:{r['apartment_id']}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"mod_delete:{r['apartment_id']}"),
        ]])
        await call.message.answer(
            f"🚩 <b>Жалоба #{r['id']}</b>\n"
            f"🏠 {r.get('title','?')}\n"
            f"💰 {r.get('price','?')} zł · 📍 {r.get('district','?')}\n"
            f"📋 Причина: {r.get('reason','?')}\n"
            f"👤 От: <code>{r.get('user_id','?')}</code>\n"
            f"🔗 {r.get('link','?')}",
            parse_mode="HTML",
            reply_markup=kb
        )


@router.callback_query(F.data == "admin_top_refs")
async def cb_admin_top_refs(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer()
    leaders = get_leaderboard()
    if not leaders:
        await call.message.answer("👥 Рефералов пока нет.")
        return
    lines = ["📈 <b>Топ рефералов:</b>\n"]
    for i, l in enumerate(leaders, 1):
        lines.append(f"{i}. <code>{l['user_id']}</code> — {l['ref_count']} чел.")
    await call.message.answer("\n".join(lines), parse_mode="HTML")


# ── Admin: Give VIP ───────────────────────────────────────────

@router.callback_query(F.data == "admin_give_vip")
async def cb_admin_give_vip(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer()
    await call.message.answer("👤 Введи <b>user_id</b> которому выдать VIP:", parse_mode="HTML")
    await state.set_state(AdminInputState.give_vip_id)


@router.message(AdminInputState.give_vip_id)
async def admin_give_vip_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.text.strip().isdigit():
        await message.answer("❌ Введи числовой user_id")
        return
    await state.update_data(target_uid=int(message.text.strip()))
    await state.set_state(AdminInputState.give_vip_days)
    await message.answer("📅 Сколько дней VIP? (например: 30)")


@router.message(AdminInputState.give_vip_days)
async def admin_give_vip_days(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.text.strip().isdigit():
        await message.answer("❌ Введи число дней")
        return
    data = await state.get_data()
    uid = data["target_uid"]
    days = int(message.text.strip())
    await state.clear()
    set_vip(uid, 1, days=days)
    await message.answer(f"✅ VIP на {days} дней выдан пользователю <code>{uid}</code>", parse_mode="HTML")
    try:
        await message.bot.send_message(
            uid,
            f"🎉 <b>VIP активирован на {days} дней!</b>\n\n"
            "✅ Безлимитный просмотр\n✅ Умные алерты: /alert\n✅ Подписка на районы: /subscribe\n\nСпасибо! 🙏",
            parse_mode="HTML"
        )
    except Exception:
        pass


# ── Admin: Remove VIP ─────────────────────────────────────────

@router.callback_query(F.data == "admin_remove_vip")
async def cb_admin_remove_vip(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer()
    await call.message.answer("👤 Введи <b>user_id</b> у которого снять VIP:", parse_mode="HTML")
    await state.set_state(AdminInputState.remove_vip_id)


@router.message(AdminInputState.remove_vip_id)
async def admin_remove_vip_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.text.strip().isdigit():
        await message.answer("❌ Введи числовой user_id")
        return
    uid = int(message.text.strip())
    await state.clear()
    set_vip(uid, 0)
    await message.answer(f"✅ VIP снят с пользователя <code>{uid}</code>", parse_mode="HTML")


# ── Admin: Ban ────────────────────────────────────────────────

@router.callback_query(F.data == "admin_ban_user")
async def cb_admin_ban_user(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer()
    await call.message.answer("🚫 Введи <b>user_id</b> для блокировки:", parse_mode="HTML")
    await state.set_state(AdminInputState.ban_id)


@router.message(AdminInputState.ban_id)
async def admin_ban_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.text.strip().isdigit():
        await message.answer("❌ Введи числовой user_id")
        return
    uid = int(message.text.strip())
    await state.clear()
    from database.db import get_conn
    conn = get_conn()
    conn.execute("UPDATE users SET vip=-1 WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()
    await message.answer(f"🚫 Пользователь <code>{uid}</code> заблокирован.", parse_mode="HTML")


# ── Admin: Unban ──────────────────────────────────────────────

@router.callback_query(F.data == "admin_unban_user")
async def cb_admin_unban_user(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer()
    await call.message.answer("✅ Введи <b>user_id</b> для разблокировки:", parse_mode="HTML")
    await state.set_state(AdminInputState.unban_id)


@router.message(AdminInputState.unban_id)
async def admin_unban_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.text.strip().isdigit():
        await message.answer("❌ Введи числовой user_id")
        return
    uid = int(message.text.strip())
    await state.clear()
    from database.db import get_conn
    conn = get_conn()
    conn.execute("UPDATE users SET vip=0 WHERE user_id=? AND vip=-1", (uid,))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Пользователь <code>{uid}</code> разблокирован.", parse_mode="HTML")


# ── Admin: Find user ──────────────────────────────────────────

@router.callback_query(F.data == "admin_find_user")
async def cb_admin_find_user(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer()
    await call.message.answer("🔍 Введи <b>user_id</b> для поиска:", parse_mode="HTML")
    await state.set_state(AdminInputState.find_user_id)


@router.message(AdminInputState.find_user_id)
async def admin_find_user_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.text.strip().isdigit():
        await message.answer("❌ Введи числовой user_id")
        return
    uid = int(message.text.strip())
    await state.clear()
    from database.db import get_conn
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    fav_count = conn.execute("SELECT COUNT(*) FROM favorites WHERE user_id=?", (uid,)).fetchone()[0]
    alert_count = conn.execute("SELECT COUNT(*) FROM alerts WHERE user_id=? AND active=1", (uid,)).fetchone()[0]
    conn.close()
    if not user:
        await message.answer(f"❌ Пользователь <code>{uid}</code> не найден.", parse_mode="HTML")
        return
    vip_status = "🚫 Забанен" if user["vip"] == -1 else ("💎 VIP до " + (user["vip_until"] or "")[:10] if user["vip"] else "🆓 Бесплатный")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💎 Выдать VIP 30д", callback_data=f"admin_revoke:vip30:{uid}"),
            InlineKeyboardButton(text="➖ Снять VIP", callback_data=f"admin_revoke:novip:{uid}"),
        ],
        [
            InlineKeyboardButton(text="🚫 Забанить", callback_data=f"admin_do_ban:{uid}"),
            InlineKeyboardButton(text="✅ Разбанить", callback_data=f"admin_do_unban:{uid}"),
        ],
    ])
    await message.answer(
        f"👤 <b>Пользователь {uid}</b>\n\n"
        f"📌 Статус: {vip_status}\n"
        f"👁 Просмотров: {user['views']}\n"
        f"❤️ Избранных: {fav_count}\n"
        f"🎯 Алертов: {alert_count}\n"
        f"👥 Рефералов: {user['ref_count']}\n"
        f"🌍 Язык: {user['lang'] or 'ru'}\n"
        f"📅 Регистрация: {(user['created_at'] or '')[:10]}",
        parse_mode="HTML",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("admin_revoke:"))
async def cb_admin_revoke(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    parts = call.data.split(":")
    action, uid = parts[1], int(parts[2])
    if action == "vip30":
        set_vip(uid, 1, days=30)
        await call.answer(f"✅ VIP 30д выдан {uid}")
        try:
            await call.bot.send_message(uid, "🎉 <b>VIP активирован на 30 дней!</b>", parse_mode="HTML")
        except Exception:
            pass
    elif action == "novip":
        set_vip(uid, 0)
        await call.answer(f"✅ VIP снят с {uid}")


@router.callback_query(F.data.startswith("admin_do_ban:"))
async def cb_admin_do_ban(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    from database.db import get_conn
    conn = get_conn()
    conn.execute("UPDATE users SET vip=-1 WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()
    await call.answer(f"🚫 {uid} забанен")
    await call.message.edit_text(call.message.text + f"\n\n🚫 <b>Забанен</b>", parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_do_unban:"))
async def cb_admin_do_unban(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    uid = int(call.data.split(":")[1])
    from database.db import get_conn
    conn = get_conn()
    conn.execute("UPDATE users SET vip=0 WHERE user_id=? AND vip=-1", (uid,))
    conn.commit()
    conn.close()
    await call.answer(f"✅ {uid} разбанен")
    await call.message.edit_text(call.message.text + f"\n\n✅ <b>Разбанен</b>", parse_mode="HTML")


# ── Admin: Finance ────────────────────────────────────────────

@router.callback_query(F.data == "admin_finance")
async def cb_admin_finance(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer()
    from database.db import get_conn
    conn = get_conn()
    vip_count = conn.execute("SELECT COUNT(*) FROM users WHERE vip=1").fetchone()[0]
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    # Stars payments: count users who paid via stars (vip_until set, rough estimate)
    paid_vip = conn.execute(
        "SELECT COUNT(*) FROM users WHERE vip=1 AND vip_until IS NOT NULL"
    ).fetchone()[0]
    conn.close()
    potential = vip_count * VIP_PRICE
    await call.message.answer(
        f"💰 <b>Финансовая статистика</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"💎 VIP активных: <b>{vip_count}</b>\n"
        f"💵 Потенциальный доход: <b>{potential} zł/мес</b>\n"
        f"   ({vip_count} × {VIP_PRICE} zł)\n\n"
        f"⭐ Stars цена: <b>{VIP_STARS_PRICE} XTR</b> (~{VIP_PRICE} zł)\n\n"
        f"💳 Revolut: @d_yaromenka\n"
        f"📱 BLIK: +48 731 359 199",
        parse_mode="HTML"
    )


# ── Admin: Backup ─────────────────────────────────────────────

@router.callback_query(F.data == "admin_backup")
async def cb_admin_backup(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer("📦 Отправляю бэкап...")
    from config import DB_PATH
    import os
    if not os.path.exists(DB_PATH):
        await call.message.answer("❌ База данных не найдена.")
        return
    try:
        from aiogram.types import FSInputFile
        await call.message.answer_document(
            FSInputFile(DB_PATH, filename="Flats.db"),
            caption=f"💾 Бэкап базы данных\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
    except Exception as e:
        await call.message.answer(f"❌ Ошибка: {e}")


@router.message(Command("setvip"))
async def cmd_setvip(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    days = int(args[2]) if len(args) >= 3 and args[2].isdigit() else 30
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Использование: /setvip [user_id] [дней=30]")
        return
    target_id = int(args[1])
    set_vip(target_id, 1, days=days)
    await message.answer(f"✅ VIP на {days} дней активирован для {target_id}")
    try:
        await message.bot.send_message(
            target_id,
            f"🎉 <b>VIP активирован на {days} дней!</b>\n\n"
            "• Безлимитный просмотр\n"
            "• Умные алерты: /alert\n"
            "• Подписка на районы: /subscribe\n\nСпасибо за поддержку! 🙏",
            parse_mode="HTML"
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


@router.message(Command("userinfo"))
async def cmd_userinfo(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Использование: /userinfo [user_id]")
        return
    uid = int(args[1])
    from database.db import get_conn
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    fav_count = conn.execute("SELECT COUNT(*) FROM favorites WHERE user_id=?", (uid,)).fetchone()[0]
    alert_count = conn.execute("SELECT COUNT(*) FROM alerts WHERE user_id=? AND active=1", (uid,)).fetchone()[0]
    conn.close()
    if not user:
        await message.answer(f"❌ Пользователь {uid} не найден.")
        return
    vip_until = user["vip_until"][:10] if user["vip_until"] else "нет"
    await message.answer(
        f"👤 <b>Пользователь {uid}</b>\n\n"
        f"💎 VIP: {'да до ' + vip_until if user['vip'] else 'нет'}\n"
        f"👁 Просмотров: {user['views']}\n"
        f"❤️ Избранных: {fav_count}\n"
        f"🎯 Алертов: {alert_count}\n"
        f"👥 Рефералов: {user['ref_count']}\n"
        f"🌍 Язык: {user['lang'] or 'ru'}\n"
        f"📅 Регистрация: {(user['created_at'] or '')[:10]}\n\n"
        f"Действия:\n"
        f"/setvip {uid} 30\n"
        f"/removevip {uid}",
        parse_mode="HTML"
    )


@router.message(Command("ban"))
async def cmd_ban(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Использование: /ban [user_id]")
        return
    uid = int(args[1])
    from database.db import get_conn
    conn = get_conn()
    conn.execute("UPDATE users SET vip=-1 WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()
    await message.answer(f"🚫 Пользователь {uid} заблокирован.")


# ── Callbacks ────────────────────────────────────────────────

@router.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery, state: FSMContext):
    from bot.middleware import is_subscribed
    if await is_subscribed(call.bot, call.from_user.id):
        await call.answer("✅ Подписка подтверждена!", show_alert=True)
        await call.message.delete()
        user = get_or_create_user(call.from_user.id)
        lang = get_lang(call.from_user.id)
        name = call.from_user.first_name or "друг"
        if not user["vip"]:
            bar = "🟩" * min(user["views"], FREE_VIEWS) + "⬜" * max(0, FREE_VIEWS - user["views"])
            vip_badge = t(lang, "free_badge", bar=bar, used=user["views"], total=FREE_VIEWS)
        else:
            vip_until = user.get("vip_until", "")[:10] if user.get("vip_until") else "∞"
            vip_badge = t(lang, "vip_badge", until=vip_until)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "btn_find"), callback_data="next"),
                InlineKeyboardButton(text=t(lang, "btn_filter"), callback_data="open_filter"),
            ],
            [
                InlineKeyboardButton(text=t(lang, "btn_vip"), callback_data="open_vip"),
                InlineKeyboardButton(text=t(lang, "btn_ref"), callback_data="open_ref"),
            ],
        ])
        await call.message.answer(
            t(lang, "start_greeting", name=name, badge=vip_badge),
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
    favs = get_favorites(call.from_user.id)
    if not favs:
        await call.message.answer("❤️ Избранное пусто.\nДобавляй кнопкой под объявлением.")
        return
    await call.message.answer(f"❤️ <b>Избранное ({len(favs)}):</b>", parse_mode="HTML")
    for apt in favs[:10]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"fav_remove:{apt['id']}"),
            InlineKeyboardButton(text="🔗 Открыть", url=apt["link"]),
        ]])
        await call.message.answer(apt_text(apt), reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "open_alerts")
async def cb_open_alerts(call: CallbackQuery, state: FSMContext):
    await call.answer()
    user = get_or_create_user(call.from_user.id)
    if not user["vip"]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"⭐ VIP — {VIP_PRICE} zł/мес", callback_data="open_vip")
        ]])
        await call.message.answer(
            "🔔 <b>Умный алерт</b> — VIP функция.\n\nЗадай параметры и я напишу тебе <b>мгновенно</b> когда появится подходящая квартира.",
            parse_mode="HTML", reply_markup=kb
        )
        return
    alerts = get_user_alerts(call.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать алерт", callback_data="alert_create")],
        *[[InlineKeyboardButton(
            text=f"🗑 #{a['id']}: {a.get('district','любой')} до {a.get('price_max','∞')} zł",
            callback_data=f"alert_del:{a['id']}"
        )] for a in alerts],
    ])
    await call.message.answer(
        f"🔔 <b>Твои алерты ({len(alerts)}/5):</b>\n\nКогда появится квартира по параметрам — напишу сразу.",
        parse_mode="HTML", reply_markup=kb
    )


@router.callback_query(F.data == "open_vip")
async def cb_open_vip(call: CallbackQuery):
    await call.answer()
    # Inline version — pass user_id correctly
    user = get_or_create_user(call.from_user.id)
    if user["vip"]:
        subs = get_user_subscriptions(call.from_user.id)
        vip_until = user.get("vip_until", "")[:10] if user.get("vip_until") else "∞"
        await call.message.answer(
            f"💎 <b>VIP активен до: {vip_until}</b>\n\n"
            f"🔔 Подписки: {', '.join(subs) if subs else 'нет'}\n\n"
            f"• Алерты: /alert\n• Статистика: /mystats",
            parse_mode="HTML"
        )
        return
    ref = get_ref_stats(call.from_user.id)
    ref_count = ref.get("ref_count", 0)
    ref_progress = min(ref_count, REFERRAL_REQUIRED)
    ref_bar = "🟩" * ref_progress + "⬜" * (REFERRAL_REQUIRED - ref_progress)
    favs = get_favorites(call.from_user.id)
    fav_count = len(favs)
    fav_bar = "🟩" * min(fav_count, 10) + "⬜" * (10 - min(fav_count, 10))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐ Оплатить Stars ({VIP_STARS_PRICE} XTR)", callback_data="vip_stars")],
        [InlineKeyboardButton(text=f"💳 Оплатить {VIP_PRICE} zł/мес (Revolut/BLIK)", callback_data="vip_how_to_pay")],
        [InlineKeyboardButton(text="👥 Получить бесплатно (рефералы)", callback_data="open_ref")],
    ])
    await call.message.answer(
        f"⭐ <b>VIP — {VIP_PRICE} zł/мес</b>\n\n"
        f"✅ Безлимитный просмотр\n✅ Умные алерты\n✅ Подписка на районы\n✅ Уведомления о снижении цены\n\n"
        f"━━━━━━━━━━━━━━━━━━\n🆓 <b>Бесплатно:</b>\n\n"
        f"👥 Рефералы: {ref_bar} {ref_count}/{REFERRAL_REQUIRED}\n"
        f"❤️ Избранное: {fav_bar} {fav_count}/10",
        parse_mode="HTML", reply_markup=kb
    )


@router.callback_query(F.data == "open_ref")
async def cb_open_ref(call: CallbackQuery):
    await call.answer()
    stats = get_ref_stats(call.from_user.id)
    if not stats:
        return
    ref_code = stats["ref_code"]
    ref_count = stats["ref_count"]
    bot_me = await call.bot.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start=ref_{ref_code}"
    next_reward = REFERRAL_REQUIRED - (ref_count % REFERRAL_REQUIRED)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📤 Поделиться ссылкой", switch_inline_query=ref_link)
    ]])
    await call.message.answer(
        f"👥 <b>Пригласи друзей — получи VIP бесплатно!</b>\n\n"
        f"Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        f"👤 Приглашено: {ref_count} чел.\n"
        f"🎁 До следующего VIP: ещё {next_reward} чел.\n\n"
        f"За каждые {REFERRAL_REQUIRED} приглашённых — {REFERRAL_REWARD_DAYS} дней VIP!",
        parse_mode="HTML", reply_markup=kb
    )


@router.callback_query(F.data == "open_stats")
async def cb_open_stats(call: CallbackQuery):
    await call.answer()
    # Use call.from_user.id — not call.message (which belongs to the bot)
    user = get_or_create_user(call.from_user.id)
    subs = get_user_subscriptions(call.from_user.id)
    favs = get_favorites(call.from_user.id)
    alerts = get_user_alerts(call.from_user.id)
    ref = get_ref_stats(call.from_user.id)
    ref_count = ref.get("ref_count", 0)
    if not user["vip"]:
        used = user["views"]
        bar = "🟩" * min(used, FREE_VIEWS) + "⬜" * max(0, FREE_VIEWS - used)
        vip_line = f"🆓 {bar} {used}/{FREE_VIEWS} просмотров"
    else:
        vip_until = user.get("vip_until", "")[:10] if user.get("vip_until") else "∞"
        vip_line = f"💎 VIP до {vip_until}"
    fav_count = len(favs)
    streak = get_user_streak_days(call.from_user.id)
    streak_line = f"\n🔥 Стрик: <b>{streak} дней подряд</b>!" if streak >= 3 else (f"\n📆 Активен {streak} дн. подряд" if streak > 0 else "")
    await call.message.answer(
        f"📊 <b>Твоя статистика</b>\n\n"
        f"📌 Статус: {vip_line}\n"
        f"👁 Просмотрено: {user['views']} квартир\n"
        f"❤️ Избранное: {fav_count}\n"
        f"🔔 Подписки: {', '.join(subs) if subs else 'нет'}\n"
        f"🎯 Алертов: {len(alerts)}\n"
        f"👥 Приглашено: {ref_count} чел.\n"
        f"📅 С нами с: {user['created_at'][:10]}"
        f"{streak_line}",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "open_prices")
async def cb_open_prices(call: CallbackQuery):
    await call.answer()
    await cmd_prices(call.message)


@router.callback_query(F.data == "open_today")
async def cb_open_today(call: CallbackQuery, state: FSMContext):
    await call.answer()
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
    await call.message.answer(
        f"🆕 Сегодня добавлено <b>{count}</b> квартир!",
        parse_mode="HTML", reply_markup=kb
    )

@router.callback_query(F.data == "cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer("Отменено")
    await call.message.delete()


@router.callback_query(F.data == "reset_filters")
async def cb_reset_filters(call: CallbackQuery, state: FSMContext):
    await state.update_data(filters={}, offset=0)
    await call.answer("✅ Фильтры сброшены!", show_alert=True)


# ── Rating ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("rate:"))
async def cb_rate(call: CallbackQuery):
    parts = call.data.split(":")
    rating = int(parts[1])
    apt_id = int(parts[2])
    rate_apartment(call.from_user.id, apt_id, rating)
    emoji = "👍 Лайк!" if rating == 1 else "👎 Дизлайк"
    await call.answer(emoji)


@router.callback_query(F.data.startswith("share:"))
async def cb_share(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    apt = get_apartment_by_id(apt_id)
    if not apt:
        await call.answer("Объявление не найдено", show_alert=True)
        return
    await call.answer()
    bot_me = await call.bot.get_me()
    source_icons = {"OLX": "🟠", "Otodom": "🔵", "Gratka": "🟢", "Morizon": "🟣", "Adresowo": "🟡", "Domiporta": "🔴", "Lento": "🟤"}
    icon = source_icons.get(apt.get("source", ""), "📡")
    share_text = (
        f"🏠 <b>{apt['title']}</b>\n"
        f"💰 {apt['price']} zł/мес\n"
        f"📍 {apt.get('district', 'Warszawa')}\n"
        f"🔗 {apt['link']}\n\n"
        f"{icon} Найдено через @{bot_me.username}"
    )
    await call.message.answer(share_text, parse_mode="HTML")


@router.callback_query(F.data.startswith("seen:"))
async def cb_seen(call: CallbackQuery, state: FSMContext):
    apt_id = int(call.data.split(":")[1])
    mark_seen(call.from_user.id, apt_id)
    await call.answer("👁 Отмечено как просмотренное")
    await show_next_apartment(call.from_user.id, call.bot, state, call.message.chat.id)


@router.callback_query(F.data.startswith("found:"))
async def cb_found(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    apt = get_apartment_by_id(apt_id)
    source = apt.get("source", "") if apt else ""
    record_conversion(call.from_user.id, apt_id, source)
    await call.answer("🎉 Поздравляем!", show_alert=True)
    await call.message.answer(
        "🎉 <b>Отлично! Рады за тебя!</b>\n\n"
        "Если бот помог найти квартиру — расскажи друзьям:\n"
        "👉 /ref — пригласи друга и получи VIP бесплатно\n\n"
        "Удачи на новом месте! 🏠",
        parse_mode="HTML"
    )
    # Notify admin
    for admin_id in ADMIN_IDS:
        try:
            apt_info = f"🏠 {apt['title']} · {apt.get('price',0)} zł · {apt.get('source','')}" if apt else f"apt_id={apt_id}"
            await call.bot.send_message(
                admin_id,
                f"✅ <b>Конверсия!</b>\n"
                f"👤 <code>{call.from_user.id}</code>\n"
                f"{apt_info}",
                parse_mode="HTML"
            )
        except Exception:
            pass


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

    streak = get_user_streak_days(message.from_user.id)
    streak_line = ""
    if streak >= 3:
        streak_line = f"\n🔥 Стрик: <b>{streak} дней подряд</b>!"
    elif streak > 0:
        streak_line = f"\n📆 Активен {streak} дн. подряд"

    await message.answer(
        f"📊 <b>Твоя статистика</b>\n\n"
        f"📌 Статус: {vip_line}\n"
        f"👁 Просмотрено: {user['views']} квартир\n"
        f"❤️ Избранное: {fav_count}\n"
        f"🔔 Подписки: {', '.join(subs) if subs else 'нет'}\n"
        f"🎯 Алертов: {len(alerts)}\n"
        f"👥 Приглашено: {ref_count} чел.\n"
        f"📅 С нами с: {user['created_at'][:10]}"
        f"{streak_line}"
        f"{next_reward}",
        parse_mode="HTML"
    )


# ── /hot — горячие квартиры (много лайков за 24ч) ─────────────

@router.message(Command("hot"))
async def cmd_hot(message: Message):
    apts = get_hot_apartments(limit=5)
    if not apts:
        await message.answer(
            "🔥 Пока нет горячих квартир.\n\n"
            "Ставь 👍 под квартирами — самые популярные появятся здесь!"
        )
        return
    await message.answer("🔥 <b>Горячие квартиры (топ лайков за 24ч):</b>", parse_mode="HTML")
    for apt in apts:
        score = apt.get("hot_score", 0)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❤️ Избранное", callback_data=f"fav_add:{apt['id']}"),
            InlineKeyboardButton(text="🔗 Открыть", url=apt["link"]),
        ]])
        text = apt_text(apt) + f"\n\n🔥 {score} лайков"
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "open_hot")
async def cb_open_hot(call: CallbackQuery):
    await call.answer()
    await cmd_hot(call.message)


# ── /drops — снижение цен за 24ч ─────────────────────────────

@router.message(Command("drops"))
async def cmd_drops(message: Message):
    drops = get_price_drops_today(limit=5)
    if not drops:
        await message.answer(
            "📉 <b>Снижений цен пока нет</b>\n\n"
            "Бот отслеживает изменения цен при каждом парсинге.\n"
            "Как только цена снизится — покажу здесь.\n\n"
            "💡 Настрой алерт чтобы получать уведомления: /alert",
            parse_mode="HTML"
        )
        return
    await message.answer("📉 <b>Снижение цен за 48ч:</b>", parse_mode="HTML")
    for apt in drops:
        old = apt.get("old_price") or 0
        current = apt.get("price") or 0
        diff = int(old) - int(current) if old and current else 0
        pct = int(diff / old * 100) if old else 0
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❤️ Сохранить", callback_data=f"fav_add:{apt['id']}"),
            InlineKeyboardButton(text="🔗 Открыть", url=apt["link"]),
        ]])
        text = (
            f"📉 <b>-{diff} zł ({pct}%)</b>\n"
            f"🏠 {apt['title']}\n"
            f"💰 <s>{old} zł</s> → <b>{current} zł/мес</b>\n"
            f"📍 {apt.get('district', 'Warszawa')}"
        )
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "open_drops")
async def cb_open_drops(call: CallbackQuery):
    await call.answer()
    await cmd_drops(call.message)


# ── /compare — сравнение квартир (уникальная фича) ────────────

@router.message(Command("compare"))
async def cmd_compare(message: Message):
    favs = get_favorites(message.from_user.id)
    if len(favs) < 2:
        await message.answer(
            "📊 <b>Сравнение квартир</b>\n\n"
            "Добавь минимум 2 квартиры в избранное ❤️ и я сравню их рядом!\n\n"
            "Нажми /next чтобы смотреть квартиры.",
            parse_mode="HTML"
        )
        return

    # Compare first 3 favorites
    to_compare = favs[:3]
    lines = ["📊 <b>Сравнение квартир:</b>\n"]
    headers = ["🥇 Вариант 1", "🥈 Вариант 2", "🥉 Вариант 3"]

    for i, apt in enumerate(to_compare):
        price = apt.get("price") or "—"
        rooms = f"{apt['rooms']} комн." if apt.get("rooms") else "—"
        area = f"{apt['area']} м²" if apt.get("area") else "—"
        district = apt.get("district") or "—"
        source = apt.get("source") or "—"
        lines.append(
            f"{headers[i]}\n"
            f"🏠 {apt['title'][:40]}...\n"
            f"💰 {price} zł/мес\n"
            f"📍 {district}\n"
            f"🛏 {rooms} · 📐 {area}\n"
            f"📡 {source}\n"
            f"🔗 {apt['link']}\n"
        )

    # Highlight cheapest
    prices = [apt.get("price") or 999999 for apt in to_compare]
    min_idx = prices.index(min(prices))
    lines.append(f"✅ <b>Лучшая цена: {headers[min_idx]}</b>")

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❤️ Смотреть избранное", callback_data="open_favorites")
    ]])
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "open_compare")
async def cb_open_compare(call: CallbackQuery):
    await call.answer()
    await cmd_compare(call.message)


# ── Disclaimer accept ─────────────────────────────────────────

@router.callback_query(F.data == "accept_disclaimer")
async def cb_accept_disclaimer(call: CallbackQuery, state: FSMContext):
    await call.answer("✅ Принято!")
    data = await state.get_data()
    pending_ref = data.get("pending_ref")

    user = get_or_create_user(call.from_user.id)

    # Process referral if pending
    if pending_ref and pending_ref.startswith("ref_"):
        ref_code = pending_ref[4:]
        rewarded = apply_referral(call.from_user.id, ref_code)
        if rewarded:
            await call.message.answer("🎁 Реферальный бонус активирован! Пригласивший получил 7 дней VIP.")

    lang = get_lang(call.from_user.id)
    name = call.from_user.first_name or "друг"

    # VIP trial message
    early_msg = ""
    if user.get("vip") and user.get("vip_until"):
        vip_until = user.get("vip_until", "")[:10]
        early_msg = f"\n\n🎁 <b>Тебе активирован пробный VIP на 1 день бесплатно!</b>\nДо {vip_until} — безлимит, алерты, всё включено.\nПотом {VIP_PRICE} zł/мес — /vip"

    # Start onboarding: ask district
    await state.update_data(pending_ref=pending_ref, onboard_early_msg=early_msg)
    await state.set_state(OnboardingState.waiting_district)
    await call.message.answer(
        f"👋 Привет, <b>{name}</b>! Давай настроим поиск под тебя.\n\n"
        f"📍 <b>Шаг 1/2: Выбери район Варшавы</b>\n\n"
        f"Или нажми «Все районы» если ещё не определился:",
        parse_mode="HTML",
        reply_markup=districts_keyboard("onboard_d")
    )


@router.callback_query(F.data.startswith("onboard_d:"))
async def cb_onboard_district(call: CallbackQuery, state: FSMContext):
    district = call.data.split(":", 1)[1]
    filters = {} if district == "все" else {"district": district}
    await state.update_data(filters=filters, offset=0)
    await call.message.edit_text(
        f"📍 Район: <b>{'Все' if district == 'все' else district}</b>\n\n"
        f"💰 <b>Шаг 2/2: Максимальный бюджет</b>\n\n"
        f"Сколько готов платить в месяц?",
        parse_mode="HTML",
        reply_markup=price_keyboard("onboard_p")
    )
    await state.set_state(OnboardingState.waiting_budget)


@router.callback_query(F.data.startswith("onboard_p:"), OnboardingState.waiting_budget)
async def cb_onboard_budget(call: CallbackQuery, state: FSMContext):
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    filters = data.get("filters", {})
    if val > 0:
        filters["price_max"] = val
    await state.update_data(filters=filters, offset=0)
    await state.set_state(None)

    lang = get_lang(call.from_user.id)
    early_msg = data.get("onboard_early_msg", "")
    user = get_or_create_user(call.from_user.id)

    budget_str = f"до {val} zł" if val > 0 else "без ограничений"
    district_str = filters.get("district", "все районы")

    await call.message.edit_text(
        f"✅ <b>Отлично! Настройки сохранены:</b>\n\n"
        f"📍 Район: <b>{district_str}</b>\n"
        f"💰 Бюджет: <b>{budget_str}</b>\n\n"
        f"Показываю первую квартиру 👇"
        + early_msg,
        parse_mode="HTML"
    )
    await show_next_apartment(call.from_user.id, call.bot, state, call.message.chat.id)


# ── Report apartment ──────────────────────────────────────────

@router.callback_query(F.data.startswith("report:"))
async def cb_report_start(call: CallbackQuery, state: FSMContext):
    apt_id = int(call.data.split(":")[1])
    await state.update_data(report_apt_id=apt_id)
    await state.set_state(ReportState.waiting_reason)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🤖 Фейк/мошенник", callback_data="report_reason:fake"),
            InlineKeyboardButton(text="💸 Цена не та", callback_data="report_reason:price"),
        ],
        [
            InlineKeyboardButton(text="📷 Фото не совпадает", callback_data="report_reason:photo"),
            InlineKeyboardButton(text="🔁 Дубликат", callback_data="report_reason:duplicate"),
        ],
        [
            InlineKeyboardButton(text="🚫 Уже сдана", callback_data="report_reason:rented"),
            InlineKeyboardButton(text="❓ Другое", callback_data="report_reason:other"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])
    await call.answer()
    await call.message.answer("🚩 <b>Причина жалобы:</b>", parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("report_reason:"))
async def cb_report_reason(call: CallbackQuery, state: FSMContext):
    reason_map = {
        "fake": "Фейк/мошенник",
        "price": "Цена не соответствует",
        "photo": "Фото не совпадает",
        "duplicate": "Дубликат",
        "rented": "Уже сдана",
        "other": "Другое",
    }
    reason_key = call.data.split(":")[1]
    reason = reason_map.get(reason_key, reason_key)
    data = await state.get_data()
    apt_id = data.get("report_apt_id")
    await state.clear()

    if not apt_id:
        await call.answer("Ошибка", show_alert=True)
        return

    report_apartment(call.from_user.id, apt_id, reason)
    await call.answer("✅ Жалоба отправлена!", show_alert=True)
    await call.message.delete()

    # Re-query apt AFTER increment to get updated reported count
    from database.db import get_conn
    conn = get_conn()
    apt = conn.execute("SELECT * FROM apartments WHERE id=?", (apt_id,)).fetchone()
    conn.close()

    notify_ids = list(ADMIN_IDS) + list(MODERATOR_IDS)
    for mod_id in notify_ids:
        try:
            kb_mod = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Проверено", callback_data=f"mod_verify:{apt_id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"mod_delete:{apt_id}"),
            ]])
            apt_info = f"🏠 {apt['title']}\n💰 {apt['price']} zł\n📍 {apt['district']}\n🔗 {apt['link']}" if apt else f"ID: {apt_id}"
            await call.bot.send_message(
                mod_id,
                f"🚩 <b>Новая жалоба!</b>\n\n"
                f"{apt_info}\n\n"
                f"📋 Причина: <b>{reason}</b>\n"
                f"👤 От: <code>{call.from_user.id}</code>",
                parse_mode="HTML",
                reply_markup=kb_mod
            )
        except Exception:
            pass

    # Alert admins if apartment reaches 3+ reports
    if apt and apt["reported"] >= 3:
        for admin_id in ADMIN_IDS:
            try:
                kb_alert = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🗑 Удалить объявление", callback_data=f"mod_delete:{apt_id}"),
                    InlineKeyboardButton(text="✅ Проверено", callback_data=f"mod_verify:{apt_id}"),
                ]])
                await call.bot.send_message(
                    admin_id,
                    f"⚠️ <b>Объявление получило {apt['reported']} жалобы!</b>\n\n"
                    f"🏠 {apt['title']}\n"
                    f"💰 {apt['price']} zł · 📍 {apt['district']}\n"
                    f"🔗 {apt['link']}\n\n"
                    f"Рекомендуется проверить или удалить.",
                    parse_mode="HTML",
                    reply_markup=kb_alert
                )
            except Exception:
                pass


# ── Moderator panel ───────────────────────────────────────────

@router.message(Command("mod"))
async def cmd_mod(message: Message):
    if not is_moderator(message.from_user.id):
        return
    stats = get_mod_stats(message.from_user.id)
    reports = get_pending_reports(limit=5)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🚩 Жалобы ({len(reports)})", callback_data="mod_reports"),
            InlineKeyboardButton(text="📋 Мои действия", callback_data="mod_my_stats"),
        ],
        [
            InlineKeyboardButton(text="🔍 Проверить объявление", callback_data="mod_check"),
        ],
    ])
    await message.answer(
        f"🛡 <b>Панель модератора</b>\n\n"
        f"✅ Проверено: {stats['verified']}\n"
        f"🗑 Удалено: {stats['deleted']}\n"
        f"🚩 Ожидают проверки: {len(reports)}\n\n"
        f"Команды:\n"
        f"/modstats — моя статистика\n"
        f"/mod — эта панель",
        parse_mode="HTML",
        reply_markup=kb
    )


@router.callback_query(F.data == "mod_reports")
async def cb_mod_reports(call: CallbackQuery):
    if not is_moderator(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await call.answer()
    reports = get_pending_reports(limit=10)
    if not reports:
        await call.message.answer("✅ Жалоб нет!")
        return
    await call.message.answer(f"🚩 <b>Последние жалобы ({len(reports)}):</b>", parse_mode="HTML")
    for r in reports:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Проверено", callback_data=f"mod_verify:{r['apartment_id']}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"mod_delete:{r['apartment_id']}"),
        ]])
        await call.message.answer(
            f"🚩 <b>Жалоба #{r['id']}</b>\n"
            f"🏠 {r.get('title','?')}\n"
            f"💰 {r.get('price','?')} zł · 📍 {r.get('district','?')}\n"
            f"📋 Причина: {r.get('reason','?')}\n"
            f"🔗 {r.get('link','?')}",
            parse_mode="HTML",
            reply_markup=kb
        )


@router.callback_query(F.data == "mod_my_stats")
async def cb_mod_my_stats(call: CallbackQuery):
    if not is_moderator(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await call.answer()
    stats = get_mod_stats(call.from_user.id)
    await call.message.answer(
        f"📋 <b>Твоя статистика модератора:</b>\n\n"
        f"✅ Проверено объявлений: {stats['verified']}\n"
        f"🗑 Удалено объявлений: {stats['deleted']}",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("mod_verify:"))
async def cb_mod_verify(call: CallbackQuery):
    if not is_moderator(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    apt_id = int(call.data.split(":")[1])
    verify_apartment(apt_id, call.from_user.id)
    await call.answer("✅ Объявление проверено!")
    await call.message.edit_text(
        call.message.text + "\n\n✅ <b>Проверено модератором</b>",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("mod_delete:"))
async def cb_mod_delete(call: CallbackQuery):
    if not is_moderator(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    apt_id = int(call.data.split(":")[1])
    delete_apartment(apt_id, call.from_user.id, note="Удалено по жалобе")
    await call.answer("🗑 Объявление удалено!")
    await call.message.edit_text(
        call.message.text + "\n\n🗑 <b>Удалено</b>",
        parse_mode="HTML"
    )


# ── /setmod — admin assigns moderator ────────────────────────

@router.message(Command("setmod"))
async def cmd_setmod(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Использование: /setmod [user_id]")
        return
    uid = int(args[1])
    set_user_role(uid, "moderator")
    await message.answer(f"✅ Пользователь {uid} назначен модератором.")
    try:
        await message.bot.send_message(
            uid,
            "🛡 <b>Тебе выданы права модератора!</b>\n\n"
            "Теперь ты можешь:\n"
            "• Проверять объявления (/mod)\n"
            "• Удалять фейки\n"
            "• Получать уведомления о жалобах\n\n"
            "Используй /mod для открытия панели.",
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.message(Command("removemod"))
async def cmd_removemod(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Использование: /removemod [user_id]")
        return
    uid = int(args[1])
    set_user_role(uid, "user")
    await message.answer(f"✅ Права модератора сняты с {uid}.")


@router.callback_query(F.data == "mod_check")
async def cb_mod_check(call: CallbackQuery):
    if not is_moderator(call.from_user.id):
        await call.answer("⛔", show_alert=True)
        return
    await call.answer()
    reported = get_reported_apartments(limit=5)
    if not reported:
        await call.message.answer("✅ Нет объявлений с жалобами.")
        return
    await call.message.answer("🔍 <b>Объявления с жалобами:</b>", parse_mode="HTML")
    for apt in reported:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Проверено", callback_data=f"mod_verify:{apt['id']}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"mod_delete:{apt['id']}"),
        ]])
        await call.message.answer(
            f"🏠 {apt['title']}\n"
            f"💰 {apt.get('price','?')} zł · 📍 {apt.get('district','?')}\n"
            f"🚩 Жалоб: {apt.get('reported', 0)}\n"
            f"🔗 {apt['link']}",
            parse_mode="HTML",
            reply_markup=kb
        )


# ── /modstats ─────────────────────────────────────────────────

@router.message(Command("modstats"))
async def cmd_modstats(message: Message):
    if not is_moderator(message.from_user.id):
        return
    stats = get_mod_stats(message.from_user.id)
    reports = get_pending_reports(limit=20)
    await message.answer(
        f"📊 <b>Статистика модератора</b>\n\n"
        f"✅ Проверено: {stats['verified']}\n"
        f"🗑 Удалено: {stats['deleted']}\n"
        f"🚩 Всего жалоб в очереди: {len(reports)}\n\n"
        f"💎 <b>Плюшки модератора:</b>\n"
        f"• VIP бесплатно навсегда\n"
        f"• Доступ к панели /mod\n"
        f"• Уведомления о жалобах\n"
        f"• Значок ✅ на проверенных объявлениях",
        parse_mode="HTML"
    )


# ── /backup — admin DB download ──────────────────────────────

@router.message(Command("backup"))
async def cmd_backup(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    from config import DB_PATH
    import os
    if not os.path.exists(DB_PATH):
        await message.answer("❌ База данных не найдена.")
        return
    try:
        from aiogram.types import FSInputFile
        await message.answer_document(
            FSInputFile(DB_PATH, filename="Flats.db"),
            caption=f"💾 Резервная копия базы данных\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ── /map — интерактивная карта районов с ценами ───────────────

@router.message(Command("map"))
async def cmd_map(message: Message):
    stats = get_price_stats()
    districts = stats["by_district"]

    # Filter to Warsaw districts only (exclude suburbs/junk)
    warsaw_districts = [
        r for r in districts
        if any(w in r["district"].lower() for w in [
            "warszawa", "mokotów", "ursynów", "wilanów", "wola", "śródmieście",
            "praga", "żoliborz", "bielany", "bemowo", "ochota", "targówek",
            "białołęka", "ursus", "wesoła", "wawer", "rembertów", "włochy",
            "międzylesie", "kabaty", "natolin", "służew", "sadyba",
        ])
    ]

    if not warsaw_districts:
        await message.answer(
            "🗺 <b>Карта цен</b>\n\n"
            "Пока мало данных. Запусти парсер и подожди немного.\n\n"
            "Данные появятся после первого цикла парсинга.",
            parse_mode="HTML"
        )
        return

    lines = ["🗺 <b>Карта цен по районам Варшавы:</b>\n"]
    for r in warsaw_districts[:12]:
        avg = int(r["avg"])
        cnt = r["cnt"]
        mn = int(r["min"])
        bar = "🟢" if avg < 2500 else ("🟡" if avg < 3500 else "🔴")
        lines.append(f"{bar} <b>{r['district']}</b>\n   avg {avg} zł · от {mn} zł · {cnt} объявл.")

    if stats["overall_avg"]:
        lines.append(f"\n💰 Средняя по Варшаве: <b>{stats['overall_avg']} zł</b>")
    lines.append(f"📦 Всего объявлений: {stats['total']}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Фильтр по району", callback_data="open_filter")],
        [InlineKeyboardButton(text="💚 Самые дешёвые", callback_data="open_cheap")],
    ])
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "open_map")
async def cb_open_map(call: CallbackQuery):
    await call.answer()
    await cmd_map(call.message)


# ── /cheap — самые дешёвые прямо сейчас ──────────────────────

@router.message(Command("cheap"))
async def cmd_cheap(message: Message):
    user = get_or_create_user(message.from_user.id)
    apts = get_cheapest_apartments(limit=5, price_max=2500)
    if not apts:
        await message.answer("😔 Квартир до 2500 zł сейчас нет.\n\nПопробуй /alert — напишу как только появятся!")
        return
    await message.answer("💚 <b>Самые дешёвые прямо сейчас (до 2500 zł):</b>", parse_mode="HTML")
    for apt in apts:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❤️ Сохранить", callback_data=f"fav_add:{apt['id']}"),
            InlineKeyboardButton(text="🔗 Открыть", url=apt["link"]),
        ]])
        await message.answer(apt_text(apt), reply_markup=kb, parse_mode="HTML")


# ── /similar — похожие квартиры ───────────────────────────────

@router.callback_query(F.data.startswith("similar:"))
async def cb_similar(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    similar = get_similar_apartments(apt_id, limit=3)
    if not similar:
        await call.answer("😔 Похожих квартир не найдено", show_alert=True)
        return
    await call.answer()
    await call.message.answer("🔍 <b>Похожие квартиры:</b>", parse_mode="HTML")
    for apt in similar:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❤️ Сохранить", callback_data=f"fav_add:{apt['id']}"),
            InlineKeyboardButton(text="🔗 Открыть", url=apt["link"]),
        ]])
        await call.message.answer(apt_text(apt), reply_markup=kb, parse_mode="HTML")


# ── /note — личные заметки к квартирам ───────────────────────

@router.callback_query(F.data.startswith("note:"))
async def cb_note_start(call: CallbackQuery, state: FSMContext):
    apt_id = int(call.data.split(":")[1])
    await state.update_data(note_apt_id=apt_id)
    await state.set_state(NoteState.waiting_note)
    await call.answer()
    await call.message.answer(
        "📝 <b>Напиши заметку к этой квартире:</b>\n\n"
        "Например: «Хозяин адекватный, торговался», «Шумная улица», «Хочу посмотреть»\n\n"
        "Максимум 500 символов.",
        parse_mode="HTML"
    )


@router.message(NoteState.waiting_note)
async def note_save(message: Message, state: FSMContext):
    data = await state.get_data()
    apt_id = data.get("note_apt_id")
    await state.clear()
    if not apt_id:
        return
    add_user_note(message.from_user.id, apt_id, message.text.strip())
    await message.answer("✅ Заметка сохранена! Смотри все заметки: /notes")


@router.message(Command("notes"))
async def cmd_notes(message: Message):
    notes = get_user_notes(message.from_user.id)
    if not notes:
        await message.answer(
            "📝 <b>Заметки</b>\n\n"
            "У тебя пока нет заметок.\n"
            "Добавляй заметки к квартирам кнопкой 📝 под объявлением.",
            parse_mode="HTML"
        )
        return
    await message.answer(f"📝 <b>Твои заметки ({len(notes)}):</b>", parse_mode="HTML")
    for n in notes[:10]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔗 Открыть квартиру", url=n["link"]),
        ]])
        await message.answer(
            f"🏠 <b>{n['title'][:50]}</b>\n"
            f"💰 {n['price']} zł\n"
            f"📝 {n['note']}\n"
            f"📅 {n['created_at'][:10]}",
            parse_mode="HTML",
            reply_markup=kb
        )


# ── /feedback — обратная связь ────────────────────────────────

@router.message(Command("feedback"))
async def cmd_feedback(message: Message, state: FSMContext):
    await state.set_state(FeedbackState.waiting_text)
    await message.answer(
        "💬 <b>Обратная связь</b>\n\n"
        "Напиши что думаешь о боте, что улучшить, что не работает.\n"
        "Читаю каждое сообщение лично! 🙏",
        parse_mode="HTML"
    )


@router.message(FeedbackState.waiting_text)
async def feedback_send(message: Message, state: FSMContext):
    await state.clear()
    text = message.text.strip()
    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                f"💬 <b>Фидбек от пользователя</b>\n\n"
                f"👤 {message.from_user.full_name} (<code>{message.from_user.id}</code>)\n"
                f"📛 @{message.from_user.username or 'нет'}\n\n"
                f"💬 {text}",
                parse_mode="HTML"
            )
        except Exception:
            pass
    await message.answer(
        "✅ Спасибо! Твой отзыв отправлен.\n\n"
        "Стараемся делать бот лучше каждый день 🙏"
    )


# ── /stats — публичная статистика бота ───────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    s = get_stats()
    new_today = get_new_today_count()
    await message.answer(
        f"📊 <b>Статистика DDFlatsBot</b>\n\n"
        f"🏠 Квартир в базе: <b>{s['apartments']}</b>\n"
        f"🆕 Добавлено сегодня: <b>{new_today}</b>\n"
        f"👥 Пользователей: <b>{s['users']}</b>\n"
        f"💎 VIP подписчиков: <b>{s['vip']}</b>\n"
        f"❤️ Сохранено в избранное: <b>{s['favorites']}</b>\n"
        f"🕐 Последний парсинг: <b>{s['last_parse'][:16] if s['last_parse'] != 'никогда' else 'никогда'}</b>\n\n"
        f"📡 Источники: OLX · Otodom · Gratka · Morizon\n"
        f"⏱ Обновление каждые 10 минут",
        parse_mode="HTML"
    )


# ── Улучшенная клавиатура квартиры с новыми кнопками ─────────

def apt_keyboard_full(apt_id: int, lat=None, lon=None) -> InlineKeyboardMarkup:
    """Extended keyboard with note, similar, share buttons."""
    row1 = [
        InlineKeyboardButton(text="❤️ Сохранить", callback_data=f"fav_add:{apt_id}"),
        InlineKeyboardButton(text="➡️ Следующая", callback_data="next"),
    ]
    row2 = [
        InlineKeyboardButton(text="👍", callback_data=f"rate:1:{apt_id}"),
        InlineKeyboardButton(text="👎", callback_data=f"rate:-1:{apt_id}"),
        InlineKeyboardButton(text="📝 Заметка", callback_data=f"note:{apt_id}"),
        InlineKeyboardButton(text="🚩", callback_data=f"report:{apt_id}"),
    ]
    row3 = [
        InlineKeyboardButton(text="🔍 Похожие", callback_data=f"similar:{apt_id}"),
    ]
    rows = [row1, row2, row3]
    map_url = f"https://www.google.com/maps/search/Warszawa+mieszkanie"
    rows.append([InlineKeyboardButton(text="🗺 На карте", url=map_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── /menu — быстрое меню ──────────────────────────────────────

@router.message(Command("menu"))
async def cmd_menu(message: Message):
    user = get_or_create_user(message.from_user.id)
    vip = "💎 VIP" if user["vip"] else f"🆓 {user['views']}/{FREE_VIEWS}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏠 Квартиры", callback_data="next"),
            InlineKeyboardButton(text="🔍 Фильтры", callback_data="open_filter"),
        ],
        [
            InlineKeyboardButton(text="❤️ Избранное", callback_data="open_favorites"),
            InlineKeyboardButton(text="📝 Заметки", callback_data="open_notes"),
        ],
        [
            InlineKeyboardButton(text="🔔 Алерты", callback_data="open_alerts"),
            InlineKeyboardButton(text="🗺 Карта цен", callback_data="open_map"),
        ],
        [
            InlineKeyboardButton(text="💚 Дешёвые", callback_data="open_cheap"),
            InlineKeyboardButton(text="🔥 Горячие", callback_data="open_hot"),
        ],
        [
            InlineKeyboardButton(text="📉 Снижения", callback_data="open_drops"),
            InlineKeyboardButton(text="📊 Сравнить", callback_data="open_compare"),
        ],
        [
            InlineKeyboardButton(text="⭐ VIP", callback_data="open_vip"),
            InlineKeyboardButton(text="👥 Рефералы", callback_data="open_ref"),
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="open_stats_pub"),
            InlineKeyboardButton(text="💬 Фидбек", callback_data="open_feedback"),
        ],
    ])
    await message.answer(
        f"📋 <b>Меню DDFlatsBot</b>  {vip}\n\nВыбери раздел:",
        parse_mode="HTML",
        reply_markup=kb
    )


@router.callback_query(F.data == "open_menu")
async def cb_open_menu(call: CallbackQuery):
    await call.answer()
    await cmd_menu(call.message)


@router.callback_query(F.data == "open_notes")
async def cb_open_notes(call: CallbackQuery):
    await call.answer()
    await cmd_notes(call.message)


@router.callback_query(F.data == "open_cheap")
async def cb_open_cheap(call: CallbackQuery):
    await call.answer()
    await cmd_cheap(call.message)


@router.callback_query(F.data == "open_stats_pub")
async def cb_open_stats_pub(call: CallbackQuery):
    await call.answer()
    await cmd_stats(call.message)


@router.callback_query(F.data == "open_feedback")
async def cb_open_feedback(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await cmd_feedback(call.message, state)


@router.callback_query(F.data == "open_help")
async def cb_open_help(call: CallbackQuery):
    await call.answer()
    await cmd_help(call.message)


# ── Улучшенный /start с новыми кнопками ──────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Все команды DDFlatsBot:</b>\n\n"
        "<b>🏠 Квартиры:</b>\n"
        "/next — следующая квартира\n"
        "/filter — фильтры (район, цена, комнаты)\n"
        "/search — поиск по ключевому слову\n"
        "/today — добавлено сегодня\n"
        "/top — топ дешёвых (до 2500 zł)\n"
        "/cheap — самые дешёвые прямо сейчас\n"
        "/hot — горячие (много лайков)\n"
        "/drops — снижение цен за 24ч\n\n"
        "<b>❤️ Личное:</b>\n"
        "/favorites — избранное\n"
        "/notes — мои заметки к квартирам\n"
        "/compare — сравнить квартиры\n"
        "/mystats — моя статистика\n\n"
        "<b>🔔 Уведомления (VIP):</b>\n"
        "/alert — умный алерт\n"
        "/subscribe — подписка на район\n\n"
        "<b>📊 Аналитика:</b>\n"
        "/prices — цены по районам\n"
        "/map — карта цен\n"
        "/stats — статистика бота\n"
        "/digest — дайджест дня\n\n"
        "<b>👥 Социальное:</b>\n"
        "/ref — пригласить друга → VIP\n"
        "/leaderboard — топ рефералов\n"
        "/feedback — написать нам\n\n"
        "<b>⚙️ Настройки:</b>\n"
        "/vip — VIP подписка\n"
        "/lang — сменить язык\n"
        "/menu — быстрое меню",
        parse_mode="HTML"
    )
