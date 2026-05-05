# i18n — Russian, Ukrainian, Polish

TEXTS = {
    "ru": {
        # ── Onboarding ──────────────────────────────────────────
        "welcome_new": (
            "🏙 <b>DDFlatsBot</b> — все квартиры Варшавы в одном месте.\n\n"
            "✅ OLX · Otodom · Gratka · Morizon · Lento и другие\n"
            "✅ Обновление каждые 10 минут\n"
            "✅ Фильтры по цене, району, комнатам\n"
            "✅ Мгновенные уведомления о новых квартирах\n\n"
            "👇 Выбери язык:"
        ),
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
            "📋 Требуй подписанный договор аренды\n\n"
            "Нажимая кнопку ниже, ты подтверждаешь согласие с условиями."
        ),
        "btn_accept":  "✅ Принимаю условия",
        "btn_decline": "❌ Отказаться",

        # ── Main menu ───────────────────────────────────────────
        "start_greeting": (
            "👋 Привет, <b>{name}</b>!\n"
            "{badge}\n\n"
            "🏙 <b>DDFlatsBot</b> — квартиры Варшавы в реальном времени.\n"
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
        "btn_map":       "🗺 Карта цен",
        "btn_menu":      "📋 Меню",

        # ── Apartment card ──────────────────────────────────────
        "btn_next":    "➡️ Следующая",
        "btn_fav_add": "❤️ Сохранить",
        "btn_on_map":  "🗺 На карте",
        "btn_note":    "📝 Заметка",
        "btn_similar": "🔍 Похожие",
        "btn_report":  "🚨 Пожаловаться",
        "btn_share":   "📤 Поделиться",
        "btn_found":   "✅ Нашёл!",

        # ── Status ──────────────────────────────────────────────
        "no_apts":     "😔 Квартир по твоим фильтрам не найдено.\n\nИзмени фильтры: /filter",
        "no_apts_yet": "😔 Квартир пока нет. Парсер работает каждые 10 минут.\n\nПопробуй позже: /next",
        "wrap_around": "🔄 Показываю сначала — новых квартир пока нет.",
        "limit_reached": (
            "⛔ <b>Бесплатный лимит {limit} квартир исчерпан.</b>\n\n"
            "💎 <b>VIP — 19 zł/мес:</b>\n"
            "✅ Безлимитный просмотр\n"
            "✅ Умные алерты\n"
            "✅ Уведомления о снижении цены\n"
            "✅ Подписка на районы"
        ),
        "vip_badge":  "💎 <b>VIP</b> до {until}",
        "free_badge": "🆓 {bar} {used}/{total} просмотров",

        # ── Bonuses ─────────────────────────────────────────────
        "ref_bonus":  "🎁 Реферальный бонус! Пригласивший получил 7 дней VIP.",
        "vip_fav10":  "\n\n🎁 <b>+3 дня VIP</b> за 10 сохранённых квартир!",
        "vip_loyal":  "\n\n🎁 <b>+2 дня VIP</b> за активность!",
        "remaining":  "\n\n📦 Ещё <b>{n}</b> квартир по фильтрам",
        "warn_check": "Всегда проверяй квартиру лично перед оплатой.",

        # ── Language ────────────────────────────────────────────
        "lang_changed": "🇷🇺 Язык изменён на Русский",

        # ── Daily rental ────────────────────────────────────────
        "daily_text": (
            "🏖 <b>Аренда посуточно в Варшаве</b>\n\n"
            "Выбери количество дней — открою лучшие предложения:\n\n"
            "🏨 Booking.com — отели и апартаменты\n"
            "🏠 Airbnb — квартиры от хозяев\n"
            "🛏 Nocowanie.pl — польская платформа"
        ),
        "daily_links": (
            "🔗 <b>Аренда на {days} дн. в Варшаве:</b>\n\n"
            "🏨 <a href=\"{booking}\">Booking.com</a>\n"
            "🏠 <a href=\"{airbnb}\">Airbnb</a>\n"
            "🛏 <a href=\"{nocowanie}\">Nocowanie.pl</a>\n\n"
            "💡 Сравни цены перед бронированием."
        ),

        # ── Help ────────────────────────────────────────────────
        "help_text": (
            "📖 <b>Все команды DDFlatsBot</b>\n\n"
            "🏠 <b>Квартиры</b>\n"
            "/next — следующая квартира\n"
            "/filter — фильтры (район, цена, комнаты)\n"
            "/ask — умный поиск: <code>/ask 2 комнаты Мокотув до 3000</code>\n"
            "/hot — горячие квартиры (топ лайков)\n"
            "/cheap — самые дешёвые\n"
            "/drops — снижения цен\n"
            "/map — карта цен по районам\n\n"
            "❤️ <b>Избранное и алерты</b>\n"
            "/favorites — моё избранное\n"
            "/alert — умный алерт (VIP)\n"
            "/subscribe — подписка на район (VIP)\n\n"
            "👤 <b>Профиль</b>\n"
            "/mystats — моя статистика\n"
            "/vip — VIP подписка\n"
            "/ref — пригласить друга → VIP\n"
            "/lang — сменить язык\n\n"
            "🏖 <b>Посуточно</b>\n"
            "/daily — аренда посуточно\n\n"
            "📋 /menu — быстрое меню"
        ),
    },

    "uk": {
        "welcome_new": (
            "🏙 <b>DDFlatsBot</b> — всі квартири Варшави в одному місці.\n\n"
            "✅ OLX · Otodom · Gratka · Morizon · Lento та інші\n"
            "✅ Оновлення кожні 10 хвилин\n"
            "✅ Фільтри за ціною, районом, кімнатами\n"
            "✅ Миттєві сповіщення про нові квартири\n\n"
            "👇 Оберіть мову:"
        ),
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
            "📋 Вимагай підписаний договір оренди\n\n"
            "Натискаючи кнопку нижче, ти підтверджуєш згоду з умовами."
        ),
        "btn_accept":  "✅ Приймаю умови",
        "btn_decline": "❌ Відмовитись",
        "start_greeting": (
            "👋 Привіт, <b>{name}</b>!\n"
            "{badge}\n\n"
            "🏙 <b>DDFlatsBot</b> — квартири Варшави в реальному часі.\n"
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
        "btn_map":       "🗺 Карта цін",
        "btn_menu":      "📋 Меню",
        "btn_next":    "➡️ Наступна",
        "btn_fav_add": "❤️ Зберегти",
        "btn_on_map":  "🗺 На карті",
        "btn_note":    "📝 Нотатка",
        "btn_similar": "🔍 Схожі",
        "btn_report":  "🚨 Поскаржитись",
        "btn_share":   "📤 Поділитись",
        "btn_found":   "✅ Знайшов!",
        "no_apts":     "😔 Квартир за вашими фільтрами не знайдено.\n\nЗміни фільтри: /filter",
        "no_apts_yet": "😔 Квартир поки немає. Парсер працює кожні 10 хвилин.",
        "wrap_around": "🔄 Показую спочатку — нових квартир поки немає.",
        "limit_reached": (
            "⛔ <b>Безкоштовний ліміт {limit} квартир вичерпано.</b>\n\n"
            "💎 <b>VIP — 19 zł/міс:</b>\n"
            "✅ Безліміт перегляду\n"
            "✅ Розумні алерти\n"
            "✅ Сповіщення про зниження ціни\n"
            "✅ Підписка на райони"
        ),
        "vip_badge":  "💎 <b>VIP</b> до {until}",
        "free_badge": "🆓 {bar} {used}/{total} переглядів",
        "ref_bonus":  "🎁 Реферальний бонус! Той хто запросив отримав 7 днів VIP.",
        "vip_fav10":  "\n\n🎁 <b>+3 дні VIP</b> за 10 збережених квартир!",
        "vip_loyal":  "\n\n🎁 <b>+2 дні VIP</b> за активність!",
        "remaining":  "\n\n📦 Ще <b>{n}</b> квартир за фільтрами",
        "warn_check": "Завжди перевіряй квартиру особисто перед оплатою.",
        "lang_changed": "🇺🇦 Мову змінено на Українську",
        "daily_text": (
            "🏖 <b>Оренда подобово у Варшаві</b>\n\n"
            "Обери кількість днів — відкрию найкращі пропозиції:\n\n"
            "🏨 Booking.com — готелі та апартаменти\n"
            "🏠 Airbnb — квартири від господарів\n"
            "🛏 Nocowanie.pl — польська платформа"
        ),
        "daily_links": (
            "🔗 <b>Оренда на {days} дн. у Варшаві:</b>\n\n"
            "🏨 <a href=\"{booking}\">Booking.com</a>\n"
            "🏠 <a href=\"{airbnb}\">Airbnb</a>\n"
            "🛏 <a href=\"{nocowanie}\">Nocowanie.pl</a>\n\n"
            "💡 Порівняй ціни перед бронюванням."
        ),
        "help_text": (
            "📖 <b>Всі команди DDFlatsBot</b>\n\n"
            "🏠 <b>Квартири</b>\n"
            "/next — наступна квартира\n"
            "/filter — фільтри (район, ціна, кімнати)\n"
            "/ask — розумний пошук: <code>/ask 2 кімнати Мокотув до 3000</code>\n"
            "/hot — гарячі квартири\n"
            "/cheap — найдешевші\n"
            "/drops — зниження цін\n"
            "/map — карта цін по районах\n\n"
            "❤️ <b>Обране та алерти</b>\n"
            "/favorites — моє обране\n"
            "/alert — розумний алерт (VIP)\n"
            "/subscribe — підписка на район (VIP)\n\n"
            "👤 <b>Профіль</b>\n"
            "/mystats — моя статистика\n"
            "/vip — VIP підписка\n"
            "/ref — запросити друга → VIP\n"
            "/lang — змінити мову\n\n"
            "📋 /menu — швидке меню"
        ),
    },

    "pl": {
        "welcome_new": (
            "🏙 <b>DDFlatsBot</b> — wszystkie mieszkania Warszawy w jednym miejscu.\n\n"
            "✅ OLX · Otodom · Gratka · Morizon · Lento i inne\n"
            "✅ Aktualizacja co 10 minut\n"
            "✅ Filtry: cena, dzielnica, liczba pokoi\n"
            "✅ Natychmiastowe powiadomienia o nowych mieszkaniach\n\n"
            "👇 Wybierz język:"
        ),
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
            "📋 Wymagaj podpisanej umowy najmu\n\n"
            "Klikając przycisk poniżej, potwierdzasz zgodę z warunkami."
        ),
        "btn_accept":  "✅ Akceptuję warunki",
        "btn_decline": "❌ Rezygnuję",
        "start_greeting": (
            "👋 Cześć, <b>{name}</b>!\n"
            "{badge}\n\n"
            "🏙 <b>DDFlatsBot</b> — mieszkania Warszawy w czasie rzeczywistym.\n"
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
        "btn_map":       "🗺 Mapa cen",
        "btn_menu":      "📋 Menu",
        "btn_next":    "➡️ Następne",
        "btn_fav_add": "❤️ Zapisz",
        "btn_on_map":  "🗺 Na mapie",
        "btn_note":    "📝 Notatka",
        "btn_similar": "🔍 Podobne",
        "btn_report":  "🚨 Zgłoś",
        "btn_share":   "📤 Udostępnij",
        "btn_found":   "✅ Znalazłem!",
        "no_apts":     "😔 Nie znaleziono mieszkań wg Twoich filtrów.\n\nZmień filtry: /filter",
        "no_apts_yet": "😔 Brak mieszkań. Parser działa co 10 minut.",
        "wrap_around": "🔄 Pokazuję od początku — brak nowych mieszkań.",
        "limit_reached": (
            "⛔ <b>Darmowy limit {limit} mieszkań wyczerpany.</b>\n\n"
            "💎 <b>VIP — 19 zł/mies:</b>\n"
            "✅ Bez limitu przeglądania\n"
            "✅ Inteligentne alerty\n"
            "✅ Powiadomienia o obniżkach cen\n"
            "✅ Subskrypcja dzielnic"
        ),
        "vip_badge":  "💎 <b>VIP</b> do {until}",
        "free_badge": "🆓 {bar} {used}/{total} przeglądań",
        "ref_bonus":  "🎁 Bonus referencyjny! Zapraszający otrzymał 7 dni VIP.",
        "vip_fav10":  "\n\n🎁 <b>+3 dni VIP</b> za 10 zapisanych mieszkań!",
        "vip_loyal":  "\n\n🎁 <b>+2 dni VIP</b> za aktywność!",
        "remaining":  "\n\n📦 Jeszcze <b>{n}</b> mieszkań wg filtrów",
        "warn_check": "Zawsze sprawdzaj mieszkanie osobiście przed płatnością.",
        "lang_changed": "🇵🇱 Język zmieniony na Polski",
        "daily_text": (
            "🏖 <b>Wynajem krótkoterminowy w Warszawie</b>\n\n"
            "Wybierz liczbę dni — otworzę najlepsze oferty:\n\n"
            "🏨 Booking.com — hotele i apartamenty\n"
            "🏠 Airbnb — mieszkania od właścicieli\n"
            "🛏 Nocowanie.pl — polska platforma"
        ),
        "daily_links": (
            "🔗 <b>Wynajem na {days} dni w Warszawie:</b>\n\n"
            "🏨 <a href=\"{booking}\">Booking.com</a>\n"
            "🏠 <a href=\"{airbnb}\">Airbnb</a>\n"
            "🛏 <a href=\"{nocowanie}\">Nocowanie.pl</a>\n\n"
            "💡 Porównaj ceny przed rezerwacją."
        ),
        "help_text": (
            "📖 <b>Wszystkie komendy DDFlatsBot</b>\n\n"
            "🏠 <b>Mieszkania</b>\n"
            "/next — następne mieszkanie\n"
            "/filter — filtry (dzielnica, cena, pokoje)\n"
            "/ask — inteligentne wyszukiwanie: <code>/ask 2 pokoje Mokotów do 3000</code>\n"
            "/hot — gorące mieszkania\n"
            "/cheap — najtańsze\n"
            "/drops — obniżki cen\n"
            "/map — mapa cen wg dzielnic\n\n"
            "❤️ <b>Ulubione i alerty</b>\n"
            "/favorites — moje ulubione\n"
            "/alert — inteligentny alert (VIP)\n"
            "/subscribe — subskrypcja dzielnicy (VIP)\n\n"
            "👤 <b>Profil</b>\n"
            "/mystats — moje statystyki\n"
            "/vip — subskrypcja VIP\n"
            "/ref — zaproś znajomego → VIP\n"
            "/lang — zmień język\n\n"
            "📋 /menu — szybkie menu"
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
