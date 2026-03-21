"""
Translations: ru / pl / en
"""

TEXTS = {
    # ── /start ──────────────────────────────────────────────────────────────
    "welcome": {
        "ru": "✈️ <b>{bot}</b>{badge}\n\nПривет, {name}! Нахожу самые дешёвые авиабилеты из Польши.\n\n🔎 Поисков сегодня: <b>{left}</b> {vip_str}\n🔥 Горящие обновляются каждые 2 часа\n📢 Канал: {channel}{extra}\n\nВыбери действие 👇",
        "pl": "✈️ <b>{bot}</b>{badge}\n\nCześć, {name}! Znajduję najtańsze bilety lotnicze z Polski.\n\n🔎 Wyszukiwań dziś: <b>{left}</b> {vip_str}\n🔥 Gorące oferty aktualizowane co 2 godziny\n📢 Kanał: {channel}{extra}\n\nWybierz akcję 👇",
        "en": "✈️ <b>{bot}</b>{badge}\n\nHey, {name}! I find the cheapest flights from Poland.\n\n🔎 Searches today: <b>{left}</b> {vip_str}\n🔥 Hot deals updated every 2 hours\n📢 Channel: {channel}{extra}\n\nChoose an action 👇",
    },
    "early_badge": {
        "ru": "\n\n🌟 <b>Ты один из первых 50 пользователей!</b>\nVIP навсегда — бесплатно. Спасибо что с нами!",
        "pl": "\n\n🌟 <b>Jesteś jednym z pierwszych 50 użytkowników!</b>\nVIP na zawsze — za darmo. Dziękujemy!",
        "en": "\n\n🌟 <b>You're one of the first 50 users!</b>\nVIP forever — for free. Thank you!",
    },
    "choose_lang": {
        "ru": "🌍 Выбери язык / Wybierz język / Choose language:",
        "pl": "🌍 Wyбери язык / Wybierz język / Choose language:",
        "en": "🌍 Choose language / Wybierz język / Выбери язык:",
    },
    "lang_set": {
        "ru": "✅ Язык установлен: Русский",
        "pl": "✅ Język ustawiony: Polski",
        "en": "✅ Language set: English",
    },
    # ── Search ───────────────────────────────────────────────────────────────
    "search_from": {
        "ru": "🛫 <b>Откуда летим?</b>",
        "pl": "🛫 <b>Skąd lecimy?</b>",
        "en": "🛫 <b>Flying from?</b>",
    },
    "search_to": {
        "ru": "🛬 <b>Куда летим?</b>",
        "pl": "🛬 <b>Dokąd lecimy?</b>",
        "en": "🛬 <b>Flying to?</b>",
    },
    "search_dates": {
        "ru": "📅 <b>Когда летим?</b>",
        "pl": "📅 <b>Kiedy lecimy?</b>",
        "en": "📅 <b>When are we flying?</b>",
    },
    "searching": {
        "ru": "🔍 Ищу билеты <b>{origin} → {dest}</b>...\n⏳ Обычно 5–10 секунд",
        "pl": "🔍 Szukam biletów <b>{origin} → {dest}</b>...\n⏳ Zwykle 5–10 sekund",
        "en": "🔍 Searching flights <b>{origin} → {dest}</b>...\n⏳ Usually 5–10 seconds",
    },
    "no_flights": {
        "ru": "😔 Билеты <b>{origin} → {dest}</b> не найдены.\n\nПопробуй:\n• Другие даты\n• Другой аэропорт",
        "pl": "😔 Nie znaleziono biletów <b>{origin} → {dest}</b>.\n\nSpróbuj:\n• Inne daty\n• Inne lotnisko",
        "en": "😔 No flights found <b>{origin} → {dest}</b>.\n\nTry:\n• Different dates\n• Different airport",
    },
    "no_roundtrip": {
        "ru": "😔 Рейсы туда-обратно <b>{origin} ↔ {dest}</b> не найдены.\nПопробуй другие даты.",
        "pl": "😔 Nie znaleziono lotów w obie strony <b>{origin} ↔ {dest}</b>.\nSpróbuj innych dat.",
        "en": "😔 No round-trip flights <b>{origin} ↔ {dest}</b> found.\nTry different dates.",
    },
    "trip_type": {
        "ru": "✈️ <b>Тип поездки:</b>",
        "pl": "✈️ <b>Rodzaj podróży:</b>",
        "en": "✈️ <b>Trip type:</b>",
    },
    "limit_reached": {
        "ru": "⛔ Лимит поисков исчерпан.\nКупи VIP для безлимитного доступа.",
        "pl": "⛔ Limit wyszukiwań wyczerpany.\nKup VIP dla nieograniczonego dostępu.",
        "en": "⛔ Search limit reached.\nBuy VIP for unlimited access.",
    },
    # ── Hot deals ────────────────────────────────────────────────────────────
    "hot_title": {
        "ru": "🔥 <b>Горящие билеты — {n} предложений:</b>",
        "pl": "🔥 <b>Gorące oferty — {n} propozycji:</b>",
        "en": "🔥 <b>Hot deals — {n} offers:</b>",
    },
    "hot_empty": {
        "ru": "🔥 <b>Горящие билеты</b>\n\nПока нет актуальных предложений.\nОбновляем каждые 2 часа!\n\n📢 Подпишись: {channel}",
        "pl": "🔥 <b>Gorące oferty</b>\n\nBrak aktualnych ofert.\nAktualizujemy co 2 godziny!\n\n📢 Subskrybuj: {channel}",
        "en": "🔥 <b>Hot deals</b>\n\nNo current offers.\nUpdated every 2 hours!\n\n📢 Subscribe: {channel}",
    },
    # ── VIP ──────────────────────────────────────────────────────────────────
    "vip_text": {
        "ru": "⭐ <b>VIP доступ</b>\n\n✅ Безлимитные поиски\n✅ Приоритетные алерты\n✅ Расширенные фильтры\n\n💰 <b>{price_pln} zł/мес</b> или <b>{price_stars} ⭐ Stars</b>",
        "pl": "⭐ <b>Dostęp VIP</b>\n\n✅ Nieograniczone wyszukiwania\n✅ Priorytetowe alerty\n✅ Rozszerzone filtry\n\n💰 <b>{price_pln} zł/mies</b> lub <b>{price_stars} ⭐ Stars</b>",
        "en": "⭐ <b>VIP Access</b>\n\n✅ Unlimited searches\n✅ Priority alerts\n✅ Extended filters\n\n💰 <b>{price_pln} PLN/month</b> or <b>{price_stars} ⭐ Stars</b>",
    },
    # ── Alerts ───────────────────────────────────────────────────────────────
    "alerts_empty": {
        "ru": "🔔 <b>Алерты</b>\n\nНет активных алертов.\nАлерт — уведомление когда цена упадёт ниже нужной суммы.",
        "pl": "🔔 <b>Alerty</b>\n\nBrak aktywnych alertów.\nAlert — powiadomienie gdy cena spadnie poniżej wybranej kwoty.",
        "en": "🔔 <b>Alerts</b>\n\nNo active alerts.\nAlert — notification when price drops below your target.",
    },
    "alert_origin": {
        "ru": "🔔 <b>Новый алерт</b>\n\nОткуда летим?",
        "pl": "🔔 <b>Nowy alert</b>\n\nSkąd lecimy?",
        "en": "🔔 <b>New alert</b>\n\nFlying from?",
    },
    "alert_dest": {
        "ru": "🛬 Куда летим?",
        "pl": "🛬 Dokąd lecimy?",
        "en": "🛬 Flying to?",
    },
    "alert_price": {
        "ru": "💰 Максимальная цена (EUR)?\n\nНапример: <code>50</code>",
        "pl": "💰 Maksymalna cena (EUR)?\n\nNp.: <code>50</code>",
        "en": "💰 Maximum price (EUR)?\n\nE.g.: <code>50</code>",
    },
    "alert_saved": {
        "ru": "✅ Алерт создан!\n✈️ {origin} → {dest}\n💰 до {price} EUR\n\nУведомлю как только найду дешёвый рейс.",
        "pl": "✅ Alert utworzony!\n✈️ {origin} → {dest}\n💰 do {price} EUR\n\nPowiadomię gdy znajdę tani lot.",
        "en": "✅ Alert created!\n✈️ {origin} → {dest}\n💰 up to {price} EUR\n\nI'll notify you when I find a cheap flight.",
    },
    # ── Misc ─────────────────────────────────────────────────────────────────
    "cancelled": {
        "ru": "❌ Отменено.",
        "pl": "❌ Anulowano.",
        "en": "❌ Cancelled.",
    },
    "session_expired": {
        "ru": "⏰ Сессия истекла. Начни новый поиск.",
        "pl": "⏰ Sesja wygasła. Rozpocznij nowe wyszukiwanie.",
        "en": "⏰ Session expired. Start a new search.",
    },
    "manual_iata": {
        "ru": "✏️ Введи IATA код аэропорта (3 буквы):\nНапример: <code>DXB</code>, <code>BKK</code>, <code>JFK</code>",
        "pl": "✏️ Wpisz kod IATA lotniska (3 litery):\nNp.: <code>DXB</code>, <code>BKK</code>, <code>JFK</code>",
        "en": "✏️ Enter airport IATA code (3 letters):\nE.g.: <code>DXB</code>, <code>BKK</code>, <code>JFK</code>",
    },
    "return_when": {
        "ru": "🔙 Когда возвращаемся?",
        "pl": "🔙 Kiedy wracamy?",
        "en": "🔙 When are we returning?",
    },
    "cheapdates_searching": {
        "ru": "📅 Ищу самые дешёвые даты <b>{origin} → {dest}</b>...\n⏳ Секунду",
        "pl": "📅 Szukam najtańszych dat <b>{origin} → {dest}</b>...\n⏳ Chwileczkę",
        "en": "📅 Finding cheapest dates <b>{origin} → {dest}</b>...\n⏳ One moment",
    },
    "cheapdates_empty": {
        "ru": "😔 Не нашёл дешёвых дат для <b>{origin} → {dest}</b>.",
        "pl": "😔 Nie znaleziono tanich dat dla <b>{origin} → {dest}</b>.",
        "en": "😔 No cheap dates found for <b>{origin} → {dest}</b>.",
    },
}


def t(key: str, lang: str = "ru", **kwargs) -> str:
    """Get translated string."""
    lang = lang if lang in ("ru", "pl", "en") else "ru"
    text = TEXTS.get(key, {}).get(lang) or TEXTS.get(key, {}).get("ru", key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text
