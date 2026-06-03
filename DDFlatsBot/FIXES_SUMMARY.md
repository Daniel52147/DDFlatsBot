# Исправления DDFlatsBot

## ✅ Исправленные проблемы:

### 1. Кнопка "Открыть" теперь работает
- **Было**: Кнопка показывалась как текст `🔗 Открыть`
- **Стало**: Кнопка работает как InlineKeyboardButton с URL
- **Файлы**: `DDFlatsBot/parser/scheduler.py`

### 2. Улучшена дедупликация
- **Было**: Дубликаты с разных сайтов попадали в базу
- **Стало**: Более агрессивная нормализация названий, убирает спецсимволы
- **Файлы**: `DDFlatsBot/database/db.py` (функция `find_duplicate`)

### 3. Улучшен календарь для посуточной аренды
- **Было**: 60 кнопок подряд, неудобно выбирать
- **Стало**: 
  - Быстрый выбор (Сегодня, Завтра, +7 дней)
  - Календарная сетка по месяцам
  - Для выезда: выбор по количеству ночей ИЛИ конкретная дата
- **Файлы**: `DDFlatsBot/bot/handlers.py` (функции `_daily_step_checkin`, `_daily_step_checkout`)

### 4. Добавлена поддержка парсинга других городов
- **Обновлены парсеры**:
  - `parser_olx.py` - поддерживает все 5 городов
  - `parser_otodom.py` - поддерживает все 5 городов
  - `parser_gratka.py`, `parser_morizon.py`, `parser_adresowo.py` - готовы к расширению
- **Scheduler** теперь парсит все города из `CITIES`
- **Файлы**: `DDFlatsBot/parser/scheduler.py`, все парсеры

### 5. Посуточная аренда показывает реальные объявления
- **Интегрирован** `parser_daily.py` в handlers
- Показывает реальные предложения с OLX и Nocowanie.pl
- После реальных предложений - ссылки на Booking/Airbnb
- **Файлы**: `DDFlatsBot/bot/handlers.py` (функция `_daily_show_results`)

## 🔧 Как запустить:

### 1. Применить миграции базы данных:
```bash
cd DDFlatsBot
python -c "from database.db import init_db; init_db()"
```

### 2. Протестировать парсеры:
```bash
cd DDFlatsBot
python test_parsers.py
```

### 3. Запустить бота:
```bash
cd DDFlatsBot
python main.py
```

## 📊 Проверка базы данных:

```python
import sqlite3
conn = sqlite3.connect('DDFlatsBot/Flats.db')

# Проверить города
print("Города:", [r[0] for r in conn.execute('SELECT DISTINCT city FROM apartments WHERE city IS NOT NULL').fetchall()])

# Количество квартир по городам
for row in conn.execute('SELECT city, COUNT(*) FROM apartments GROUP BY city'):
    print(f"{row[0]}: {row[1]} квартир")
```

## ⚠️ Важно:

1. **Миграция базы данных** выполняется автоматически при запуске `init_db()`
2. **Парсеры** запускаются каждые 10 минут через scheduler
3. **Первый запуск** может занять 5-10 минут для парсинга всех городов
4. **Дубликаты** будут автоматически отфильтрованы при сохранении

## 🐛 Если что-то не работает:

1. Проверьте логи: `python main.py` покажет все ошибки
2. Проверьте базу данных: есть ли колонка `city` в таблице `apartments`
3. Запустите тест парсеров: `python test_parsers.py`
4. Проверьте что все зависимости установлены: `pip install -r requirements.txt`
