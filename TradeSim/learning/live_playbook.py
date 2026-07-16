"""Live contingency playbook — Plan A / Plan B for every known failure mode."""

from __future__ import annotations

from typing import Any

import config

# Each scenario: situation → automatic Plan A → manual Plan B.
# `actions` lists TradeSim UI buttons, API paths, or Telegram commands.

LIVE_PLAYBOOK: list[dict[str, Any]] = [
    # ── Обвалы и рыночные кризисы (главный фокус) ─────────────────────────
    {
        "id": "flash_crash",
        "category": "market",
        "severity": "critical",
        "title": "Flash crash — обвал −10%+ за минуты",
        "situation": "Резкое падение на новости, ликвидациях или панике. Свечи длинные красные.",
        "detection": "Мозг: emergency_halt · Guardian halts · портфель −3%+ за час · волатильность x2.",
        "plan_a": "brain → emergency_halt · StoplossGuard · блок новых покупок · частичные STOP-LOSS по правилам.",
        "plan_b": "/pause all · НЕ покупать «на дне» · ждать 30–60 мин стабилизации · смотреть brain decision.",
        "actions": ["/pause", "GET /api/brain"],
    },
    {
        "id": "bear_market_slow",
        "category": "market",
        "severity": "critical",
        "title": "Медвежий рынок — −20…40% за недели",
        "situation": "Медленное кровотечение: каждый отскок продают, DCA усредняет в падающий рынок.",
        "detection": "vs Hold отрицательный · серия STALE-LOSS · DCA покупает всё чаще · P&L −5…15%.",
        "plan_a": "STALE-LOSS (−8%/36ч) · reduce_aggression · correlation block · portfolio halt при −8%.",
        "plan_b": "Live Micro или testnet · убрать мемы · preset conservative · DCA ≥12ч · не усредняться бесконечно.",
        "actions": ["POST /api/strategy/preset", "Live Micro", "/pause"],
    },
    {
        "id": "btc_dump_alts_bleed",
        "category": "market",
        "severity": "critical",
        "title": "BTC падает — альты падают в 2–3 раза сильнее",
        "situation": "BTC −5%, DOGE/SHIB −15%. Диверсификация не работает.",
        "detection": "correlation_risk.block_buys · все монеты красные · correlation agent в chatroom.",
        "plan_a": "correlation_block — нет новых buy · portfolio halt при общей просадке.",
        "plan_b": "/pause all · оставить только BTC/ETH на Live · не снимать correlation block руками.",
        "actions": ["GET /api/status → correlation_risk", "/pause"],
    },
    {
        "id": "black_swan_news",
        "category": "market",
        "severity": "critical",
        "title": "Чёрный лебедь — взлом, запрет, SEC, война",
        "situation": "Внезапная новость, рынок в свободном падении вне графика.",
        "detection": "news_watcher → bearish · brain emergency_halt · резкий объём · gap на свече.",
        "plan_a": "news_watcher → pause_dip / emergency_halt · стоп-лоссы · блок агрессии.",
        "plan_b": "/pause all · не верить «дешёвой цене» первые 2–4ч · Telegram /status · решение через сутки.",
        "actions": ["/pause", "GET /api/brain", "Chatroom → news"],
    },
    {
        "id": "dead_cat_bounce",
        "category": "market",
        "severity": "warn",
        "title": "Мёртвый кот — отскок +5…10%, потом снова вниз",
        "situation": "После обвала краткий рост, бот покупает dip — и рынок снова ломается.",
        "detection": "DIP-buy после halt · pause_dip снят рано · второй заход в минус за 24ч.",
        "plan_a": "dip_cooldown увеличен на Live · brain reduce_aggression после первого обвала.",
        "plan_b": "Не /resume all после первого зелёного часа · ждать 2–3 дня боковика · DCA не чаще 12ч.",
        "actions": ["/pause", "LIVE_MICRO_DIP_COOLDOWN_MIN=45"],
    },
    {
        "id": "capitulation_panic",
        "category": "market",
        "severity": "critical",
        "title": "Капитуляция — паника, объёмы, серия стопов",
        "situation": "Все продают, срабатывают стопы одна за другой, «кровь на улицах».",
        "detection": "3+ STOP-LOSS за день · StoplossGuard · CooldownPeriod · Telegram halt.",
        "plan_a": "StoplossGuard пауза 4ч на монету · CooldownPeriod блок buy 30 мин · emergency_halt.",
        "plan_b": "НЕ clear protections · НЕ «отбить» удвоением · стоп на сегодня · анализ завтра.",
        "actions": ["Ждать cooldown", "GET /api/integrations → protections"],
    },
    {
        "id": "pump_and_dump",
        "category": "market",
        "severity": "warn",
        "title": "Памп-дамп на мемкоине (+50% → −40%)",
        "situation": "Мем взлетел на хайпе, бот продал часть, потом обвал быстрее чем stop.",
        "detection": "SPIKE sell · затем −20% за час · slippage на sell хуже paper.",
        "plan_a": "TRAIL-PROFIT / MICRO-TP фиксируют на пампе · spike cooldown · stop-loss 12%.",
        "plan_b": "/pause на меме · убрать с Live · только majors (BTC/ETH/SOL) с реальными деньгами.",
        "actions": ["/pause DOGE", "preset conservative"],
    },
    {
        "id": "pump_spike",
        "category": "market",
        "severity": "warn",
        "title": "Резкий памп +15…30% (ещё не дамп)",
        "situation": "Цена взлетела за час, FOMO, бот на грани spike-buy.",
        "detection": "Spike watcher · TAKE-PROFIT сделки · volatility agent.",
        "plan_a": "take-profit / MICRO-TP / TRAIL-PROFIT — продажа частями · spike cooldown блокирует покупку на хае.",
        "plan_b": "Не отключать TP ради «ещё вырастет» · при сомнении /pause · зафиксировать 25–50% вручную.",
        "actions": ["Manual sell UI", "/pause BTC"],
    },
    {
        "id": "liquidity_crash",
        "category": "market",
        "severity": "critical",
        "title": "Ликвидность испарилась — огромный спред",
        "situation": "Стакан пустой, market sell исполняется на −3…8% от цены на экране.",
        "detection": "Slippage на бирже >> paper · мелкие монеты · ночь/выходные.",
        "plan_a": "Лимиты размера ордера · на мемах меньше объём.",
        "plan_b": "Не market sell всей позиции · дробить · /pause · торговать только ликвидные пары.",
        "actions": ["Limit sell", "/pause"],
    },
    {
        "id": "weekend_thin_market",
        "category": "market",
        "severity": "warn",
        "title": "Выходные / ночь — тонкий рынок",
        "situation": "Мало участников, любой ордер двигает цену, ложные пробои.",
        "detection": "Сделки ночью UTC · странные фитили на свечах · slippage выше нормы.",
        "plan_a": "На Live Micro и так мало сделок (≤3/день).",
        "plan_b": "/pause на выходные для Live · или только BTC · не scalp ночью.",
        "actions": ["/pause", "Live Micro"],
    },
    {
        "id": "gap_down_open",
        "category": "market",
        "severity": "critical",
        "title": "Гэп вниз — открылся ниже на 5…15%",
        "situation": "Ночью новость, утром цена уже далеко ниже вчерашнего закрытия.",
        "detection": "Первая свеча дня с огромным телом · позиция сразу −10% unrealized.",
        "plan_a": "STOP-LOSS по правилам · brain pause_dip при −7% на монете.",
        "plan_b": "Не усреднять в первые 15 мин · /status · если halt — не снимать до обеда.",
        "actions": ["/status", "GET /api/brain"],
    },
    {
        "id": "fomo_dip_trap",
        "category": "market",
        "severity": "warn",
        "title": "Ловушка «дешёвый dip» — падает ещё 20%",
        "situation": "Купил просадку −3%, рынок ушёл ещё на −15%. Классическая ловушка DCA.",
        "detection": "Серия DIP-buy · средняя цена выше текущей · unrealized −10%+.",
        "plan_a": "dip_cooldown · max_buy_pct снижен на Live Micro · StoplossGuard после стопов.",
        "plan_b": "Остановить DCA на этой монете · /pause · не «доливать чтобы усреднить».",
        "actions": ["/pause", "dip_cooldown_minutes ↑ в .env"],
    },
    {
        "id": "sideways_stale",
        "category": "market",
        "severity": "warn",
        "title": "Боковик / застой — деньги заморожены",
        "situation": "Цена ходит ±2% неделю, позиция в лёгком минусе, комиссии копятся.",
        "detection": "STALE-LOSS при −8% и 36+ ч · мало движения на графике.",
        "plan_a": "STALE-LOSS продаёт 15% · реже DCA на Live.",
        "plan_b": "Меньше рынков · conservative · не ждать «чуда» на мёртвом меме.",
        "actions": ["POST /api/strategy/preset"],
    },
    {
        "id": "correlation_dump",
        "category": "market",
        "severity": "critical",
        "title": "Всё падает разом — корреляция 1.0",
        "situation": "10 монет в портфеле — все красные, хеджа нет.",
        "detection": "correlation_risk.block_buys=true · heatmap весь красный.",
        "plan_a": "correlation_block · portfolio halt при −8% · reduce_aggression.",
        "plan_b": "/pause all · не покупать «одну сильную» · ждать brain continue 1–3 дня.",
        "actions": ["/pause", "GET /api/portfolio/heatmap"],
    },
    {
        "id": "single_coin_crash",
        "category": "market",
        "severity": "warn",
        "title": "Одна монета обвалилась (−30%), рынок в целом OK",
        "situation": "Delist rumor, hack одного проекта, мем умер — остальные норм.",
        "detection": "Один рынок −20%+ · остальные ±2% · StoplossGuard на символе.",
        "plan_a": "STOP-LOSS + StoplossGuard пауза на этой монете · остальные работают.",
        "plan_b": "/pause только эту монету · убрать из списка на Live · не трогать остальных без причины.",
        "actions": ["/pause DOGE", "POST /api/bot/toggle"],
    },
    {
        "id": "macro_risk_off",
        "category": "market",
        "severity": "warn",
        "title": "Макро risk-off — ставка ФРС, рецессия, сильный USD",
        "situation": "Крипта падает неделями вместе с риск-активами, без одной новости.",
        "detection": "news macro · медленный минус · vs Hold плохо · все агенты defensive.",
        "plan_a": "reduce_aggression длительно · реже DCA · profit focus снижает размер.",
        "plan_b": "Не Live с полным депозитом · 50% в USDT вне бота · testnet до разворота тренда.",
        "actions": ["testnet", "preset conservative"],
    },
    {
        "id": "v_recovery_resume",
        "category": "market",
        "severity": "info",
        "title": "Отскок V-образный — когда снова торговать?",
        "situation": "После обвала рынок +8% за день, хочется /resume all.",
        "detection": "brain decision → continue · P&L восстановился · volatility снизилась.",
        "plan_a": "brain снимает halt когда агенты согласны · protections cooldown истёк.",
        "plan_b": "Resume по одной монете · сначала BTC · Live Micro · не полный депозит сразу.",
        "actions": ["/resume BTC", "Live Micro", "GET /api/brain"],
    },
    # ── Портфель и P&L ───────────────────────────────────────────────────
    {
        "id": "daily_loss_limit",
        "category": "portfolio",
        "severity": "critical",
        "title": "Дневной лимит убытка (LIVE_MAX_DAILY_LOSS_PCT)",
        "situation": "За сутки портфель потерял ≥3% (настройка по умолчанию).",
        "detection": "binance_live risk gate · алерт в Telegram · новые ордера на биржу блокируются.",
        "plan_a": "Авто: биржа не принимает новые buy · protections CooldownPeriod.",
        "plan_b": "Стоп на сегодня · smoke test завтра · не повышать лимит в .env из паники · "
        "анализ сделок в /api/trades.",
        "actions": ["GET /api/exchange/pnl", "POST /api/smoke-test"],
    },
    {
        "id": "max_drawdown",
        "category": "portfolio",
        "severity": "critical",
        "title": "Просадка портфеля ≥ LIVE_MAX_DRAWDOWN_PCT (8%)",
        "situation": "Equity упал от пика на 8%+.",
        "detection": "risk_gate portfolio_halt · live_readiness check красный · brain emergency_halt.",
        "plan_a": "Авто: set_portfolio_halt — все покупки стоп · Telegram halt alert.",
        "plan_b": "Не resume all сразу · разобрать по монетам · вернуться на Testnet · "
        "Live Micro с $10 после 3+ дней стабильности.",
        "actions": ["GET /api/live-readiness", "POST /api/trading-mode → testnet"],
    },
    {
        "id": "fees_eating_pnl",
        "category": "portfolio",
        "severity": "warn",
        "title": "Комиссии съедают прибыль",
        "situation": ">30 сделок/день, fees >$5/день при мелком депозите.",
        "detection": "live_prep fee_warning · GET /api/fees · scorecard.",
        "plan_a": "Авто: Live Micro лимит 3 сделки/день · DCA ≥12ч · крупнее ордер при том же числе сделок.",
        "plan_b": "TRADE_MODE=normal (не active) · отключить scalp/grid на Live · "
        "цель 2–5 сделок/день.",
        "actions": ["POST /api/live-prep/start-micro", "GET /api/fees"],
    },
    {
        "id": "paper_vs_live_gap",
        "category": "portfolio",
        "severity": "warn",
        "title": "Paper +47%, Live/Testnet в минусе",
        "situation": "Paper переоценивает исполнение; реальные комиссии и slippage.",
        "detection": "benchmark live_pnl vs paper · reconcile Δ · smoke test P&L check.",
        "plan_a": "Считать Testnet эталоном, не Paper · EXCHANGE_SYNC_FROM_PAPER=true.",
        "plan_b": "Не увеличивать депозит · неделя Testnet на стабильность · "
        "сравнить /api/benchmark и /api/exchange/pnl.",
        "actions": ["GET /api/benchmark", "EXCHANGE_SYNC_FROM_PAPER=true"],
    },
    # ── Биржа и API ──────────────────────────────────────────────────────
    {
        "id": "api_down",
        "category": "exchange",
        "severity": "critical",
        "title": "Binance API недоступен / timeout",
        "situation": "Ордера не проходят, verify failed, тики замирают.",
        "detection": "stability_summary success_rate <85% · verify.ok=false · логи timeout.",
        "plan_a": "Авто: retry в binance_live · Telegram TELEGRAM_ALERT_SYNC_FAIL · "
        "paper продолжает симуляцию (осторожно на Live!).",
        "plan_b": "/pause all · проверить status.binance.com · VPN/регион · "
        "POST /api/live-prep/stability-check · не дублировать ордера вручную.",
        "actions": ["GET /api/exchange/verify", "POST /api/live-prep/stability-check", "/pause"],
    },
    {
        "id": "rate_limit",
        "category": "exchange",
        "severity": "warn",
        "title": "Rate limit 429 / IP ban",
        "situation": "Слишком много запросов, Binance режет IP.",
        "detection": "HTTP 429 в логах · sync_failures растут · verify intermittent.",
        "plan_a": "Авто: backoff в клиенте · уменьшить число рынков · feed_hub вместо poll.",
        "plan_b": "Пауза 15–30 мин · один инстанс бота (не два на одном ключе) · "
        "снизить TRADE_MODE до normal.",
        "actions": ["/pause", "Один процесс main.py"],
    },
    {
        "id": "order_rejected",
        "category": "exchange",
        "severity": "warn",
        "title": "Ордер отклонён (min notional / LOT_SIZE / balance)",
        "situation": "Binance вернул 400: NOTIONAL, LOT_SIZE, insufficient balance.",
        "detection": "sync_failures++ · лог exchange order error · reconcile Δ.",
        "plan_a": "Авто: live limits LIVE_MAX_ORDER_USD · wallet_bridge sync USDT.",
        "plan_b": "POST /api/wallet/sync-usdt · увеличить ордер до min notional ($5–10) · "
        "POST /api/exchange/sync-paper-all.",
        "actions": ["POST /api/wallet/sync-usdt", "POST /api/exchange/sync-paper-all"],
    },
    {
        "id": "geo_block_451",
        "category": "exchange",
        "severity": "critical",
        "title": "Geo-block HTTP 451",
        "situation": "Binance недоступен из региона без VPN.",
        "detection": "verify: geo blocked · 451 в логах.",
        "plan_a": "Не торговать Live с этого IP — только Paper.",
        "plan_b": "Легальный VPN / VPS в разрешённом регионе · Testnet с того же IP что будет Live · "
        "никогда не хранить ключи на чужом сервере без 2FA.",
        "actions": ["GET /api/exchange/verify", "EXCHANGE_TESTNET=true"],
    },
    {
        "id": "bad_api_keys",
        "category": "exchange",
        "severity": "critical",
        "title": "Неверные / отозванные API ключи",
        "situation": "401/403 при verify, ордера не проходят.",
        "detection": "verify.ok=false · message invalid API-key.",
        "plan_a": "Бот не шлёт ордера · EXCHANGE_ENABLED остаётся, но risk блокирует.",
        "plan_b": "Binance → API Management → новые ключи · только Spot + IP whitelist · "
        "обновить .env · перезапуск · POST /api/telegram/test.",
        "actions": [".env BINANCE_API_KEY", "GET /api/exchange/verify"],
    },
    {
        "id": "testnet_faucet_empty",
        "category": "exchange",
        "severity": "info",
        "title": "Testnet USDT закончился",
        "situation": "Faucet пуст, ордера rejected insufficient balance.",
        "detection": "Баланс USDT ≈0 на testnet · order rejected.",
        "plan_a": "Пауза торговли до пополнения.",
        "plan_b": "testnet.binance.vision faucet · POST /api/deposit paper · "
        "wallet/sync-usdt после пополнения.",
        "actions": ["testnet.binance.vision", "POST /api/wallet/sync-usdt"],
    },
    # ── Синхронизация ────────────────────────────────────────────────────
    {
        "id": "reconcile_red",
        "category": "sync",
        "severity": "warn",
        "title": "Reconcile красный (paper ≠ биржа)",
        "situation": "Δ баланса или позиции между paper и exchange.",
        "detection": "GET /api/exchange/reconcile · smoke test reconcile check.",
        "plan_a": "При EXCHANGE_SYNC_FROM_PAPER=true — sync после каждого ордера.",
        "plan_b": "POST /api/exchange/sync-paper-all · если на Live — сверить вручную на Binance · "
        "не торговать до зелёного smoke test.",
        "actions": ["GET /api/exchange/reconcile", "POST /api/exchange/sync-paper-all"],
    },
    {
        "id": "sync_failed_after_fill",
        "category": "sync",
        "severity": "critical",
        "title": "Ордер на бирже исполнен, paper не обновился",
        "situation": "Рассинхрон: реальная позиция есть, симуляция нет.",
        "detection": "sync_failures · Telegram sync alert · reconcile Δ.",
        "plan_a": "Авто: retry sync · лог в stability.",
        "plan_b": "Немедленно /pause · sync-paper-all · сверка баланса Binance · "
        "не открывать вторую позицию руками.",
        "actions": ["/pause", "POST /api/exchange/sync-paper-all", "GET /api/exchange/balances"],
    },
    {
        "id": "paper_position_no_exchange",
        "category": "sync",
        "severity": "warn",
        "title": "Paper есть позиция, на бирже нет",
        "situation": "EXCHANGE_SYNC_FROM_PAPER=false — paper-only сделки.",
        "detection": "reconcile: paper qty > exchange · ожидаемо при false sync.",
        "plan_a": "Для Testnet/Live: включить EXCHANGE_SYNC_FROM_PAPER=true.",
        "plan_b": "Не паниковать на Paper · перед Live — sync-paper-all и smoke test.",
        "actions": ["EXCHANGE_SYNC_FROM_PAPER=true", "Smoke test"],
    },
    # ── Бот и инфраструктура ─────────────────────────────────────────────
    {
        "id": "bot_crash_restart",
        "category": "infra",
        "severity": "warn",
        "title": "Краш / перезагрузка ПК",
        "situation": "main.py остановлен, позиции на бирже остались.",
        "detection": "Нет ответа /api/ping · Telegram молчит.",
        "plan_a": "При рестарте: сессии из tradesim.db · позиции engine восстанавливаются · "
        "open limits из БД.",
        "plan_b": "python main.py · GET /api/exchange/reconcile · /status в Telegram · "
        "на Live — VPS/Render 24/7.",
        "actions": ["python main.py", "GET /api/ping", "/status"],
    },
    {
        "id": "no_ticks",
        "category": "infra",
        "severity": "warn",
        "title": "Нет тиков / зависание цены",
        "situation": "График стоит, last_update старый.",
        "detection": "Лог poll failed / ws disconnect · lag heal в main.",
        "plan_a": "Авто: reconnect WS · fetch_price fallback · lag heal candles.",
        "plan_b": "Перезапуск main.py · проверить интернет · /pause до восстановления feed.",
        "actions": ["Restart main.py", "/pause"],
    },
    {
        "id": "db_corrupt",
        "category": "infra",
        "severity": "critical",
        "title": "База data/tradesim.db повреждена",
        "situation": "SQLite errors при старте.",
        "detection": "Ошибки в логе при load · API 500.",
        "plan_a": "Восстановить из бэкапа .db (если есть).",
        "plan_b": "Остановить бота · копия бэкапа · крайний случай POST /api/reset (потеря истории) · "
        "позиции сверить с Binance вручную.",
        "actions": ["Backup data/tradesim.db", "GET /api/exchange/balances"],
    },
    {
        "id": "internet_down",
        "category": "infra",
        "severity": "warn",
        "title": "Нет интернета / Wi‑Fi обрыв",
        "situation": "Все fetch failed.",
        "detection": "verify failed · нет WS · Telegram не доставляет.",
        "plan_a": "Бот ждёт reconnect.",
        "plan_b": "Не трогать биржу с телефона вслепую · восстановить сеть · "
        "reconcile после связи.",
        "actions": ["/status после связи"],
    },
    # ── Защиты и мозг ────────────────────────────────────────────────────
    {
        "id": "emergency_halt_brain",
        "category": "protections",
        "severity": "critical",
        "title": "Emergency halt от мозга",
        "situation": "brain.decision = emergency_halt — агрессия снята.",
        "detection": "UI brain panel красный · Telegram halt · reduce_aggression active.",
        "plan_a": "Авто: apply_decision — консервативные параметры · новые рискованные buy блокируются.",
        "plan_b": "Не /resume all сразу · дождаться decision=continue · проверить guardian halts.",
        "actions": ["GET /api/brain", "Ждать continue"],
    },
    {
        "id": "stoploss_guard",
        "category": "protections",
        "severity": "warn",
        "title": "StoplossGuard (3 стопа за 24ч на монету)",
        "situation": "Три STOP-LOSS на одном рынке — пауза 4ч.",
        "detection": "protections paused_symbols · reason в /api/status.",
        "plan_a": "Авто: пауза бота на символе 4ч (PROTECTION_STOPLOSS_PAUSE_SEC).",
        "plan_b": "Не POST /api/protections/clear без анализа · сменить preset · "
        "/resume BTC только после cooldown.",
        "actions": ["GET /api/integrations → protections", "POST /api/protections/clear — осторожно"],
    },
    {
        "id": "cooldown_period",
        "category": "protections",
        "severity": "warn",
        "title": "CooldownPeriod (5 убыточных продаж за час)",
        "situation": "Глобальный блок покупок на 30 мин.",
        "detection": "protections global_active · blocks_buy всех монет.",
        "plan_a": "Авто: global_cooldown 30 мин.",
        "plan_b": "Ждать окончания · не clear_all из паники · разобрать причины убытков.",
        "actions": ["Ждать global_cooldown_min"],
    },
    {
        "id": "live_micro_trade_cap",
        "category": "protections",
        "severity": "info",
        "title": "Лимит сделок Live Micro (3/день)",
        "situation": "Достигнут LIVE_MICRO_MAX_TRADES_PER_DAY.",
        "detection": "Нет новых buy на монете · live_micro в статусе.",
        "plan_a": "Авто: блок до следующих суток.",
        "plan_b": "Нормально для Micro · не повышать лимит в первую неделю.",
        "actions": ["Live Micro — ждать завтра"],
    },
    # ── Пользователь ─────────────────────────────────────────────────────
    {
        "id": "user_panic_sell_all",
        "category": "user",
        "severity": "critical",
        "title": "Паника — хочу продать всё",
        "situation": "Эмоциональная реакция на просадку.",
        "detection": "Ручные клики sell · вопрос в чате помощника.",
        "plan_a": "/pause all · вдохнуть · посмотреть /api/brain и drawdown (может быть −2%, не −20%).",
        "plan_b": "Продать 25% вручную если must · не market sell 100% в illiquid мем · "
        "вернуться на testnet.",
        "actions": ["/pause", "POST /api/trading-mode testnet"],
    },
    {
        "id": "accidental_live",
        "category": "user",
        "severity": "critical",
        "title": "Случайно включили Live без готовности",
        "situation": "TRADING_MODE=live, readiness <80%, smoke test не пройден.",
        "detection": "live_readiness ready_for_live=false · mode live.",
        "plan_a": "LIVE_REQUIRE_READINESS блокирует крупные ордера.",
        "plan_b": "Немедленно POST /api/trading-mode → testnet · /pause · smoke test · "
        "Live Micro только после фазы 3/5.",
        "actions": ["POST /api/trading-mode", "POST /api/smoke-test"],
    },
    {
        "id": "forgot_testnet_flag",
        "category": "user",
        "severity": "critical",
        "title": "EXCHANGE_TESTNET=false на реальном счёте",
        "situation": "Ордера идут на mainnet с реальными деньгами.",
        "detection": "GET /api/trading-mode · exchange testnet=false.",
        "plan_a": "—",
        "plan_b": "/pause all · .env EXCHANGE_TESTNET=true для тестов · "
        "для Live осознанно false + Live Micro $10.",
        "actions": [".env EXCHANGE_TESTNET", "GET /api/exchange/status"],
    },
    {
        "id": "manual_override_conflict",
        "category": "user",
        "severity": "warn",
        "title": "Ручная сделка конфликтует с ботом",
        "situation": "Купил на Binance вручную, бот не знает.",
        "detection": "reconcile Δ · странный P&L.",
        "plan_a": "—",
        "plan_b": "sync-paper-all · или /pause на монете · дальше только бот или только руки.",
        "actions": ["POST /api/exchange/sync-paper-all"],
    },
    # ── Telegram и мониторинг ─────────────────────────────────────────────
    {
        "id": "telegram_down",
        "category": "monitoring",
        "severity": "warn",
        "title": "Telegram не шлёт алерты",
        "situation": "Нет сообщений при halt/sync fail.",
        "detection": "GET /api/telegram/status enabled=false или chat не настроен.",
        "plan_a": "Бот работает, мониторинг через UI /api/alerts.",
        "plan_b": "POST /api/telegram/test · проверить TELEGRAM_BOT_TOKEN, CHAT_ID · "
        "/start боту в личке.",
        "actions": ["POST /api/telegram/test", ".env TELEGRAM_*"],
    },
    {
        "id": "no_monitoring_24_7",
        "category": "monitoring",
        "severity": "warn",
        "title": "Некому смотреть ночью",
        "situation": "ПК спит, алерты не видишь.",
        "detection": "Просадка утром · пропущенные halt.",
        "plan_a": "Telegram на телефон · TELEGRAM_ALERT_HALT=true.",
        "plan_b": "VPS/Render · или /pause на ночь на Live · не держать крупный депозит без присмотра.",
        "actions": ["Telegram alerts", "VPS deploy"],
    },
    # ── Эскалация Live ───────────────────────────────────────────────────
    {
        "id": "escalate_to_live_micro",
        "category": "escalation",
        "severity": "info",
        "title": "Переход Testnet → Live Micro ($10)",
        "situation": "Фазы 1–3 пройдены, smoke test ≥85%.",
        "detection": "live_prep phase 4 · smoke test passed.",
        "plan_a": "POST /api/live-prep/start-micro · LIVE_MICRO_MODE=true · ордер ≤$10.",
        "plan_b": "Если сомнение — ещё 7 дней testnet · не skip smoke test.",
        "actions": ["POST /api/live-prep/start-micro", "Smoke test"],
    },
    {
        "id": "escalate_to_full_live",
        "category": "escalation",
        "severity": "warn",
        "title": "Live Micro → полный Live",
        "situation": "7+ дней Micro без красных reconcile, P&L не критичен.",
        "detection": "readiness ready_for_live · 5/5 фаз.",
        "plan_a": "Постепенно LIVE_MAX_ORDER_USD 10→25 · отключить LIVE_MICRO_MODE.",
        "plan_b": "При первом −3% дня — откат на Micro · не удваивать депозит после удачной недели.",
        "actions": [".env LIVE_MAX_ORDER_USD", "GET /api/live-readiness"],
    },
    {
        "id": "rollback_live_to_testnet",
        "category": "escalation",
        "severity": "warn",
        "title": "Откат Live → Testnet",
        "situation": "Серия убытков, потеря доверия к стратегии.",
        "detection": "drawdown · smoke fail · пользовательское решение.",
        "plan_a": "/pause all · POST /api/trading-mode testnet.",
        "plan_b": "Закрыть позиции вручную или дать боту TP · анализ /api/trades · "
        "не возвращаться на Live минимум 2 недели paper/testnet.",
        "actions": ["POST /api/trading-mode", "/pause"],
    },
    {
        "id": "increase_deposit",
        "category": "escalation",
        "severity": "warn",
        "title": "Хочу увеличить депозит после прибыли",
        "situation": "+47% paper — соблазн вложить больше.",
        "detection": "Вопрос пользователя · хороший scorecard.",
        "plan_a": "Правило: +10–20% депозита только после 30 дней Live Micro в плюс.",
        "plan_b": "Не переносить весь paper P&L в ожидания · benchmark vs hold на testnet.",
        "actions": ["GET /api/benchmark", "GET /api/scorecard"],
    },
    # ── Ордера ───────────────────────────────────────────────────────────
    {
        "id": "stuck_limit_order",
        "category": "orders",
        "severity": "warn",
        "title": "Limit-ордер висит, цена ушла",
        "situation": "Открытый limit далеко от рынка.",
        "detection": "GET /api/orders/open · UI открытые ордера.",
        "plan_a": "Ждать или отменить автоматически при смене стратегии.",
        "plan_b": "POST /api/orders/cancel · переставить limit · /pause если их много.",
        "actions": ["GET /api/orders/open", "POST /api/orders/cancel"],
    },
    {
        "id": "partial_fill",
        "category": "orders",
        "severity": "info",
        "title": "Частичное исполнение ордера",
        "situation": "Filled 60%, остаток висит.",
        "detection": "Биржа partial · reconcile небольшой Δ.",
        "plan_a": "Авто: sync-paper под фактический fill.",
        "plan_b": "sync-paper · отменить остаток или дождаться.",
        "actions": ["POST /api/exchange/sync-paper"],
    },
    {
        "id": "slippage_worse_than_paper",
        "category": "orders",
        "severity": "warn",
        "title": "Проскальзывание хуже paper",
        "situation": "Live fill на 0.5–2% хуже симуляции.",
        "detection": "Сравнение цены сделки paper vs exchange.",
        "plan_a": "Увеличить dip_threshold · реже сделки на мемах.",
        "plan_b": "Меньше рынков · только majors на Live · limit вместо market где возможно.",
        "actions": ["preset conservative", "Limit orders UI"],
    },
]

CATEGORIES: dict[str, str] = {
    "market": "🔥 Обвалы и рыночные кризисы",
    "portfolio": "💰 Портфель (следствие рынка)",
    "exchange": "🏦 Биржа и API",
    "sync": "🔗 Синхронизация paper ↔ биржа",
    "infra": "🖥 Бот и инфраструктура",
    "protections": "🛡 Защиты и мозг",
    "user": "👤 Действия пользователя",
    "monitoring": "📡 Telegram и мониторинг",
    "escalation": "🚀 Эскалация Live",
    "orders": "📋 Ордера",
}


def build_live_playbook(*, risk_status: dict[str, Any] | None = None) -> dict[str, Any]:
    """Structured playbook for API and UI."""
    risk_status = risk_status or {}
    active_hints: list[str] = []

    if risk_status.get("portfolio_halt"):
        active_hints.append("max_drawdown")
    if risk_status.get("correlation_block"):
        active_hints.append("correlation_dump")
    prot = risk_status.get("protections") or {}
    if prot.get("global_active"):
        active_hints.append("cooldown_period")
    for sym in (prot.get("paused_symbols") or {}):
        active_hints.append("stoploss_guard")
        break

    by_category: dict[str, list[dict[str, Any]]] = {}
    for item in LIVE_PLAYBOOK:
        cat = item["category"]
        entry = {**item, "may_apply": item["id"] in active_hints}
        by_category.setdefault(cat, []).append(entry)

    categories = [
        {
            "id": cid,
            "title": CATEGORIES[cid],
            "count": len(by_category.get(cid, [])),
            "scenarios": by_category.get(cid, []),
            "primary": cid == "market",
        }
        for cid in CATEGORIES
    ]

    market_crises = by_category.get("market", [])

    return {
        "version": config.APP_VERSION,
        "title": "Рыночные кризисы — план А и план Б",
        "focus": "market_crises",
        "summary": (
            f"{len(market_crises)} рыночных сценариев (обвалы, медвежий рынок, памп-дамп, паника…) "
            f"+ {len(LIVE_PLAYBOOK) - len(market_crises)} технических. "
            "План А — бот, план Б — ты."
        ),
        "active_hints": active_hints,
        "market_crises": market_crises,
        "categories": categories,
        "quick_rules": [
            "При обвале: /pause all важнее чем «купить дешевле».",
            "План А: brain (halt/pause_dip), STOP-LOSS, STALE-LOSS, correlation block, portfolio halt −8%.",
            "План Б: не снимать protections · не усреднять в панике · Live Micro или testnet.",
            "После обвала: resume по одной монете, не all сразу · ждать brain continue.",
            f"Лимиты: ордер ≤${config.LIVE_MAX_ORDER_USD}, день ≤−{config.LIVE_MAX_DAILY_LOSS_PCT}%, просадка ≤{config.LIVE_MAX_DRAWDOWN_PCT}%.",
        ],
    }
