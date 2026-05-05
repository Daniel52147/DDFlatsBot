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
    report_apartment, get_pending_reports, verify_apartment,
    delete_apartment,
    get_cheapest_apartments, get_apartment_by_id,
    add_user_note, get_user_notes, get_similar_apartments,
    increment_apt_views, mark_seen, record_conversion, get_conversion_stats,
    get_new_since, update_last_visit, get_last_visit,
    get_apt_age_days, evaluate_price, parse_natural_query,
)
from config import FREE_VIEWS, VIP_PRICE, DISTRICTS, ADMIN_IDS, CHANNEL_LINK, CITIES
from config import REFERRAL_REQUIRED, REFERRAL_REWARD_DAYS
from bot.i18n import t
from datetime import datetime, timedelta
import urllib.parse

VIP_STARS_PRICE = 190

router = Router()

# ── Source icons ─────────────────────────────────────────────
SOURCE_ICONS = {
    "OLX": "🟠", "Otodom": "🔵", "Gratka": "🟢", "Morizon": "🟣",
    "Adresowo": "🟡", "Domiporta": "🔴", "Lento": "🟤", "Szybko": "🔷",
}


def get_lang(user_id: int) -> str:
    try:
        return get_user_lang(user_id) or "ru"
    except Exception:
        return "ru"


def auto_detect_lang(tg_lang: str | None) -> str:
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
    waiting_rooms = State()
    waiting_furnished = State()

class SearchState(StatesGroup):
    waiting_keyword = State()

class AlertState(StatesGroup):
    waiting_district = State()
    waiting_price_max = State()
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

class NoteState(StatesGroup):
    waiting_note = State()

class FeedbackState(StatesGroup):
    waiting_text = State()

class CityState(StatesGroup):
    waiting_city = State()


# ── Apartment card builder ────────────────────────────────────

def apt_text(apt: dict, lang: str = "ru") -> str:
    """Build rich apartment card text."""
    rooms_str = f"{apt['rooms']} комн." if apt.get("rooms") else ""
    area_str  = f"{apt['area']} м²" if apt.get("area") else ""
    floor_str = f"эт. {apt['floor']}" if apt.get("floor") else ""
    details   = " · ".join(filter(None, [rooms_str, area_str, floor_str]))

    verified = "✅ <b>Проверено</b>\n" if apt.get("verified") else ""
    icon = SOURCE_ICONS.get(apt.get("source", ""), "📡")

    price = apt.get("price", 0) or 0
    if price:
        ppm = f" · <i>{int(price / apt['area'])} zł/м²</i>" if apt.get("area") and apt["area"] > 0 else ""
        price_line = f"💰 <b>{price:,} zł/мес</b>{ppm}".replace(",", " ")
    else:
        price_line = "💰 <i>Цена не указана</i>"

    # Furniture tag
    furn_tag = ""
    if apt.get("furnished") == 1:
        furn_tag = " · 🛋 меблированная"
    elif apt.get("furnished") == 0:
        furn_tag = " · 🚫 без мебели"

    lines = [
        f"{verified}{icon} <b>{apt.get('title', '—')}</b>",
        price_line,
        f"📍 {apt.get('district', 'Warszawa')}",
    ]
    if details or furn_tag:
        lines.append(f"📐 {details}{furn_tag}" if details else f"📐{furn_tag}")

    # Price drop badge
    drop = get_price_drop(apt["id"]) if apt.get("id") else None
    if drop:
        lines.append(f"📉 <b>Цена снижена!</b> {drop['old']} → {drop['new']} zł (−{drop['drop']} zł)")

    # Price fairness badge
    if price and apt.get("district"):
        try:
            ev = evaluate_price(price, apt.get("district", ""), apt.get("rooms"))
            verdict_map = {
                "cheap":      "🟢 Очень дёшево",
                "below_avg":  "🟡 Ниже среднего",
                "fair":       "✅ Справедливая цена",
                "above_avg":  "🟠 Выше среднего",
                "overpriced": "🔴 Цена завышена",
            }
            if ev.get("verdict") and ev["verdict"] != "unknown" and ev.get("avg"):
                sign  = "+" if ev.get("diff_pct", 0) > 0 else ""
                badge = verdict_map.get(ev["verdict"], "")
                if badge:
                    lines.append(f"💡 {badge} ({sign}{ev['diff_pct']}% от ср. {ev['avg']} zł)")
        except Exception:
            pass

    # FOMO: views counter
    views = apt.get("apt_views", 0) or 0
    if views >= 20:
        lines.append(f"🔥 <b>Смотрели {views} раз — очень популярное!</b>")
    elif views >= 5:
        lines.append(f"👁 <i>Смотрели {views} раз</i>")

    # Stale warning
    try:
        age = get_apt_age_days(apt)
        if age >= 14:
            lines.append(f"⚠️ <i>Объявлению {age} дней — уточни актуальность.</i>")
        elif age >= 7:
            lines.append(f"🕐 <i>Объявлению {age} дней.</i>")
    except Exception:
        pass

    lines.append(f"\n🔗 <a href=\"{apt.get('link', '#')}\">Открыть объявление</a>  {icon} {apt.get('source', '')}")
    lines.append(f"\n<i>⚠️ {t(lang, 'warn_check')}</i>")
    return "\n".join(lines)


def apt_keyboard(apt_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Apartment action keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "btn_fav_add"), callback_data=f"fav_add:{apt_id}"),
            InlineKeyboardButton(text=t(lang, "btn_next"), callback_data="next"),
        ],
        [
            InlineKeyboardButton(text="👍", callback_data=f"rate:1:{apt_id}"),
            InlineKeyboardButton(text="👎", callback_data=f"rate:-1:{apt_id}"),
            InlineKeyboardButton(text=t(lang, "btn_share"), callback_data=f"share:{apt_id}"),
        ],
        [
            InlineKeyboardButton(text="👁 Уже смотрел", callback_data=f"seen:{apt_id}"),
            InlineKeyboardButton(text=t(lang, "btn_found"), callback_data=f"found:{apt_id}"),
            InlineKeyboardButton(text=t(lang, "btn_report"), callback_data=f"scam:{apt_id}"),
        ],
    ])


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
    prices = [1500, 2000, 2500, 3000, 3500, 4000, 5000, 6000, 8000]
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


def main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Main menu inline keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "btn_find"),      callback_data="next"),
            InlineKeyboardButton(text=t(lang, "btn_filter"),    callback_data="open_filter"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_favorites"), callback_data="open_favorites"),
            InlineKeyboardButton(text=t(lang, "btn_alerts"),    callback_data="open_alerts"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_hot"),       callback_data="open_hot"),
            InlineKeyboardButton(text=t(lang, "btn_drops"),     callback_data="open_drops"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_cheap"),     callback_data="open_cheap"),
            InlineKeyboardButton(text=t(lang, "btn_map"),       callback_data="open_map"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_vip"),       callback_data="open_vip"),
            InlineKeyboardButton(text=t(lang, "btn_ref"),       callback_data="open_ref"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_mystats"),   callback_data="open_stats"),
            InlineKeyboardButton(text=t(lang, "btn_daily"),     callback_data="open_daily"),
        ],
        [
            InlineKeyboardButton(text="📝 Заметки",             callback_data="open_notes"),
            InlineKeyboardButton(text="📰 Дайджест",            callback_data="open_digest"),
        ],
    ])


def city_keyboard() -> InlineKeyboardMarkup:
    """City selection keyboard."""
    rows = []
    for city_key, city_data in CITIES.items():
        rows.append([InlineKeyboardButton(
            text=city_data["label"],
            callback_data=f"city_select:{city_key}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_user_city(state_data: dict) -> str:
    """Get selected city from FSM state, default Warszawa."""
    return state_data.get("city", "Warszawa")


# ── /start ───────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    user = get_or_create_user(message.from_user.id)

    # Remove any old ReplyKeyboard silently
    try:
        rm = await message.answer(".", reply_markup=ReplyKeyboardRemove())
        await rm.delete()
    except Exception:
        pass

    # Detect new user (registered < 60s ago)
    is_new = False
    created = user.get("created_at", "")
    if created:
        try:
            is_new = (datetime.now() - datetime.fromisoformat(created)).seconds < 60
        except Exception:
            pass

    if len(args) > 1:
        await state.update_data(pending_ref=args[1])

    if is_new:
        detected = auto_detect_lang(message.from_user.language_code)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🇷🇺 Русский",    callback_data="onboard_lang:ru"),
            InlineKeyboardButton(text="🇺🇦 Українська", callback_data="onboard_lang:uk"),
            InlineKeyboardButton(text="🇵🇱 Polski",     callback_data="onboard_lang:pl"),
        ]])
        await message.answer(t(detected, "welcome_new"), parse_mode="HTML", reply_markup=kb)
        return
    await _show_main_menu(message, user)


@router.callback_query(F.data.startswith("onboard_lang:"))
async def cb_onboard_lang(call: CallbackQuery, state: FSMContext):
    lang = call.data.split(":")[1]
    set_user_lang(call.from_user.id, lang)
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_accept"),  callback_data=f"onboard_accept:{lang}")],
        [InlineKeyboardButton(text=t(lang, "btn_decline"), callback_data="onboard_decline")],
    ])
    await call.message.edit_text(t(lang, "disclaimer"), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("onboard_accept:"))
async def cb_onboard_accept(call: CallbackQuery, state: FSMContext):
    lang = call.data.split(":")[1]
    await call.answer("✅")
    # Step 2: choose city
    kb = city_keyboard()
    await call.message.edit_text(
        "🏙 <b>Выбери город для поиска квартир:</b>\n\n"
        "Каждый город — отдельная база объявлений.\n"
        "Ты сможешь сменить город в любой момент командой /city",
        parse_mode="HTML",
        reply_markup=kb
    )
    await state.update_data(onboard_lang=lang)


@router.callback_query(F.data.startswith("city_select:"))
async def cb_city_select(call: CallbackQuery, state: FSMContext):
    city = call.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("onboard_lang") or get_lang(call.from_user.id)

    # Save city in FSM state
    await state.update_data(city=city, filters={}, offset=0)

    city_label = CITIES.get(city, {}).get("label", city)

    # If coming from onboarding — show disclaimer
    if data.get("onboard_lang"):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_accept"),  callback_data=f"onboard_accept_final:{lang}")],
            [InlineKeyboardButton(text=t(lang, "btn_decline"), callback_data="onboard_decline")],
        ])
        await call.message.edit_text(
            f"✅ Город: <b>{city_label}</b>\n\n" + t(lang, "disclaimer"),
            parse_mode="HTML",
            reply_markup=kb
        )
    else:
        # City change from /city command
        await call.answer(f"✅ Город изменён на {city_label}", show_alert=True)
        try:
            await call.message.delete()
        except Exception:
            pass


@router.callback_query(F.data.startswith("onboard_accept_final:"))
async def cb_onboard_accept_final(call: CallbackQuery, state: FSMContext):
    lang = call.data.split(":")[1]
    await call.answer("✅")
    try:
        await call.message.delete()
    except Exception:
        pass

    data = await state.get_data()
    pending_ref = data.get("pending_ref", "")
    if pending_ref and pending_ref.startswith("ref_"):
        rewarded = apply_referral(call.from_user.id, pending_ref[4:])
        if rewarded:
            await call.message.answer(t(lang, "ref_bonus"))

    user = get_or_create_user(call.from_user.id)
    name = call.from_user.first_name or "друг"
    vip_badge = _vip_badge(user, lang)
    city = data.get("city", "Warszawa")
    city_label = CITIES.get(city, {}).get("label", city)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏠 Смотреть квартиры", callback_data="next"),
        InlineKeyboardButton(text="🔍 Настроить фильтры", callback_data="open_filter"),
    ]])
    await call.message.answer(
        t(lang, "start_greeting", name=name, badge=vip_badge) +
        f"\n\n📍 Город: <b>{city_label}</b>",
        parse_mode="HTML",
        reply_markup=kb
    )
    await show_next_apartment(call.from_user.id, call.bot, state, call.message.chat.id)


@router.callback_query(F.data == "onboard_decline")
async def cb_onboard_decline(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "❌ Ты отказался от условий использования.\n\nЕсли передумаешь — нажми /start снова."
    )


def _vip_badge(user: dict, lang: str) -> str:
    if user.get("vip"):
        until = (user.get("vip_until") or "")[:10] or "∞"
        return t(lang, "vip_badge", until=until)
    used = user.get("views", 0)
    bar = "🟩" * min(used, FREE_VIEWS) + "⬜" * max(0, FREE_VIEWS - used)
    return t(lang, "free_badge", bar=bar, used=used, total=FREE_VIEWS)


async def _show_main_menu(message, user: dict, from_user=None):
    fu = from_user or message.from_user
    name = fu.first_name or "друг"
    lang = get_lang(fu.id)

    # Auto-VIP check
    extra = ""
    reason = check_auto_vip_conditions(fu.id)
    if reason == "fav10":
        extra = t(lang, "vip_fav10")
        user = get_or_create_user(fu.id)
    elif reason == "loyal":
        extra = t(lang, "vip_loyal")
        user = get_or_create_user(fu.id)

    vip_badge = _vip_badge(user, lang)

    # New since last visit
    new_msg = ""
    last_visit = get_last_visit(fu.id)
    if last_visit:
        new_count = get_new_since(last_visit)
        if new_count > 0:
            new_msg = f"\n\n🆕 <b>+{new_count}</b> новых квартир с твоего последнего визита!"
    update_last_visit(fu.id)

    await message.answer(
        t(lang, "start_greeting", name=name, badge=vip_badge) + extra + new_msg,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(lang)
    )


# ── /menu ────────────────────────────────────────────────────

@router.message(Command("menu"))
async def cmd_menu(message: Message):
    lang = get_lang(message.from_user.id)
    user = get_or_create_user(message.from_user.id)
    vip_badge = _vip_badge(user, lang)
    name = message.from_user.first_name or "друг"
    await message.answer(
        t(lang, "start_greeting", name=name, badge=vip_badge),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(lang)
    )


@router.message(Command("city"))
async def cmd_city(message: Message, state: FSMContext):
    data = await state.get_data()
    current = data.get("city", "Warszawa")
    current_label = CITIES.get(current, {}).get("label", current)
    await message.answer(
        f"🏙 <b>Выбор города</b>\n\nСейчас: <b>{current_label}</b>\n\n"
        "Выбери город — квартиры будут показываться только из него:",
        parse_mode="HTML",
        reply_markup=city_keyboard()
    )


@router.callback_query(F.data == "open_menu")
async def cb_open_menu(call: CallbackQuery):
    await call.answer()
    lang = get_lang(call.from_user.id)
    user = get_or_create_user(call.from_user.id)
    vip_badge = _vip_badge(user, lang)
    name = call.from_user.first_name or "друг"
    await call.message.answer(
        t(lang, "start_greeting", name=name, badge=vip_badge),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(lang)
    )


# ── /next — show apartment ────────────────────────────────────

async def _send_no_apts(bot, chat_id: int, filters: dict, lang: str):
    """Smart 'no results' message — shows what was searched and suggests relaxing filters."""
    # Build what was searched
    parts = []
    if filters.get("district"):
        parts.append(f"📍 {filters['district']}")
    if filters.get("price_max"):
        parts.append(f"до {filters['price_max']} zł")
    if filters.get("rooms"):
        parts.append(f"{filters['rooms']} комн.")
    if filters.get("furnished") == 1:
        parts.append("🛋 меблированная")
    elif filters.get("furnished") == 0:
        parts.append("без мебели")

    # Count what's available without strict filters
    total_in_district = 0
    if filters.get("district"):
        total_in_district = count_apartments({"district": filters["district"]}, vip=True)

    total_all = count_apartments({}, vip=True)

    searched = "  ·  ".join(parts) if parts else "все квартиры"

    text = (
        f"😔 <b>По фильтрам не найдено</b>\n\n"
        f"Искал: {searched}\n\n"
    )

    if total_in_district > 0 and filters.get("district"):
        text += f"💡 В районе <b>{filters['district']}</b> есть <b>{total_in_district}</b> квартир без учёта цены/комнат.\n\n"
    elif total_all > 0:
        text += f"💡 В базе есть <b>{total_all}</b> квартир — попробуй расширить фильтры.\n\n"
    else:
        text += "⏳ База пока пустая — парсер работает каждые 10 минут.\n\n"

    text += "Что сделать:\n• Убери фильтр по комнатам или мебели\n• Увеличь максимальную цену\n• Выбери другой район"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Сбросить фильтры", callback_data="reset_filters"),
            InlineKeyboardButton(text="🔍 Изменить", callback_data="open_filter"),
        ],
        [InlineKeyboardButton(text="🏠 Все квартиры", callback_data="next")],
    ])
    await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)


async def show_next_apartment(user_id: int, bot, state: FSMContext, chat_id: int):
    user = get_or_create_user(user_id)
    is_vip = bool(user.get("vip"))
    lang = get_lang(user_id)
    data = await state.get_data()

    if user.get("views", 0) >= FREE_VIEWS and not is_vip:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ VIP — {VIP_PRICE} zł/мес", callback_data="open_vip")],
            [InlineKeyboardButton(text="👥 Получить бесплатно", callback_data="open_ref")],
        ])
        await bot.send_message(
            chat_id,
            t(lang, "limit_reached", limit=FREE_VIEWS),
            parse_mode="HTML",
            reply_markup=kb
        )
        return

    offset = data.get("offset", 0)
    filters = data.get("filters", {})

    # Apply city filter — ensures Warsaw listings don't mix with Kraków etc.
    city = data.get("city", "Warszawa")
    if city and city != "Warszawa":
        # For non-Warsaw cities, filter by city name in district field
        city_filters = {**filters, "district": city}
    else:
        city_filters = filters  # Warsaw is default, no extra filter needed

    apartments = get_apartments(filters=city_filters, offset=offset, vip=is_vip)

    if not apartments:
        if offset > 0:
            await state.update_data(offset=0)
            apartments = get_apartments(filters=city_filters, offset=0, vip=is_vip)
            if apartments:
                await bot.send_message(chat_id, t(lang, "wrap_around"))
            else:
                await _send_no_apts(bot, chat_id, city_filters, lang)
                return
        else:
            await _send_no_apts(bot, chat_id, city_filters, lang)
            return

    apt = apartments[0]
    await state.update_data(offset=offset + 1, last_apt_id=apt["id"])
    increment_views(user_id)
    increment_apt_views(apt["id"])
    record_user_activity(user_id)

    total = count_apartments(city_filters, vip=is_vip)
    text = apt_text(apt, lang)
    remaining = max(0, total - offset - 1)
    if remaining > 0:
        text += t(lang, "remaining", n=remaining)

    # Warn about approaching limit
    views_used = user.get("views", 0) + 1
    if not is_vip and views_used == FREE_VIEWS - 1:
        text += f"\n\n⚠️ <b>Осталась 1 квартира</b> из бесплатных {FREE_VIEWS}."

    kb = apt_keyboard(apt["id"], lang=lang)
    # Add map + similar buttons
    map_url = f"https://www.google.com/maps/search/{urllib.parse.quote(apt.get('district','') + ', Warszawa')}"
    kb.inline_keyboard.append([
        InlineKeyboardButton(text=t(lang, "btn_on_map"), url=map_url),
        InlineKeyboardButton(text=t(lang, "btn_similar"), callback_data=f"similar:{apt['id']}"),
    ])

    image = apt.get("image", "")
    sent = False
    if image and image.startswith("http") and len(image) > 15:
        try:
            await bot.send_photo(chat_id, image, caption=text, reply_markup=kb, parse_mode="HTML")
            sent = True
        except Exception:
            pass
    if not sent:
        await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("next"))
async def cmd_next(message: Message, state: FSMContext):
    await show_next_apartment(message.from_user.id, message.bot, state, message.chat.id)


@router.callback_query(F.data == "next")
async def cb_next(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await show_next_apartment(call.from_user.id, call.bot, state, call.message.chat.id)


@router.callback_query(F.data == "skip")
async def cb_skip(call: CallbackQuery, state: FSMContext):
    await call.answer("⏭")
    await show_next_apartment(call.from_user.id, call.bot, state, call.message.chat.id)


# ── /filter ──────────────────────────────────────────────────

@router.message(Command("filter"))
async def cmd_filter(message: Message, state: FSMContext):
    await state.set_state(FilterState.waiting_district)
    await message.answer(
        "📍 <b>Шаг 1/4: Выбери район</b>",
        parse_mode="HTML",
        reply_markup=districts_keyboard("filter_d")
    )


@router.callback_query(F.data == "open_filter")
async def cb_open_filter(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(FilterState.waiting_district)
    await call.message.answer(
        "📍 <b>Шаг 1/4: Выбери район</b>",
        parse_mode="HTML",
        reply_markup=districts_keyboard("filter_d")
    )


@router.callback_query(F.data.startswith("filter_d:"))
async def cb_filter_district(call: CallbackQuery, state: FSMContext):
    district = call.data.split(":", 1)[1]
    filters = {} if district == "все" else {"district": district}
    await state.update_data(filters=filters, offset=0)
    label = "Все районы" if district == "все" else district
    await call.message.edit_text(
        f"📍 Район: <b>{label}</b>\n\n💰 <b>Шаг 2/4: Максимальная цена</b>",
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
    label = f"{val} zł" if val else "без ограничений"
    await call.message.edit_text(
        f"💰 Макс. цена: <b>{label}</b>\n\n🛏 <b>Шаг 3/4: Количество комнат</b>",
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
    label = "любое" if val == 0 else str(val)
    await call.message.edit_text(
        f"🛏 Комнат: <b>{label}</b>\n\n🛋 <b>Шаг 4/4: Меблированная?</b>",
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
    await state.update_data(filters=filters, offset=0)
    await state.set_state(None)

    user = get_or_create_user(call.from_user.id)
    total = count_apartments(filters, vip=bool(user.get("vip")))

    parts = []
    if filters.get("district"):
        parts.append(f"📍 {filters['district']}")
    if filters.get("price_max"):
        parts.append(f"до {filters['price_max']} zł")
    if filters.get("rooms"):
        parts.append(f"{filters['rooms']} комн.")
    if filters.get("furnished") == 1:
        parts.append("🛋 меблированная")
    elif filters.get("furnished") == 0:
        parts.append("🚫 без мебели")

    summary = "  ·  ".join(parts) if parts else "Все квартиры"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🏠 Смотреть ({total})", callback_data="next")],
        [InlineKeyboardButton(text="🔄 Сбросить фильтры", callback_data="reset_filters")],
    ])
    await call.message.edit_text(
        f"✅ <b>Фильтры установлены!</b>\n\n{summary}\n🏠 Найдено: <b>{total}</b> квартир",
        parse_mode="HTML",
        reply_markup=kb
    )


@router.callback_query(F.data == "reset_filters")
async def cb_reset_filters(call: CallbackQuery, state: FSMContext):
    await state.update_data(filters={}, offset=0)
    await call.answer("✅ Фильтры сброшены!", show_alert=True)


# ── /ask — natural language search ───────────────────────────

@router.message(Command("ask"))
async def cmd_ask(message: Message, state: FSMContext):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "🤖 <b>Умный поиск</b>\n\n"
            "Напиши что ищешь:\n\n"
            "• <code>/ask 2 комнаты Мокотув до 3000</code>\n"
            "• <code>/ask однушка в центре до 2500 zł</code>\n"
            "• <code>/ask studio Wola 2000</code>\n"
            "• <code>/ask 3 pokoje Ursynów meblowane</code>",
            parse_mode="HTML"
        )
        return

    query = args[1].strip()
    try:
        filters = parse_natural_query(query)
    except Exception:
        filters = {}

    if not filters:
        await message.answer(
            "😔 Не смог распознать параметры.\n\n"
            "Попробуй: <code>/ask 2 комнаты Мокотув до 3000</code>",
            parse_mode="HTML"
        )
        return

    user = get_or_create_user(message.from_user.id)
    await state.update_data(filters=filters, offset=0)
    total = count_apartments(filters, vip=bool(user.get("vip")))

    parts = []
    if filters.get("rooms"):
        parts.append(f"🛏 {filters['rooms']} комн.")
    if filters.get("district"):
        parts.append(f"📍 {filters['district']}")
    if filters.get("price_max"):
        parts.append(f"💰 до {filters['price_max']} zł")
    if filters.get("furnished") == 1:
        parts.append("🛋 меблированная")

    summary = "  ·  ".join(parts) if parts else "все квартиры"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"🏠 Смотреть ({total})", callback_data="next"),
        InlineKeyboardButton(text="🔍 Изменить", callback_data="open_filter"),
    ]])
    await message.answer(
        f"🤖 <b>Понял! Ищу:</b>\n{summary}\n\n🏠 Найдено: <b>{total}</b> квартир",
        parse_mode="HTML",
        reply_markup=kb
    )


# ── /favorites ───────────────────────────────────────────────

@router.message(Command("favorites"))
async def cmd_favorites(message: Message):
    await _show_favorites(message.from_user.id, message)


@router.callback_query(F.data == "open_favorites")
async def cb_open_favorites(call: CallbackQuery):
    await call.answer()
    await _show_favorites(call.from_user.id, call.message)


async def _show_favorites(user_id: int, target):
    favs = get_favorites(user_id)
    if not favs:
        await target.answer(
            "❤️ <b>Избранное пусто</b>\n\nДобавляй квартиры кнопкой ❤️ под объявлением.",
            parse_mode="HTML"
        )
        return

    header_kb = None
    if len(favs) >= 2:
        header_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📊 Сравнить", callback_data="open_compare"),
        ]])
    await target.answer(
        f"❤️ <b>Избранное ({len(favs)}):</b>",
        parse_mode="HTML",
        reply_markup=header_kb
    )
    for apt in favs[:10]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"fav_remove:{apt['id']}"),
            InlineKeyboardButton(text="🔗 Открыть", url=apt["link"]),
        ]])
        await target.answer(apt_text(apt), reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("fav_add:"))
async def cb_fav_add(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    add_favorite(call.from_user.id, apt_id)
    await call.answer("❤️ Добавлено в избранное!")


@router.callback_query(F.data.startswith("fav_remove:"))
async def cb_fav_remove(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    remove_favorite(call.from_user.id, apt_id)
    await call.answer("🗑 Удалено из избранного")
    try:
        await call.message.delete()
    except Exception:
        pass


# ── /vip ─────────────────────────────────────────────────────

@router.message(Command("vip"))
async def cmd_vip(message: Message):
    await _show_vip(message.from_user.id, message)


@router.callback_query(F.data == "open_vip")
async def cb_open_vip(call: CallbackQuery):
    await call.answer()
    await _show_vip(call.from_user.id, call.message)


async def _show_vip(user_id: int, target):
    user = get_or_create_user(user_id)
    if user.get("vip"):
        subs = get_user_subscriptions(user_id)
        until = (user.get("vip_until") or "")[:10] or "∞"
        await target.answer(
            f"💎 <b>VIP активен до: {until}</b>\n\n"
            f"🔔 Подписки: {', '.join(subs) if subs else 'нет'}\n\n"
            f"• Умные алерты: /alert\n"
            f"• Подписка на район: /subscribe\n"
            f"• Статистика: /mystats",
            parse_mode="HTML"
        )
        return

    ref = get_ref_stats(user_id)
    ref_count = ref.get("ref_count", 0)
    ref_bar = "🟩" * min(ref_count, REFERRAL_REQUIRED) + "⬜" * max(0, REFERRAL_REQUIRED - ref_count)
    favs = get_favorites(user_id)
    fav_count = len(favs)
    fav_bar = "🟩" * min(fav_count, 10) + "⬜" * max(0, 10 - fav_count)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐ Оплатить Stars ({VIP_STARS_PRICE} XTR)", callback_data="vip_stars")],
        [InlineKeyboardButton(text=f"💳 Оплатить {VIP_PRICE} zł/мес (Revolut/BLIK)", callback_data="vip_how_to_pay")],
        [InlineKeyboardButton(text="👥 Получить бесплатно (рефералы)", callback_data="open_ref")],
    ])
    await target.answer(
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
        f"   → сохрани 10 квартир = 3 дня VIP автоматически",
        parse_mode="HTML",
        reply_markup=kb
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
        parse_mode="HTML",
        reply_markup=kb
    )


@router.callback_query(F.data == "vip_request")
async def cb_vip_request(call: CallbackQuery):
    await call.answer("✅ Запрос отправлен!")
    for admin_id in ADMIN_IDS:
        try:
            kb_admin = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Активировать VIP", callback_data=f"admin_approve:{call.from_user.id}"),
                InlineKeyboardButton(text="❌ Отклонить",        callback_data=f"admin_reject:{call.from_user.id}"),
            ]])
            await call.bot.send_message(
                admin_id,
                f"💳 <b>Запрос VIP</b>\n\n"
                f"👤 {call.from_user.full_name}\n"
                f"🆔 <code>{call.from_user.id}</code>\n"
                f"📛 @{call.from_user.username or 'нет'}\n\n"
                f"Проверь перевод на Revolut @d_yaromenka и нажми кнопку:",
                parse_mode="HTML",
                reply_markup=kb_admin
            )
        except Exception:
            pass
    await call.message.answer(
        "✅ <b>Запрос отправлен!</b>\n\n"
        "Проверю оплату и активирую VIP в течение нескольких часов.\n"
        "Получишь уведомление как только VIP будет активирован. 🙏",
        parse_mode="HTML"
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
            "✅ Безлимитный просмотр\n✅ Умные алерты: /alert\n✅ Подписка: /subscribe\n\nСпасибо! 🙏",
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


# ── /alert ───────────────────────────────────────────────────

@router.message(Command("alert"))
async def cmd_alert(message: Message, state: FSMContext):
    await _show_alerts(message.from_user.id, message, state)


@router.callback_query(F.data == "open_alerts")
async def cb_open_alerts(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _show_alerts(call.from_user.id, call.message, state)


async def _show_alerts(user_id: int, target, state: FSMContext):
    user = get_or_create_user(user_id)
    if not user.get("vip"):
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"⭐ VIP — {VIP_PRICE} zł/мес", callback_data="open_vip")
        ]])
        await target.answer(
            "🔔 <b>Умный алерт</b> — VIP функция.\n\n"
            "Задай параметры и я напишу тебе <b>мгновенно</b> когда появится подходящая квартира.",
            parse_mode="HTML",
            reply_markup=kb
        )
        return
    alerts = get_user_alerts(user_id)
    rows = [[InlineKeyboardButton(text="➕ Создать алерт", callback_data="alert_create")]]
    for a in alerts:
        district = a.get("district") or "любой"
        price_max = a.get("price_max") or "∞"
        rows.append([InlineKeyboardButton(
            text=f"🗑 #{a['id']}: {district} до {price_max} zł",
            callback_data=f"alert_del:{a['id']}"
        )])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await target.answer(
        f"🔔 <b>Твои алерты ({len(alerts)}/5):</b>\n\nКогда появится квартира по параметрам — напишу сразу.",
        parse_mode="HTML",
        reply_markup=kb
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
    await call.message.edit_text("💰 Максимальная цена для алерта:", reply_markup=price_keyboard("alert_pmax"))
    await state.set_state(AlertState.waiting_price_max)


@router.callback_query(F.data.startswith("alert_pmax:"), AlertState.waiting_price_max)
async def cb_alert_price_max(call: CallbackQuery, state: FSMContext):
    val = int(call.data.split(":")[1])
    await state.update_data(alert_price_max=val if val > 0 else None)
    await call.message.edit_text("🛏 Количество комнат для алерта:", reply_markup=rooms_keyboard("alert_rooms"))
    await state.set_state(AlertState.waiting_rooms)


@router.callback_query(F.data.startswith("alert_rooms:"), AlertState.waiting_rooms)
async def cb_alert_rooms(call: CallbackQuery, state: FSMContext):
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    await state.set_state(None)
    create_alert(
        call.from_user.id,
        district=data.get("alert_district"),
        price_min=None,
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
    summary = " · ".join(parts) if parts else "Любые квартиры"
    await call.message.edit_text(
        f"✅ <b>Алерт создан!</b>\n{summary}\n\nНапишу тебе сразу как появится подходящая квартира. 🔔",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("alert_del:"))
async def cb_alert_del(call: CallbackQuery):
    alert_id = int(call.data.split(":")[1])
    delete_alert(alert_id, call.from_user.id)
    await call.answer("🗑 Алерт удалён")
    try:
        await call.message.delete()
    except Exception:
        pass


# ── /ref ─────────────────────────────────────────────────────

@router.message(Command("ref"))
async def cmd_ref(message: Message):
    await _show_ref(message.from_user.id, message)


@router.callback_query(F.data == "open_ref")
async def cb_open_ref(call: CallbackQuery):
    await call.answer()
    await _show_ref(call.from_user.id, call.message)


async def _show_ref(user_id: int, target):
    stats = get_ref_stats(user_id)
    if not stats:
        return
    ref_code = stats.get("ref_code", "")
    ref_count = stats.get("ref_count", 0)
    bot_me = await target.bot.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start=ref_{ref_code}"
    next_reward = REFERRAL_REQUIRED - (ref_count % REFERRAL_REQUIRED)
    bar = "🟩" * (ref_count % REFERRAL_REQUIRED) + "⬜" * next_reward

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📤 Поделиться ссылкой", switch_inline_query=ref_link)
    ]])
    await target.answer(
        f"👥 <b>Пригласи друзей — получи VIP бесплатно!</b>\n\n"
        f"Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        f"👤 Приглашено: <b>{ref_count}</b> чел.\n"
        f"🎁 Прогресс: {bar} {ref_count % REFERRAL_REQUIRED}/{REFERRAL_REQUIRED}\n"
        f"   До следующего VIP: ещё <b>{next_reward}</b> чел.\n\n"
        f"За каждые {REFERRAL_REQUIRED} приглашённых — {REFERRAL_REWARD_DAYS} дней VIP бесплатно!",
        parse_mode="HTML",
        reply_markup=kb
    )


# ── /mystats ─────────────────────────────────────────────────

@router.message(Command("mystats"))
async def cmd_mystats(message: Message):
    await _show_stats(message.from_user.id, message)


@router.callback_query(F.data == "open_stats")
async def cb_open_stats(call: CallbackQuery):
    await call.answer()
    await _show_stats(call.from_user.id, call.message)


async def _show_stats(user_id: int, target):
    user = get_or_create_user(user_id)
    subs = get_user_subscriptions(user_id)
    favs = get_favorites(user_id)
    alerts = get_user_alerts(user_id)
    ref = get_ref_stats(user_id)
    ref_count = ref.get("ref_count", 0)
    lang = get_lang(user_id)

    vip_line = _vip_badge(user, lang)
    fav_count = len(favs)
    streak = get_user_streak_days(user_id)
    streak_line = ""
    if streak >= 7:
        streak_line = f"\n🔥 Стрик: <b>{streak} дней подряд</b>! 🏆"
    elif streak >= 3:
        streak_line = f"\n🔥 Стрик: <b>{streak} дней подряд</b>!"
    elif streak > 0:
        streak_line = f"\n📆 Активен {streak} дн. подряд"

    next_vip = ""
    if not user.get("vip"):
        remaining_refs = max(0, REFERRAL_REQUIRED - (ref_count % REFERRAL_REQUIRED))
        remaining_favs = max(0, 10 - fav_count)
        next_vip = (
            f"\n\n🎯 <b>До бесплатного VIP:</b>\n"
            f"❤️ Сохрани ещё {remaining_favs} квартир → 3 дня VIP\n"
            f"👥 Пригласи ещё {remaining_refs} друзей → {REFERRAL_REWARD_DAYS} дней VIP"
        )

    created = (user.get("created_at") or "")[:10]
    await target.answer(
        f"📊 <b>Твоя статистика</b>\n\n"
        f"📌 Статус: {vip_line}\n"
        f"👁 Просмотрено: <b>{user.get('views', 0)}</b> квартир\n"
        f"❤️ Избранное: <b>{fav_count}</b>\n"
        f"🔔 Подписки: {', '.join(subs) if subs else 'нет'}\n"
        f"🎯 Алертов: <b>{len(alerts)}</b>\n"
        f"👥 Приглашено: <b>{ref_count}</b> чел.\n"
        f"📅 С нами с: {created}"
        f"{streak_line}"
        f"{next_vip}",
        parse_mode="HTML"
    )


# ── /hot ─────────────────────────────────────────────────────

@router.message(Command("hot"))
async def cmd_hot(message: Message):
    await _show_hot(message)


@router.callback_query(F.data == "open_hot")
async def cb_open_hot(call: CallbackQuery):
    await call.answer()
    await _show_hot(call.message)


async def _show_hot(target):
    apts = get_hot_apartments(limit=5)
    if not apts:
        await target.answer(
            "🔥 <b>Горячих квартир пока нет</b>\n\n"
            "Ставь 👍 под квартирами — самые популярные появятся здесь!",
            parse_mode="HTML"
        )
        return
    await target.answer("🔥 <b>Горячие квартиры (топ лайков за 24ч):</b>", parse_mode="HTML")
    for apt in apts:
        score = apt.get("hot_score", 0)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❤️ Сохранить", callback_data=f"fav_add:{apt['id']}"),
            InlineKeyboardButton(text="🔗 Открыть", url=apt["link"]),
        ]])
        await target.answer(
            apt_text(apt) + f"\n\n🔥 <b>{score} лайков</b>",
            reply_markup=kb,
            parse_mode="HTML"
        )


# ── /drops ───────────────────────────────────────────────────

@router.message(Command("drops"))
async def cmd_drops(message: Message):
    await _show_drops(message)


@router.callback_query(F.data == "open_drops")
async def cb_open_drops(call: CallbackQuery):
    await call.answer()
    await _show_drops(call.message)


async def _show_drops(target):
    drops = get_price_drops_today(limit=5)
    if not drops:
        await target.answer(
            "📉 <b>Снижений цен пока нет</b>\n\n"
            "Бот отслеживает изменения цен при каждом парсинге.\n"
            "Как только цена снизится — покажу здесь.\n\n"
            "💡 Настрой алерт: /alert",
            parse_mode="HTML"
        )
        return
    await target.answer("📉 <b>Снижение цен за 48ч:</b>", parse_mode="HTML")
    for apt in drops:
        old = apt.get("old_price") or 0
        current = apt.get("price") or 0
        diff = int(old) - int(current) if old and current else 0
        pct = int(diff / old * 100) if old else 0
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❤️ Сохранить", callback_data=f"fav_add:{apt['id']}"),
            InlineKeyboardButton(text="🔗 Открыть", url=apt["link"]),
        ]])
        await target.answer(
            f"📉 <b>−{diff} zł (−{pct}%)</b>\n"
            f"🏠 {apt.get('title', '—')}\n"
            f"💰 <s>{old} zł</s> → <b>{current} zł/мес</b>\n"
            f"📍 {apt.get('district', 'Warszawa')}",
            reply_markup=kb,
            parse_mode="HTML"
        )


# ── /cheap ───────────────────────────────────────────────────

@router.message(Command("cheap"))
async def cmd_cheap(message: Message):
    await _show_cheap(message)


@router.callback_query(F.data == "open_cheap")
async def cb_open_cheap(call: CallbackQuery):
    await call.answer()
    await _show_cheap(call.message)


async def _show_cheap(target):
    try:
        apts = get_cheapest_apartments(limit=5)
    except Exception:
        from database.db import get_apartments
        apts = get_apartments(filters={"price_max": 2500}, offset=0, limit=5, vip=True)
    if not apts:
        await target.answer("😔 Дешёвых квартир пока нет. Попробуй позже.")
        return
    await target.answer("💚 <b>Самые дешёвые квартиры:</b>", parse_mode="HTML")
    for apt in apts:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❤️ Сохранить", callback_data=f"fav_add:{apt['id']}"),
            InlineKeyboardButton(text="🔗 Открыть", url=apt["link"]),
        ]])
        await target.answer(apt_text(apt), reply_markup=kb, parse_mode="HTML")


# ── /map — price map by district ─────────────────────────────

@router.message(Command("map"))
async def cmd_map(message: Message):
    await _show_map(message)


@router.callback_query(F.data == "open_map")
async def cb_open_map(call: CallbackQuery):
    await call.answer()
    await _show_map(call.message)


async def _show_map(target):
    from database.db import get_conn
    conn = get_conn()
    rows = conn.execute("""
        SELECT district, COUNT(*) as cnt, AVG(price) as avg_price, MIN(price) as min_price
        FROM apartments
        WHERE price > 500 AND price < 20000 AND district != '' AND district IS NOT NULL
        GROUP BY district
        HAVING cnt >= 2
        ORDER BY avg_price ASC
        LIMIT 15
    """).fetchall()
    conn.close()

    if not rows:
        await target.answer(
            "🗺 <b>Карта цен</b>\n\nДанных пока мало. Подожди первого парсинга.",
            parse_mode="HTML"
        )
        return

    lines = ["🗺 <b>Средние цены по районам Варшавы:</b>\n"]
    for r in rows:
        avg = int(r["avg_price"])
        bar_len = min(int(avg / 600), 8)
        bar = "█" * bar_len + "░" * (8 - bar_len)
        lines.append(
            f"📍 <b>{r['district']}</b>\n"
            f"   {bar} avg <b>{avg} zł</b> · от {r['min_price']} zł · {r['cnt']} объявл."
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔍 Выбрать район", callback_data="open_filter"),
    ]])
    await target.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


# ── /daily — short-term rental ────────────────────────────────

@router.message(Command("daily"))
async def cmd_daily(message: Message):
    await _show_daily(message)


@router.callback_query(F.data == "open_daily")
async def cb_open_daily(call: CallbackQuery):
    await call.answer()
    await _show_daily(call.message)


async def _show_daily(target):
    lang = get_lang(target.chat.id if hasattr(target, "chat") else target.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 день",  callback_data="daily_days:1"),
            InlineKeyboardButton(text="3 дня",   callback_data="daily_days:3"),
            InlineKeyboardButton(text="7 дней",  callback_data="daily_days:7"),
        ],
        [
            InlineKeyboardButton(text="14 дней", callback_data="daily_days:14"),
            InlineKeyboardButton(text="30 дней", callback_data="daily_days:30"),
        ],
    ])
    await target.answer(t(lang, "daily_text"), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("daily_days:"))
async def cb_daily_days(call: CallbackQuery):
    days = int(call.data.split(":")[1])
    lang = get_lang(call.from_user.id)
    from datetime import date, timedelta
    checkin = date.today().isoformat()
    checkout = (date.today() + timedelta(days=days)).isoformat()
    booking = f"https://www.booking.com/searchresults.pl.html?ss=Warszawa&checkin={checkin}&checkout={checkout}&group_adults=2"
    airbnb = f"https://www.airbnb.pl/s/Warszawa/homes?checkin={checkin}&checkout={checkout}"
    nocowanie = f"https://www.nocowanie.pl/noclegi/warszawa/?od={checkin}&do={checkout}"
    await call.answer()
    await call.message.answer(
        t(lang, "daily_links", days=days, booking=booking, airbnb=airbnb, nocowanie=nocowanie),
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# ── /subscribe ───────────────────────────────────────────────

@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    user = get_or_create_user(message.from_user.id)
    if not user.get("vip"):
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
    if not user.get("vip"):
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


# ── /lang ─────────────────────────────────────────────────────

@router.message(Command("lang"))
async def cmd_lang(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский",    callback_data="lang:ru"),
        InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang:uk"),
        InlineKeyboardButton(text="🇵🇱 Polski",     callback_data="lang:pl"),
    ]])
    await message.answer("🌍 Выбери язык / Wybierz język / Оберіть мову:", reply_markup=kb)


@router.callback_query(F.data.startswith("lang:"))
async def cb_lang(call: CallbackQuery):
    lang = call.data.split(":")[1]
    set_user_lang(call.from_user.id, lang)
    await call.answer(t(lang, "lang_changed"), show_alert=True)
    try:
        await call.message.delete()
    except Exception:
        pass


# ── /help ─────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message):
    lang = get_lang(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📋 Главное меню", callback_data="open_menu"),
    ]])
    await message.answer(t(lang, "help_text"), parse_mode="HTML", reply_markup=kb)


# ── /digest ───────────────────────────────────────────────────

@router.message(Command("digest"))
async def cmd_digest(message: Message):
    digest = get_daily_digest()
    if not digest.get("new_today"):
        await message.answer("📭 Сегодня новых квартир пока нет. Парсер работает каждые 10 минут.")
        return
    text = (
        f"📰 <b>Дайджест за сегодня:</b>\n\n"
        f"🏠 Новых квартир: <b>{digest['new_today']}</b>\n"
    )
    if digest.get("avg_price"):
        text += f"💰 Средняя цена: <b>{digest['avg_price']} zł</b>\n"
    if digest.get("cheapest"):
        c = digest["cheapest"]
        text += (
            f"\n🏆 <b>Самая дешёвая сегодня:</b>\n"
            f"🏠 {c.get('title', '—')}\n"
            f"💰 {c.get('price', 0)} zł/мес · 📍 {c.get('district', 'Warszawa')}\n"
            f"🔗 {c.get('link', '')}"
        )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏠 Смотреть все", callback_data="open_today")
    ]])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "open_digest")
async def cb_open_digest(call: CallbackQuery):
    await call.answer()
    await cmd_digest(call.message)


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
        parse_mode="HTML",
        reply_markup=kb
    )


# ── Callbacks: rating, share, seen, found, scam ───────────────

@router.callback_query(F.data.startswith("rate:"))
async def cb_rate(call: CallbackQuery):
    parts = call.data.split(":")
    rating = int(parts[1])
    apt_id = int(parts[2])
    rate_apartment(call.from_user.id, apt_id, rating)
    await call.answer("👍 Лайк!" if rating == 1 else "👎 Дизлайк")


@router.callback_query(F.data.startswith("share:"))
async def cb_share(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    apt = get_apartment_by_id(apt_id)
    if not apt:
        await call.answer("Объявление не найдено", show_alert=True)
        return
    await call.answer()
    bot_me = await call.bot.get_me()
    icon = SOURCE_ICONS.get(apt.get("source", ""), "📡")
    share_text = (
        f"🏠 {apt.get('title', '—')}\n"
        f"💰 {apt.get('price', 0)} zł/мес\n"
        f"📍 {apt.get('district', 'Warszawa')}\n"
        f"🔗 {apt.get('link', '')}\n\n"
        f"{icon} Найдено через @{bot_me.username}"
    )
    share_url = (
        f"https://t.me/share/url"
        f"?url={urllib.parse.quote(apt.get('link', ''))}"
        f"&text={urllib.parse.quote(share_text)}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📤 Поделиться в Telegram", url=share_url),
        InlineKeyboardButton(text="🔗 Открыть", url=apt.get("link", "#")),
    ]])
    await call.message.answer(
        f"📤 <b>Поделиться:</b>\n\n"
        f"🏠 {apt.get('title', '—')}\n"
        f"💰 {apt.get('price', 0)} zł/мес · 📍 {apt.get('district', 'Warszawa')}",
        parse_mode="HTML",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("seen:"))
async def cb_seen(call: CallbackQuery, state: FSMContext):
    apt_id = int(call.data.split(":")[1])
    mark_seen(call.from_user.id, apt_id)
    await call.answer("👁 Отмечено")
    await show_next_apartment(call.from_user.id, call.bot, state, call.message.chat.id)


@router.callback_query(F.data.startswith("found:"))
async def cb_found(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    apt = get_apartment_by_id(apt_id)
    source = apt.get("source", "") if apt else ""
    record_conversion(call.from_user.id, apt_id, source)
    await call.answer("🎉 Поздравляем!", show_alert=True)

    bot_me = await call.bot.get_me()
    ref_stats = get_ref_stats(call.from_user.id)
    ref_code = ref_stats.get("ref_code", "")
    ref_link = f"https://t.me/{bot_me.username}?start=ref_{ref_code}" if ref_code else f"https://t.me/{bot_me.username}"
    share_text = "Нашёл квартиру в Варшаве через этого бота! Рекомендую 🏠"
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote(share_text)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📤 Поделиться ботом с другом", url=share_url),
    ]])
    await call.message.answer(
        "🎉 <b>Поздравляем с новой квартирой!</b>\n\n"
        "Если бот помог — расскажи друзьям.\n"
        "За каждого приглашённого — <b>7 дней VIP бесплатно!</b> 🎁",
        parse_mode="HTML",
        reply_markup=kb
    )
    for admin_id in ADMIN_IDS:
        try:
            apt_info = f"🏠 {apt.get('title','?')} · {apt.get('price',0)} zł · {apt.get('source','')}" if apt else f"apt_id={apt_id}"
            await call.bot.send_message(
                admin_id,
                f"✅ <b>Конверсия!</b>\n👤 <code>{call.from_user.id}</code>\n{apt_info}",
                parse_mode="HTML"
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("scam:"))
async def cb_scam(call: CallbackQuery, state: FSMContext):
    apt_id = int(call.data.split(":")[1])
    await state.update_data(report_apt_id=apt_id)
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Мошенник/скам",    callback_data=f"report_reason:scam:{apt_id}")],
        [InlineKeyboardButton(text="❌ Уже сдано",         callback_data=f"report_reason:rented:{apt_id}")],
        [InlineKeyboardButton(text="💰 Цена не та",        callback_data=f"report_reason:price:{apt_id}")],
        [InlineKeyboardButton(text="📷 Фото не совпадает", callback_data=f"report_reason:photo:{apt_id}")],
        [InlineKeyboardButton(text="❌ Отмена",            callback_data="cancel")],
    ])
    await call.message.answer("🚨 <b>Причина жалобы:</b>", parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("report_reason:"))
async def cb_report_reason(call: CallbackQuery):
    parts = call.data.split(":")
    reason = parts[1]
    apt_id = int(parts[2])
    reason_labels = {
        "scam": "Мошенник/скам",
        "rented": "Уже сдано",
        "price": "Цена не та",
        "photo": "Фото не совпадает",
    }
    try:
        report_apartment(call.from_user.id, apt_id, reason_labels.get(reason, reason))
    except Exception:
        pass
    await call.answer("✅ Жалоба отправлена. Спасибо!", show_alert=True)
    try:
        await call.message.delete()
    except Exception:
        pass


@router.callback_query(F.data.startswith("similar:"))
async def cb_similar(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    await call.answer()
    try:
        similar = get_similar_apartments(apt_id, limit=3)
    except Exception:
        similar = []
    if not similar:
        await call.message.answer("😔 Похожих квартир не найдено.")
        return
    await call.message.answer("🔍 <b>Похожие квартиры:</b>", parse_mode="HTML")
    for apt in similar:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❤️ Сохранить", callback_data=f"fav_add:{apt['id']}"),
            InlineKeyboardButton(text="🔗 Открыть", url=apt["link"]),
        ]])
        await call.message.answer(apt_text(apt), reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "open_compare")
async def cb_open_compare(call: CallbackQuery):
    await call.answer()
    favs = get_favorites(call.from_user.id)
    if len(favs) < 2:
        await call.message.answer("❤️ Добавь минимум 2 квартиры в избранное для сравнения.")
        return
    lines = ["📊 <b>Сравнение квартир из избранного:</b>\n"]
    for apt in favs[:5]:
        price = apt.get("price", 0) or 0
        rooms = apt.get("rooms", "?")
        area = apt.get("area", "?")
        ppm = f"{int(price / apt['area'])} zł/м²" if apt.get("area") and price else "—"
        lines.append(
            f"🏠 <b>{apt.get('title', '—')[:40]}</b>\n"
            f"   💰 {price} zł · 🛏 {rooms} комн. · 📐 {area} м² · {ppm}\n"
            f"   📍 {apt.get('district', 'Warszawa')} · {SOURCE_ICONS.get(apt.get('source',''), '📡')} {apt.get('source','')}"
        )
    await call.message.answer("\n\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data == "cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer("Отменено")
    try:
        await call.message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery, state: FSMContext):
    from bot.middleware import is_subscribed
    if await is_subscribed(call.bot, call.from_user.id):
        await call.answer("✅ Подписка подтверждена!", show_alert=True)
        try:
            await call.message.delete()
        except Exception:
            pass
        user = get_or_create_user(call.from_user.id)
        await _show_main_menu(call.message, user, from_user=call.from_user)
    else:
        await call.answer("❌ Ты ещё не подписался на @ddflots!", show_alert=True)


# ── Admin panel ───────────────────────────────────────────────

def _admin_kb(pending_count: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 Пользователи",   callback_data="admin_users"),
            InlineKeyboardButton(text="💎 VIP список",     callback_data="admin_vip_list"),
        ],
        [
            InlineKeyboardButton(text="➕ Выдать VIP",     callback_data="admin_give_vip"),
            InlineKeyboardButton(text="➖ Снять VIP",      callback_data="admin_remove_vip"),
        ],
        [
            InlineKeyboardButton(text="🔍 Найти юзера",   callback_data="admin_find_user"),
            InlineKeyboardButton(text="💰 Финансы",        callback_data="admin_finance"),
        ],
        [
            InlineKeyboardButton(text="🚫 Забанить",       callback_data="admin_ban_user"),
            InlineKeyboardButton(text="✅ Разбанить",      callback_data="admin_unban_user"),
        ],
        [
            InlineKeyboardButton(text="📢 Рассылка всем",  callback_data="admin_broadcast"),
            InlineKeyboardButton(text="📢 VIP рассылка",   callback_data="admin_broadcast_vip"),
        ],
        [
            InlineKeyboardButton(text="📊 Парсер",         callback_data="admin_parse_stats"),
            InlineKeyboardButton(text="🔄 Запустить",      callback_data="admin_parse"),
        ],
        [
            InlineKeyboardButton(text=f"🚩 Жалобы ({pending_count})", callback_data="admin_reports"),
            InlineKeyboardButton(text="🗑 Очистить старые", callback_data="admin_cleanup"),
        ],
        [
            InlineKeyboardButton(text="📈 Топ рефералов",  callback_data="admin_top_refs"),
            InlineKeyboardButton(text="💾 Бэкап БД",       callback_data="admin_backup"),
        ],
    ])


async def _send_admin_panel(target, bot=None):
    stats = get_stats()
    last = (stats.get("last_parse") or "никогда")[:16]
    pending = get_pending_reports(limit=50)
    conv = get_conversion_stats()
    text = (
        f"🛠 <b>Админ-панель DDFlatsBot</b>\n\n"
        f"🏠 Квартир: <b>{stats['apartments']}</b> (+{stats.get('new_today', 0)} сегодня)\n"
        f"👥 Пользователей: <b>{stats['users']}</b> (+{stats.get('new_users_today', 0)} сегодня)\n"
        f"💎 VIP активных: <b>{stats['vip']}</b>\n"
        f"❤️ Избранных: <b>{stats['favorites']}</b>\n"
        f"📊 Активных сегодня: <b>{stats.get('active_today', 0)}</b>\n"
        f"✅ Конверсий: <b>{conv.get('total', 0)}</b> (+{conv.get('today', 0)} сегодня)\n"
        f"🕐 Последний парсинг: <b>{last}</b>"
    )
    kb = _admin_kb(len(pending))
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
        mark = "💎" if r["vip"] == 1 else ("🚫" if r["vip"] == -1 else "🆓")
        date_str = (r["created_at"] or "")[:10]
        lines.append(f"{mark} <code>{r['user_id']}</code> · 👁{r['views']} · 👥{r['ref_count']} · {date_str}")
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
        until = (r["vip_until"] or "")[:10] or "∞"
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
        "SELECT source, COUNT(*) as cnt FROM apartments GROUP BY source ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    lines = ["📊 <b>Статистика парсера:</b>\n"]
    for r in rows:
        last = (r["last"] or "")[:16]
        lines.append(f"📡 <b>{r['source']}</b>: +{r['total']} · {last}")
    lines.append("\n<b>В базе сейчас:</b>")
    for r in src_counts:
        lines.append(f"  {r['source']}: {r['cnt']} объявл.")
    await call.message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data == "admin_cleanup")
async def cb_admin_cleanup(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.answer("🗑 Очистка...")
    from database.db import get_conn
    cutoff = (datetime.now() - timedelta(days=30)).isoformat()
    conn = get_conn()
    deleted = conn.execute("DELETE FROM apartments WHERE created_at < ?", (cutoff,)).rowcount
    conn.commit()
    conn.close()
    await call.message.answer(f"✅ Удалено {deleted} объявлений старше 30 дней.")


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.message.answer("✏️ Введи текст рассылки (всем пользователям):")
    await state.update_data(broadcast_target="all")
    await state.set_state(BroadcastState.waiting_message)
    await call.answer()


@router.callback_query(F.data == "admin_broadcast_vip")
async def cb_admin_broadcast_vip(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    await call.message.answer("✏️ Введи текст рассылки для VIP пользователей:")
    await state.update_data(broadcast_target="vip")
    await state.set_state(BroadcastState.waiting_message)
    await call.answer()


@router.message(BroadcastState.waiting_message)
async def broadcast_send(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    target = data.get("broadcast_target", "all")
    user_ids = get_all_vip_user_ids() if target == "vip" else get_all_user_ids()
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
            InlineKeyboardButton(text="🗑 Удалить",   callback_data=f"mod_delete:{r['apartment_id']}"),
        ]])
        await call.message.answer(
            f"🚩 <b>Жалоба #{r['id']}</b>\n"
            f"🏠 {r.get('title', '?')}\n"
            f"💰 {r.get('price', '?')} zł · 📍 {r.get('district', '?')}\n"
            f"📋 Причина: {r.get('reason', '?')}\n"
            f"👤 От: <code>{r.get('user_id', '?')}</code>",
            parse_mode="HTML",
            reply_markup=kb
        )


@router.callback_query(F.data.startswith("mod_verify:"))
async def cb_mod_verify(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    apt_id = int(call.data.split(":")[1])
    try:
        verify_apartment(apt_id)
    except Exception:
        pass
    await call.answer("✅ Отмечено как проверенное")
    await call.message.edit_text(call.message.text + "\n\n✅ <b>Проверено</b>", parse_mode="HTML")


@router.callback_query(F.data.startswith("mod_delete:"))
async def cb_mod_delete(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    apt_id = int(call.data.split(":")[1])
    try:
        delete_apartment(apt_id)
    except Exception:
        pass
    await call.answer("🗑 Удалено")
    await call.message.edit_text(call.message.text + "\n\n🗑 <b>Удалено</b>", parse_mode="HTML")


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
    conn.close()
    potential = vip_count * VIP_PRICE
    await call.message.answer(
        f"💰 <b>Финансовая статистика</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"💎 VIP активных: <b>{vip_count}</b>\n"
        f"💵 Потенциальный доход: <b>{potential} zł/мес</b>\n\n"
        f"⭐ Stars цена: <b>{VIP_STARS_PRICE} XTR</b> (~{VIP_PRICE} zł)\n\n"
        f"💳 Revolut: @d_yaromenka\n"
        f"📱 BLIK: +48 731 359 199",
        parse_mode="HTML"
    )


# ── Admin: Give/Remove VIP ────────────────────────────────────

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
            "✅ Безлимитный просмотр\n✅ Умные алерты: /alert\n✅ Подписка: /subscribe\n\nСпасибо! 🙏",
            parse_mode="HTML"
        )
    except Exception:
        pass


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
        await message.answer(f"❌ Пользователь {uid} не найден.")
        return
    vip_until = (user["vip_until"] or "")[:10] or "нет"
    vip_status = f"да до {vip_until}" if user["vip"] == 1 else ("заблокирован" if user["vip"] == -1 else "нет")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выдать VIP 30д", callback_data=f"admin_do_vip:{uid}:30")],
        [InlineKeyboardButton(text="🚫 Забанить",       callback_data=f"admin_do_ban:{uid}")],
        [InlineKeyboardButton(text="✅ Разбанить",      callback_data=f"admin_do_unban:{uid}")],
    ])
    await message.answer(
        f"👤 <b>Пользователь {uid}</b>\n\n"
        f"💎 VIP: {vip_status}\n"
        f"👁 Просмотров: {user['views']}\n"
        f"❤️ Избранных: {fav_count}\n"
        f"🎯 Алертов: {alert_count}\n"
        f"👥 Рефералов: {user['ref_count']}\n"
        f"🌍 Язык: {user['lang'] or 'ru'}\n"
        f"📅 Регистрация: {(user['created_at'] or '')[:10]}",
        parse_mode="HTML",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("admin_do_vip:"))
async def cb_admin_do_vip(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    parts = call.data.split(":")
    uid = int(parts[1])
    days = int(parts[2]) if len(parts) > 2 else 30
    set_vip(uid, 1, days=days)
    await call.answer(f"✅ VIP {days}д выдан {uid}")
    await call.message.edit_text(call.message.text + f"\n\n✅ <b>VIP {days}д выдан</b>", parse_mode="HTML")


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
    await call.answer(f"🚫 {uid} заблокирован")
    await call.message.edit_text(call.message.text + f"\n\n🚫 <b>Заблокирован</b>", parse_mode="HTML")


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


# ── Admin shortcut commands ───────────────────────────────────

@router.message(Command("setvip"))
async def cmd_setvip(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Использование: /setvip [user_id] [дней=30]")
        return
    days = int(args[2]) if len(args) >= 3 and args[2].isdigit() else 30
    target_id = int(args[1])
    set_vip(target_id, 1, days=days)
    await message.answer(f"✅ VIP на {days} дней активирован для {target_id}")
    try:
        await message.bot.send_message(
            target_id,
            f"🎉 <b>VIP активирован на {days} дней!</b>\n\n"
            "✅ Безлимитный просмотр\n✅ Алерты: /alert\n✅ Подписка: /subscribe\n\nСпасибо! 🙏",
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
    vip_until = (user["vip_until"] or "")[:10] or "нет"
    await message.answer(
        f"👤 <b>Пользователь {uid}</b>\n\n"
        f"💎 VIP: {'да до ' + vip_until if user['vip'] == 1 else 'нет'}\n"
        f"👁 Просмотров: {user['views']}\n"
        f"❤️ Избранных: {fav_count}\n"
        f"🎯 Алертов: {alert_count}\n"
        f"👥 Рефералов: {user['ref_count']}\n"
        f"🌍 Язык: {user['lang'] or 'ru'}\n"
        f"📅 Регистрация: {(user['created_at'] or '')[:10]}\n\n"
        f"/setvip {uid} 30\n/removevip {uid}",
        parse_mode="HTML"
    )


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
        marker = " ← ты" if leader["user_id"] == message.from_user.id else ""
        lines.append(f"{medal} ID{leader['user_id']} — {leader['ref_count']} чел.{marker}")
    lines.append("\n👥 Топ-3 каждый месяц получают VIP!\n/ref — твоя реферальная ссылка")
    await message.answer("\n".join(lines), parse_mode="HTML")


# ── /notes — personal notes on apartments ────────────────────

@router.message(Command("notes"))
async def cmd_notes(message: Message):
    await _show_notes(message.from_user.id, message)


@router.callback_query(F.data == "open_notes")
async def cb_open_notes(call: CallbackQuery):
    await call.answer()
    await _show_notes(call.from_user.id, call.message)


async def _show_notes(user_id: int, target):
    notes = get_user_notes(user_id)
    if not notes:
        await target.answer(
            "📝 <b>Заметки пусты</b>\n\n"
            "Чтобы добавить заметку к квартире — нажми кнопку 📝 под объявлением.",
            parse_mode="HTML"
        )
        return
    await target.answer(f"📝 <b>Твои заметки ({len(notes)}):</b>", parse_mode="HTML")
    for note in notes[:10]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔗 Открыть квартиру", url=note.get("link", "#")),
        ]])
        text = (
            f"🏠 <b>{note.get('title', '—')[:50]}</b>\n"
            f"💰 {note.get('price', 0)} zł/мес\n"
            f"📝 <i>{note.get('note', '')}</i>\n"
            f"📅 {(note.get('created_at') or '')[:10]}"
        )
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("note:"))
async def cb_note_start(call: CallbackQuery, state: FSMContext):
    apt_id = int(call.data.split(":")[1])
    await state.update_data(note_apt_id=apt_id)
    await call.answer()
    await call.message.answer(
        "📝 Напиши заметку к этой квартире (например: «хороший район, позвонить в пн»):"
    )
    await state.set_state(NoteState.waiting_note)


@router.message(NoteState.waiting_note)
async def note_received(message: Message, state: FSMContext):
    data = await state.get_data()
    apt_id = data.get("note_apt_id")
    if not apt_id:
        await state.clear()
        return
    note_text = message.text.strip()[:500]
    add_user_note(message.from_user.id, apt_id, note_text)
    await state.clear()
    await message.answer("✅ Заметка сохранена! Посмотреть все: /notes")


# ── Fallback for unknown messages ─────────────────────────────

@router.message()
async def fallback(message: Message):
    lang = get_lang(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏠 Найти квартиру", callback_data="next"),
        InlineKeyboardButton(text="📋 Меню",           callback_data="open_menu"),
    ]])
    await message.answer(
        "🤔 Не понял команду.\n\n"
        "Используй /help для списка команд или нажми кнопку ниже.",
        reply_markup=kb
    )
