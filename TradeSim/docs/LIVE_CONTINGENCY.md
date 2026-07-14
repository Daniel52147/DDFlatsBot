# Рыночные кризисы — план А и план Б

Фокус: **обвалы, медвежий рынок, паника, памп-дамп** — не API и не sync.

UI: **Биржа → «Обвалы и рынок — план А / план Б»**  
API: `GET /api/live-playbook` → поле `market_crises`

---

## Все рыночные сценарии

| # | Ситуация | План А (бот) | План Б (ты) |
|---|----------|--------------|-------------|
| 1 | **Flash crash −10%+** | emergency_halt, STOP-LOSS | `/pause all`, не ловить дно |
| 2 | **Медвежий рынок −20…40%** | STALE-LOSS, halt −8% | Live Micro, убрать мемы |
| 3 | **BTC падает, альты x2 хуже** | correlation_block | `/pause all`, только BTC/ETH |
| 4 | **Чёрный лебедь (SEC, взлом)** | news → pause_dip/halt | `/pause`, решение через сутки |
| 5 | **Мёртвый кот (отскок → снова вниз)** | dip_cooldown | не resume all после 1 зелёного часа |
| 6 | **Капитуляция, серия стопов** | StoplossGuard, Cooldown | не clear protections, стоп на день |
| 7 | **Памп-дамп мема** | TRAIL-PROFIT, stop 12% | `/pause` мем, только majors |
| 8 | **Памп +15…30%** | take-profit частями | зафиксировать 25–50% |
| 9 | **Нет ликвидности, спред** | лимит размера | limit sell, дробить |
| 10 | **Выходные / ночь** | ≤3 сделки/день Micro | `/pause` на Live |
| 11 | **Гэп вниз утром** | STOP-LOSS, pause_dip | не усреднять первые 15 мин |
| 12 | **Ловушка dip (ещё −20%)** | dip_cooldown | `/pause`, не доливать |
| 13 | **Боковик / застой** | STALE-LOSS 15% | conservative, меньше рынков |
| 14 | **Всё падает разом** | correlation + halt | `/pause all`, ждать 1–3 дня |
| 15 | **Одна монета −30%** | STOP на символе | `/pause` только её |
| 16 | **Макро risk-off (ФРС)** | reduce_aggression | testnet, 50% в USDT вне бота |
| 17 | **V-отскок — когда resume?** | brain continue | `/resume BTC` по одной, не all |

---

## Золотое правило при обвале

**План А** уже работает: мозг, стопы, correlation, halt −8%.  
**План Б для тебя:** `/pause` → не усреднять → не снимать protections → завтра решать.

---

*TradeSim v55+ · `learning/live_playbook.py`*
