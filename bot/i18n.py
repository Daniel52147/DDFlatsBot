# i18n — Russian, Ukrainian, Polish

TEXTS = {
    "ru": {
        # ── Onboarding ──────────────────────────────────────────
        "welcome_new": (
            "🏙 <b>DDFlatsBot</b> — все квартиры Варшавы в одном месте.\n\n"
            "✅ OLX · Otodom · Gratka · Morizon · Lento и другие\n"
            "✅ Обновление каждые 10 минут\n"
            "✅ Фильтры по цене, району, комнатам\n"
            "✅ Мгновенные уведомления о новых квартирах\n"
            "✅ Аренда посуточно через Booking и Airbnb\n\n"
            "👇 Выбери язык:"
        ),
        "choose_lang": "🌍 Выбери язык:",
        "disclaimer": (
            "📋 <b>Условия использования DDFlatsBot</b>\n\n"
            "Бот агрегирует объявления с OLX, Otodom, Gratka, Morizon и других сайтов.\n\n"
            "<b>⚠️ Мы НЕ несём ответственности за:</b>\n"
            "• Достоверность и актуальность объявлений\n"
            "• Действия арендодателей\n"
            "• Мошеннические объявления\n\n"
            "<b>🔐 Правила безопасности:</b>\n"
            "🔍 Всегда проверяй квартиру лично перед оплатой\n"
            "💳 Никогда не переводи деньги без просмотра\n"
            "📋 Требуй подписанный договор аренды\n"
            "🚫 При подозрении на мошенничество — сообщи нам\n\n"
            "Нажимая кнопку ниже, ты подтверждаешь что прочитал и согласен с условиями."
        ),
        "btn_accept": "✅ Принимаю условия",
        "btn_decline": "❌ Отказаться",

        # ── Main menu ───────────────────────────────────────────
        "start_greeting": (
            "👋 Привет, <b>{name}</b>!\n"
            "{badge}\n\n"
            "🏙 <b>DDFlatsBot</b> — квартиры Варшавы в одном месте.\n"
            "Обновляю каждые 10 минут: OLX · Otodom · Gratka · Morizon.\n\n"
            "⚠️ <i>Всегда проверяй квартиру лично перед оплатой.</i>"
        ),
        "btn_find":      "🏠 Найти квартиру",
        "btn_filter":    "🔍 Фильтры",
        "btn_favorites": "❤️ Избранное",
        "btn_alerts":    "🔔 Алерты",
        "btn_vip":       "⭐ VIP",
        "btn_ref":       "👥 Пригласить друга",
        "btn_cheap":     "💚 Дешёвые",
        "btn_hot":       "🔥 Горячие",
        "btn_drops":     "📉 Снижения цен",
        "btn_daily":     "🏖 Посуточно",
        "btn_mystats":   "📊 Статистика",

        # ── Apartment card ──────────────────────────────────────
        "btn_next":    "➡️ Следующая",
        "btn_fav_add": "❤️ Сохранить",
        "btn_on_map":  "🗺 На карте",
        "btn_note":    "📝 Заметка",
        "btn_similar": "🔍 Похожие",

        # ── Status ──────────────────────────────────────────────
        "no_apts":     "😔 Квартир по твоим фильтрам не найдено.\n\nИзмени фильтры: /filter",
        "no_apts_yet": "😔 Квартир пока нет. Парсер работает каждые 10 минут.\n\nПопробуй позже: /next",
        "wrap_around": "🔄 Показываю сначала — новых квартир пока нет.",
        "limit_reached": (
            "⛔ <b>Бесплатный лимит {limit} квартир исчерпан.</b>\n\n"
            "💎 <b>VIP — 19 zł/мес:</b>\n"
            "✅ Безлимитный просмотр\n"
            "✅ Умные алерты\n"
            "✅ Уведомления о снижении цены"
        ),
        "vip_badge":  "💎 VIP до {until}",
        "free_badge": "🆓 {bar} {used}/{total}",

        # ── Bonuses ─────────────────────────────────────────────
        "early_adopter": "\n\n🎁 <b>Ты в числе первых 50!</b> VIP на 7 дней бесплатно!",
        "ref_bonus":     "🎁 Реферальный бонус! Пригласивший получил 7 дней VIP.",
        "vip_fav10":     "\n\n🎁 <b>+3 дня VIP</b> за 10 сохранённых квартир!",
        "vip_loyal":     "\n\n🎁 <b>+2 дня VIP</b> за активность!",
        "remaining":     "\n\n📦 Ещё {n} квартир по фильтрам",
        "warn_check":    "Всегда проверяй квартиру лично перед оплатой.",

        # ── Language ────────────────────────────────────────────
        "lang_set_ru": "🇷🇺 Язык: Русский",
        "lang_set_uk": "🇺🇦 Мова: Українська",
        "lang_set_pl": "🇵🇱 Język: Polski",

        # ── Daily rental ────────────────────────────────────────
        "daily_text": (
            "🏖 <b>Аренда посуточно в Варшаве</b>\n\n"
            "Выбери количество дней — я открою лучшие предложения:\n\n"
            "🏨 Booking.com — отели и апартаменты\n"
            "🏠 Airbnb — квартиры от хозяев\n"
            "🛏 Nocowanie.pl — польская платформа\n\n"
            "Или нажми кнопку выше чтобы посмотреть объявления из нашей базы."
        ),
        "btn_1day":   "1 день",
        "btn_3days":  "3 дня",
        "btn_7days":  "7 дней",
        "btn_14days": "14 дней",
        "btn_30days": "30 дней",
        "daily_links": (
            "🔗 <b>Аренда на {days} дн. в Варшаве:</b>\n\n"
            "🏨 <a href=\"{booking}\">Booking.com</a> — отели и апартаменты\n"
            "🏠 <a href=\"{airbnb}\">Airbnb</a> — квартиры от хозяев\n"
            "🛏 <a href=\"{nocowanie}\">Nocowanie.pl</a> — польская платформа\n\n"
            "💡 Сравни цены на всех платформах перед бронированием."
        ),
    },

    "uk": {
        "welcome_new": (
            "🏙 <b>DDFlatsBot</b> — всі квартири Варшави в одному місці.\n\n"
            "✅ OLX · Otodom · Gratka · Morizon · Lento та інші\n"
            "✅ Оновлення кожні 10 хвилин\n"
            "✅ Фільтри за ціною, районом, кімнатами\n"
            "✅ Миттєві сповіщення про нові квартири\n"
            "✅ Оренда подобово через Booking та Airbnb\n\n"
            "👇 Оберіть мову:"
        ),
        "choose_lang": "🌍 Оберіть мову:",
        "disclaimer": (
            "📋 <b>Умови використання DDFlatsBot</b>\n\n"
            "Бот агрегує оголошення з OLX, Otodom, Gratka, Morizon та інших сайтів.\n\n"
            "<b>⚠️ Ми НЕ несемо відповідальності за:</b>\n"
            "• Достовірність та актуальність оголошень\n"
            "• Дії орендодавців\n"
            "• Шахрайські оголошення\n\n"
            "<b>🔐 Правила безпеки:</b>\n"
            "🔍 Завжди перевіряй квартиру особисто перед оплатою\n"
            "💳 Ніколи не переводь гроші без перегляду\n"
            "📋 Вимагай підписаний договір оренди\n"
            "🚫 При підозрі на шахрайство — повідом нам\n\n"
            "Натискаючи кнопку нижче, ти підтверджуєш що прочитав і погоджуєшся з умовами."
        ),
        "btn_accept": "✅ Приймаю умови",
        "btn_decline": "❌ Відмовитись",
        "start_greeting": (
            "👋 Привіт, <b>{name}</b>!\n"
            "{badge}\n\n"
            "🏙 <b>DDFlatsBot</b> — квартири Варшави в одному місці.\n"
            "Оновлюю кожні 10 хвилин: OLX · Otodom · Gratka · Morizon.\n\n"
            "⚠️ <i>Завжди перевіряй квартиру особисто перед оплатою.</i>"
        ),
        "btn_find":      "🏠 Знайти квартиру",
        "btn_filter":    "🔍 Фільтри",
        "btn_favorites": "❤️ Обране",
        "btn_alerts":    "🔔 Алерти",
        "btn_vip":       "⭐ VIP",
        "btn_ref":       "👥 Запросити друга",
        "btn_cheap":     "💚 Дешеві",
        "btn_hot":       "🔥 Гарячі",
        "btn_drops":     "📉 Зниження цін",
        "btn_daily":     "🏖 Подобово",
        "btn_mystats":   "📊 Статистика",
        "btn_next":    "➡️ Наступна",
        "btn_fav_add": "❤️ Зберегти",
        "btn_on_map":  "🗺 На карті",
        "btn_note":    "📝 Нотатка",
        "btn_similar": "🔍 Схожі",
        "no_apts":     "😔 Квартир за вашими фільтрами не знайдено.\n\nЗміни фільтри: /filter",
        "no_apts_yet": "😔 Квартир поки немає. Парсер працює кожні 10 хвилин.",
        "wrap_around": "🔄 Показую спочатку — нових квартир поки немає.",
        "limit_reached": (
            "⛔ <b>Безкоштовний ліміт {limit} квартир вичерпано.</b>\n\n"
            "💎 <b>VIP — 19 zł/міс:</b>\n"
            "✅ Безліміт перегляду\n"
            "✅ Розумні алерти\n"
            "✅ Сповіщення про зниження ціни"
        ),
        "vip_badge":  "💎 VIP до {until}",
        "free_badge": "🆓 {bar} {used}/{total}",
        "early_adopter": "\n\n🎁 <b>Ти серед перших 50!</b> VIP на 7 днів безкоштовно!",
        "ref_bonus":     "🎁 Реферальний бонус! Той хто запросив отримав 7 днів VIP.",
        "vip_fav10":     "\n\n🎁 <b>+3 дні VIP</b> за 10 збережених квартир!",
        "vip_loyal":     "\n\n🎁 <b>+2 дні VIP</b> за активність!",
        "remaining":     "\n\n📦 Ще {n} квартир за фільтрами",
        "warn_check":    "Завжди перевіряй квартиру особисто перед оплатою.",
        "lang_set_ru": "🇷🇺 Мова: Російська",
        "lang_set_uk": "🇺🇦 Мова: Українська",
        "lang_set_pl": "🇵🇱 Мова: Польська",
        "daily_text": (
            "🏖 <b>Оренда подобово у Варшаві</b>\n\n"
            "Обери кількість днів — я відкрию найкращі пропозиції:\n\n"
            "🏨 Booking.com — готелі та апартаменти\n"
            "🏠 Airbnb — квартири від господарів\n"
            "🛏 Nocowanie.pl — польська платформа\n\n"
            "Або натисни кнопку вище щоб переглянути оголошення з нашої бази."
        ),
        "btn_1day":   "1 день",
        "btn_3days":  "3 дні",
        "btn_7days":  "7 днів",
        "btn_14days": "14 днів",
        "btn_30days": "30 днів",
        "daily_links": (
            "🔗 <b>Оренда на {days} дн. у Варшаві:</b>\n\n"
            "🏨 <a href=\"{booking}\">Booking.com</a> — готелі та апартаменти\n"
            "🏠 <a href=\"{airbnb}\">Airbnb</a> — квартири від господарів\n"
            "🛏 <a href=\"{nocowanie}\">Nocowanie.pl</a> — польська платформа\n\n"
            "💡 Порівняй ціни на всіх платформах перед бронюванням."
        ),
    },

    "pl": {
        "welcome_new": (
            "🏙 <b>DDFlatsBot</b> — wszystkie mieszkania Warszawy w jednym miejscu.\n\n"
            "✅ OLX · Otodom · Gratka · Morizon · Lento i inne\n"
            "✅ Aktualizacja co 10 minut\n"
            "✅ Filtry: cena, dzielnica, liczba pokoi\n"
            "✅ Natychmiastowe powiadomienia o nowych mieszkaniach\n"
            "✅ Wynajem krótkoterminowy przez Booking i Airbnb\n\n"
            "👇 Wybierz język:"
        ),
        "choose_lang": "🌍 Wybierz język:",
        "disclaimer": (
            "📋 <b>Warunki użytkowania DDFlatsBot</b>\n\n"
            "Bot agreguje ogłoszenia z OLX, Otodom, Gratka, Morizon i innych serwisów.\n\n"
            "<b>⚠️ NIE ponosimy odpowiedzialności za:</b>\n"
            "• Wiarygodność i aktualność ogłoszeń\n"
            "• Działania wynajmujących\n"
            "• Oszukańcze ogłoszenia\n\n"
            "<b>🔐 Zasady bezpieczeństwa:</b>\n"
            "🔍 Zawsze sprawdzaj mieszkanie osobiście przed płatnością\n"
            "💳 Nigdy nie przelewaj pieniędzy bez oglądania\n"
            "📋 Wymagaj podpisanej umowy najmu\n"
            "🚫 W przypadku podejrzenia oszustwa — zgłoś nam\n\n"
            "Klikając przycisk poniżej, potwierdzasz że przeczytałeś i zgadzasz się z warunkami."
        ),
        "btn_accept": "✅ Akceptuję warunki",
        "btn_decline": "❌ Rezygnuję",
        "start_greeting": (
            "👋 Cześć, <b>{name}</b>!\n"
            "{badge}\n\n"
            "🏙 <b>DDFlatsBot</b> — mieszkania Warszawy w jednym miejscu.\n"
            "Aktualizuję co 10 minut: OLX · Otodom · Gratka · Morizon.\n\n"
            "⚠️ <i>Zawsze sprawdzaj mieszkanie osobiście przed płatnością.</i>"
        ),
        "btn_find":      "🏠 Znajdź mieszkanie",
        "btn_filter":    "🔍 Filtry",
        "btn_favorites": "❤️ Ulubione",
        "btn_alerts":    "🔔 Alerty",
        "btn_vip":       "⭐ VIP",
        "btn_ref":       "👥 Zaproś znajomego",
        "btn_cheap":     "💚 Najtańsze",
        "btn_hot":       "🔥 Gorące",
        "btn_drops":     "📉 Obniżki cen",
        "btn_daily":     "🏖 Na doby",
        "btn_mystats":   "📊 Statystyki",
        "btn_next":    "➡️ Następne",
        "btn_fav_add": "❤️ Zapisz",
        "btn_on_map":  "🗺 Na mapie",
        "btn_note":    "📝 Notatka",
        "btn_similar": "🔍 Podobne",
        "no_apts":     "😔 Nie znaleziono mieszkań wg Twoich filtrów.\n\nZmień filtry: /filter",
        "no_apts_yet": "😔 Brak mieszkań. Parser działa co 10 minut.",
        "wrap_around": "🔄 Pokazuję od początku — brak nowych mieszkań.",
        "limit_reached": (
            "⛔ <b>Darmowy limit {limit} mieszkań wyczerpany.</b>\n\n"
            "💎 <b>VIP — 19 zł/mies:</b>\n"
            "✅ Bez limitu przeglądania\n"
            "✅ Inteligentne alerty\n"
            "✅ Powiadomienia o obniżkach cen"
        ),
        "vip_badge":  "💎 VIP do {until}",
        "free_badge": "🆓 {bar} {used}/{total}",
        "early_adopter": "\n\n🎁 <b>Jesteś w pierwszych 50!</b> VIP na 7 dni za darmo!",
        "ref_bonus":     "🎁 Bonus referencyjny! Zapraszający otrzymał 7 dni VIP.",
        "vip_fav10":     "\n\n🎁 <b>+3 dni VIP</b> za 10 zapisanych mieszkań!",
        "vip_loyal":     "\n\n🎁 <b>+2 dni VIP</b> za aktywność!",
        "remaining":     "\n\n📦 Jeszcze {n} mieszkań wg filtrów",
        "warn_check":    "Zawsze sprawdzaj mieszkanie osobiście przed płatnością.",
        "lang_set_ru": "🇷🇺 Język: Rosyjski",
        "lang_set_uk": "🇺🇦 Język: Ukraiński",
        "lang_set_pl": "🇵🇱 Język: Polski",
        "daily_text": (
            "🏖 <b>Wynajem krótkoterminowy w Warszawie</b>\n\n"
            "Wybierz liczbę dni — otworzę najlepsze oferty:\n\n"
            "🏨 Booking.com — hotele i apartamenty\n"
            "🏠 Airbnb — mieszkania od właścicieli\n"
            "🛏 Nocowanie.pl — polska platforma\n\n"
            "Lub naciśnij przycisk powyżej aby zobaczyć ogłoszenia z naszej bazy."
        ),
        "btn_1day":   "1 dzień",
        "btn_3days":  "3 dni",
        "btn_7days":  "7 dni",
        "btn_14days": "14 dni",
        "btn_30days": "30 dni",
        "daily_links": (
            "🔗 <b>Wynajem na {days} dni w Warszawie:</b>\n\n"
            "🏨 <a href=\"{booking}\">Booking.com</a> — hotele i apartamenty\n"
            "🏠 <a href=\"{airbnb}\">Airbnb</a> — mieszkania od właścicieli\n"
            "🛏 <a href=\"{nocowanie}\">Nocowanie.pl</a> — polska platforma\n\n"
            "💡 Porównaj ceny na wszystkich platformach przed rezerwacją."
        ),
    },
}

DEFAULT_LANG = "ru"


def t(lang: str, key: str, **kwargs) -> str:
    lang = lang if lang in TEXTS else DEFAULT_LANG
    text = TEXTS[lang].get(key, TEXTS[DEFAULT_LANG].get(key, key))
    try:
        return text.format(**kwargs) if kwargs else text
    except (KeyError, IndexError):
        return text
