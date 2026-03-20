CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    lang        TEXT    DEFAULT 'ru',
    vip         INTEGER DEFAULT 0,
    vip_until   TEXT,
    searches_today INTEGER DEFAULT 0,
    searches_date  TEXT,
    total_searches INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now')),
    last_seen   TEXT    DEFAULT (datetime('now'))
)
"""

CREATE_ALERTS = """
CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    origin      TEXT    NOT NULL,
    destination TEXT    NOT NULL,
    price_max   INTEGER,
    date_from   TEXT,
    date_to     TEXT,
    active      INTEGER DEFAULT 1,
    created_at  TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
)
"""

CREATE_SEARCHES = """
CREATE TABLE IF NOT EXISTS searches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    origin      TEXT,
    destination TEXT,
    date_from   TEXT,
    date_to     TEXT,
    results     INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now'))
)
"""

CREATE_FAVORITES = """
CREATE TABLE IF NOT EXISTS favorites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    origin      TEXT,
    destination TEXT,
    price       INTEGER,
    airline     TEXT,
    depart_at   TEXT,
    arrive_at   TEXT,
    link        TEXT,
    saved_at    TEXT    DEFAULT (datetime('now'))
)
"""

CREATE_HOT_DEALS = """
CREATE TABLE IF NOT EXISTS hot_deals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    origin      TEXT,
    destination TEXT,
    price       INTEGER,
    airline     TEXT,
    depart_at   TEXT,
    link        TEXT,
    found_at    TEXT    DEFAULT (datetime('now')),
    notified    INTEGER DEFAULT 0
)
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_active ON alerts(active);
CREATE INDEX IF NOT EXISTS idx_searches_user ON searches(user_id);
CREATE INDEX IF NOT EXISTS idx_hot_deals_notified ON hot_deals(notified);
"""

ALL_TABLES = [
    CREATE_USERS,
    CREATE_ALERTS,
    CREATE_SEARCHES,
    CREATE_FAVORITES,
    CREATE_HOT_DEALS,
]
