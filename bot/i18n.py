# Simple i18n — Russian (default), Ukrainian, Polish

TEXTS = {
    "ru": {
        # Start
        "start_greeting": (
            "👋 Привет, {name}!\n"
            "{badge}\n\n"
            "🏙 <b>DDFlatsBot</b> — квартиры Варшавы в одном месте.\n"
            "Парсю OLX · Otodom · Gratka · Morizon каждые 10 минут.\n\n"
            "⚠️ Бот агрегирует объявления с внешних сайтов. "
            "Всегда проверяй квартиру лично."
        ),
        "disclaimer": (
            "⚠️ <b>Перед использованием прочитай:</b>\n\n"
            "DDFlatsBot — агрегатор объявлений с OLX, Otodom, Gratka, Morizon.\n\n"
            "<b>Мы НЕ несём ответственности за:</b>\n"
            "• Достоверность объявлений\n"
            "• Действия арендодателей\n"
            "• Мошеннические объявления\n\n"
            "<b>Правила безопасности:</b>\n"
            "🔍 Всегда проверяй квартиру лично\n"
            "💳 Не переводи деньги без просмотра\n"
            "📋 Требуй договор аренды\n\n"
            "Нажимая кнопку ниже, ты соглашаешься с условиями."
        ),
        "btn_accept": "✅ Принимаю условия",
        "btn_find": "🏠 Найти квартиру",
        "btn_filter": "🔍 Фильтры",
        "btn_favorites": "❤️ Избранное",
        "btn_alerts": "🔔 Алерты",
        "btn_vip": "⭐ VIP доступ",
        "btn_ref": "👥 Пригласить друга",
        "btn_cheap": "💚 Дешёвые",
        "btn_hot": "🔥 Горячие",
        "btn_drops": "📉 Снижения цен",
        "btn_map": "🗺 Карта цен",
        "btn_notes": "📝 Заметки",
        "btn_mystats": "📊 Моя статистика",
        "btn_next": "➡️ Следующая",
        "btn_fav_add": "❤️ Избранное",
        "btn_on_map": "🗺 На карте",
        "btn_note": "📝 Заметка",
        "btn_similar": "🔍 Похожие",
        "no_apts": "😔 Квартир по твоим фильтрам не найдено.\n\nПопробуй изменить фильтры: /filter\nИли сбрось их: /start",
        "no_apts_yet": "😔 Квартир пока нет. Парсер работает каждые 10 минут.\n\nПопробуй позже или измени фильтры: /filter",
        "wrap_around": "🔄 Показываю сначала — новых квартир пока нет.",
        "limit_reached": "⛔ Бесплатный лимит {limit} квартир исчерпан.\n\n💎 VIP — безлимит + алерты + уведомления о снижении цены",
        "vip_badge": "💎 VIP до {until}",
        "free_badge": "🆓 {bar} {used}/{total}",
        "choose_lang": "🌍 Выбери язык:",
        "lang_set_ru": "🇷🇺 Язык: Русский",
        "lang_set_uk": "🇺🇦 Мова: Українська",
        "lang_set_pl": "🇵🇱 Język: Polski",
        "early_adopter": "\n\n🎁 <b>Ты в числе первых 50!</b> VIP на 7 дней бесплатно!",
        "ref_bonus": "🎁 Реферальный бонус активирован! Пригласивший получил 7 дней VIP.",
        "vip_fav10": "\n\n🎁 <b>+3 дня VIP</b> за 10 сохранённых квартир!",
        "vip_loyal": "\n\n🎁 <b>+2 дня VIP</b> за активность!",
        "remaining": "\n\n📦 Ещё {n} квартир по фильтрам",
        "warn_check": "⚠️ Всегда проверяй квартиру лично перед оплатой.",
    },
    "uk": {
        "start_greeting": (
            "👋 Привіт, {name}!\n"
            "{badge}\n\n"
            "🏙 <b>DDFlatsBot</b> — квартири Варшави в одному місці.\n"
            "Парсю OLX · Otodom · Gratka · Morizon кожні 10 хвилин.\n\n"
            "⚠️ Бот агрегує оголошення з зовнішніх сайтів. "
            "Завжди перевіряй квартиру особисто."
        ),
        "disclaimer": (
            "⚠️ <b>Перед використанням прочитай:</b>\n\n"
            "DDFlatsBot — агрегатор оголошень з OLX, Otodom, Gratka, Morizon.\n\n"
            "<b>Ми НЕ несемо відповідальності за:</b>\n"
            "• Достовірність оголошень\n"
            "• Дії орендодавців\n"
            "• Шахрайські оголошення\n\n"
            "<b>Правила безпеки:</b>\n"
            "🔍 Завжди перевіряй квартиру особисто\n"
            "💳 Не переводь гроші без перегляду\n"
            "📋 Вимагай договір оренди\n\n"
            "Натискаючи кнопку нижче, ти погоджуєшся з умовами."
        ),
        "btn_accept": "✅ Приймаю умови",
        "btn_find": "🏠 Знайти квартиру",
        "btn_filter": "🔍 Фільтри",
        "btn_favorites": "❤️ Обране",
        "btn_alerts": "🔔 Алерти",
        "btn_vip": "⭐ VIP доступ",
        "btn_ref": "👥 Запросити друга",
        "btn_cheap": "💚 Дешеві",
        "btn_hot": "🔥 Гарячі",
        "btn_drops": "📉 Зниження цін",
        "btn_map": "🗺 Карта цін",
        "btn_notes": "📝 Нотатки",
        "btn_mystats": "📊 Моя статистика",
        "btn_next": "➡️ Наступна",
        "btn_fav_add": "❤️ Обране",
        "btn_on_map": "🗺 На карті",
        "btn_note": "📝 Нотатка",
        "btn_similar": "🔍 Схожі",
        "no_apts": "😔 Квартир за вашими фільтрами не знайдено.\n\nСпробуй змінити фільтри: /filter",
        "no_apts_yet": "😔 Квартир поки немає. Парсер працює кожні 10 хвилин.",
        "wrap_around": "🔄 Показую спочатку — нових квартир поки немає.",
        "limit_reached": "⛔ Безкоштовний ліміт {limit} квартир вичерпано.\n\n💎 VIP — безліміт + алерти + сповіщення про зниження ціни",
        "vip_badge": "💎 VIP до {until}",
        "free_badge": "🆓 {bar} {used}/{total}",
        "choose_lang": "🌍 Оберіть мову:",
        "lang_set_ru": "🇷🇺 Мова: Російська",
        "lang_set_uk": "🇺🇦 Мова: Українська",
        "lang_set_pl": "🇵🇱 Мова: Польська",
        "early_adopter": "\n\n🎁 <b>Ти серед перших 50!</b> VIP на 7 днів безкоштовно!",
        "ref_bonus": "🎁 Реферальний бонус активовано! Той хто запросив отримав 7 днів VIP.",
        "vip_fav10": "\n\n🎁 <b>+3 дні VIP</b> за 10 збережених квартир!",
        "vip_loyal": "\n\n🎁 <b>+2 дні VIP</b> за активність!",
        "remaining": "\n\n📦 Ще {n} квартир за фільтрами",
        "warn_check": "⚠️ Завжди перевіряй квартиру особисто перед оплатою.",
    },
    "pl": {
        "start_greeting": (
            "👋 Cześć, {name}!\n"
            "{badge}\n\n"
            "🏙 <b>DDFlatsBot</b> — mieszkania Warszawy w jednym miejscu.\n"
            "Parsuje OLX · Otodom · Gratka · Morizon co 10 minut.\n\n"
            "⚠️ Bot agreguje ogłoszenia z zewnętrznych stron. "
            "Zawsze sprawdzaj mieszkanie osobiście."
        ),
        "disclaimer": (
            "⚠️ <b>Przed użyciem przeczytaj:</b>\n\n"
            "DDFlatsBot — agregator ogłoszeń z OLX, Otodom, Gratka, Morizon.\n\n"
            "<b>NIE ponosimy odpowiedzialności za:</b>\n"
            "• Wiarygodność ogłoszeń\n"
            "• Działania wynajmujących\n"
            "• Oszukańcze ogłoszenia\n\n"
            "<b>Zasady bezpieczeństwa:</b>\n"
            "🔍 Zawsze sprawdzaj mieszkanie osobiście\n"
            "💳 Nie przelewaj pieniędzy bez oglądania\n"
            "📋 Wymagaj umowy najmu\n\n"
            "Klikając przycisk poniżej, zgadzasz się z warunkami."
        ),
        "btn_accept": "✅ Akceptuję warunki",
        "btn_find": "🏠 Znajdź mieszkanie",
        "btn_filter": "🔍 Filtry",
        "btn_favorites": "❤️ Ulubione",
        "btn_alerts": "🔔 Alerty",
        "btn_vip": "⭐ Dostęp VIP",
        "btn_ref": "👥 Zaproś znajomego",
        "btn_cheap": "💚 Najtańsze",
        "btn_hot": "🔥 Gorące",
        "btn_drops": "📉 Obniżki cen",
        "btn_map": "🗺 Mapa cen",
        "btn_notes": "📝 Notatki",
        "btn_mystats": "📊 Moje statystyki",
        "btn_next": "➡️ Następne",
        "btn_fav_add": "❤️ Ulubione",
        "btn_on_map": "🗺 Na mapie",
        "btn_note": "📝 Notatka",
        "btn_similar": "🔍 Podobne",
        "no_apts": "😔 Nie znaleziono mieszkań wg Twoich filtrów.\n\nSpróbuj zmienić filtry: /filter",
        "no_apts_yet": "😔 Brak mieszkań. Parser działa co 10 minut.",
        "wrap_around": "🔄 Pokazuję od początku — brak nowych mieszkań.",
        "limit_reached": "⛔ Darmowy limit {limit} mieszkań wyczerpany.\n\n💎 VIP — bez limitu + alerty + powiadomienia o obniżkach",
        "vip_badge": "💎 VIP do {until}",
        "free_badge": "🆓 {bar} {used}/{total}",
        "choose_lang": "🌍 Wybierz język:",
        "lang_set_ru": "🇷🇺 Język: Rosyjski",
        "lang_set_uk": "🇺🇦 Język: Ukraiński",
        "lang_set_pl": "🇵🇱 Język: Polski",
        "early_adopter": "\n\n🎁 <b>Jesteś w pierwszych 50!</b> VIP na 7 dni za darmo!",
        "ref_bonus": "🎁 Bonus referencyjny aktywowany! Zapraszający otrzymał 7 dni VIP.",
        "vip_fav10": "\n\n🎁 <b>+3 dni VIP</b> za 10 zapisanych mieszkań!",
        "vip_loyal": "\n\n🎁 <b>+2 dni VIP</b> za aktywność!",
        "remaining": "\n\n📦 Jeszcze {n} mieszkań wg filtrów",
        "warn_check": "⚠️ Zawsze sprawdzaj mieszkanie osobiście przed płatnością.",
    },
}

DEFAULT_LANG = "ru"


def t(lang: str, key: str, **kwargs) -> str:
    lang = lang if lang in TEXTS else DEFAULT_LANG
    text = TEXTS[lang].get(key, TEXTS[DEFAULT_LANG].get(key, key))
    return text.format(**kwargs) if kwargs else text
