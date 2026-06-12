# i18n — Russian, Ukrainian, Polish, English

TEXTS = {
    "ru": {
        # ── Onboarding ──────────────────────────────────────────
        "welcome_new": (
            "🏙 <b>DDFlatsBot</b> — квартиры <b>10 городов Польши</b>.\n\n"
            "🆓 Бесплатно · безлимит просмотров\n"
            "📍 Поиск в радиусе 100 км от города\n"
            "🏖 Посуточно: OLX, Otodom, Booking, Airbnb\n"
            "✅ OLX · Otodom · Gratka · Morizon · обновление каждые 10 мин\n\n"
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
            "🏙 <b>{city}</b> + соседние города (до 100 км)\n"
            "📊 В базе: <b>{count}</b> объявлений\n"
            "🏖 Посуточная аренда — кнопка в меню\n\n"
            "⚠️ <i>Всегда проверяй квартиру лично перед оплатой.</i>"
        ),
        "city_changed": "📍 Город: <b>{city}</b>\n🏠 Доступно: <b>{count}</b> квартир\nФильтры сброшены.",
        "menu_style_capital": "🏛 Столичный режим",
        "menu_style_coastal": "🌊 Прибрежный режим",
        "menu_style_industrial": "🏭 Промышленный режим",
        "menu_style_culture": "🎭 Культурный режим",
        "menu_style_business": "💼 Деловой режим",
        "menu_style_quiet": "🌿 Спокойный режим",
        "btn_settings": "⚙️ Настройки",
        "btn_notes": "📝 Заметки",
        "btn_digest": "📰 Дайджест",
        "btn_advanced": "🔬 Расширенный поиск",
        "btn_change_city": "🏙 Сменить город",
        "btn_hide": "🚫 Скрыть",
        "btn_seen": "👁 Уже смотрел",
        "daily_step1": "🏖 <b>Посуточная аренда</b>\n\n📍 <b>Шаг 1/5: Город</b>\nТекущий: <b>{city}</b>",
        "daily_step2": "📅 <b>Шаг 2/5: Дата заезда</b>",
        "daily_step3": "📅 <b>Шаг 3/5: Дата выезда</b>\nЗаезд: <b>{checkin}</b>",
        "daily_step4": "👥 <b>Шаг 4/5: Гости</b>",
        "daily_step5": "🏠 <b>Шаг 5/5: Тип жилья</b>",
        "daily_searching": "🔍 Ищу посуточно в <b>{city}</b>…\n📅 {checkin} → {checkout}",
        "daily_found": "🏠 <b>{n}</b> вариантов в {city}:",
        "daily_none": "😔 В {city} мало объявлений посуточно.\nСмотри агрегаторы ниже:",
        "today": "Сегодня",
        "tomorrow": "Завтра",
        "daily_card": "🏠 <b>{title}</b>\n💰 <b>{price}</b> zł/{night_label} · {total} zł за {nights} {nights_label}\n📍 {district}{rating}\n🔗 <a href=\"{link}\">{open_label}</a>",
        "daily_night": "ночь",
        "daily_nights": "ноч.",
        "daily_open": "Открыть на {source}",
        "daily_btn_open": "🔗 Открыть",
        "daily_summary": (
            "🏖 <b>Посуточная аренда</b>\n\n"
            "📍 {city}\n"
            "📅 {checkin} → {checkout} ({nights} {nights_label})\n"
            "👥 {guests} {guests_label} · {type}\n\n"
            "🔗 <b>{best_links}</b>\n\n"
            "🏨 <a href=\"{booking}\">Booking.com</a>\n"
            "🏠 <a href=\"{airbnb}\">Airbnb</a>\n"
            "🛏 <a href=\"{nocowanie}\">Nocowanie.pl</a>\n"
            "🏢 <a href=\"{flatio}\">Flatio</a> — меблированные{tips}"
        ),
        "daily_tips": (
            "\n\n💡 <b>Советы:</b>\n"
            "• Выше — готовые квартиры OLX/Otodom/Flatio\n"
            "• Flatio — меблированные, от 14 дней\n"
            "• Booking — значок «Гениальная цена»\n"
            "• Airbnb — от 7 ночей дешевле"
        ),
        "daily_best_links": "Агрегаторы (если мало объявлений):",
        "daily_guests_label": "гост.",
        "daily_type_apartment": "🏠 Квартира",
        "daily_type_house": "🏡 Дом/Вилла",
        "daily_type_room": "🛏 Комната",
        "daily_type_hotel": "🏨 Отель",
        "daily_type_any": "🏕 Любой тип",
        "daily_btn_change": "🔄 Изменить",
        "daily_btn_menu": "📋 Меню",
        "daily_custom_city": "✏️ Другой город",
        "daily_custom_prompt": "✏️ Напиши город или район:",
        "daily_nights_btn": "{n} н.",
        "daily_nights_btn_long": "{n} дн.",
        "daily_checkin_label": "Заезд: {date}",
        "daily_or_date": "📅 Или выбери дату выезда:",
        "city_onboard": "✅ Город: <b>{city}</b>\n\n",
        "city_alert": "✅ {city}",
        "btn_find":      "🏠 Найти квартиру",
        "btn_filter":    "🔍 Фильтры",
        "btn_favorites": "❤️ Избранное",
        "btn_alerts":    "🔔 Алерты",
        "btn_subscribe": "🔔 Районы",
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
            "⛔ <b>Лимит {limit} просмотров исчерпан.</b>\n\n"
            "Пригласи друзей: /ref"
        ),
        "vip_badge":  "💎 <b>VIP</b> до {until}",
        "free_badge": "🆓 {bar} {used}/{total} просмотров",

        # ── Bonuses ─────────────────────────────────────────────
        "ref_bonus":  "🎁 Спасибо за приглашение друга!",
        "vip_fav10":  "\n\n🎁 <b>+3 дня VIP</b> за 10 сохранённых квартир!",
        "vip_loyal":  "\n\n🎁 <b>+2 дня VIP</b> за активность!",
        "remaining":  "\n\n📦 Ещё <b>{n}</b> квартир по фильтрам",
        "warn_check": "Всегда проверяй квартиру лично перед оплатой.",

        # ── Language ────────────────────────────────────────────
        "lang_changed": "🇷🇺 Язык изменён на Русский",

        # ── Daily rental ────────────────────────────────────────
        "daily_text": (
            "🏖 <b>Посуточная аренда</b>\n\n"
            "Выбери город и даты — найду предложения на OLX, Otodom, Flatio, Nocowanie:\n\n"
            "🏨 Booking.com · 🏠 Airbnb · 🛏 Nocowanie.pl"
        ),
        "daily_links": (
            "🔗 <b>Аренда на {days} дн.:</b>\n\n"
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
            "/alert — умные алерты (до 5)\n"
            "/subscribe — подписка на район\n\n"
            "👤 <b>Профиль</b>\n"
            "/mystats — моя статистика\n"
            "/notes — мои заметки\n"
            "/digest — дайджест за сегодня\n"
            "/ref — пригласить друга\n"
            "/lang — сменить язык\n"
            "/settings — настройки поиска\n\n"
            "🏖 <b>Посуточно</b>\n"
            "/daily — аренда посуточно\n\n"
            "📋 /menu — быстрое меню"
        ),
    },

    "uk": {
        "welcome_new": (
            "🏙 <b>DDFlatsBot</b> — квартири <b>10 міст Польщі</b>.\n\n"
            "🆓 Безкоштовно · безліміт переглядів\n"
            "📍 Пошук у радіусі 100 км від міста\n"
            "🏖 Подобово: OLX, Otodom, Booking, Airbnb\n"
            "✅ OLX · Otodom · Gratka · Morizon · оновлення кожні 10 хв\n\n"
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
            "🏙 <b>{city}</b> + сусідні міста (до 100 км)\n"
            "📊 В базі: <b>{count}</b> оголошень\n"
            "🏖 Подобова оренда — кнопка в меню\n\n"
            "⚠️ <i>Завжди перевіряй квартиру особисто перед оплатою.</i>"
        ),
        "city_changed": "📍 Місто: <b>{city}</b>\n🏠 Доступно: <b>{count}</b>\nФільтри скинуто.",
        "btn_find":      "🏠 Знайти квартиру",
        "btn_filter":    "🔍 Фільтри",
        "btn_favorites": "❤️ Обране",
        "btn_alerts":    "🔔 Алерти",
        "btn_subscribe": "🔔 Райони",
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
            "⛔ <b>Ліміт {limit} переглядів вичерпано.</b>\n\n"
            "Запроси друзів: /ref"
        ),
        "vip_badge":  "💎 <b>VIP</b> до {until}",
        "free_badge": "🆓 {bar} {used}/{total} переглядів",
        "ref_bonus":  "🎁 Дякуємо за запрошення друга!",
        "vip_fav10":  "\n\n🎁 <b>+3 дні VIP</b> за 10 збережених квартир!",
        "vip_loyal":  "\n\n🎁 <b>+2 дні VIP</b> за активність!",
        "remaining":  "\n\n📦 Ще <b>{n}</b> квартир за фільтрами",
        "warn_check": "Завжди перевіряй квартиру особисто перед оплатою.",
        "lang_changed": "🇺🇦 Мову змінено на Українську",
        "daily_text": (
            "🏖 <b>Оренда подобово</b>\n\n"
            "Обери місто та дати — знайду на OLX, Otodom, Flatio, Nocowanie:\n\n"
            "🏨 Booking.com · 🏠 Airbnb · 🛏 Nocowanie.pl"
        ),
        "daily_links": (
            "🔗 <b>Оренда на {days} дн.:</b>\n\n"
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
            "/alert — розумні алерти (до 5)\n"
            "/subscribe — підписка на район\n\n"
            "👤 <b>Профіль</b>\n"
            "/mystats — моя статистика\n"
            "/notes — мої нотатки\n"
            "/digest — дайджест за сьогодні\n"
            "/ref — запросити друга\n"
            "/lang — змінити мову\n"
            "/settings — налаштування пошуку\n\n"
            "🏖 <b>Подобово</b>\n"
            "/daily — оренда подобово\n\n"
            "📋 /menu — швидке меню"
        ),
    },

    "pl": {
        "welcome_new": (
            "🏙 <b>DDFlatsBot</b> — mieszkania w <b>10 miastach Polski</b>.\n\n"
            "🆓 Za darmo · bez limitu przeglądania\n"
            "📍 Szukaj w promieniu 100 km od miasta\n"
            "🏖 Na doby: OLX, Otodom, Booking, Airbnb\n"
            "✅ OLX · Otodom · Gratka · Morizon · aktualizacja co 10 min\n\n"
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
            "🏙 <b>{city}</b> + okoliczne miasta (do 100 km)\n"
            "📊 W bazie: <b>{count}</b> ogłoszeń\n"
            "🏖 Wynajem krótkoterminowy — przycisk w menu\n\n"
            "⚠️ <i>Zawsze sprawdzaj mieszkanie osobiście przed płatnością.</i>"
        ),
        "city_changed": "📍 Miasto: <b>{city}</b>\n🏠 Dostępne: <b>{count}</b> ogłoszeń\nFiltry zresetowane.",
        "btn_find":      "🏠 Znajdź mieszkanie",
        "btn_filter":    "🔍 Filtry",
        "btn_favorites": "❤️ Ulubione",
        "btn_alerts":    "🔔 Alerty",
        "btn_subscribe": "🔔 Dzielnice",
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
            "⛔ <b>Limit {limit} przeglądów wyczerpany.</b>\n\n"
            "Zaproś znajomych: /ref"
        ),
        "vip_badge":  "💎 <b>VIP</b> do {until}",
        "free_badge": "🆓 {bar} {used}/{total} przeglądań",
        "ref_bonus":  "🎁 Dzięki za zaproszenie znajomego!",
        "vip_fav10":  "\n\n🎁 <b>+3 dni VIP</b> za 10 zapisanych mieszkań!",
        "vip_loyal":  "\n\n🎁 <b>+2 dni VIP</b> za aktywność!",
        "remaining":  "\n\n📦 Jeszcze <b>{n}</b> mieszkań wg filtrów",
        "warn_check": "Zawsze sprawdzaj mieszkanie osobiście przed płatnością.",
        "lang_changed": "🇵🇱 Język zmieniony na Polski",
        "daily_text": (
            "🏖 <b>Wynajem krótkoterminowy</b>\n\n"
            "Wybierz miasto i daty — szukam na OLX, Otodom, Flatio, Nocowanie:\n\n"
            "🏨 Booking.com · 🏠 Airbnb · 🛏 Nocowanie.pl"
        ),
        "daily_links": (
            "🔗 <b>Wynajem na {days} dni:</b>\n\n"
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
            "/alert — inteligentne alerty (do 5)\n"
            "/subscribe — subskrypcja dzielnicy\n\n"
            "👤 <b>Profil</b>\n"
            "/mystats — moje statystyki\n"
            "/notes — moje notatki\n"
            "/digest — digest na dziś\n"
            "/ref — zaproś znajomego\n"
            "/lang — zmień język\n"
            "/settings — ustawienia wyszukiwania\n\n"
            "🏖 <b>Na doby</b>\n"
            "/daily — wynajem krótkoterminowy\n\n"
            "📋 /menu — szybkie menu"
        ),
    },

    "en": {
        "welcome_new": (
            "🏙 <b>DDFlatsBot</b> — apartments in <b>10 Polish cities</b>.\n\n"
            "🆓 Free · unlimited browsing\n"
            "📍 Search within 100 km of your city\n"
            "🏖 Short-term: OLX, Otodom, Booking, Airbnb\n"
            "✅ OLX · Otodom · Gratka · Morizon · updates every 10 min\n\n"
            "👇 Choose your language:"
        ),
        "disclaimer": (
            "📋 <b>DDFlatsBot Terms of Use</b>\n\n"
            "The bot aggregates listings from OLX, Otodom, Gratka, Morizon and other sites.\n\n"
            "<b>⚠️ We are NOT responsible for:</b>\n"
            "• Accuracy and freshness of listings\n"
            "• Landlord actions\n"
            "• Fraudulent ads\n\n"
            "<b>🔐 Safety rules:</b>\n"
            "🔍 Always view the apartment in person before paying\n"
            "💳 Never transfer money without viewing\n"
            "📋 Require a signed lease agreement\n\n"
            "By tapping Accept you agree to these terms."
        ),
        "btn_accept": "✅ I accept",
        "btn_decline": "❌ Decline",
        "start_greeting": (
            "👋 Hi, <b>{name}</b>!\n"
            "{badge}\n\n"
            "🏙 <b>{city}</b> + nearby cities (up to 100 km)\n"
            "📊 Active listings: <b>{count}</b>\n"
            "🏖 Short-term rentals — button in menu\n\n"
            "⚠️ <i>Always verify the apartment in person before payment.</i>"
        ),
        "city_changed": "📍 City: <b>{city}</b>\n🏠 Available: <b>{count}</b> listings\nFilters reset.",
        "menu_style_capital": "🏛 Capital mode",
        "menu_style_coastal": "🌊 Coastal mode",
        "menu_style_industrial": "🏭 Industrial mode",
        "menu_style_culture": "🎭 Culture mode",
        "menu_style_business": "💼 Business mode",
        "menu_style_quiet": "🌿 Quiet mode",
        "btn_find": "🏠 Find apartment",
        "btn_filter": "🔍 Filters",
        "btn_favorites": "❤️ Favorites",
        "btn_alerts": "🔔 Alerts",
        "btn_subscribe": "🔔 Districts",
        "btn_ref": "👥 Invite friend",
        "btn_cheap": "💚 Cheapest",
        "btn_hot": "🔥 Hot deals",
        "btn_drops": "📉 Price drops",
        "btn_daily": "🏖 Short-term",
        "btn_mystats": "📊 Stats",
        "btn_map": "🗺 Price map",
        "btn_menu": "📋 Menu",
        "btn_settings": "⚙️ Settings",
        "btn_notes": "📝 Notes",
        "btn_digest": "📰 Digest",
        "btn_advanced": "🔬 Advanced search",
        "btn_change_city": "🏙 Change city",
        "btn_hide": "🚫 Hide",
        "btn_seen": "👁 Already seen",
        "btn_next": "➡️ Next",
        "btn_fav_add": "❤️ Save",
        "btn_on_map": "🗺 On map",
        "btn_note": "📝 Note",
        "btn_similar": "🔍 Similar",
        "btn_report": "🚨 Report",
        "btn_share": "📤 Share",
        "btn_found": "✅ Found one!",
        "no_apts": "😔 No apartments match your filters.\n\nTry /filter",
        "no_apts_yet": "😔 No listings yet. Parser runs every 10 minutes.\n\nTry later: /next",
        "wrap_around": "🔄 Back to start — no new listings yet.",
        "limit_reached": (
            "⛔ <b>Limit of {limit} views reached.</b>\n\n"
            "Invite friends: /ref"
        ),
        "vip_badge": "💎 <b>VIP</b> until {until}",
        "free_badge": "🆓 {bar} {used}/{total} views",
        "ref_bonus": "🎁 Thanks for inviting a friend!",
        "vip_fav10": "\n\n🎁 <b>+3 days VIP</b> for 10 saved apartments!",
        "vip_loyal": "\n\n🎁 <b>+2 days VIP</b> for activity!",
        "remaining": "\n\n📦 <b>{n}</b> more listings match your filters",
        "warn_check": "Always verify the apartment in person before payment.",
        "lang_changed": "🇬🇧 Language set to English",
        "daily_text": (
            "🏖 <b>Short-term rental</b>\n\n"
            "Pick dates — best offers from OLX & Nocowanie.pl:\n\n"
            "🏨 Booking.com\n"
            "🏠 Airbnb\n"
            "🛏 Nocowanie.pl"
        ),
        "daily_links": (
            "🔗 <b>Rent for {days} days:</b>\n\n"
            "🏨 <a href=\"{booking}\">Booking.com</a>\n"
            "🏠 <a href=\"{airbnb}\">Airbnb</a>\n"
            "🛏 <a href=\"{nocowanie}\">Nocowanie.pl</a>"
        ),
        "daily_step1": "🏖 <b>Short-term rental</b>\n\n📍 <b>Step 1/5: City</b>\nCurrent: <b>{city}</b>",
        "daily_step2": "📅 <b>Step 2/5: Check-in</b>",
        "daily_step3": "📅 <b>Step 3/5: Check-out</b>\nCheck-in: <b>{checkin}</b>",
        "daily_step4": "👥 <b>Step 4/5: Guests</b>",
        "daily_step5": "🏠 <b>Step 5/5: Property type</b>",
        "daily_searching": "🔍 Searching short-term in <b>{city}</b>…\n📅 {checkin} → {checkout}",
        "daily_found": "🏠 <b>{n}</b> options in {city}:",
        "daily_none": "😔 Few short-term listings in {city}.\nTry platforms below:",
        "today": "Today",
        "tomorrow": "Tomorrow",
        "daily_card": "🏠 <b>{title}</b>\n💰 <b>{price}</b> zł/{night_label} · {total} zł for {nights} {nights_label}\n📍 {district}{rating}\n🔗 <a href=\"{link}\">{open_label}</a>",
        "daily_night": "night",
        "daily_nights": "nights",
        "daily_open": "Open on {source}",
        "daily_btn_open": "🔗 Open",
        "daily_summary": (
            "🏖 <b>Short-term rental</b>\n\n"
            "📍 {city}\n"
            "📅 {checkin} → {checkout} ({nights} {nights_label})\n"
            "👥 {guests} {guests_label} · {type}\n\n"
            "🔗 <b>{best_links}</b>\n\n"
            "🏨 <a href=\"{booking}\">Booking.com</a>\n"
            "🏠 <a href=\"{airbnb}\">Airbnb</a>\n"
            "🛏 <a href=\"{nocowanie}\">Nocowanie.pl</a>\n"
            "🏢 <a href=\"{flatio}\">Flatio</a> — furnished{tips}"
        ),
        "daily_tips": (
            "\n\n💡 <b>Tips:</b>\n"
            "• Above — ready listings OLX/Otodom/Flatio\n"
            "• Flatio — furnished, from 14 days\n"
            "• Booking — «Genius» deals\n"
            "• Airbnb — 7+ nights often cheaper"
        ),
        "daily_best_links": "Platforms (if few listings):",
        "daily_guests_label": "guests",
        "daily_type_apartment": "🏠 Apartment",
        "daily_type_house": "🏡 House/Villa",
        "daily_type_room": "🛏 Room",
        "daily_type_hotel": "🏨 Hotel",
        "daily_type_any": "🏕 Any type",
        "daily_btn_change": "🔄 Change",
        "daily_btn_menu": "📋 Menu",
        "daily_custom_city": "✏️ Other city",
        "daily_custom_prompt": "✏️ Type city or district:",
        "daily_nights_btn": "{n} n.",
        "daily_nights_btn_long": "{n} d.",
        "daily_checkin_label": "Check-in: {date}",
        "daily_or_date": "📅 Or pick check-out date:",
        "city_onboard": "✅ City: <b>{city}</b>\n\n",
        "city_alert": "✅ {city}",
        "help_text": (
            "📖 <b>DDFlatsBot commands</b>\n\n"
            "🏠 <b>Apartments</b>\n"
            "/next — next listing\n"
            "/filter — filters (district, price, rooms)\n"
            "/ask — smart search: <code>/ask 2 rooms Mokotow under 3000</code>\n"
            "/hot — hot listings\n"
            "/cheap — cheapest\n"
            "/drops — price drops\n"
            "/map — price map by district\n\n"
            "❤️ <b>Favorites & alerts</b>\n"
            "/favorites — saved listings\n"
            "/alert — smart alerts (up to 5)\n"
            "/subscribe — district subscription\n\n"
            "👤 <b>Profile</b>\n"
            "/mystats — my stats\n"
            "/notes — my notes\n"
            "/digest — today's digest\n"
            "/ref — invite a friend\n"
            "/lang — change language\n"
            "/settings — search settings\n\n"
            "🏖 <b>Short-term</b>\n"
            "/daily — short-term rental\n\n"
            "📋 /menu — quick menu"
        ),
    },
}

from bot.i18n_extra import LANG_EXTRA

for _lang, _extra in LANG_EXTRA.items():
    if _lang in TEXTS:
        TEXTS[_lang].update(_extra)

SUPPORTED_LANGS = ("ru", "uk", "pl", "en")
DEFAULT_LANG = "ru"


def t(lang: str, key: str, **kwargs) -> str:
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    text = TEXTS[lang].get(key, TEXTS[DEFAULT_LANG].get(key, key))
    try:
        return text.format(**kwargs) if kwargs else text
    except (KeyError, IndexError):
        return text
