# SkyCheap ✈️ — Telegram Flight Search Bot

Find cheap flights from Poland in seconds. Real prices, real links, instant alerts.

🤖 **Bot:** [@DDSkyCheapBot](https://t.me/DDSkyCheapBot)  
📢 **Channel:** [@DDfrets](https://t.me/DDfrets)

---

## Features

- 🔍 One-way and round-trip search from any Polish airport
- 🔥 Hot deals — cheapest flights updated every 2 hours
- 📅 Cheapest dates — find the best day to fly
- 📆 Week prices — price calendar for next 7 days
- 🔔 Price alerts — get notified when price drops
- ⭐ Favorites — save routes you fly often
- 👑 VIP mode — unlimited searches (19 zł/month or 50 ⭐ Stars)
- 🌍 80+ destinations worldwide

## Supported Routes

Flies from: Warsaw (WAW/WMI), Kraków (KRK), Wrocław (WRO), Gdańsk (GDN), Katowice (KTW), Poznań (POZ)

To: Barcelona, Rome, London, Paris, Dubai, Bangkok, Amsterdam, Lisbon, Athens, Istanbul, Tenerife, Prague, Vienna, Berlin and 70+ more.

## Tech Stack

- Python 3.11
- [aiogram 3.x](https://docs.aiogram.dev/) — Telegram Bot framework
- SQLite — user data, alerts, favorites
- Ryanair API, Wizz Air API, Kiwi.com Tequila API, fast-flights (Google Flights)
- Deployed on [Render](https://render.com)

## Self-Hosting

```bash
git clone https://github.com/Daniel52147/DDFlatsBot.git
cd DDFlatsBot
pip install -r requirements.txt
```

Set environment variables:
```
BOT_TOKEN=your_telegram_bot_token
ADMIN_IDS=your_telegram_id
CHANNEL_ID=@your_channel
KIWI_API_KEY=your_kiwi_tequila_key   # optional, for real prices
```

Run:
```bash
python main.py
```

## Deploy on Render

1. Fork this repo
2. Create a new **Worker** service on [render.com](https://render.com)
3. Set env vars: `BOT_TOKEN`, `ADMIN_IDS`, `CHANNEL_ID`, `PYTHON_VERSION=3.11.9`
4. Build command: `pip install -r requirements.txt`
5. Start command: `python main.py`

---

Also includes **DDFlatsBot** — Warsaw apartment search bot (OLX, Otodom, Gratka, Morizon, Lento, Szybko, Nieruchomosci, Adresowo).

🏠 **Flats Bot:** [@DDFlatsBot](https://t.me/DDFlatsBot)
