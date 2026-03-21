import urllib.parse
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from config import POPULAR_DESTINATIONS, CHANNEL_LINK, VIP_PRICE_PLN, VIP_PRICE_STARS, FREE_SEARCHES


# ── Main menu ──────────────────────────────────────────────────────────────────

def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="🔎 Найти билет"), KeyboardButton(text="🔄 Туда-обратно"))
    kb.row(KeyboardButton(text="🔥 Горящие"),     KeyboardButton(text="🌍 Популярные"))
    kb.row(KeyboardButton(text="📅 Дешёвые даты"), KeyboardButton(text="🔔 Алерты"))
    kb.row(KeyboardButton(text="❤️ Избранное"),   KeyboardButton(text="⭐ VIP"))
    return kb.as_markup(resize_keyboard=True)


# ── Trip type ──────────────────────────────────────────────────────────────────

def trip_type_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➡️ Только туда", callback_data="trip:oneway")
    builder.button(text="🔄 Туда-обратно", callback_data="trip:roundtrip")
    builder.adjust(1)
    return builder.as_markup()


# ── Filters ────────────────────────────────────────────────────────────────────

def filters_kb(direct_only: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    direct_label = "✅ Только прямые" if direct_only else "🔀 Только прямые"
    builder.button(text=direct_label, callback_data=f"filter:direct:{int(not direct_only)}")
    builder.button(text="✅ Применить", callback_data="filter:apply")
    builder.adjust(1)
    return builder.as_markup()


# ── Origin selection ───────────────────────────────────────────────────────────

def origins_kb(callback_prefix: str = "origin") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    airports = [
        ("WAW", "🏙 Варшава"), ("KRK", "🏰 Краков"),
        ("WRO", "🌉 Вроцлав"), ("GDN", "⚓ Гданьск"),
        ("KTW", "🏭 Катовице"), ("POZ", "🎓 Познань"),
    ]
    for code, label in airports:
        builder.button(text=f"{label} ({code})", callback_data=f"{callback_prefix}:{code}")
    builder.adjust(2)
    return builder.as_markup()


# ── Destination selection ──────────────────────────────────────────────────────

def destinations_kb(callback_prefix: str = "dest") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for city, code in POPULAR_DESTINATIONS:
        builder.button(text=city, callback_data=f"{callback_prefix}:{code}:{city.split()[0]}")
    builder.button(text="✏️ Другой город (IATA)", callback_data=f"{callback_prefix}:manual")
    builder.adjust(2)
    return builder.as_markup()


# ── Date selection ─────────────────────────────────────────────────────────────

def date_range_kb(label_prefix: str = "dates") -> InlineKeyboardMarkup:
    """
    label_prefix='dates'  → callback_data = 'dates:dd/mm/yyyy:dd/mm/yyyy'
    label_prefix='return' → callback_data = 'return:dd/mm/yyyy:dd/mm/yyyy'
    """
    from datetime import datetime, timedelta
    builder = InlineKeyboardBuilder()
    now = datetime.now()
    options = []

    for offset_months in range(0, 5):
        month_start = (now.replace(day=1) + timedelta(days=32 * offset_months)).replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        if month_end < now:
            continue
        actual_start = max(now + timedelta(days=1), month_start)
        label = month_start.strftime("%B %Y")
        ru_months = {
            "January": "Январь", "February": "Февраль", "March": "Март",
            "April": "Апрель", "May": "Май", "June": "Июнь",
            "July": "Июль", "August": "Август", "September": "Сентябрь",
            "October": "Октябрь", "November": "Ноябрь", "December": "Декабрь",
        }
        for en, ru in ru_months.items():
            label = label.replace(en, ru)
        d_from = actual_start.strftime("%d/%m/%Y")
        d_to = month_end.strftime("%d/%m/%Y")
        options.append((f"📅 {label}", d_from, d_to))

    options.append((
        "🌐 Любые даты (6 мес)",
        (now + timedelta(days=1)).strftime("%d/%m/%Y"),
        (now + timedelta(days=180)).strftime("%d/%m/%Y"),
    ))

    for label, d_from, d_to in options:
        builder.button(text=label, callback_data=f"{label_prefix}:{d_from}:{d_to}")
    builder.adjust(1)
    return builder.as_markup()


# ── Flight card ────────────────────────────────────────────────────────────────

def flight_card_kb(flight: dict, idx: int, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛒 Купить билет", url=flight["link"]),
        InlineKeyboardButton(text="❤️ Сохранить", callback_data=f"fav:save:{idx}"),
    )
    if total > 1:
        nav = []
        if idx > 0:
            nav.append(InlineKeyboardButton(text="◀️ Дешевле", callback_data=f"flight:prev:{idx}"))
        nav.append(InlineKeyboardButton(text=f"{idx+1} / {total}", callback_data="noop"))
        if idx < total - 1:
            nav.append(InlineKeyboardButton(text="Дороже ▶️", callback_data=f"flight:next:{idx}"))
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(text="🔔 Алерт на маршрут",
                             callback_data=f"alert:route:{flight['origin']}:{flight['destination']}"),
        InlineKeyboardButton(text="🔎 Новый поиск", callback_data="search:new"),
    )
    return builder.as_markup()


# ── Hot deal card ──────────────────────────────────────────────────────────────

def hot_deal_kb(deal: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    link = deal.get("link", "https://www.google.com/travel/flights")
    builder.row(
        InlineKeyboardButton(text="🛒 Купить билет", url=link),
        InlineKeyboardButton(text="❤️ Сохранить", callback_data=f"fav:hotdeal:{deal.get('id', 0)}"),
    )
    builder.row(
        InlineKeyboardButton(text="🔔 Алерт на маршрут",
                             callback_data=f"alert:route:{deal.get('origin','WAW')}:{deal.get('destination','BCN')}"),
        InlineKeyboardButton(text="🔥 Ещё горящие", callback_data="hot:more"),
    )
    return builder.as_markup()


# ── Alerts list ────────────────────────────────────────────────────────────────

def alerts_list_kb(alerts: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for a in alerts:
        label = f"✈️ {a['origin']} → {a['destination']}"
        if a.get("price_max"):
            label += f"  до {a['price_max']}€"
        builder.button(text=label, callback_data=f"alert:del:{a['id']}")
    builder.row(InlineKeyboardButton(text="➕ Добавить алерт", callback_data="alert:new"))
    if alerts:
        builder.row(InlineKeyboardButton(text="🗑 Удалить все", callback_data="alert:delall"))
    builder.adjust(1)
    return builder.as_markup()


# ── Favorites ──────────────────────────────────────────────────────────────────

def favorites_kb(favs: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for f in favs:
        airline = f.get("airline") or ""
        label = f"✈️ {f['origin']}→{f['destination']}  {f['price']}€  {airline}"
        builder.button(text=label[:60], callback_data=f"fav:open:{f['id']}")
    if favs:
        builder.row(InlineKeyboardButton(text="🗑 Очистить всё", callback_data="fav:clear"))
    builder.adjust(1)
    return builder.as_markup()


# ── VIP ────────────────────────────────────────────────────────────────────────

def vip_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"⭐ Оплатить {VIP_PRICE_STARS} Stars (Telegram)", callback_data="vip:pay:stars")
    builder.button(text=f"💳 Revolut / BLIK — {VIP_PRICE_PLN} zł", callback_data="vip:pay:manual")
    builder.button(text="📢 Канал с горящими", url=CHANNEL_LINK)
    builder.adjust(1)
    return builder.as_markup()


def vip_manual_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Я оплатил — жду активацию", callback_data="vip:paid:manual")
    builder.button(text="◀️ Назад", callback_data="vip:back")
    builder.adjust(1)
    return builder.as_markup()


# ── Cancel ─────────────────────────────────────────────────────────────────────

def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()


# ── Share ──────────────────────────────────────────────────────────────────────

def share_kb(flight: dict, bot_username: str = "DDSkyCheapBot") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 Купить билет", url=flight["link"])
    share_text = (
        f"✈️ Нашёл билет {flight.get('origin_city','?')} → {flight.get('dest_city','?')} "
        f"за {flight['price']}€! Смотри в @{bot_username}"
    )
    share_url = (
        f"https://t.me/share/url?url={urllib.parse.quote(flight['link'])}"
        f"&text={urllib.parse.quote(share_text)}"
    )
    builder.button(text="📤 Поделиться", url=share_url)
    builder.adjust(2)
    return builder.as_markup()
