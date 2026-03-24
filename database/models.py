CREATE_APARTMENTS = """
CREATE TABLE IF NOT EXISTS apartments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT,
    price       INTEGER,
    district    TEXT,
    rooms       INTEGER,
    area        REAL,
    floor       TEXT,
    furnished   INTEGER DEFAULT 0,
    link        TEXT UNIQUE,
    image       TEXT,
    source      TEXT,
    created_at  TEXT
)
"""

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    vip         INTEGER DEFAULT 0,
    vip_until   TEXT,
    views       INTEGER DEFAULT 0,
    ref_code    TEXT UNIQUE,
    referred_by INTEGER,
    ref_count   INTEGER DEFAULT 0,
    lang        TEXT DEFAULT 'ru',
    created_at  TEXT
)
"""

CREATE_RATINGS = """
CREATE TABLE IF NOT EXISTS ratings (
    user_id      INTEGER,
    apartment_id INTEGER,
    rating       INTEGER,
    PRIMARY KEY (user_id, apartment_id)
)
"""

CREATE_FAVORITES = """
CREATE TABLE IF NOT EXISTS favorites (
    user_id      INTEGER,
    apartment_id INTEGER,
    PRIMARY KEY (user_id, apartment_id)
)
"""

CREATE_SUBSCRIPTIONS = """
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id  INTEGER,
    district TEXT,
    PRIMARY KEY (user_id, district)
)
"""

CREATE_ALERTS = """
CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    district    TEXT,
    price_min   INTEGER,
    price_max   INTEGER,
    rooms       INTEGER,
    active      INTEGER DEFAULT 1,
    created_at  TEXT
)
"""

CREATE_STATS = """
CREATE TABLE IF NOT EXISTS parse_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT,
    count      INTEGER,
    logged_at  TEXT
)
"""

CREATE_PRICE_HISTORY = """
CREATE TABLE IF NOT EXISTS price_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    apartment_id INTEGER,
    price        INTEGER,
    recorded_at  TEXT
)
"""

CREATE_USER_NOTES = """
CREATE TABLE IF NOT EXISTS user_notes (
    user_id    INTEGER,
    apt_id     INTEGER,
    note       TEXT,
    created_at TEXT,
    PRIMARY KEY (user_id, apt_id)
)
"""

# Performance indexes
CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_apartments_score ON apartments(score DESC);
CREATE INDEX IF NOT EXISTS idx_apartments_created ON apartments(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_apartments_price ON apartments(price);
"""
