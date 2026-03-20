from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from config import POPULAR_DESTINATIONS, POPULAR_ORIGINS, CHANNEL_LINK


# ── Main menu ──────────────────────────────────────────────────────────────────

def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(
        KeyboardButton(text="🔎 Найти билет"),
        KeyboardButton(text="🔥 Горящие билеты"),
    )
    kb.row(
        KeyboardButton(text="🔔 Мои алерты"),
        KeyboardButton(text="❤️ Избранное"),
    )
    kb.row(
        KeyboardButton(text="⭐ VIP"),
        KeyboardButton(text="📊 Статистика"),
    )
    return kb.as_markup(resize_keyboard=True)


# ── Origin selection ───────────────────────────────────────────────────────────

def origins_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    labels = {
        "WAW": "✈️ Варшава (WAW)",
        "KRK": "✈️ Краков (KRK)",
        "WRO": "✈️ Вроцлав (WRO)",
        "GDN": "✈️ Гданьск (GDN)",
        "KTW": "✈️ Катовице (KTW)",
        "POZ": "✈️ Познань (POZ)",
    }
    for code, label in labels.items():
        builder.button(text=label, callback_data=f"origin:{code}")
    builder.adjust(2)
    return builder.as_markup()


# ── Destination selection ──────────────────────────────────────────────────────

def destinations_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for city, code in POPULAR_DESTINATIONS:
        builder.button(text=f"🌍 {city}", callback_data=f"dest:{code}:{city}")
    builder.button(text="✏️ Ввести вручную", callback_data="dest:manual")
    builder.adjust(2)
    return builder.as_markup()


# ── Date selection ─────────────────────────────────────────────────────────────

def date_range_kb() -> InlineKeyboardMarkup:
    from datetime import datetime, timedelta
    builder = InlineKeyboardBuilder()
    now = datetime.now()
    options = [
        ("📅 Ближайшие 2 недели", 0, 14),
        ("📅 Следующий месяц",    0, 30),
        ("📅 2–3 месяца",         0, 90),
        ("📅 Любые даты",         0, 180),
    ]
    for label, offset_from, offset_to in options:
        d_from = (now + timedelta(days=offset_from)).strftime("%d/%m/%Y")
        d_to   = (now + timedelta(days=offset_to)).strftime("%d/%m/%Y")
        builder.button(text=label, callback_data=f"dates:{d_from}:{d_to}")
    builder.adjust(1)
    return builder.as_markup()


# ── Flight results ─────────────────────────────────────────────────────────────

def flight_card_kb(flight: dict, idx: int, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Купить билет", url=flight["link"])
    builder.button(text="❤️ Сохранить", callback_data=f"fav:save:{idx}")
    if total > 1:
        nav = []
        if idx > 0:
            nav.append(InlineKeyboardButton(text="◀️", callback_data=f"flight:prev:{idx}"))
        nav.append(InlineKeyboardButton(text=f"{idx+1}/{total}", callback_data="noop"))
        if idx < total - 1:
            nav.append(InlineKeyboardButton(text="▶️", callback_data=f"flight:next:{idx}"))
        builder.row(*nav)
    builder.button(text="🔔 Алерт на маршрут", callback_data=f"alert:route:{flight['origin']}:{flight['destination']}")
    builder.button(text="🔎 Новый поиск", callback_data="search:new")
    builder.adjust(2)
    return builder.as_markup()


# ── Hot deal card ──────────────────────────────────────────────────────────────

def hot_deal_kb(flight: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Купить билет", url=flight["link"])
    builder.button(text="❤️ Сохранить", callback_data=f"fav:deal:{flight.get('id', 0)}")
    builder.button(text="🔥 Ещё горящие", callback_data="hot:more")
    builder.adjust(2)
    return builder.as_markup()


# ── Alerts ─────────────────────────────────────────────────────────────────────

def alerts_list_kb(alerts: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for a in alerts:
        label = f"✈️ {a['origin']} → {a['destination']}"
        if a.get("price_max"):
            label += f" (до {a['price_max']}€)"
        builder.button(text=label, callback_data=f"alert:del:{a['id']}")
    builder.button(text="➕ Добавить алерт", callback_data="alert:new")
    builder.button(text="🗑 Удалить все", callback_data="alert:delall")
    builder.adjust(1)
    return builder.as_markup()


# ── Favorites ──────────────────────────────────────────────────────────────────

def favorites_kb(favs: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for f in favs:
        label = f"✈️ {f['origin']}→{f['destination']} {f['price']}€ {f['airline'] or ''}"
        builder.button(text=label[:60], callback_data=f"fav:open:{f['id']}")
    builder.button(text="🗑 Очистить всё", callback_data="fav:clear")
    builder.adjust(1)
    return builder.as_markup()


# ── VIP ────────────────────────────────────────────────────────────────────────

def vip_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить 19 zł (карта)", callback_data="vip:pay:card")
    builder.button(text="⭐ Оплатить 50 Stars", callback_data="vip:pay:stars")
    builder.button(text="📢 Канал с горящими", url=CHANNEL_LINK)
    builder.adjust(1)
    return builder.as_markup()


# ── Cancel ─────────────────────────────────────────────────────────────────────

def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()
