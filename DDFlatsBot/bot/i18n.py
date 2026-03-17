# Simple i18n — Russian (default), Ukrainian, Polish

TEXTS = {
    "ru": {
        "start_greeting": "👋 Привет, {name}! {badge}\n\n🏙 Я <b>DDFlatsBot</b> — нахожу квартиры в Варшаве.\nПарсю OLX, Otodom, Gratka, Morizon каждые 10 минут.",
        "btn_find": "🏠 Найти квартиру",
        "btn_filter": "🔍 Фильтры",
        "btn_favorites": "❤️ Избранное",
        "btn_alerts": "🔔 Алерты",
        "btn_vip": "⭐ VIP доступ",
        "btn_ref": "👥 Пригласить друга",
        "btn_prices": "📊 Цены по районам",
        "btn_today": "🆕 Сегодня",
        "btn_next": "➡️ Следующая",
        "btn_fav": "❤️ Избранное",
        "btn_skip": "🗑 Пропустить",
        "btn_map": "🗺 На карте",
        "btn_filter_inline": "🔍 Фильтры",
        "no_apts": "😔 Квартир по твоим фильтрам не найдено.\n\nПопробуй изменить фильтры: /filter",
        "limit_reached": "⛔ Бесплатный лимит {limit} квартир исчерпан.\n\n💎 VIP — безлимит + алерты + уведомления о снижении цены",
        "vip_active": "💎 <b>VIP активен до: {until}</b>",
        "choose_lang": "🌍 Выбери язык / Wybierz język / Оберіть мову:",
        "lang_set": "✅ Язык установлен: Русский",
    },
    "uk": {
        "start_greeting": "👋 Привіт, {name}! {badge}\n\n🏙 Я <b>DDFlatsBot</b> — знаходжу квартири у Варшаві.\nПарсю OLX, Otodom, Gratka, Morizon кожні 10 хвилин.",
        "btn_find": "🏠 Знайти квартиру",
        "btn_filter": "🔍 Фільтри",
        "btn_favorites": "❤️ Обране",
        "btn_alerts": "🔔 Алерти",
        "btn_vip": "⭐ VIP доступ",
        "btn_ref": "👥 Запросити друга",
        "btn_prices": "📊 Ціни по районах",
        "btn_today": "🆕 Сьогодні",
        "btn_next": "➡️ Наступна",
        "btn_fav": "❤️ Обране",
        "btn_skip": "🗑 Пропустити",
        "btn_map": "🗺 На карті",
        "btn_filter_inline": "🔍 Фільтри",
        "no_apts": "😔 Квартир за вашими фільтрами не знайдено.\n\nСпробуй змінити фільтри: /filter",
        "limit_reached": "⛔ Безкоштовний ліміт {limit} квартир вичерпано.\n\n💎 VIP — безліміт + алерти + сповіщення про зниження ціни",
        "vip_active": "💎 <b>VIP активний до: {until}</b>",
        "choose_lang": "🌍 Виберіть мову / Wybierz język / Выбери язык:",
        "lang_set": "✅ Мову встановлено: Українська",
    },
    "pl": {
        "start_greeting": "👋 Cześć, {name}! {badge}\n\n🏙 Jestem <b>DDFlatsBot</b> — szukam mieszkań w Warszawie.\nParsuje OLX, Otodom, Gratka, Morizon co 10 minut.",
        "btn_find": "🏠 Znajdź mieszkanie",
        "btn_filter": "🔍 Filtry",
        "btn_favorites": "❤️ Ulubione",
        "btn_alerts": "🔔 Alerty",
        "btn_vip": "⭐ Dostęp VIP",
        "btn_ref": "👥 Zaproś znajomego",
        "btn_prices": "📊 Ceny w dzielnicach",
        "btn_today": "🆕 Dzisiaj",
        "btn_next": "➡️ Następne",
        "btn_fav": "❤️ Ulubione",
        "btn_skip": "🗑 Pomiń",
        "btn_map": "🗺 Na mapie",
        "btn_filter_inline": "🔍 Filtry",
        "no_apts": "😔 Nie znaleziono mieszkań wg Twoich filtrów.\n\nSpróbuj zmienić filtry: /filter",
        "limit_reached": "⛔ Darmowy limit {limit} mieszkań wyczerpany.\n\n💎 VIP — bez limitu + alerty + powiadomienia o obniżkach cen",
        "vip_active": "💎 <b>VIP aktywny do: {until}</b>",
        "choose_lang": "🌍 Wybierz język / Выбери язык / Оберіть мову:",
        "lang_set": "✅ Język ustawiony: Polski",
    },
}

DEFAULT_LANG = "ru"


def t(lang: str, key: str, **kwargs) -> str:
    lang = lang if lang in TEXTS else DEFAULT_LANG
    text = TEXTS[lang].get(key, TEXTS[DEFAULT_LANG].get(key, key))
    return text.format(**kwargs) if kwargs else text
