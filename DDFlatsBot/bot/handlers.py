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
    create_alert, get_user_alerts, delete_alert, get_price_drop, get_alert_limit,
    rate_apartment, set_user_lang, get_user_lang,
    get_leaderboard, get_daily_digest,
    get_hot_apartments, get_price_drops_today, record_user_activity,
    get_user_streak_days, get_all_user_ids, get_all_vip_user_ids,
    report_apartment, get_pending_reports, verify_apartment,
    delete_apartment,
    get_cheapest_apartments, get_apartment_by_id,
    add_user_note, get_user_notes, get_similar_apartments,
    increment_apt_views, mark_seen, get_search_exclude_ids, get_user_hide_seen,
    set_user_hide_seen, get_user_search_radius, set_user_search_radius,
    hide_apartment, record_conversion, get_conversion_stats,
    get_new_since, update_last_visit, get_last_visit,
    get_apt_age_days, evaluate_price, parse_natural_query,
    set_user_city, get_user_city_db, get_admin_city_stats,
)
from config import (
    FREE_VIEWS, BOT_FREE_MODE, DISTRICTS, ADMIN_IDS, CHANNEL_LINK, CITIES,
    CITY_DISTRICTS, resolve_search_cities, get_cities_in_radius,
    MIN_LISTINGS_PLATFORM_HINT,
    CITY_MENU_STYLE, BOOKING_LOCATIONS, AIRBNB_LOCATIONS, flatio_daily_url,
    DISTRICT_ALL, is_all_district,
)
from config import REFERRAL_REQUIRED, REFERRAL_REWARD_DAYS
from bot.i18n import t
from datetime import datetime, timedelta
import urllib.parse


router = Router()

# ── Source icons ─────────────────────────────────────────────
SOURCE_ICONS = {
    "OLX": "🟠", "Otodom": "🔵", "Gratka": "🟢", "Morizon": "🟣",
    "Adresowo": "🟡", "Domiporta": "🔴", "Lento": "🟤", "Szybko": "🔷",
}


def search_exclude_ids(user_id: int, state_data: dict | None = None) -> list | None:
    """Exclude hidden + optionally seen — same logic for count and listing."""
    hide_seen = None
    if state_data is not None and "hide_seen" in state_data:
        hide_seen = state_data.get("hide_seen")
    return get_search_exclude_ids(user_id, hide_seen=hide_seen)


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
    if code == "en":
        return "en"
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
    set_cookie = State()

class ReportState(StatesGroup):
    waiting_reason = State()

class NoteState(StatesGroup):
    waiting_note = State()

class FeedbackState(StatesGroup):
    waiting_text = State()

class CityState(StatesGroup):
    waiting_city = State()

class DailyState(StatesGroup):
    waiting_location  = State()   # city or custom location
    waiting_checkin   = State()   # check-in date
    waiting_checkout  = State()   # check-out date
    waiting_guests    = State()   # number of guests
    waiting_type      = State()   # apartment/house/room/hostel
    waiting_area_min   = State()
    waiting_price_per_m = State()
    waiting_rooms_max  = State()
    waiting_floor_min  = State()
    waiting_options    = State()  # photo_only, new_only toggles


# ── Apartment card builder ────────────────────────────────────

def _search_filters(user_id: int, filters: dict | None = None) -> dict:
    """Merge user city + radius into filter dict for DB queries."""
    f = dict(filters or {})
    city = f.get("city") or get_user_city_db(user_id)
    f["city"] = city
    if "search_radius_km" not in f:
        f["search_radius_km"] = get_user_search_radius(user_id)
    return f


def _apt_matches_user_city(apt: dict, city: str, radius_km: int | None = None) -> bool:
    """Skip listings outside selected city (and radius, if enabled)."""
    from validation.geographic import city_from_link
    allowed = set(resolve_search_cities(city, radius_km))
    link_city = city_from_link(apt.get("link", "") or "")
    if link_city and link_city not in allowed:
        return False
    apt_city = apt.get("city") or ""
    if apt_city and apt_city not in allowed:
        return False
    return True


def apt_text(apt: dict, lang: str = "ru") -> str:
    """Build rich apartment card text."""
    rooms_str = t(lang, "apt_rooms", n=apt["rooms"]) if apt.get("rooms") else ""
    area_str = t(lang, "apt_area", area=apt["area"]) if apt.get("area") else ""
    floor_str = t(lang, "apt_floor", floor=apt["floor"]) if apt.get("floor") else ""
    details = " · ".join(filter(None, [rooms_str, area_str, floor_str]))

    verified = t(lang, "apt_verified") if apt.get("verified") else ""
    icon = SOURCE_ICONS.get(apt.get("source", ""), "📡")

    price = apt.get("price", 0) or 0
    if price:
        ppm = ""
        if apt.get("area") and apt["area"] > 0:
            ppm = t(lang, "apt_ppm", ppm=int(price / apt["area"]))
        price_line = t(
            lang, "apt_price_month",
            price=f"{price:,}".replace(",", " "),
            ppm=ppm,
        )
    else:
        price_line = t(lang, "apt_no_price")

    furn_tag = ""
    if apt.get("furnished") == 1:
        furn_tag = t(lang, "apt_furnished")
    elif apt.get("furnished") == 0:
        furn_tag = t(lang, "apt_unfurnished")

    city = apt.get("city", "Warszawa")
    city_label = CITIES.get(city, {}).get("label", city)
    district = apt.get("district", "")
    location = f"{district}, {city_label}" if district else city_label

    lines = [
        f"{verified}{icon} <b>{apt.get('title', '—')}</b>",
        price_line,
        f"📍 {location}",
    ]
    if details or furn_tag:
        lines.append(f"📐 {details}{furn_tag}" if details else f"📐{furn_tag}")

    drop = get_price_drop(apt["id"]) if apt.get("id") else None
    if drop:
        lines.append(t(
            lang, "apt_price_drop",
            old=drop["old"], new=drop["new"], drop=drop["drop"],
        ))

    if price and apt.get("district"):
        try:
            ev = evaluate_price(price, apt.get("district", ""), apt.get("rooms"))
            verdict_map = {
                "cheap": t(lang, "verdict_cheap"),
                "below_avg": t(lang, "verdict_below_avg"),
                "fair": t(lang, "verdict_fair"),
                "above_avg": t(lang, "verdict_above_avg"),
                "overpriced": t(lang, "verdict_overpriced"),
            }
            if ev.get("verdict") and ev["verdict"] != "unknown" and ev.get("avg"):
                sign = "+" if ev.get("diff_pct", 0) > 0 else ""
                badge = verdict_map.get(ev["verdict"], "")
                if badge:
                    lines.append(t(
                        lang, "verdict_line",
                        badge=badge, sign=sign, pct=ev["diff_pct"], avg=ev["avg"],
                    ))
        except Exception:
            pass

    views = apt.get("apt_views", 0) or 0
    if views >= 20:
        lines.append(t(lang, "apt_views_hot", n=views))
    elif views >= 5:
        lines.append(t(lang, "apt_views_some", n=views))

    try:
        age = get_apt_age_days(apt)
        if age >= 14:
            lines.append(t(lang, "apt_stale_14", n=age))
        elif age >= 7:
            lines.append(t(lang, "apt_stale_7", n=age))
    except Exception:
        pass

    lines.append(
        f"\n🔗 <a href=\"{apt.get('link', '#')}\">{t(lang, 'apt_open')}</a>  "
        f"{icon} {apt.get('source', '')}"
    )
    lines.append(f"\n<i>⚠️ {t(lang, 'warn_check')}</i>")
    return "\n".join(lines)


def apt_keyboard(apt_id: int, lang: str = "ru", has_prev: bool = False) -> InlineKeyboardMarkup:
    """Apartment action keyboard."""
    row1 = [InlineKeyboardButton(text=t(lang, "btn_fav_add"), callback_data=f"fav_add:{apt_id}")]
    if has_prev:
        row1.append(InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="prev"))
    row1.append(InlineKeyboardButton(text=t(lang, "btn_next"), callback_data="next"))

    return InlineKeyboardMarkup(inline_keyboard=[
        row1,
        [
            InlineKeyboardButton(text="👍", callback_data=f"rate:1:{apt_id}"),
            InlineKeyboardButton(text="👎", callback_data=f"rate:-1:{apt_id}"),
            InlineKeyboardButton(text=t(lang, "btn_share"), callback_data=f"share:{apt_id}"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_hide"), callback_data=f"hide:{apt_id}"),
            InlineKeyboardButton(text=t(lang, "btn_seen"), callback_data=f"seen:{apt_id}"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_found"), callback_data=f"found:{apt_id}"),
            InlineKeyboardButton(text=t(lang, "btn_report"), callback_data=f"scam:{apt_id}"),
        ],
    ])


def _district_label(district: str, lang: str) -> str:
    if is_all_district(district):
        return t(lang, "filter_all_districts_label")
    return district


def _format_subs(subs: list[str], lang: str) -> str:
    if not subs:
        return t(lang, "stats_none")
    return ", ".join(_district_label(s, lang) for s in subs)


def districts_keyboard(action: str = "sub", city: str = "Warszawa", lang: str = "ru") -> InlineKeyboardMarkup:
    """Build districts keyboard for the given city."""
    city_districts = CITY_DISTRICTS.get(city, CITY_DISTRICTS["Warszawa"])
    buttons = []
    row = []
    for d in city_districts:
        row.append(InlineKeyboardButton(text=d, callback_data=f"{action}:{d}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(
        text=t(lang, "filter_all_districts"), callback_data=f"{action}:{DISTRICT_ALL}",
    )])
    buttons.append([InlineKeyboardButton(text=t(lang, "filter_cancel"), callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def price_keyboard(action: str, lang: str = "ru") -> InlineKeyboardMarkup:
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
    buttons.append([InlineKeyboardButton(text=t(lang, "filter_any"), callback_data=f"{action}:0")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def rooms_keyboard(action: str, lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "filter_room_btn", n=1), callback_data=f"{action}:1"),
            InlineKeyboardButton(text=t(lang, "filter_room_btn", n=2), callback_data=f"{action}:2"),
            InlineKeyboardButton(text=t(lang, "filter_room_btn", n=3), callback_data=f"{action}:3"),
            InlineKeyboardButton(text="4+", callback_data=f"{action}:4"),
        ],
        [InlineKeyboardButton(text=t(lang, "filter_any"), callback_data=f"{action}:0")],
    ])


def _menu_btn(lang: str, key: str, callback: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=t(lang, key), callback_data=callback)


def city_menu_keyboard(lang: str, city: str) -> InlineKeyboardMarkup:
    """City-specific menu layout — different order and emphasis per city."""
    style = CITY_MENU_STYLE.get(city, "quiet")
    style_key = f"menu_style_{style}"
    rows = [[InlineKeyboardButton(text=t(lang, style_key), callback_data="noop")]]

    B = lambda k, c: _menu_btn(lang, k, c)

    if style == "coastal":
        body = [
            [B("btn_daily", "open_daily"), B("btn_map", "open_map")],
            [B("btn_find", "next"), B("btn_filter", "open_filter")],
            [B("btn_hot", "open_hot"), B("btn_cheap", "open_cheap")],
            [B("btn_favorites", "open_favorites"), B("btn_alerts", "open_alerts")],
            [B("btn_drops", "open_drops"), B("btn_mystats", "open_stats")],
            [B("btn_subscribe", "open_subscribe"), B("btn_ref", "open_ref")],
            [B("btn_notes", "open_notes"), B("btn_digest", "open_digest")],
            [B("btn_advanced", "open_advanced")],
            [B("btn_settings", "open_settings"), B("btn_change_city", "open_city_pick")],
        ]
    elif style == "capital":
        body = [
            [B("btn_find", "next"), B("btn_filter", "open_filter")],
            [B("btn_hot", "open_hot"), B("btn_daily", "open_daily")],
            [B("btn_map", "open_map"), B("btn_cheap", "open_cheap")],
            [B("btn_favorites", "open_favorites"), B("btn_alerts", "open_alerts")],
            [B("btn_drops", "open_drops"), B("btn_mystats", "open_stats")],
            [B("btn_subscribe", "open_subscribe"), B("btn_ref", "open_ref")],
            [B("btn_notes", "open_notes"), B("btn_advanced", "open_advanced")],
            [B("btn_settings", "open_settings"), B("btn_change_city", "open_city_pick")],
        ]
    elif style == "industrial":
        body = [
            [B("btn_cheap", "open_cheap"), B("btn_find", "next")],
            [B("btn_filter", "open_filter"), B("btn_hot", "open_hot")],
            [B("btn_daily", "open_daily"), B("btn_map", "open_map")],
            [B("btn_favorites", "open_favorites"), B("btn_alerts", "open_alerts")],
            [B("btn_drops", "open_drops"), B("btn_mystats", "open_stats")],
            [B("btn_subscribe", "open_subscribe"), B("btn_ref", "open_ref")],
            [B("btn_notes", "open_notes"), B("btn_digest", "open_digest")],
            [B("btn_advanced", "open_advanced")],
            [B("btn_settings", "open_settings"), B("btn_change_city", "open_city_pick")],
        ]
    elif style == "culture":
        body = [
            [B("btn_find", "next"), B("btn_hot", "open_hot")],
            [B("btn_filter", "open_filter"), B("btn_daily", "open_daily")],
            [B("btn_map", "open_map"), B("btn_cheap", "open_cheap")],
            [B("btn_favorites", "open_favorites"), B("btn_alerts", "open_alerts")],
            [B("btn_drops", "open_drops"), B("btn_mystats", "open_stats")],
            [B("btn_subscribe", "open_subscribe"), B("btn_ref", "open_ref")],
            [B("btn_notes", "open_notes"), B("btn_digest", "open_digest")],
            [B("btn_advanced", "open_advanced")],
            [B("btn_settings", "open_settings"), B("btn_change_city", "open_city_pick")],
        ]
    elif style == "business":
        body = [
            [B("btn_find", "next"), B("btn_map", "open_map")],
            [B("btn_filter", "open_filter"), B("btn_cheap", "open_cheap")],
            [B("btn_hot", "open_hot"), B("btn_daily", "open_daily")],
            [B("btn_favorites", "open_favorites"), B("btn_alerts", "open_alerts")],
            [B("btn_drops", "open_drops"), B("btn_mystats", "open_stats")],
            [B("btn_subscribe", "open_subscribe"), B("btn_ref", "open_ref")],
            [B("btn_notes", "open_notes"), B("btn_advanced", "open_advanced")],
            [B("btn_settings", "open_settings"), B("btn_change_city", "open_city_pick")],
        ]
    else:  # quiet
        body = [
            [B("btn_find", "next"), B("btn_filter", "open_filter")],
            [B("btn_cheap", "open_cheap"), B("btn_daily", "open_daily")],
            [B("btn_favorites", "open_favorites"), B("btn_hot", "open_hot")],
            [B("btn_alerts", "open_alerts"), B("btn_map", "open_map")],
            [B("btn_drops", "open_drops"), B("btn_mystats", "open_stats")],
            [B("btn_subscribe", "open_subscribe"), B("btn_ref", "open_ref")],
            [B("btn_notes", "open_notes"), B("btn_digest", "open_digest")],
            [B("btn_advanced", "open_advanced")],
            [B("btn_settings", "open_settings"), B("btn_change_city", "open_city_pick")],
        ]

    body.append([B("btn_platforms", "open_platforms")])
    return InlineKeyboardMarkup(inline_keyboard=rows + body)


def city_quick_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Quick actions right after city change."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "btn_find"), callback_data="next"),
            InlineKeyboardButton(text=t(lang, "btn_platforms"), callback_data="open_platforms"),
            InlineKeyboardButton(text=t(lang, "btn_filter"), callback_data="open_filter"),
        ],
        [InlineKeyboardButton(text=t(lang, "btn_menu"), callback_data="open_menu")],
    ])


def main_menu_keyboard(lang: str, city: str = "Warszawa") -> InlineKeyboardMarkup:
    return city_menu_keyboard(lang, city)


def build_menu_text(user_id: int, lang: str, city: str, name: str, user: dict, extra: str = "") -> str:
    city_label = CITIES.get(city, {}).get("label", city)
    count = count_apartments(_search_filters(user_id, {"city": city}), vip=True)
    vip_badge = _status_badge(user, lang)
    new_msg = ""
    last_visit = get_last_visit(user_id)
    if last_visit:
        new_count = get_new_since(last_visit)
        if new_count > 0:
            new_msg = t(lang, "new_since_visit", n=new_count)
    return t(lang, "start_greeting", name=name, badge=vip_badge, city=city_label, count=count) + extra + new_msg


def city_keyboard() -> InlineKeyboardMarkup:
    """City selection keyboard (two cities per row)."""
    items = list(CITIES.items())
    rows = []
    for i in range(0, len(items), 2):
        row = [
            InlineKeyboardButton(
                text=items[j][1]["label"],
                callback_data=f"city_select:{items[j][0]}",
            )
            for j in range(i, min(i + 2, len(items)))
        ]
        rows.append(row)
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

    # Restore city from DB so /start doesn't reset it
    saved_city = get_user_city_db(message.from_user.id)
    await state.update_data(
        city=saved_city,
        hide_seen=get_user_hide_seen(message.from_user.id),
    )

    # Detect new user (registered < 60s ago)
    is_new = False
    created = user.get("created_at", "")
    if created:
        try:
            is_new = (datetime.now() - datetime.fromisoformat(created)).total_seconds() < 60
        except Exception:
            pass

    if len(args) > 1:
        ref_arg = args[1]
        await state.update_data(pending_ref=ref_arg)
        if ref_arg.startswith("ref_") and not is_new:
            if apply_referral(message.from_user.id, ref_arg[4:]):
                lang = get_lang(message.from_user.id)
                await message.answer(t(lang, "ref_bonus"))

    if is_new:
        detected = auto_detect_lang(message.from_user.language_code)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Русский",    callback_data="onboard_lang:ru"),
                InlineKeyboardButton(text="🇺🇦 Українська", callback_data="onboard_lang:uk"),
            ],
            [
                InlineKeyboardButton(text="🇵🇱 Polski",     callback_data="onboard_lang:pl"),
                InlineKeyboardButton(text="🇬🇧 English",    callback_data="onboard_lang:en"),
            ],
        ])
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
        t(lang, "onboard_city_step"),
        parse_mode="HTML",
        reply_markup=kb,
    )
    await state.update_data(onboard_lang=lang)


@router.callback_query(F.data.startswith("city_select:"))
async def cb_city_select(call: CallbackQuery, state: FSMContext):
    city = call.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("onboard_lang") or get_lang(call.from_user.id)
    city_label = CITIES.get(city, {}).get("label", city)

    # Save city in FSM AND in DB — reset pagination and history
    set_user_city(call.from_user.id, city)
    await state.update_data(
        city=city,
        daily_city=city,
        daily_location=city_label,
        filters={},
        offset=0,
        history=[],
    )

    # Onboarding: city picked after terms — finish setup
    if data.get("onboard_lang"):
        await call.answer(t(lang, "city_alert", city=city_label), show_alert=True)
        try:
            await call.message.delete()
        except Exception:
            pass
        pending_ref = data.get("pending_ref", "")
        if pending_ref and pending_ref.startswith("ref_"):
            if apply_referral(call.from_user.id, pending_ref[4:]):
                await call.message.answer(t(lang, "ref_bonus"))
        user = get_or_create_user(call.from_user.id)
        name = call.from_user.first_name or t(lang, "friend_default")
        text = build_menu_text(call.from_user.id, lang, city, name, user)
        await call.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=city_menu_keyboard(lang, city),
        )
        await show_next_apartment(call.from_user.id, call.bot, state, call.message.chat.id)
        await state.update_data(onboard_lang=None)
    else:
        # City change from /city command — confirm and show menu
        await call.answer(t(lang, "city_alert", city=city_label), show_alert=True)
        try:
            await call.message.delete()
        except Exception:
            pass
        # Show updated main menu with new city
        user = get_or_create_user(call.from_user.id)
        name = call.from_user.first_name or t(lang, "friend_default")
        count = count_apartments(_search_filters(call.from_user.id, {"city": city}), vip=True)
        await call.message.answer(
            t(lang, "city_changed", city=city_label, count=count),
            parse_mode="HTML",
            reply_markup=city_quick_keyboard(lang),
        )
        if count < MIN_LISTINGS_PLATFORM_HINT:
            await call.message.answer(
                t(lang, "platforms_intro"),
                parse_mode="HTML",
                reply_markup=_external_search_keyboard(lang, city),
            )


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
    name = call.from_user.first_name or t(lang, "friend_default")
    city = data.get("city", "Warszawa")
    text = build_menu_text(call.from_user.id, lang, city, name, user)
    await call.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=city_menu_keyboard(lang, city),
    )
    await show_next_apartment(call.from_user.id, call.bot, state, call.message.chat.id)


@router.callback_query(F.data == "onboard_decline")
async def cb_onboard_decline(call: CallbackQuery):
    await call.answer()
    lang = get_lang(call.from_user.id)
    await call.message.edit_text(t(lang, "decline_terms"))


def _status_badge(user: dict, lang: str) -> str:
    if BOT_FREE_MODE:
        return t(lang, "free_unlimited_badge")
    used = user.get("views", 0)
    bar = "🟩" * min(used, FREE_VIEWS) + "⬜" * max(0, FREE_VIEWS - used)
    return t(lang, "free_badge", bar=bar, used=used, total=FREE_VIEWS)


async def _show_main_menu(message, user: dict, from_user=None):
    fu = from_user or message.from_user
    lang = get_lang(fu.id)
    name = fu.first_name or t(lang, "friend_default")

    extra = ""
    city = get_user_city_db(fu.id)
    update_last_visit(fu.id)
    text = build_menu_text(fu.id, lang, city, name, user, extra=extra)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=city_menu_keyboard(lang, city),
    )


# ── /menu ────────────────────────────────────────────────────

@router.message(Command("menu"))
async def cmd_menu(message: Message):
    lang = get_lang(message.from_user.id)
    user = get_or_create_user(message.from_user.id)
    name = message.from_user.first_name or t(lang, "friend_default")
    city = get_user_city_db(message.from_user.id)
    text = build_menu_text(message.from_user.id, lang, city, name, user)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=city_menu_keyboard(lang, city),
    )


@router.callback_query(F.data == "open_city_pick")
async def cb_open_city_pick(call: CallbackQuery, state: FSMContext):
    await call.answer()
    lang = get_lang(call.from_user.id)
    data = await state.get_data()
    current = data.get("city") or get_user_city_db(call.from_user.id)
    current_label = CITIES.get(current, {}).get("label", current)
    await call.message.answer(
        t(lang, "city_pick_title", city=current_label) + t(lang, "city_pick_hint"),
        parse_mode="HTML",
        reply_markup=city_keyboard(),
    )


@router.message(Command("city"))
async def cmd_city(message: Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    data = await state.get_data()
    current = data.get("city") or get_user_city_db(message.from_user.id)
    current_label = CITIES.get(current, {}).get("label", current)
    await message.answer(
        t(lang, "city_pick_title", city=current_label) + t(lang, "city_pick_hint"),
        parse_mode="HTML",
        reply_markup=city_keyboard(),
    )


@router.callback_query(F.data == "open_platforms")
async def cb_open_platforms(call: CallbackQuery):
    await call.answer()
    lang = get_lang(call.from_user.id)
    city = get_user_city_db(call.from_user.id)
    await call.message.answer(
        t(lang, "platforms_intro"),
        parse_mode="HTML",
        reply_markup=_external_search_keyboard(lang, city),
    )


@router.callback_query(F.data == "open_menu")
async def cb_open_menu(call: CallbackQuery):
    await call.answer()
    lang = get_lang(call.from_user.id)
    user = get_or_create_user(call.from_user.id)
    name = call.from_user.first_name or t(lang, "friend_default")
    city = get_user_city_db(call.from_user.id)
    text = build_menu_text(call.from_user.id, lang, city, name, user)
    await call.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=city_menu_keyboard(lang, city),
    )


# ── /next — show apartment ────────────────────────────────────

def _external_search_keyboard(lang: str, city: str) -> InlineKeyboardMarkup:
    from bot.search_links import city_platform_urls
    urls = city_platform_urls(city)
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "btn_search_olx"), url=urls["olx"]),
            InlineKeyboardButton(text=t(lang, "btn_search_otodom"), url=urls["otodom"]),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_search_gratka"), url=urls["gratka"]),
            InlineKeyboardButton(text=t(lang, "btn_search_morizon"), url=urls["morizon"]),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_reset_filters"), callback_data="reset_filters"),
            InlineKeyboardButton(text=t(lang, "btn_change_filter"), callback_data="open_filter"),
        ],
        [InlineKeyboardButton(text=t(lang, "btn_all_apts"), callback_data="next")],
    ])


async def _send_no_apts(bot, chat_id: int, filters: dict, lang: str):
    """No results — hints + direct links to OLX/Otodom/Gratka/Morizon for this city."""
    parts = []
    city = filters.get("city", "Warszawa")
    city_label = CITIES.get(city, {}).get("label", city)

    if filters.get("district"):
        parts.append(f"📍 {filters['district']}")
    if filters.get("price_max"):
        parts.append(t(lang, "filter_price_max", price=filters["price_max"]))
    if filters.get("rooms"):
        parts.append(t(lang, "filter_rooms_n", n=filters["rooms"]))
    if filters.get("furnished") == 1:
        parts.append(t(lang, "filter_furnished"))
    elif filters.get("furnished") == 0:
        parts.append(t(lang, "filter_unfurnished"))

    base = {"city": city}
    if filters.get("search_radius_km") is not None:
        base["search_radius_km"] = filters["search_radius_km"]
    total_in_district = 0
    if filters.get("district"):
        total_in_district = count_apartments(
            {**base, "district": filters["district"]}, vip=True
        )
    total_all = count_apartments(base, vip=True)

    searched = "  ·  ".join(parts) if parts else t(lang, "filter_all_apts")

    text = t(lang, "no_apts_title")
    text += t(lang, "no_apts_searched", searched=searched)
    text += t(lang, "no_apts_city", city=city_label)

    if total_in_district > 0 and filters.get("district"):
        text += t(
            lang, "no_apts_district_hint",
            district=filters["district"], n=total_in_district,
        )
    elif total_all > 0:
        text += t(lang, "no_apts_city_hint", city=city_label, n=total_all)
    else:
        text += t(lang, "no_apts_empty_db")

    text += t(lang, "no_apts_alt_title")
    text += t(lang, "no_apts_actions")

    await bot.send_message(
        chat_id, text, parse_mode="HTML",
        reply_markup=_external_search_keyboard(lang, city),
    )


async def show_next_apartment(user_id: int, bot, state: FSMContext, chat_id: int):
    user = get_or_create_user(user_id)
    is_vip = bool(user.get("vip"))
    lang = get_lang(user_id)
    data = await state.get_data()

    if not BOT_FREE_MODE and user.get("views", 0) >= FREE_VIEWS and not is_vip:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "limit_ref_btn"), callback_data="open_ref")],
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

    # DB city is source of truth — prevents stale FSM showing wrong city listings
    city = get_user_city_db(user_id)
    radius_km = get_user_search_radius(user_id)
    await state.update_data(city=city)
    city_filters = _search_filters(user_id, filters)
    exclude_ids = search_exclude_ids(user_id, data)

    total = count_apartments(city_filters, vip=is_vip, exclude_ids=exclude_ids)
    if total == 0:
        await _send_no_apts(bot, chat_id, city_filters, lang)
        return
    if offset >= total:
        if offset > 0:
            await state.update_data(offset=0)
            offset = 0
            await bot.send_message(chat_id, t(lang, "wrap_around"))
        else:
            await _send_no_apts(bot, chat_id, city_filters, lang)
            return

    apt = None
    skip = 0
    batch_offset = offset
    while apt is None and batch_offset < total:
        apartments = get_apartments(
            filters=city_filters,
            offset=batch_offset,
            limit=8,
            vip=is_vip,
            exclude_ids=exclude_ids,
        )
        if not apartments:
            break
        for i, candidate in enumerate(apartments):
            if _apt_matches_user_city(candidate, city, radius_km):
                apt = candidate
                skip = batch_offset - offset + i
                break
        batch_offset += len(apartments)

    if not apt:
        await _send_no_apts(bot, chat_id, city_filters, lang)
        return

    mark_seen(user_id, apt["id"])
    history = data.get("history", [])
    if apt["id"] not in history:
        history = (history + [apt["id"]])[-5:]
    await state.update_data(
        offset=offset + skip + 1,
        last_apt_id=apt["id"],
        history=history,
    )
    increment_views(user_id)
    increment_apt_views(apt["id"])
    record_user_activity(user_id)

    text = apt_text(apt, lang)
    if apt.get("city") and apt.get("city") != city:
        near_label = CITIES.get(apt["city"], {}).get("label", apt["city"])
        text = t(lang, "apt_nearby_badge", city=near_label) + "\n" + text
    remaining = max(0, total - offset - skip - 1)
    if remaining > 0:
        text += t(lang, "remaining", n=remaining)

    if not BOT_FREE_MODE:
        views_used = user.get("views", 0) + 1
        if not is_vip and views_used == FREE_VIEWS - 1:
            text += t(lang, "limit_one_left", limit=FREE_VIEWS)

    kb = apt_keyboard(apt["id"], lang=lang, has_prev=len(history) > 1)
    from bot.search_links import city_platform_urls
    urls = city_platform_urls(city)
    kb.inline_keyboard.append([
        InlineKeyboardButton(text=t(lang, "btn_search_olx"), url=urls["olx"]),
        InlineKeyboardButton(text=t(lang, "btn_platforms"), callback_data="open_platforms"),
    ])
    apt_city = apt.get("city", city)
    apt_label = CITIES.get(apt_city, {}).get("label", apt_city)
    district = apt.get("district", "")
    map_location = f"{district}, {apt_label}" if district else apt_label
    map_url = f"https://www.google.com/maps/search/{urllib.parse.quote(map_location)}"
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


@router.callback_query(F.data == "prev")
async def cb_prev(call: CallbackQuery, state: FSMContext):
    """Go back to previous apartment."""
    await call.answer()
    data = await state.get_data()
    history = data.get("history", [])
    current_id = data.get("last_apt_id")

    # Remove current from history to get previous
    if current_id in history:
        history.remove(current_id)
    lang = get_lang(call.from_user.id)
    if not history:
        await call.message.answer(t(lang, "prev_none"))
        return

    prev_id = history[-1]
    apt = get_apartment_by_id(prev_id)
    if not apt:
        await call.message.answer(t(lang, "prev_gone"))
        return

    await state.update_data(history=history, last_apt_id=prev_id,
                            offset=max(0, data.get("offset", 1) - 1))

    text = apt_text(apt, lang)
    kb = apt_keyboard(apt["id"], lang=lang, has_prev=len(history) > 1)
    city = apt.get("city", "Warszawa")
    district = apt.get("district", "")
    map_location = f"{district}, {city}" if district else city
    map_url = f"https://www.google.com/maps/search/{urllib.parse.quote(map_location)}"
    kb.inline_keyboard.append([
        InlineKeyboardButton(text=t(lang, "btn_on_map"), url=map_url),
        InlineKeyboardButton(text=t(lang, "btn_similar"), callback_data=f"similar:{apt['id']}"),
    ])

    image = apt.get("image", "")
    sent = False
    if image and image.startswith("http") and len(image) > 15:
        try:
            await call.bot.send_photo(call.message.chat.id, image, caption=text,
                                      reply_markup=kb, parse_mode="HTML")
            sent = True
        except Exception:
            pass
    if not sent:
        await call.bot.send_message(call.message.chat.id, text, reply_markup=kb, parse_mode="HTML")


# ── /filter ──────────────────────────────────────────────────

@router.message(Command("filter"))
async def cmd_filter(message: Message, state: FSMContext):
    lang = get_lang(message.from_user.id)
    data = await state.get_data()
    city = data.get("city", get_user_city_db(message.from_user.id))
    await state.set_state(FilterState.waiting_district)
    await message.answer(
        t(lang, "filter_step1"),
        parse_mode="HTML",
        reply_markup=districts_keyboard("filter_d", city, lang),
    )


@router.callback_query(F.data == "open_filter")
async def cb_open_filter(call: CallbackQuery, state: FSMContext):
    await call.answer()
    lang = get_lang(call.from_user.id)
    data = await state.get_data()
    city = data.get("city", get_user_city_db(call.from_user.id))
    await state.set_state(FilterState.waiting_district)
    await call.message.answer(
        t(lang, "filter_step1"),
        parse_mode="HTML",
        reply_markup=districts_keyboard("filter_d", city, lang),
    )


@router.callback_query(F.data.startswith("filter_d:"))
async def cb_filter_district(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    district = call.data.split(":", 1)[1]
    filters = {} if is_all_district(district) else {"district": district}
    await state.update_data(filters=filters, offset=0)
    label = _district_label(district, lang)
    await call.message.edit_text(
        t(lang, "filter_district_set", label=label) + t(lang, "filter_step2"),
        parse_mode="HTML",
        reply_markup=price_keyboard("filter_pmax", lang),
    )
    await state.set_state(FilterState.waiting_price_max)


@router.callback_query(F.data.startswith("filter_pmax:"))
async def cb_filter_price_max(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    filters = data.get("filters", {})
    if val > 0:
        filters["price_max"] = val
    await state.update_data(filters=filters)
    label = f"{val} zł" if val else t(lang, "filter_price_any")
    await call.message.edit_text(
        t(lang, "filter_price_set", label=label) + t(lang, "filter_step3"),
        parse_mode="HTML",
        reply_markup=rooms_keyboard("filter_rooms", lang),
    )
    await state.set_state(FilterState.waiting_rooms)


@router.callback_query(F.data.startswith("filter_rooms:"))
async def cb_filter_rooms(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    filters = data.get("filters", {})
    if val > 0:
        filters["rooms"] = val
    await state.update_data(filters=filters)
    label = t(lang, "filter_rooms_any") if val == 0 else str(val)
    await call.message.edit_text(
        t(lang, "filter_rooms_set", label=label) + t(lang, "filter_step4"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "filter_furn_yes"), callback_data="filter_furn:1"),
                InlineKeyboardButton(text=t(lang, "filter_furn_no"), callback_data="filter_furn:0"),
                InlineKeyboardButton(text=t(lang, "filter_furn_any"), callback_data="filter_furn:any"),
            ],
        ]),
    )
    await state.set_state(FilterState.waiting_furnished)


@router.callback_query(F.data.startswith("filter_furn:"))
async def cb_filter_furnished(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    val = call.data.split(":")[1]
    data = await state.get_data()
    filters = data.get("filters", {})
    if val == "1":
        filters["furnished"] = 1
    elif val == "0":
        filters["furnished"] = 0

    filters = _search_filters(call.from_user.id, filters)
    city = filters["city"]

    await state.update_data(filters=filters, offset=0)
    await state.set_state(None)

    user = get_or_create_user(call.from_user.id)
    exclude_ids = search_exclude_ids(call.from_user.id, data)
    total = count_apartments(filters, vip=bool(user.get("vip")), exclude_ids=exclude_ids)

    parts = []
    city_label = CITIES.get(city, {}).get("label", city)
    parts.append(f"📍 {city_label}")
    if filters.get("district"):
        parts.append(f"{filters['district']}")
    if filters.get("price_max"):
        parts.append(t(lang, "filter_price_max", price=filters["price_max"]))
    if filters.get("rooms"):
        parts.append(t(lang, "filter_rooms_n", n=filters["rooms"]))
    if filters.get("furnished") == 1:
        parts.append(t(lang, "filter_furnished"))
    elif filters.get("furnished") == 0:
        parts.append(t(lang, "filter_unfurnished"))

    summary = "  ·  ".join(parts)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=t(lang, "filter_view_btn", total=total),
            callback_data="next",
        )],
        [InlineKeyboardButton(text=t(lang, "btn_reset_filters"), callback_data="reset_filters")],
    ])
    hint = t(lang, "filter_hide_seen_hint") if get_user_hide_seen(call.from_user.id) else ""
    await call.message.edit_text(
        t(lang, "filter_applied", summary=summary, total=total, hint=hint),
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(F.data == "reset_filters")
async def cb_reset_filters(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    await state.update_data(filters={}, offset=0)
    await call.answer(t(lang, "filter_reset_ok"), show_alert=True)


# ── /ask — natural language search ───────────────────────────

@router.message(Command("ask"))
async def cmd_ask(message: Message, state: FSMContext):
    args = message.text.split(maxsplit=1)
    lang = get_lang(message.from_user.id)
    if len(args) < 2:
        await message.answer(t(lang, "ask_help"), parse_mode="HTML")
        return

    query = args[1].strip()
    try:
        filters = parse_natural_query(query)
    except Exception:
        filters = {}

    if not filters:
        await message.answer(t(lang, "ask_fail"), parse_mode="HTML")
        return

    user = get_or_create_user(message.from_user.id)
    data = await state.get_data()
    filters = _search_filters(message.from_user.id, filters)
    await state.update_data(filters=filters, offset=0)
    exclude_ids = search_exclude_ids(message.from_user.id, data)
    total = count_apartments(filters, vip=bool(user.get("vip")), exclude_ids=exclude_ids)

    parts = []
    if filters.get("rooms"):
        parts.append(t(lang, "filter_rooms_n", n=filters["rooms"]))
    if filters.get("district"):
        parts.append(f"📍 {filters['district']}")
    if filters.get("price_max"):
        parts.append(t(lang, "filter_price_max", price=filters["price_max"]))
    if filters.get("furnished") == 1:
        parts.append(t(lang, "filter_furnished"))

    summary = "  ·  ".join(parts) if parts else t(lang, "filter_all_apts")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "filter_view_btn", total=total), callback_data="next"),
        InlineKeyboardButton(text=t(lang, "btn_change_filter"), callback_data="open_filter"),
    ]])
    await message.answer(
        t(lang, "ask_ok", summary=summary, total=total),
        parse_mode="HTML",
        reply_markup=kb,
    )

# ── /favorites ───────────────────────────────────────────────

@router.message(Command("favorites"))
async def cmd_favorites(message: Message):
    await _show_favorites(message.from_user.id, message, page=0)


@router.callback_query(F.data == "open_favorites")
async def cb_open_favorites(call: CallbackQuery):
    await call.answer()
    await _show_favorites(call.from_user.id, call.message, page=0)


@router.callback_query(F.data.startswith("fav_page:"))
async def cb_fav_page(call: CallbackQuery):
    await call.answer()
    page = int(call.data.split(":")[1])
    await _show_favorites(call.from_user.id, call.message, page=page)


async def _show_favorites(user_id: int, target, page: int = 0):
    lang = get_lang(user_id)
    favs = get_favorites(user_id)
    if not favs:
        await target.answer(t(lang, "fav_empty"), parse_mode="HTML")
        return

    PAGE_SIZE = 5
    total = len(favs)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    page_favs = favs[page * PAGE_SIZE: (page + 1) * PAGE_SIZE]

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"fav_page:{page-1}"))
    nav_row.append(InlineKeyboardButton(
        text=t(lang, "fav_nav", page=page + 1, total_pages=total_pages, total=total),
        callback_data="noop",
    ))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"fav_page:{page+1}"))

    header_kb = InlineKeyboardMarkup(inline_keyboard=[nav_row])
    if len(favs) >= 2:
        header_kb.inline_keyboard.append([
            InlineKeyboardButton(text=t(lang, "fav_compare_btn"), callback_data="open_compare"),
        ])

    await target.answer(
        t(lang, "fav_header", page=page + 1, total_pages=total_pages, total=total),
        parse_mode="HTML",
        reply_markup=header_kb,
    )
    for apt in page_favs:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t(lang, "fav_delete"), callback_data=f"fav_remove:{apt['id']}"),
            InlineKeyboardButton(text=t(lang, "btn_open_link"), url=apt["link"]),
        ]])
        await target.answer(apt_text(apt, lang), reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("fav_add:"))
async def cb_fav_add(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    add_favorite(call.from_user.id, apt_id)
    await call.answer(t(get_lang(call.from_user.id), "fav_added"))


@router.callback_query(F.data.startswith("fav_remove:"))
async def cb_fav_remove(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    remove_favorite(call.from_user.id, apt_id)
    await call.answer(t(get_lang(call.from_user.id), "fav_removed"))
    try:
        await call.message.delete()
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
    lang = get_lang(user_id)
    user = get_or_create_user(user_id)
    alerts = get_user_alerts(user_id)
    limit = get_alert_limit()
    rows = []
    if len(alerts) < limit:
        rows.append([InlineKeyboardButton(
            text=t(lang, "alert_btn_create"),
            callback_data="alert_create",
        )])
    for a in alerts:
        district = a.get("district") or t(lang, "alert_any_district")
        price_max = a.get("price_max") or "∞"
        apt_city = a.get("city") or ""
        city_tag = f" · {apt_city}" if apt_city else ""
        rows.append([InlineKeyboardButton(
            text=t(lang, "alert_item", id=a["id"], district=district, price_max=price_max, city=city_tag),
            callback_data=f"alert_del:{a['id']}",
        )])
    kb = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
    await target.answer(
        t(lang, "alert_list", n=len(alerts), limit=limit, hint=""),
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(F.data == "alert_create")
async def cb_alert_create(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    user = get_or_create_user(call.from_user.id)
    limit = get_alert_limit()
    if len(get_user_alerts(call.from_user.id)) >= limit:
        await call.answer(t(lang, "alert_limit_reached", limit=limit), show_alert=True)
        return
    await call.answer()
    data = await state.get_data()
    city = data.get("city", get_user_city_db(call.from_user.id))
    await state.update_data(alert_city=city)
    await call.message.answer(
        t(lang, "alert_pick_district"),
        reply_markup=districts_keyboard("alert_d", city, lang),
    )
    await state.set_state(AlertState.waiting_district)


@router.callback_query(F.data.startswith("alert_d:"))
async def cb_alert_district(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    district = call.data.split(":", 1)[1]
    await state.update_data(alert_district=None if is_all_district(district) else district)
    await call.message.edit_text(
        t(lang, "alert_pick_price"),
        reply_markup=price_keyboard("alert_pmax"),
    )
    await state.set_state(AlertState.waiting_price_max)


@router.callback_query(F.data.startswith("alert_pmax:"), AlertState.waiting_price_max)
async def cb_alert_price_max(call: CallbackQuery, state: FSMContext):
    val = int(call.data.split(":")[1])
    lang = get_lang(call.from_user.id)
    await state.update_data(alert_price_max=val if val > 0 else None)
    await call.message.edit_text(
        t(lang, "alert_pick_rooms"),
        reply_markup=rooms_keyboard("alert_rooms"),
    )
    await state.set_state(AlertState.waiting_rooms)


@router.callback_query(F.data.startswith("alert_rooms:"), AlertState.waiting_rooms)
async def cb_alert_rooms(call: CallbackQuery, state: FSMContext):
    val = int(call.data.split(":")[1])
    lang = get_lang(call.from_user.id)
    data = await state.get_data()
    await state.set_state(None)
    city = data.get("alert_city") or get_user_city_db(call.from_user.id)
    create_alert(
        call.from_user.id,
        district=data.get("alert_district"),
        price_min=None,
        price_max=data.get("alert_price_max"),
        rooms=val if val > 0 else None,
        city=city,
    )
    parts = []
    city_label = CITIES.get(city, {}).get("label", city)
    parts.append(city_label)
    if data.get("alert_district"):
        parts.append(f"📍 {data['alert_district']}")
    if data.get("alert_price_max"):
        parts.append(t(lang, "adv_part_price", price=data["alert_price_max"]))
    if val > 0:
        parts.append(t(lang, "filter_rooms_n", n=val))
    summary = " · ".join(parts) if parts else t(lang, "adv_summary_all")
    await call.message.edit_text(t(lang, "alert_created", summary=summary), parse_mode="HTML")


@router.callback_query(F.data.startswith("alert_del:"))
async def cb_alert_del(call: CallbackQuery):
    delete_alert(int(call.data.split(":")[1]), call.from_user.id)
    await call.answer(t(get_lang(call.from_user.id), "alert_deleted"))
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

    lang = get_lang(user_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "ref_share_btn"), switch_inline_query=ref_link)],
        [InlineKeyboardButton(text=t(lang, "leaderboard_btn"), callback_data="open_leaderboard")],
    ])
    await target.answer(
        t(
            lang, "ref_body",
            link=ref_link,
            count=ref_count,
            bar=bar,
            progress=ref_count % REFERRAL_REQUIRED,
            required=REFERRAL_REQUIRED,
            next_reward=next_reward,
        ),
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


@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext):
    await _show_settings(message.from_user.id, message, state)


@router.callback_query(F.data == "open_settings")
async def cb_open_settings(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _show_settings(call.from_user.id, call.message, state)


@router.callback_query(F.data == "toggle_hide_seen")
async def cb_toggle_hide_seen(call: CallbackQuery, state: FSMContext):
    hide = not get_user_hide_seen(call.from_user.id)
    set_user_hide_seen(call.from_user.id, hide)
    await state.update_data(hide_seen=hide)
    await call.answer(t(get_lang(call.from_user.id), "settings_saved"))
    await _show_settings(call.from_user.id, call.message, state, edit=True)


@router.callback_query(F.data == "toggle_search_radius")
async def cb_toggle_search_radius(call: CallbackQuery, state: FSMContext):
    from config import SEARCH_RADIUS_KM_DEFAULT
    uid = call.from_user.id
    current = get_user_search_radius(uid)
    new_radius = 0 if current > 0 else SEARCH_RADIUS_KM_DEFAULT
    set_user_search_radius(uid, new_radius)
    await call.answer(t(get_lang(uid), "settings_saved"))
    await _show_settings(uid, call.message, state, edit=True)


async def _show_settings(user_id: int, target, state: FSMContext, edit: bool = False):
    lang = get_lang(user_id)
    hide = get_user_hide_seen(user_id)
    await state.update_data(hide_seen=hide)
    city = (await state.get_data()).get("city") or get_user_city_db(user_id)
    city_label = CITIES.get(city, {}).get("label", city)
    radius_km = get_user_search_radius(user_id)
    nearby = get_cities_in_radius(city, radius_km) if radius_km > 0 else [city]
    nearby_labels = ", ".join(
        CITIES.get(c, {}).get("label", c).split(" ", 1)[-1]
        if " " in CITIES.get(c, {}).get("label", c) else c
        for c in nearby[1:4]
    )
    if len(nearby) > 4:
        nearby_labels += f" +{len(nearby) - 4}"
    extra_part = f" ({nearby_labels})" if nearby_labels else ""
    toggle_hide = t(lang, "settings_hide_seen_on") if hide else t(lang, "settings_hide_seen_off")
    toggle_radius = (
        t(lang, "settings_radius_on", km=radius_km, extra=extra_part)
        if radius_km > 0
        else t(lang, "settings_radius_off")
    )
    text = t(
        lang, "settings_title",
        city=city_label,
        radius_hint=t(lang, "settings_radius_hint") if radius_km > 0 else "",
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_radius, callback_data="toggle_search_radius")],
        [InlineKeyboardButton(text=toggle_hide, callback_data="toggle_hide_seen")],
        [InlineKeyboardButton(text=t(lang, "settings_change_city"), callback_data="open_city_pick")],
        [InlineKeyboardButton(text=t(lang, "settings_back_menu"), callback_data="open_menu")],
    ])
    if edit:
        await target.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


async def _show_stats(user_id: int, target):
    user = get_or_create_user(user_id)
    subs = get_user_subscriptions(user_id)
    favs = get_favorites(user_id)
    alerts = get_user_alerts(user_id)
    ref = get_ref_stats(user_id)
    ref_count = ref.get("ref_count", 0)
    lang = get_lang(user_id)

    vip_line = _status_badge(user, lang)
    fav_count = len(favs)
    streak = get_user_streak_days(user_id)
    created = (user.get("created_at") or "")[:10]
    subs_text = _format_subs(subs, lang)
    streak_line = ""
    if streak >= 7:
        streak_line = t(lang, "stats_streak_hot", n=streak)
    elif streak >= 3:
        streak_line = t(lang, "stats_streak", n=streak)
    elif streak > 0:
        streak_line = t(lang, "stats_active", n=streak)

    refs_mod = ref_count % REFERRAL_REQUIRED
    if ref_count > 0 and refs_mod == 0:
        ref_progress = t(lang, "stats_ref_top")
    elif ref_count == 0:
        ref_progress = t(lang, "stats_ref_progress", refs=REFERRAL_REQUIRED)
    else:
        ref_progress = t(lang, "stats_ref_progress", refs=REFERRAL_REQUIRED - refs_mod)

    await target.answer(
        t(
            lang, "stats_body",
            vip_line=vip_line,
            views=user.get("views", 0),
            favs=fav_count,
            subs=subs_text,
            alerts=len(alerts),
            refs=ref_count,
            created=created,
            streak=streak_line,
            next_vip=ref_progress,
        ),
        parse_mode="HTML",
    )


# ── /hot ─────────────────────────────────────────────────────

@router.message(Command("hot"))
async def cmd_hot(message: Message):
    await _show_hot(message, message.from_user.id)


@router.callback_query(F.data == "open_hot")
async def cb_open_hot(call: CallbackQuery):
    await call.answer()
    await _show_hot(call.message, call.from_user.id)


async def _show_hot(target, user_id: int | None = None):
    uid = user_id or getattr(target, "chat", None) and target.chat.id
    if uid is None and hasattr(target, "from_user"):
        uid = target.from_user.id
    lang = get_lang(uid) if uid else "ru"
    city = get_user_city_db(uid) if uid else "Warszawa"
    radius = get_user_search_radius(uid) if uid else 100
    apts = get_hot_apartments(limit=5, city=city, radius_km=radius)
    if not apts:
        await target.answer(t(lang, "hot_empty"), parse_mode="HTML")
        return
    await target.answer(t(lang, "hot_title"), parse_mode="HTML")
    for apt in apts:
        score = apt.get("hot_score", 0)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t(lang, "btn_save"), callback_data=f"fav_add:{apt['id']}"),
            InlineKeyboardButton(text=t(lang, "btn_open_link"), url=apt["link"]),
        ]])
        await target.answer(
            apt_text(apt, lang) + t(lang, "hot_score", n=score),
            reply_markup=kb,
            parse_mode="HTML",
        )


# ── /drops ───────────────────────────────────────────────────

@router.message(Command("drops"))
async def cmd_drops(message: Message):
    await _show_drops(message, message.from_user.id)


@router.callback_query(F.data == "open_drops")
async def cb_open_drops(call: CallbackQuery):
    await call.answer()
    await _show_drops(call.message, call.from_user.id)


async def _show_drops(target, user_id: int | None = None):
    uid = user_id or (getattr(target, "chat", None) and target.chat.id)
    if uid is None and hasattr(target, "from_user"):
        uid = target.from_user.id
    lang = get_lang(uid) if uid else "ru"
    city = get_user_city_db(uid) if uid else "Warszawa"
    radius = get_user_search_radius(uid) if uid else 100
    drops = get_price_drops_today(limit=5, city=city, radius_km=radius)
    if not drops:
        await target.answer(t(lang, "drops_empty"), parse_mode="HTML")
        return
    await target.answer(t(lang, "drops_title"), parse_mode="HTML")
    for apt in drops:
        old = apt.get("old_price") or 0
        current = apt.get("price") or 0
        diff = int(old) - int(current) if old and current else 0
        pct = int(diff / old * 100) if old else 0
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t(lang, "btn_save"), callback_data=f"fav_add:{apt['id']}"),
            InlineKeyboardButton(text=t(lang, "btn_open_link"), url=apt["link"]),
        ]])
        await target.answer(
            t(
                lang, "drops_card",
                diff=diff, pct=pct, title=apt.get("title", "—"),
                old=old, current=current, district=apt.get("district", city),
            ),
            reply_markup=kb,
            parse_mode="HTML",
        )


# ── /cheap ───────────────────────────────────────────────────

@router.message(Command("cheap"))
async def cmd_cheap(message: Message):
    await _show_cheap(message, message.from_user.id)


@router.callback_query(F.data == "open_cheap")
async def cb_open_cheap(call: CallbackQuery):
    await call.answer()
    await _show_cheap(call.message, call.from_user.id)


async def _show_cheap(target, user_id: int | None = None):
    uid = user_id or (getattr(target, "chat", None) and target.chat.id)
    if uid is None and hasattr(target, "from_user"):
        uid = target.from_user.id
    lang = get_lang(uid) if uid else "ru"
    city = get_user_city_db(uid) if uid else "Warszawa"
    radius = get_user_search_radius(uid) if uid else 100
    try:
        apts = get_cheapest_apartments(limit=5, city=city, radius_km=radius)
    except Exception:
        apts = get_apartments(
            filters=_search_filters(uid, {"price_max": 2500}) if uid else {"price_max": 2500},
            offset=0, limit=5, vip=True,
        )
    if not apts:
        await target.answer(t(lang, "cheap_empty"), parse_mode="HTML")
        return
    await target.answer(t(lang, "cheap_title"), parse_mode="HTML")
    for apt in apts:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t(lang, "btn_save"), callback_data=f"fav_add:{apt['id']}"),
            InlineKeyboardButton(text=t(lang, "btn_open_link"), url=apt["link"]),
        ]])
        await target.answer(apt_text(apt, lang), reply_markup=kb, parse_mode="HTML")


# ── /map — price map by district ─────────────────────────────

@router.message(Command("map"))
async def cmd_map(message: Message):
    await _show_map(message, message.from_user.id)


@router.callback_query(F.data == "open_map")
async def cb_open_map(call: CallbackQuery):
    await call.answer()
    await _show_map(call.message, call.from_user.id)


async def _show_map(target, user_id: int | None = None):
    uid = user_id or (getattr(target, "chat", None) and target.chat.id)
    if uid is None and hasattr(target, "from_user"):
        uid = target.from_user.id
    lang = get_lang(uid) if uid else "ru"
    city = get_user_city_db(uid) if uid else "Warszawa"
    city_label = CITIES.get(city, {}).get("label", city)
    radius = get_user_search_radius(uid) if uid else 100
    cities = resolve_search_cities(city, radius)
    multi_city = len(cities) > 1
    from database.db import get_conn
    conn = get_conn()
    placeholders = ",".join("?" * len(cities))
    if multi_city:
        rows = conn.execute(f"""
            SELECT district, city, COUNT(*) as cnt, AVG(price) as avg_price, MIN(price) as min_price
            FROM apartments
            WHERE city IN ({placeholders}) AND price > 500 AND price < 20000
              AND district != '' AND district IS NOT NULL AND reported < 10
            GROUP BY district, city
            HAVING cnt >= 2
            ORDER BY avg_price ASC
            LIMIT 20
        """, tuple(cities)).fetchall()
    else:
        rows = conn.execute("""
            SELECT district, COUNT(*) as cnt, AVG(price) as avg_price, MIN(price) as min_price
            FROM apartments
            WHERE city = ? AND price > 500 AND price < 20000
              AND district != '' AND district IS NOT NULL AND reported < 10
            GROUP BY district
            HAVING cnt >= 2
            ORDER BY avg_price ASC
            LIMIT 15
        """, (city,)).fetchall()
    conn.close()

    if not rows:
        await target.answer(t(lang, "map_empty"), parse_mode="HTML")
        return

    if multi_city:
        lines = [t(lang, "map_title_radius", city=city_label, n=len(cities) - 1)]
    else:
        lines = [t(lang, "map_title", city=city_label)]
    for r in rows:
        avg = int(r["avg_price"])
        bar_len = min(int(avg / 600), 8)
        bar = "█" * bar_len + "░" * (8 - bar_len)
        if multi_city:
            row_city = CITIES.get(r["city"], {}).get("label", r["city"])
            lines.append(t(
                lang, "map_row_city",
                district=r["district"], city=row_city, bar=bar, avg=avg,
                min_price=r["min_price"], cnt=r["cnt"],
            ))
        else:
            lines.append(t(
                lang, "map_row",
                district=r["district"], bar=bar, avg=avg,
                min_price=r["min_price"], cnt=r["cnt"],
            ))

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "map_pick_district"), callback_data="open_filter"),
    ]])
    await target.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


# ── /daily — short-term rental ────────────────────────────────

@router.message(Command("daily"))
async def cmd_daily(message: Message, state: FSMContext):
    await _start_daily(message.from_user.id, message, state)


@router.callback_query(F.data == "open_daily")
async def cb_open_daily(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _start_daily(call.from_user.id, call.message, state)


async def _start_daily(user_id: int, target, state: FSMContext):
    """Step 1: choose city for short-term rental."""
    data = await state.get_data()
    lang = get_lang(user_id)
    city = get_user_city_db(user_id) or data.get("city", "Warszawa")
    city_label = CITIES.get(city, {}).get("label", city)
    await state.update_data(daily_city=city, daily_location=city_label, city=city)

    items = list(CITIES.items())
    rows = []
    for i in range(0, len(items), 2):
        row = []
        for j in range(i, min(i + 2, len(items))):
            c, info = items[j]
            mark = " ✅" if c == city else ""
            row.append(InlineKeyboardButton(
                text=info["label"] + mark,
                callback_data=f"daily_loc:{c}",
            ))
        rows.append(row)
    rows.append([InlineKeyboardButton(
        text=t(lang, "daily_custom_city"),
        callback_data="daily_loc_custom",
    )])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await target.answer(
        t(lang, "daily_step1", city=city_label),
        parse_mode="HTML",
        reply_markup=kb,
    )
    await state.set_state(DailyState.waiting_location)


@router.callback_query(F.data.startswith("daily_loc:"), DailyState.waiting_location)
async def cb_daily_loc(call: CallbackQuery, state: FSMContext):
    city = call.data.split(":")[1]
    city_label = CITIES.get(city, {}).get("label", city)
    await state.update_data(daily_city=city, daily_location=city_label)
    await call.answer()
    await _daily_step_checkin(call.message, state, call.from_user.id)


@router.callback_query(F.data == "daily_loc_custom", DailyState.waiting_location)
async def cb_daily_loc_custom(call: CallbackQuery, state: FSMContext):
    await call.answer()
    lang = get_lang(call.from_user.id)
    await call.message.answer(t(lang, "daily_custom_prompt"), parse_mode="HTML")


def _guess_city_from_text(text: str) -> str | None:
    low = text.lower()
    for city_key, info in CITIES.items():
        if city_key.lower() in low or info.get("url_olx", "") in low:
            return city_key
    return None


@router.message(DailyState.waiting_location)
async def daily_location_text(message: Message, state: FSMContext):
    location = message.text.strip()
    guessed = _guess_city_from_text(location)
    await state.update_data(
        daily_location=location,
        daily_city=guessed,
    )
    await _daily_step_checkin(message, state, message.from_user.id)


async def _daily_step_checkin(target, state: FSMContext, user_id: int = 0):
    """Step 2: choose check-in date with improved calendar."""
    from datetime import date, timedelta
    lang = get_lang(user_id) if user_id else "ru"
    today = date.today()
    
    # Show calendar for current and next month
    rows = []
    rows.append([InlineKeyboardButton(
        text=f"📅 {today.strftime('%B %Y')}",
        callback_data="noop"
    )])
    
    # Quick picks for next 7 days
    quick_row = []
    for i in range(7):
        d = today + timedelta(days=i)
        label = t(lang, "today") if i == 0 else (t(lang, "tomorrow") if i == 1 else d.strftime("%d.%m"))
        quick_row.append(InlineKeyboardButton(
            text=label,
            callback_data=f"daily_ci:{d.isoformat()}"
        ))
        if len(quick_row) == 4:
            rows.append(quick_row)
            quick_row = []
    if quick_row:
        rows.append(quick_row)
    
    # Calendar grid for current month (remaining days)
    month_start = today
    month_end = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    
    cal_row = []
    for i in range((month_end - today).days + 1):
        d = today + timedelta(days=i)
        if i < 7:  # Skip first week (already in quick picks)
            continue
        cal_row.append(InlineKeyboardButton(
            text=d.strftime("%d"),
            callback_data=f"daily_ci:{d.isoformat()}"
        ))
        if len(cal_row) == 7:
            rows.append(cal_row)
            cal_row = []
    if cal_row:
        rows.append(cal_row)
    
    # Next month header + dates
    next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    rows.append([InlineKeyboardButton(
        text=f"📅 {next_month.strftime('%B %Y')}",
        callback_data="noop"
    )])
    
    next_month_end = (next_month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    cal_row = []
    for i in range((next_month_end - next_month).days + 1):
        d = next_month + timedelta(days=i)
        cal_row.append(InlineKeyboardButton(
            text=d.strftime("%d"),
            callback_data=f"daily_ci:{d.isoformat()}"
        ))
        if len(cal_row) == 7:
            rows.append(cal_row)
            cal_row = []
    if cal_row:
        rows.append(cal_row)

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await target.answer(t(lang, "daily_step2"), parse_mode="HTML", reply_markup=kb)
    await state.set_state(DailyState.waiting_checkin)


@router.callback_query(F.data.startswith("daily_ci:"), DailyState.waiting_checkin)
async def cb_daily_checkin(call: CallbackQuery, state: FSMContext):
    checkin = call.data.split(":")[1]
    await state.update_data(daily_checkin=checkin)
    await call.answer()
    await _daily_step_checkout(call.message, state, checkin, call.from_user.id)


async def _daily_step_checkout(target, state: FSMContext, checkin: str, user_id: int = 0):
    """Step 3: choose check-out date with improved calendar."""
    from datetime import date, timedelta
    lang = get_lang(user_id) if user_id else "ru"
    ci = date.fromisoformat(checkin)
    
    # Show quick picks for common durations
    rows = []
    rows.append([InlineKeyboardButton(
        text=t(lang, "daily_checkin_label", date=ci.strftime("%d.%m.%Y")),
        callback_data="noop",
    )])
    
    # Quick duration picks
    quick_durations = [1, 2, 3, 4, 5, 6, 7, 10, 14, 21, 30]
    row = []
    for nights in quick_durations:
        co = ci + timedelta(days=nights)
        label = (
            t(lang, "daily_nights_btn", n=nights)
            if nights < 7
            else t(lang, "daily_nights_btn_long", n=nights)
        )
        row.append(InlineKeyboardButton(
            text=label,
            callback_data=f"daily_co:{co.isoformat()}:{nights}"
        ))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    
    # Calendar for next 30 days from check-in
    rows.append([InlineKeyboardButton(
        text=t(lang, "daily_or_date"),
        callback_data="noop",
    )])
    
    cal_row = []
    for i in range(1, 31):
        co = ci + timedelta(days=i)
        cal_row.append(InlineKeyboardButton(
            text=co.strftime("%d.%m"),
            callback_data=f"daily_co:{co.isoformat()}:{i}"
        ))
        if len(cal_row) == 5:
            rows.append(cal_row)
            cal_row = []
    if cal_row:
        rows.append(cal_row)

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    ci_fmt = ci.strftime("%d.%m.%Y")
    await target.answer(
        t(lang, "daily_step3", checkin=ci_fmt),
        parse_mode="HTML",
        reply_markup=kb,
    )
    await state.set_state(DailyState.waiting_checkout)


@router.callback_query(F.data.startswith("daily_co:"), DailyState.waiting_checkout)
async def cb_daily_checkout(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    checkout = parts[1]
    nights = int(parts[2])
    await state.update_data(daily_checkout=checkout, daily_nights=nights)
    await call.answer()
    await _daily_step_guests(call.message, state, call.from_user.id)


async def _daily_step_guests(target, state: FSMContext, user_id: int = 0):
    """Step 4: number of guests."""
    lang = get_lang(user_id) if user_id else "ru"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 👤",  callback_data="daily_g:1"),
            InlineKeyboardButton(text="2 👥",  callback_data="daily_g:2"),
            InlineKeyboardButton(text="3 👥",  callback_data="daily_g:3"),
            InlineKeyboardButton(text="4 👥",  callback_data="daily_g:4"),
        ],
        [
            InlineKeyboardButton(text="5 👥",  callback_data="daily_g:5"),
            InlineKeyboardButton(text="6+ 👥", callback_data="daily_g:6"),
        ],
    ])
    await target.answer(t(lang, "daily_step4"), parse_mode="HTML", reply_markup=kb)
    await state.set_state(DailyState.waiting_guests)


@router.callback_query(F.data.startswith("daily_g:"), DailyState.waiting_guests)
async def cb_daily_guests(call: CallbackQuery, state: FSMContext):
    guests = int(call.data.split(":")[1])
    await state.update_data(daily_guests=guests)
    await call.answer()
    await _daily_step_type(call.message, state, call.from_user.id)


async def _daily_step_type(target, state: FSMContext, user_id: int = 0):
    """Step 5: property type."""
    lang = get_lang(user_id) if user_id else "ru"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "daily_type_apartment"), callback_data="daily_t:apartment"),
            InlineKeyboardButton(text=t(lang, "daily_type_house"), callback_data="daily_t:house"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "daily_type_room"), callback_data="daily_t:room"),
            InlineKeyboardButton(text=t(lang, "daily_type_hotel"), callback_data="daily_t:hotel"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "daily_type_any"), callback_data="daily_t:any"),
        ],
    ])
    await target.answer(t(lang, "daily_step5"), parse_mode="HTML", reply_markup=kb)
    await state.set_state(DailyState.waiting_type)


@router.callback_query(F.data.startswith("daily_t:"), DailyState.waiting_type)
async def cb_daily_type(call: CallbackQuery, state: FSMContext):
    prop_type = call.data.split(":")[1]
    await state.update_data(daily_type=prop_type)
    await call.answer()
    await _daily_show_results(call.from_user.id, call.message, state)


async def _daily_show_results(user_id: int, target, state: FSMContext):
    """Show real daily rental listings + booking links."""
    data = await state.get_data()
    location    = data.get("daily_location", "Warszawa")
    city_key    = data.get("daily_city", "Warszawa")
    checkin     = data.get("daily_checkin", "")
    checkout    = data.get("daily_checkout", "")
    nights      = data.get("daily_nights", 1)
    guests      = data.get("daily_guests", 2)
    prop_type   = data.get("daily_type", "any")

    from datetime import date
    if not checkin:
        checkin = date.today().isoformat()
    if not checkout:
        from datetime import timedelta
        checkout = (date.fromisoformat(checkin) + timedelta(days=nights)).isoformat()

    ci_fmt = date.fromisoformat(checkin).strftime("%d.%m.%Y")
    co_fmt = date.fromisoformat(checkout).strftime("%d.%m.%Y")
    
    # Search real listings from OLX and Nocowanie
    from parser.parser_daily import search_daily_rentals
    lang = get_lang(user_id)
    
    if not city_key:
        city_key = get_user_city_db(user_id)
    city_label = CITIES.get(city_key, {}).get("label", city_key)
    radius_km = get_user_search_radius(user_id)
    nearby = get_cities_in_radius(city_key, radius_km) if radius_km > 0 else [city_key]
    radius_note = ""
    if radius_km > 0 and len(nearby) > 1:
        radius_note = t(lang, "daily_radius_note", km=radius_km, n=len(nearby))

    await target.answer(
        t(lang, "daily_searching", city=city_label, checkin=ci_fmt, checkout=co_fmt) + radius_note,
        parse_mode="HTML",
    )

    try:
        listings = search_daily_rentals(
            checkin, checkout, guests, city_key=city_key, radius_km=radius_km,
        )
    except Exception as e:
        print(f"[Daily] Search error: {e}")
        listings = []

    if listings:
        await target.answer(
            t(lang, "daily_found", n=len(listings), city=city_label),
            parse_mode="HTML",
        )
        night_label = t(lang, "daily_night") if nights == 1 else t(lang, "daily_nights")
        for apt in listings[:12]:
            price_night = apt.get("price_per_night", 0)
            total = apt.get("total_price", 0)
            title = apt.get("title", "—")
            apt_city = apt.get("city", city_key)
            apt_city_label = CITIES.get(apt_city, {}).get("label", apt_city)
            district = apt.get("district", location)
            if apt_city != city_key:
                district = f"{district}, {apt_city_label}" if district else apt_city_label
            source = apt.get("source", "")
            link = apt.get("link", "")
            rating = apt.get("rating")
            rating_str = f" · ⭐ {rating}/10" if rating else ""
            text = t(
                lang,
                "daily_card",
                title=title,
                price=price_night,
                night_label=night_label,
                total=total,
                nights=nights,
                nights_label=night_label,
                district=district,
                rating=rating_str,
                link=link,
                open_label=t(lang, "daily_open", source=source),
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=t(lang, "daily_btn_open"), url=link),
            ]])
            
            image = apt.get('image', '')
            if image and image.startswith('http'):
                try:
                    await target.answer_photo(image, caption=text, reply_markup=kb, parse_mode="HTML")
                except Exception:
                    await target.answer(text, reply_markup=kb, parse_mode="HTML")
            else:
                await target.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(
            t(lang, "daily_none", city=city_label),
            parse_mode="HTML",
        )

    # Property type mapping per platform
    type_booking = {
        "apartment": "&nflt=ht_id%3D201",   # apartments
        "house":     "&nflt=ht_id%3D213",   # villas/houses
        "room":      "&nflt=ht_id%3D216",   # private rooms
        "hotel":     "&nflt=ht_id%3D204",   # hotels
        "any":       "",
    }
    type_airbnb = {
        "apartment": "&room_types%5B%5D=Entire+home%2Fapt",
        "house":     "&room_types%5B%5D=Entire+home%2Fapt",
        "room":      "&room_types%5B%5D=Private+room",
        "hotel":     "&room_types%5B%5D=Hotel+room",
        "any":       "",
    }
    _type_keys = {
        "apartment": "daily_type_apartment",
        "house": "daily_type_house",
        "room": "daily_type_room",
        "hotel": "daily_type_hotel",
        "any": "daily_type_any",
    }
    type_label = t(lang, _type_keys.get(prop_type, "daily_type_any"))

    b_loc = BOOKING_LOCATIONS.get(city_key, city_key)
    a_loc = AIRBNB_LOCATIONS.get(city_key, city_key.replace(" ", "-") + "--Poland")

    t_book = type_booking.get(prop_type, "")
    t_air  = type_airbnb.get(prop_type, "")

    import urllib.parse as _up
    booking   = (f"https://www.booking.com/searchresults.pl.html"
                 f"?ss={_up.quote(b_loc)}&checkin={checkin}&checkout={checkout}"
                 f"&group_adults={guests}&no_rooms=1{t_book}")
    airbnb    = (f"https://www.airbnb.pl/s/{_up.quote(a_loc)}/homes"
                 f"?checkin={checkin}&checkout={checkout}&adults={guests}{t_air}")
    nocowanie = (f"https://www.nocowanie.pl/noclegi/{_up.quote(b_loc.lower())}/"
                 f"?od={checkin}&do={checkout}&osoby={guests}")
    flatio = flatio_daily_url(city_key)

    nights_label = t(lang, "daily_night") if nights == 1 else t(lang, "daily_nights")
    text = t(
        lang,
        "daily_summary",
        city=location,
        checkin=ci_fmt,
        checkout=co_fmt,
        nights=nights,
        nights_label=nights_label,
        guests=guests,
        guests_label=t(lang, "daily_guests_label"),
        type=type_label,
        best_links=t(lang, "daily_best_links"),
        booking=booking,
        airbnb=airbnb,
        nocowanie=nocowanie,
        flatio=flatio,
        tips=t(lang, "daily_tips"),
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "daily_btn_change"), callback_data="open_daily"),
            InlineKeyboardButton(text=t(lang, "daily_btn_menu"), callback_data="open_menu"),
        ],
    ])
    await target.answer(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=kb)
    await state.set_state(None)


# ── /subscribe ───────────────────────────────────────────────

async def _show_subscribe(user_id: int, target, state: FSMContext):
    lang = get_lang(user_id)
    data = await state.get_data()
    city = data.get("city", get_user_city_db(user_id))
    subs = get_user_subscriptions(user_id)
    subs_text = _format_subs(subs, lang)
    await target.answer(
        t(lang, "subscribe_intro", subs=subs_text),
        parse_mode="HTML",
        reply_markup=districts_keyboard("sub", city, lang),
    )


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message, state: FSMContext):
    await _show_subscribe(message.from_user.id, message, state)


@router.callback_query(F.data == "open_subscribe")
async def cb_open_subscribe(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _show_subscribe(call.from_user.id, call.message, state)


@router.callback_query(F.data.startswith("sub:"))
async def cb_subscribe(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    district = call.data.split(":", 1)[1]
    subscribe_district(call.from_user.id, district)
    await call.answer(t(lang, "subscribe_ok", district=_district_label(district, lang)))
    data = await state.get_data()
    city = data.get("city", get_user_city_db(call.from_user.id))
    subs = get_user_subscriptions(call.from_user.id)
    subs_text = _format_subs(subs, lang)
    await call.message.edit_text(
        t(lang, "subscribe_more", subs=subs_text),
        parse_mode="HTML",
        reply_markup=districts_keyboard("sub", city, lang),
    )


# ── /lang ─────────────────────────────────────────────────────

@router.message(Command("lang"))
async def cmd_lang(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский",    callback_data="lang:ru"),
            InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang:uk"),
        ],
        [
            InlineKeyboardButton(text="🇵🇱 Polski",     callback_data="lang:pl"),
            InlineKeyboardButton(text="🇬🇧 English",    callback_data="lang:en"),
        ],
    ])
    lang = get_lang(message.from_user.id)
    await message.answer(t(lang, "lang_pick"), parse_mode="HTML", reply_markup=kb)


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
        InlineKeyboardButton(text=t(lang, "btn_menu"), callback_data="open_menu"),
    ]])
    await message.answer(t(lang, "help_text"), parse_mode="HTML", reply_markup=kb)


# ── /digest ───────────────────────────────────────────────────

@router.message(Command("digest"))
async def cmd_digest(message: Message):
    lang = get_lang(message.from_user.id)
    digest = get_daily_digest()
    if not digest.get("new_today"):
        await message.answer(t(lang, "digest_empty"))
        return
    text = t(lang, "digest_title", n=digest["new_today"])
    if digest.get("avg_price"):
        text += t(lang, "digest_avg", price=digest["avg_price"])
    if digest.get("cheapest"):
        c = digest["cheapest"]
        text += t(
            lang, "digest_cheapest",
            title=c.get("title", "—"),
            price=c.get("price", 0),
            district=c.get("district", "Warszawa"),
            link=c.get("link", ""),
        )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "digest_btn_all"), callback_data="open_today")
    ]])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "open_digest")
async def cb_open_digest(call: CallbackQuery):
    await call.answer()
    await cmd_digest(call.message)


@router.callback_query(F.data == "open_today")
async def cb_open_today(call: CallbackQuery, state: FSMContext):
    await call.answer()
    lang = get_lang(call.from_user.id)
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
        InlineKeyboardButton(text=t(lang, "digest_btn_browse"), callback_data="next")
    ]])
    await call.message.answer(
        t(lang, "digest_today_count", n=count),
        parse_mode="HTML",
        reply_markup=kb
    )


# ── Callbacks: rating, share, seen, found, scam ───────────────

@router.callback_query(F.data.startswith("rate:"))
async def cb_rate(call: CallbackQuery):
    parts = call.data.split(":")
    rating = int(parts[1])
    apt_id = int(parts[2])
    lang = get_lang(call.from_user.id)
    rate_apartment(call.from_user.id, apt_id, rating)
    await call.answer(t(lang, "rate_like") if rating == 1 else t(lang, "rate_dislike"))


@router.callback_query(F.data.startswith("share:"))
async def cb_share(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    lang = get_lang(call.from_user.id)
    apt = get_apartment_by_id(apt_id)
    if not apt:
        await call.answer(t(lang, "share_not_found"), show_alert=True)
        return
    await call.answer()
    bot_me = await call.bot.get_me()
    icon = SOURCE_ICONS.get(apt.get("source", ""), "📡")
    share_text = t(
        lang, "share_text",
        title=apt.get("title", "—"),
        price=apt.get("price", 0),
        district=apt.get("district", "Warszawa"),
        link=apt.get("link", ""),
        icon=icon,
        bot=bot_me.username,
    )
    share_url = (
        f"https://t.me/share/url"
        f"?url={urllib.parse.quote(apt.get('link', ''))}"
        f"&text={urllib.parse.quote(share_text)}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "share_btn_tg"), url=share_url),
        InlineKeyboardButton(text=t(lang, "notify_btn_open"), url=apt.get("link", "#")),
    ]])
    await call.message.answer(
        t(
            lang, "share_title",
            title=apt.get("title", "—"),
            price=apt.get("price", 0),
            district=apt.get("district", "Warszawa"),
        ),
        parse_mode="HTML",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("hide:"))
async def cb_hide(call: CallbackQuery, state: FSMContext):
    apt_id = int(call.data.split(":")[1])
    lang = get_lang(call.from_user.id)
    hide_apartment(call.from_user.id, apt_id)
    mark_seen(call.from_user.id, apt_id)
    await call.answer(t(lang, "hide_ok"))
    await show_next_apartment(call.from_user.id, call.bot, state, call.message.chat.id)


@router.callback_query(F.data.startswith("seen:"))
async def cb_seen(call: CallbackQuery, state: FSMContext):
    apt_id = int(call.data.split(":")[1])
    lang = get_lang(call.from_user.id)
    mark_seen(call.from_user.id, apt_id)
    await call.answer(t(lang, "seen_ok"))
    await show_next_apartment(call.from_user.id, call.bot, state, call.message.chat.id)


@router.callback_query(F.data.startswith("found:"))
async def cb_found(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    apt = get_apartment_by_id(apt_id)
    source = apt.get("source", "") if apt else ""
    lang = get_lang(call.from_user.id)
    record_conversion(call.from_user.id, apt_id, source)
    await call.answer(t(lang, "found_congrats"), show_alert=True)

    bot_me = await call.bot.get_me()
    ref_stats = get_ref_stats(call.from_user.id)
    ref_code = ref_stats.get("ref_code", "")
    ref_link = f"https://t.me/{bot_me.username}?start=ref_{ref_code}" if ref_code else f"https://t.me/{bot_me.username}"
    city = get_user_city_db(call.from_user.id)
    city_label = CITIES.get(city, {}).get("label", city)
    share_text = t(lang, "found_share_text", city=city_label)
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(ref_link)}&text={urllib.parse.quote(share_text)}"

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "found_share_btn"), url=share_url),
    ]])
    await call.message.answer(
        t(lang, "found_share_pitch"),
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
    lang = get_lang(call.from_user.id)
    await call.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "report_scam"),    callback_data=f"report_reason:scam:{apt_id}")],
        [InlineKeyboardButton(text=t(lang, "report_rented"),   callback_data=f"report_reason:rented:{apt_id}")],
        [InlineKeyboardButton(text=t(lang, "report_price"),    callback_data=f"report_reason:price:{apt_id}")],
        [InlineKeyboardButton(text=t(lang, "report_photo"),    callback_data=f"report_reason:photo:{apt_id}")],
        [InlineKeyboardButton(text=t(lang, "report_cancel"),   callback_data="cancel")],
    ])
    await call.message.answer(t(lang, "report_title"), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("report_reason:"))
async def cb_report_reason(call: CallbackQuery):
    parts = call.data.split(":")
    reason = parts[1]
    apt_id = int(parts[2])
    lang = get_lang(call.from_user.id)
    reason_labels = {
        "scam": t(lang, "report_scam"),
        "rented": t(lang, "report_rented"),
        "price": t(lang, "report_price"),
        "photo": t(lang, "report_photo"),
    }
    try:
        report_apartment(call.from_user.id, apt_id, reason_labels.get(reason, reason))
    except Exception:
        pass
    await call.answer(t(lang, "report_ok"), show_alert=True)
    try:
        await call.message.delete()
    except Exception:
        pass


@router.callback_query(F.data.startswith("similar:"))
async def cb_similar(call: CallbackQuery):
    apt_id = int(call.data.split(":")[1])
    lang = get_lang(call.from_user.id)
    await call.answer()
    try:
        similar = get_similar_apartments(apt_id, limit=3)
    except Exception:
        similar = []
    if not similar:
        await call.message.answer(t(lang, "similar_empty"))
        return
    await call.message.answer(t(lang, "similar_title"), parse_mode="HTML")
    for apt in similar:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t(lang, "btn_fav_add"), callback_data=f"fav_add:{apt['id']}"),
            InlineKeyboardButton(text=t(lang, "notify_btn_open"), url=apt["link"]),
        ]])
        await call.message.answer(apt_text(apt, lang), reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "open_compare")
async def cb_open_compare(call: CallbackQuery):
    await call.answer()
    lang = get_lang(call.from_user.id)
    favs = get_favorites(call.from_user.id)
    if len(favs) < 2:
        await call.message.answer(t(lang, "compare_need_two"), parse_mode="HTML")
        return
    lines = [t(lang, "compare_title")]
    for apt in favs[:5]:
        price = apt.get("price", 0) or 0
        rooms = apt.get("rooms", "?")
        area = apt.get("area", "?")
        if apt.get("area") and price:
            ppm = t(lang, "compare_ppm", ppm=int(price / apt["area"]))
        else:
            ppm = t(lang, "compare_ppm_na")
        lines.append(t(
            lang, "compare_row",
            title=apt.get("title", "—")[:40],
            price=price,
            rooms=rooms,
            area=area,
            ppm=ppm,
            district=apt.get("district", "—"),
            source_icon=SOURCE_ICONS.get(apt.get("source", ""), "📡"),
            source=apt.get("source", ""),
        ))
    await call.message.answer("\n\n".join(lines), parse_mode="HTML")
    for apt in favs[:5]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t(lang, "notify_btn_open"), url=apt["link"]),
        ]])
        await call.message.answer(apt_text(apt, lang), reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    await state.clear()
    await call.answer(t(lang, "cancel_ok"))
    try:
        await call.message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery, state: FSMContext):
    from bot.middleware import is_subscribed
    lang = get_lang(call.from_user.id)
    if await is_subscribed(call.bot, call.from_user.id):
        await call.answer(t(lang, "mw_sub_ok"), show_alert=True)
        try:
            await call.message.delete()
        except Exception:
            pass
        user = get_or_create_user(call.from_user.id)
        await _show_main_menu(call.message, user, from_user=call.from_user)
    else:
        await call.answer(t(lang, "mw_sub_fail"), show_alert=True)


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
        [
            InlineKeyboardButton(text="🍪 Куки Gratka",    callback_data="admin_cookie:Gratka"),
            InlineKeyboardButton(text="🍪 Куки Morizon",   callback_data="admin_cookie:Morizon"),
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


@router.message(Command("parse"))
async def cmd_parse(message: Message):
    """Admin: force full multi-city parse."""
    if message.from_user.id not in ADMIN_IDS:
        return
    import threading
    from parser.scheduler import parse_all
    await message.answer("🔄 <b>Парсер запущен</b>\nВсе 10 городов, ~15–30 мин.\nСледи за логами в Render.", parse_mode="HTML")
    threading.Thread(target=parse_all, daemon=True).start()


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Admin: per-city DB inventory and validation stats."""
    if message.from_user.id not in ADMIN_IDS:
        return
    data = get_admin_city_stats()
    lines = [
        f"📊 <b>Статистика по городам</b> (всего: <b>{data['total']}</b>)",
        f"⚠️ Неверный city в выборке: <b>{data['mislabeled_sample']}</b>\n",
    ]
    for c in data["cities"]:
        mark = "🔴" if c["count"] < 20 else ("🟡" if c["count"] < 100 else "🟢")
        lines.append(f"{mark} {c['label']}: <b>{c['count']}</b> · парс {c['last_parse']}")
    if data["rejects"]:
        lines.append("\n<b>Отклонения за 24ч:</b>")
        for r in data["rejects"][:12]:
            lines.append(
                f"  {r['reason']} / {r['target_city'] or '?'}: {r['cnt']}"
            )
    await message.answer("\n".join(lines), parse_mode="HTML")


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


@router.callback_query(F.data.startswith("admin_cookie:"))
async def cb_admin_cookie(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("⛔", show_alert=True)
        return
    source = call.data.split(":")[1]
    await call.answer()
    from config import PARSER_COOKIES
    current = PARSER_COOKIES.get(source, "не установлены")[:50]
    await call.message.answer(
        f"🍪 <b>Куки для {source}</b>\n\n"
        f"Текущие: <code>{current}...</code>\n\n"
        f"Как получить куки:\n"
        f"1. Открой {source}.pl в браузере\n"
        f"2. F12 → Application → Cookies\n"
        f"3. Скопируй все куки в формате: <code>name1=val1; name2=val2</code>\n\n"
        f"Отправь строку куки следующим сообщением:",
        parse_mode="HTML"
    )
    await state.update_data(cookie_source=source)
    await state.set_state(AdminInputState.set_cookie)


@router.message(AdminInputState.set_cookie)
async def admin_set_cookie(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    source = data.get("cookie_source", "")
    cookie_str = message.text.strip()
    await state.clear()
    if source:
        from config import PARSER_COOKIES
        PARSER_COOKIES[source] = cookie_str
        await message.answer(
            f"✅ Куки для <b>{source}</b> установлены!\n"
            f"Будут использованы при следующем парсинге.\n\n"
            f"Запустить парсер сейчас: /admin → 🔄 Запустить",
            parse_mode="HTML"
        )


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
    from config import VIP_PRICE
    potential = vip_count * VIP_PRICE
    await call.message.answer(
        f"💰 <b>Финансовая статистика</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"💎 Legacy VIP в БД: <b>{vip_count}</b>\n"
        f"💵 (архив) потенциал: <b>{potential} zł/мес</b>\n\n"
        f"<i>Публичный VIP отключён — бот полностью бесплатный.</i>",
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

async def _show_leaderboard(user_id: int, target):
    lang = get_lang(user_id)
    leaders = get_leaderboard()
    if not leaders:
        await target.answer(t(lang, "leaderboard_empty"), parse_mode="HTML")
        return
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    lines = [t(lang, "leaderboard_title")]
    for i, leader in enumerate(leaders):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        marker = t(lang, "leaderboard_you") if leader["user_id"] == user_id else ""
        lines.append(t(
            lang, "leaderboard_row",
            medal=medal, id=leader["user_id"],
            count=leader["ref_count"], marker=marker,
        ))
    lines.append(t(lang, "leaderboard_footer"))
    await target.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message):
    await _show_leaderboard(message.from_user.id, message)


@router.callback_query(F.data == "open_leaderboard")
async def cb_open_leaderboard(call: CallbackQuery):
    await call.answer()
    await _show_leaderboard(call.from_user.id, call.message)


# ── /notes — personal notes on apartments ────────────────────

@router.message(Command("notes"))
async def cmd_notes(message: Message):
    await _show_notes(message.from_user.id, message)


@router.callback_query(F.data == "open_notes")
async def cb_open_notes(call: CallbackQuery):
    await call.answer()
    await _show_notes(call.from_user.id, call.message)


async def _show_notes(user_id: int, target):
    lang = get_lang(user_id)
    notes = get_user_notes(user_id)
    if not notes:
        await target.answer(t(lang, "notes_empty"), parse_mode="HTML")
        return
    await target.answer(t(lang, "notes_title", n=len(notes)), parse_mode="HTML")
    for note in notes[:10]:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=t(lang, "notes_btn_open"), url=note.get("link", "#")),
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
    lang = get_lang(call.from_user.id)
    await state.update_data(note_apt_id=apt_id)
    await call.answer()
    await call.message.answer(t(lang, "notes_prompt"))
    await state.set_state(NoteState.waiting_note)


@router.message(NoteState.waiting_note)
async def note_received(message: Message, state: FSMContext):
    data = await state.get_data()
    apt_id = data.get("note_apt_id")
    if not apt_id:
        await state.clear()
        return
    note_text = message.text.strip()[:500]
    lang = get_lang(message.from_user.id)
    add_user_note(message.from_user.id, apt_id, note_text)
    await state.clear()
    await message.answer(t(lang, "notes_saved"))


# ── Advanced search ───────────────────────────────────────────

def _adv_summary(f: dict, lang: str) -> str:
    """Build human-readable summary of advanced filters."""
    parts = []
    if f.get("district"):
        parts.append(f"📍 {f['district']}")
    if f.get("price_max"):
        parts.append(t(lang, "adv_part_price", price=f["price_max"]))
    if f.get("rooms"):
        parts.append(t(lang, "adv_part_rooms_from", n=f["rooms"]))
    if f.get("rooms_max"):
        parts.append(t(lang, "adv_part_rooms_to", n=f["rooms_max"]))
    if f.get("area_min"):
        parts.append(t(lang, "adv_part_area", area=f["area_min"]))
    if f.get("price_per_m_max"):
        parts.append(t(lang, "adv_part_ppm", ppm=f["price_per_m_max"]))
    if f.get("floor_min"):
        parts.append(t(lang, "adv_part_floor", floor=f["floor_min"]))
    if f.get("furnished") == 1:
        parts.append(t(lang, "filter_furnished"))
    if f.get("photo_only"):
        parts.append(t(lang, "adv_part_photo"))
    if f.get("new_only"):
        parts.append(t(lang, "adv_part_new"))
    return "  ·  ".join(parts) if parts else t(lang, "adv_summary_all")


def _adv_keyboard(f: dict, lang: str) -> InlineKeyboardMarkup:
    on = " ✅"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "adv_btn_district"), callback_data="adv_district"),
            InlineKeyboardButton(text=t(lang, "adv_btn_price"), callback_data="adv_price"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "adv_btn_rooms_min"), callback_data="adv_rooms_min"),
            InlineKeyboardButton(text=t(lang, "adv_btn_rooms_max"), callback_data="adv_rooms_max"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "adv_btn_area"), callback_data="adv_area"),
            InlineKeyboardButton(text=t(lang, "adv_btn_ppm"), callback_data="adv_ppm"),
        ],
        [InlineKeyboardButton(text=t(lang, "adv_btn_floor"), callback_data="adv_floor")],
        [
            InlineKeyboardButton(
                text=t(lang, "adv_btn_photo") + (on if f.get("photo_only") else ""),
                callback_data="adv_toggle:photo",
            ),
            InlineKeyboardButton(
                text=t(lang, "adv_btn_new") + (on if f.get("new_only") else ""),
                callback_data="adv_toggle:new",
            ),
        ],
        [InlineKeyboardButton(
            text=t(lang, "adv_btn_furn") + (on if f.get("furnished") == 1 else ""),
            callback_data="adv_toggle:furn",
        )],
        [InlineKeyboardButton(text=t(lang, "adv_btn_apply"), callback_data="adv_apply")],
        [InlineKeyboardButton(text=t(lang, "adv_btn_reset"), callback_data="adv_reset")],
    ])


@router.message(Command("advanced"))
async def cmd_advanced(message: Message, state: FSMContext):
    await _open_advanced(message, state, message.from_user.id)


@router.callback_query(F.data == "open_advanced")
async def cb_open_advanced(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await _open_advanced(call.message, state, call.from_user.id)


async def _open_advanced(target, state: FSMContext, user_id: int):
    lang = get_lang(user_id)
    data = await state.get_data()
    f = data.get("filters", {})
    await target.answer(
        t(lang, "adv_title", summary=_adv_summary(f, lang)),
        parse_mode="HTML",
        reply_markup=_adv_keyboard(f, lang),
    )


# ── Advanced: district ────────────────────────────────────────

@router.callback_query(F.data == "adv_district")
async def cb_adv_district(call: CallbackQuery, state: FSMContext):
    await call.answer()
    lang = get_lang(call.from_user.id)
    data = await state.get_data()
    city = data.get("city", get_user_city_db(call.from_user.id))
    await call.message.answer(
        t(lang, "adv_pick_district"),
        reply_markup=districts_keyboard("adv_d", city, lang),
    )


@router.callback_query(F.data.startswith("adv_d:"))
async def cb_adv_d(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    district = call.data.split(":", 1)[1]
    data = await state.get_data()
    f = data.get("filters", {})
    if is_all_district(district):
        f.pop("district", None)
        label = t(lang, "filter_all_districts_label")
    else:
        f["district"] = district
        label = district
    await state.update_data(filters=f, offset=0)
    await call.answer(t(lang, "adv_district_set", label=label))
    await _open_advanced(call.message, state, call.from_user.id)


# ── Advanced: price ───────────────────────────────────────────

@router.callback_query(F.data == "adv_price")
async def cb_adv_price(call: CallbackQuery, state: FSMContext):
    await call.answer()
    lang = get_lang(call.from_user.id)
    await call.message.answer(
        t(lang, "adv_pick_price"),
        reply_markup=price_keyboard("adv_p"),
    )


@router.callback_query(F.data.startswith("adv_p:"))
async def cb_adv_p(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    f = data.get("filters", {})
    if val > 0:
        f["price_max"] = val
    else:
        f.pop("price_max", None)
    await state.update_data(filters=f, offset=0)
    await call.answer(
        t(lang, "adv_price_set", price=val) if val else t(lang, "adv_no_limit")
    )
    await _open_advanced(call.message, state, call.from_user.id)


# ── Advanced: rooms min/max ───────────────────────────────────

@router.callback_query(F.data == "adv_rooms_min")
async def cb_adv_rooms_min(call: CallbackQuery, state: FSMContext):
    await call.answer()
    lang = get_lang(call.from_user.id)
    await call.message.answer(
        t(lang, "adv_pick_rooms_min"),
        reply_markup=rooms_keyboard("adv_rmin"),
    )


@router.callback_query(F.data.startswith("adv_rmin:"))
async def cb_adv_rmin(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    f = data.get("filters", {})
    if val > 0:
        f["rooms"] = val
    else:
        f.pop("rooms", None)
    await state.update_data(filters=f, offset=0)
    await call.answer(
        t(lang, "adv_rooms_min_set", n=val) if val else t(lang, "adv_any_rooms")
    )
    await _open_advanced(call.message, state, call.from_user.id)


@router.callback_query(F.data == "adv_rooms_max")
async def cb_adv_rooms_max(call: CallbackQuery, state: FSMContext):
    await call.answer()
    lang = get_lang(call.from_user.id)
    await call.message.answer(
        t(lang, "adv_pick_rooms_max"),
        reply_markup=rooms_keyboard("adv_rmax"),
    )


@router.callback_query(F.data.startswith("adv_rmax:"))
async def cb_adv_rmax(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    f = data.get("filters", {})
    if val > 0:
        f["rooms_max"] = val
    else:
        f.pop("rooms_max", None)
    await state.update_data(filters=f, offset=0)
    await call.answer(
        t(lang, "adv_rooms_max_set", n=val) if val else t(lang, "adv_any_rooms")
    )
    await _open_advanced(call.message, state, call.from_user.id)


# ── Advanced: area min ────────────────────────────────────────

@router.callback_query(F.data == "adv_area")
async def cb_adv_area(call: CallbackQuery, state: FSMContext):
    await call.answer()
    lang = get_lang(call.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="20 м²", callback_data="adv_a:20"),
            InlineKeyboardButton(text="30 м²", callback_data="adv_a:30"),
            InlineKeyboardButton(text="40 м²", callback_data="adv_a:40"),
        ],
        [
            InlineKeyboardButton(text="50 м²", callback_data="adv_a:50"),
            InlineKeyboardButton(text="60 м²", callback_data="adv_a:60"),
            InlineKeyboardButton(text="80 м²", callback_data="adv_a:80"),
        ],
        [InlineKeyboardButton(text=t(lang, "adv_no_limit"), callback_data="adv_a:0")],
    ])
    await call.message.answer(t(lang, "adv_pick_area"), reply_markup=kb)


@router.callback_query(F.data.startswith("adv_a:"))
async def cb_adv_a(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    f = data.get("filters", {})
    if val > 0:
        f["area_min"] = val
    else:
        f.pop("area_min", None)
    await state.update_data(filters=f, offset=0)
    await call.answer(
        t(lang, "adv_area_set", area=val) if val else t(lang, "adv_no_limit")
    )
    await _open_advanced(call.message, state, call.from_user.id)


# ── Advanced: price per m² ────────────────────────────────────

@router.callback_query(F.data == "adv_ppm")
async def cb_adv_ppm(call: CallbackQuery, state: FSMContext):
    await call.answer()
    lang = get_lang(call.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="30 zł/м²", callback_data="adv_pm:30"),
            InlineKeyboardButton(text="40 zł/м²", callback_data="adv_pm:40"),
            InlineKeyboardButton(text="50 zł/м²", callback_data="adv_pm:50"),
        ],
        [
            InlineKeyboardButton(text="60 zł/м²", callback_data="adv_pm:60"),
            InlineKeyboardButton(text="80 zł/м²", callback_data="adv_pm:80"),
            InlineKeyboardButton(text="100 zł/м²", callback_data="adv_pm:100"),
        ],
        [InlineKeyboardButton(text=t(lang, "adv_no_limit"), callback_data="adv_pm:0")],
    ])
    await call.message.answer(t(lang, "adv_ppm_help"), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("adv_pm:"))
async def cb_adv_pm(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    f = data.get("filters", {})
    if val > 0:
        f["price_per_m_max"] = val
    else:
        f.pop("price_per_m_max", None)
    await state.update_data(filters=f, offset=0)
    await call.answer(
        t(lang, "adv_ppm_set", ppm=val) if val else t(lang, "adv_no_limit")
    )
    await _open_advanced(call.message, state, call.from_user.id)


# ── Advanced: floor ───────────────────────────────────────────

@router.callback_query(F.data == "adv_floor")
async def cb_adv_floor(call: CallbackQuery, state: FSMContext):
    await call.answer()
    lang = get_lang(call.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1+", callback_data="adv_fl:1"),
            InlineKeyboardButton(text="2+", callback_data="adv_fl:2"),
            InlineKeyboardButton(text="3+", callback_data="adv_fl:3"),
        ],
        [
            InlineKeyboardButton(text="4+", callback_data="adv_fl:4"),
            InlineKeyboardButton(text="5+", callback_data="adv_fl:5"),
            InlineKeyboardButton(text=t(lang, "adv_any_floor"), callback_data="adv_fl:0"),
        ],
    ])
    await call.message.answer(t(lang, "adv_pick_floor"), reply_markup=kb)


@router.callback_query(F.data.startswith("adv_fl:"))
async def cb_adv_fl(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    val = int(call.data.split(":")[1])
    data = await state.get_data()
    f = data.get("filters", {})
    if val > 0:
        f["floor_min"] = val
    else:
        f.pop("floor_min", None)
    await state.update_data(filters=f, offset=0)
    await call.answer(
        t(lang, "adv_floor_set", floor=val) if val else t(lang, "adv_any_floor")
    )
    await _open_advanced(call.message, state, call.from_user.id)


# ── Advanced: toggles ─────────────────────────────────────────

@router.callback_query(F.data.startswith("adv_toggle:"))
async def cb_adv_toggle(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    key = call.data.split(":")[1]
    data = await state.get_data()
    f = data.get("filters", {})

    if key == "photo":
        f["photo_only"] = not f.get("photo_only", False)
        state = t(lang, "adv_on" if f["photo_only"] else "adv_off")
        await call.answer(t(lang, "adv_toggle_photo", state=state))
    elif key == "new":
        f["new_only"] = not f.get("new_only", False)
        state = t(lang, "adv_on" if f["new_only"] else "adv_off")
        await call.answer(t(lang, "adv_toggle_new", state=state))
    elif key == "furn":
        if f.get("furnished") == 1:
            f.pop("furnished", None)
            await call.answer(t(lang, "adv_toggle_furn", state=t(lang, "adv_off")))
        else:
            f["furnished"] = 1
            await call.answer(t(lang, "adv_toggle_furn", state=t(lang, "adv_on")))

    await state.update_data(filters=f, offset=0)
    await _open_advanced(call.message, state, call.from_user.id)


# ── Advanced: apply ───────────────────────────────────────────

@router.callback_query(F.data == "adv_apply")
async def cb_adv_apply(call: CallbackQuery, state: FSMContext):
    await call.answer()
    lang = get_lang(call.from_user.id)
    data = await state.get_data()
    f = data.get("filters", {})
    city_filters = _search_filters(call.from_user.id, f)

    user = get_or_create_user(call.from_user.id)
    exclude_ids = search_exclude_ids(call.from_user.id, data)
    total = count_apartments(city_filters, vip=bool(user.get("vip")), exclude_ids=exclude_ids)
    summary = _adv_summary(f, lang)
    hint = t(lang, "filter_hide_seen_hint") if get_user_hide_seen(call.from_user.id) else ""

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "adv_btn_view", total=total), callback_data="next")],
        [InlineKeyboardButton(text=t(lang, "adv_btn_edit"), callback_data="open_advanced")],
        [InlineKeyboardButton(text=t(lang, "adv_btn_reset"), callback_data="adv_reset")],
    ])
    await call.message.answer(
        t(lang, "adv_applied", summary=summary, total=total, hint=hint),
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(F.data == "adv_reset")
async def cb_adv_reset(call: CallbackQuery, state: FSMContext):
    lang = get_lang(call.from_user.id)
    await state.update_data(filters={}, offset=0)
    await call.answer(t(lang, "adv_reset_ok"), show_alert=True)
    await _open_advanced(call.message, state, call.from_user.id)


# ── Fallback for unknown messages ─────────────────────────────

@router.message()
async def fallback(message: Message):
    lang = get_lang(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "btn_find"), callback_data="next"),
        InlineKeyboardButton(text=t(lang, "btn_menu"), callback_data="open_menu"),
    ]])
    await message.answer(t(lang, "unknown_cmd"), reply_markup=kb)
