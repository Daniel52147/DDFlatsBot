import sqlite3
import os
import random
import string
import re
from datetime import datetime, timedelta
from database.models import (
    CREATE_APARTMENTS, CREATE_USERS, CREATE_FAVORITES,
    CREATE_SUBSCRIPTIONS, CREATE_ALERTS, CREATE_STATS, CREATE_PRICE_HISTORY,
    CREATE_RATINGS, CREATE_INDEXES, CREATE_USER_NOTES,
)
from config import DB_PATH, VIP_EARLY_ACCESS_MINUTES, REFERRAL_REWARD_DAYS, EARLY_ADOPTER_LIMIT


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    # WAL mode: better concurrency for multi-threaded bot
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=10000")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def init_db():
    print(f"[DB] Initializing database at: {DB_PATH}")
    print(f"[DB] File exists: {os.path.exists(DB_PATH)}")
    conn = get_conn()
    c = conn.cursor()
    for sql in [CREATE_APARTMENTS, CREATE_USERS, CREATE_FAVORITES,
                CREATE_SUBSCRIPTIONS, CREATE_ALERTS, CREATE_STATS,
                CREATE_PRICE_HISTORY, CREATE_RATINGS, CREATE_USER_NOTES]:
        c.execute(sql)

    # Create performance indexes
    for stmt in CREATE_INDEXES.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            try:
                c.execute(stmt)
            except Exception:
                pass

    # user_seen table
    try:
        c.execute("""CREATE TABLE IF NOT EXISTS user_seen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            apt_id INTEGER NOT NULL,
            seen_at TEXT,
            UNIQUE(user_id, apt_id)
        )""")
    except Exception:
        pass

    migrations = [
        "ALTER TABLE users ADD COLUMN vip_until TEXT",
        "ALTER TABLE users ADD COLUMN ref_code TEXT",
        "ALTER TABLE users ADD COLUMN referred_by INTEGER",
        "ALTER TABLE users ADD COLUMN ref_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'ru'",
        "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'",
        "ALTER TABLE users ADD COLUMN last_visit TEXT",
        "ALTER TABLE users ADD COLUMN city TEXT DEFAULT 'Warszawa'",
        "ALTER TABLE users ADD COLUMN hide_seen INTEGER DEFAULT 1",
        "ALTER TABLE users ADD COLUMN search_radius_km INTEGER DEFAULT 100",
        "ALTER TABLE alerts ADD COLUMN city TEXT",
        """CREATE TABLE IF NOT EXISTS hidden_apartments (
            user_id INTEGER NOT NULL,
            apt_id INTEGER NOT NULL,
            hidden_at TEXT,
            UNIQUE(user_id, apt_id)
        )""",
        "ALTER TABLE apartments ADD COLUMN rooms INTEGER",
        "ALTER TABLE apartments ADD COLUMN area REAL",
        "ALTER TABLE apartments ADD COLUMN floor TEXT",
        "ALTER TABLE apartments ADD COLUMN furnished INTEGER DEFAULT 0",
        "ALTER TABLE apartments ADD COLUMN image TEXT",
        "ALTER TABLE apartments ADD COLUMN score REAL DEFAULT 0",
        "ALTER TABLE apartments ADD COLUMN verified INTEGER DEFAULT 0",
        "ALTER TABLE apartments ADD COLUMN reported INTEGER DEFAULT 0",
        "ALTER TABLE apartments ADD COLUMN apt_views INTEGER DEFAULT 0",
        "ALTER TABLE apartments ADD COLUMN city TEXT DEFAULT 'Warszawa'",
        """CREATE TABLE IF NOT EXISTS user_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            UNIQUE(user_id, date)
        )""",
        """CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            apartment_id INTEGER,
            reason TEXT,
            created_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS mod_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mod_id INTEGER,
            action TEXT,
            target_id INTEGER,
            note TEXT,
            created_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS conversions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            apt_id INTEGER,
            source TEXT,
            created_at TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS validation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reason TEXT NOT NULL,
            target_city TEXT,
            link TEXT,
            logged_at TEXT NOT NULL
        )""",
    ]
    for sql in migrations:
        try:
            c.execute(sql)
        except Exception:
            pass  # Column already exists — skip

    conn.commit()
    conn.close()
    try:
        from database.migrations import run_all_migrations
        run_all_migrations(DB_PATH)
    except Exception as e:
        print(f"[DB] Schema migrations: {e}")
    cleanup_junk_listings()
    # One-time migration: set city for existing apartments without city
    _migrate_city_field()
    _backfill_city_from_source()
    sync_apartments_city_from_links()


# ── Apartments ───────────────────────────────────────────────

def _is_apartment_listing(title: str, price: int) -> bool:
    """Filter out non-apartment listings before saving."""
    if not title:
        return False
    t = title.lower()
    junk = [
        "osuszacz", "klimatyzator", "agregat", "laweta", "przyczepa",
        "rower", "samochód", "skuter", "motor", "kamera", "telewizor",
        "lodówka", "pralka", "zmywarka", "garaż", "parking",
        "miejsce postojowe", "komórka", "działka", "lokal użytkowy",
        "biuro na wynajem", "magazyn", "hala ", "sprzedam dom",
        "na sprzedaż", "sprzedaż", "skup", "usługi",
        "na godziny", "godz/",
        "osuszanie", "pochłaniacz",
    ]
    for kw in junk:
        if kw in t:
            return False
    # Price sanity: rentals in Warsaw are 500–20000 zł
    if price and (price < 300 or price > 30000):
        return False
    return True


_NON_WARSAW = {
    "widzew", "górna", "bałuty", "polesie", "retkinia", "śródmieście-wschód",
    "zgierz", "łódź", "lodz", "częstochowa", "radomsko", "kutno", "łęczyca",
    "piotrków", "łask", "zduńska", "zelów", "sieradz", "tomaszów",
    "opoczno", "gdańsk", "gdansk", "kraków", "krakow", "wrocław", "wroclaw",
    "poznań", "poznan", "katowice", "lublin", "szczecin", "bydgoszcz", "białystok",
}


def _is_warsaw(district: str) -> bool:
    """Return False if district clearly belongs to another city."""
    if not district:
        return True  # unknown district — allow
    d = district.lower().strip()
    for city in _NON_WARSAW:
        if city in d:
            return False
    return True


# ── City detection ────────────────────────────────────────────

_CITY_KEYWORDS = {
    "Warszawa":  ["warszawa", "warsaw", "варшав", "варшав"],
    "Kraków":    ["kraków", "krakow", "cracow", "краков", "краків"],
    "Wrocław":   ["wrocław", "wroclaw", "breslau", "вроцлав"],
    "Gdańsk":    ["gdańsk", "gdansk", "danzig", "гданьск", "гданськ"],
    "Poznań":    ["poznań", "poznan", "познань", "познань"],
    "Łódź":      ["łódź", "lodz", "лодзь"],
    "Katowice":  ["katowice", "катовице"],
    "Szczecin":  ["szczecin", "щецин"],
    "Lublin":    ["lublin", "люблин"],
    "Białystok": ["białystok", "bialystok", "белосток"],
}


def _has_false_positive_street(text: str, city: str) -> bool:
    """Street names like Wrocławska must not reassign listing to Wrocław."""
    try:
        from validation.geographic import FALSE_POSITIVE_STREETS, _normalize_street
        streets = FALSE_POSITIVE_STREETS.get(city, [])
        t = _normalize_street(text)
    except Exception:
        return False
    return any(fp in t for fp in streets)


def _detect_city(title: str, district: str, source_city: str = "") -> str:
    """
    Detect which city an apartment belongs to.
    Priority: source_city (parser) > word-boundary title/district > default.
    """
    if source_city and source_city in _CITY_KEYWORDS:
        return source_city

    text = f"{district} {title}".lower()
    if source_city and _has_false_positive_street(text, source_city):
        return source_city

    for city, keywords in _CITY_KEYWORDS.items():
        if source_city and city != source_city:
            continue
        for kw in keywords:
            if _re.search(rf"(?<![a-ząćęłńóśźż]){_re.escape(kw)}(?![a-ząćęłńóśźż])", text):
                return city

    return source_city or "Warszawa"


# ── Data normalizer ───────────────────────────────────────────

import re as _re

_ROOM_PATTERNS = [
    (_re.compile(r'\bkawalerka\b', _re.I), 1),
    (_re.compile(r'\bstudio\b', _re.I), 1),
    (_re.compile(r'\b1\s*-?\s*(?:pok|pokój|pokoje|pokoi|комн|комнат|room)\b', _re.I), 1),
    (_re.compile(r'\b2\s*-?\s*(?:pok|pokój|pokoje|pokoi|комн|комнат|room)\b', _re.I), 2),
    (_re.compile(r'\b3\s*-?\s*(?:pok|pokój|pokoje|pokoi|комн|комнат|room)\b', _re.I), 3),
    (_re.compile(r'\b4\s*-?\s*(?:pok|pokój|pokoje|pokoi|комн|комнат|room)\b', _re.I), 4),
    (_re.compile(r'\b5\s*-?\s*(?:pok|pokój|pokoje|pokoi|комн|комнат|room)\b', _re.I), 5),
    # Standalone digit before pokoje/комнат
    (_re.compile(r'\b([1-5])\s+(?:pokoje?|pokoi|комнат[ыа]?|кімнат[иа]?)\b', _re.I), None),
]

_AREA_RE   = _re.compile(r'(\d+(?:[.,]\d+)?)\s*m[²2]', _re.I)
_FLOOR_RE  = _re.compile(r'(?:piętro|floor|этаж|поверх)[^\d]*(\d+)', _re.I)
_FLOOR_RE2 = _re.compile(r'\b(\d+)\s*/\s*\d+\s*(?:piętro|floor|этаж|поверх|p\.)', _re.I)

_FURNISHED_YES = _re.compile(
    r'\b(?:umeblowane|meblowane|furnished|с\s*мебел|меблирован|з\s*меблями|umeblowany)\b', _re.I
)
_FURNISHED_NO = _re.compile(
    r'\b(?:bez\s*mebli|nieumeblowane|unfurnished|без\s*мебел|без\s*меблів)\b', _re.I
)


def normalize_apartment(data: dict) -> dict:
    """
    Auto-fill missing fields (rooms, area, floor, furnished, city)
    by parsing the title. Called before saving to DB.
    Existing non-None values are preserved.
    """
    title    = data.get("title", "") or ""
    district = data.get("district", "") or ""
    text     = title  # parse title only — description not available

    # ── Rooms ─────────────────────────────────────────────────
    if not data.get("rooms"):
        for pattern, value in _ROOM_PATTERNS:
            m = pattern.search(text)
            if m:
                if value is not None:
                    data["rooms"] = value
                else:
                    # Pattern with capture group
                    try:
                        data["rooms"] = int(m.group(1))
                    except Exception:
                        pass
                break

    # ── Area ──────────────────────────────────────────────────
    if not data.get("area"):
        m = _AREA_RE.search(text)
        if m:
            try:
                data["area"] = float(m.group(1).replace(",", "."))
            except Exception:
                pass

    # ── Floor ─────────────────────────────────────────────────
    if not data.get("floor"):
        m = _FLOOR_RE.search(text) or _FLOOR_RE2.search(text)
        if m:
            data["floor"] = m.group(1)

    # ── Furnished ─────────────────────────────────────────────
    if data.get("furnished") is None or data.get("furnished") == 0:
        if _FURNISHED_YES.search(text):
            data["furnished"] = 1
        elif _FURNISHED_NO.search(text):
            data["furnished"] = 0
        # else: leave as 0 (unknown = treat as not furnished)

    # ── City ──────────────────────────────────────────────────
    if not data.get("city"):
        data["city"] = _detect_city(title, district, data.get("source_city", ""))

    return data


def save_apartment(data: dict) -> bool:
    # Normalize before any checks
    data = normalize_apartment(dict(data))

    if not _is_apartment_listing(data.get("title", ""), data.get("price", 0)):
        return False

    target_city = data.get("source_city") or data.get("city", "Warszawa")
    try:
        from validation.geographic import GeographicValidator
        from config import CITY_DISTRICTS
        geo = GeographicValidator(CITY_DISTRICTS).validate(data, target_city)
        if not geo.valid:
            return False
        data["city"] = geo.city or target_city
        if geo.district:
            data["district"] = geo.district
    except Exception:
        city = data.get("city", "Warszawa")
        if city == "Warszawa" and not _is_warsaw(data.get("district", "")):
            return False

    if find_duplicate(data.get("title", ""), data.get("price", 0), data.get("source", "")):
        return False
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, price FROM apartments WHERE link=?", (data["link"],))
    existing = c.fetchone()
    if existing:
        if data.get("price") and existing["price"] != data["price"]:
            c.execute(
                "INSERT INTO price_history (apartment_id, price, recorded_at) VALUES (?,?,?)",
                (existing["id"], data["price"], datetime.now().isoformat())
            )
            c.execute("UPDATE apartments SET price=? WHERE id=?",
                      (data["price"], existing["id"]))
            conn.commit()
        conn.close()
        return False
    c.execute("""
        INSERT INTO apartments
        (title, price, district, city, rooms, area, floor, furnished, link, image, source, created_at)
        VALUES (:title,:price,:district,:city,:rooms,:area,:floor,:furnished,:link,:image,:source,:created_at)
    """, {**data, "city": data.get("city", "Warszawa"), "created_at": datetime.now().isoformat()})
    conn.commit()
    conn.close()
    return True


_FILTER_FALLBACK = [
    (True, True),
    (True, False),
    (False, False),
]


def build_filter_query(
    filters: dict | None = None,
    strict_rooms: bool = True,
    strict_furnished: bool = True,
    vip: bool = False,
    exclude_ids: list | None = None,
    select: str = "SELECT *",
) -> tuple[str, list]:
    """Shared WHERE clause for count and fetch — keeps totals in sync with results."""
    q = f"{select} FROM apartments WHERE reported < 10 AND (duplicate_of IS NULL)"
    p: list = []

    if not vip and VIP_EARLY_ACCESS_MINUTES > 0:
        cutoff = (datetime.now() - timedelta(minutes=VIP_EARLY_ACCESS_MINUTES)).isoformat()
        q += " AND created_at <= ?"
        p.append(cutoff)

    f = filters or {}
    if f.get("district"):
        q += " AND district LIKE ?"
        p.append(f"%{f['district']}%")
    if f.get("price_max"):
        q += " AND price <= ? AND price > 0"
        p.append(f["price_max"])
    if f.get("price_min"):
        q += " AND price >= ?"
        p.append(f["price_min"])
    if f.get("rooms") and strict_rooms:
        q += " AND (rooms = ? OR rooms IS NULL)"
        p.append(f["rooms"])
    if f.get("keyword"):
        q += " AND (title LIKE ? OR district LIKE ?)"
        p.append(f"%{f['keyword']}%")
        p.append(f"%{f['keyword']}%")
    if f.get("today"):
        q += " AND created_at >= ?"
        p.append(f["today"])
    if f.get("furnished") is not None and strict_furnished:
        q += " AND (furnished = ? OR furnished IS NULL)"
        p.append(f["furnished"])
    if f.get("area_min"):
        q += " AND (area >= ? OR area IS NULL)"
        p.append(f["area_min"])
    if f.get("price_per_m_max") and f.get("area_min"):
        q += " AND area > 0 AND (price * 1.0 / area) <= ?"
        p.append(f["price_per_m_max"])
    if f.get("rooms_max"):
        q += " AND (rooms <= ? OR rooms IS NULL)"
        p.append(f["rooms_max"])
    if f.get("floor_min"):
        q += " AND (CAST(floor AS INTEGER) >= ? OR floor IS NULL)"
        p.append(f["floor_min"])
    if f.get("photo_only"):
        q += " AND image IS NOT NULL AND image != ''"
    if f.get("new_only"):
        from datetime import date
        q += " AND created_at >= ?"
        p.append(date.today().isoformat())
    city = f.get("city", "Warszawa")
    radius_km = f.get("search_radius_km")
    try:
        from config import CITIES, city_slug, resolve_search_cities, SEARCH_RADIUS_KM_DEFAULT
        if radius_km is None:
            radius_km = SEARCH_RADIUS_KM_DEFAULT
        search_cities = resolve_search_cities(city, radius_km)
        if len(search_cities) == 1:
            q += " AND city = ?"
            p.append(search_cities[0])
        else:
            placeholders = ",".join("?" * len(search_cities))
            q += f" AND city IN ({placeholders})"
            p.extend(search_cities)
        allowed = set(search_cities)
        for other in CITIES:
            if other in allowed:
                continue
            slug = city_slug(other)
            if slug:
                q += " AND LOWER(link) NOT LIKE ?"
                p.append(f"%/{slug}/%")
    except Exception:
        q += " AND city = ?"
        p.append(city)
    if exclude_ids:
        placeholders = ",".join("?" * len(exclude_ids))
        q += f" AND id NOT IN ({placeholders})"
        p.extend(exclude_ids)
    return q, p


def _resolve_filter_level(
    conn,
    filters: dict | None,
    vip: bool = False,
    exclude_ids: list | None = None,
) -> tuple[bool, bool, int]:
    """Pick the same fallback tier count and fetch both use."""
    c = conn.cursor()
    for strict_r, strict_f in _FILTER_FALLBACK:
        q, p = build_filter_query(
            filters, strict_r, strict_f, vip, exclude_ids, select="SELECT COUNT(*)"
        )
        total = c.execute(q, p).fetchone()[0]
        if total > 0:
            return strict_r, strict_f, total
    return True, True, 0


def get_apartments(
    filters: dict = None,
    offset: int = 0,
    limit: int = 1,
    vip: bool = False,
    exclude_ids: list = None,
) -> list[dict]:
    """
    Fetch apartments. Uses the same filter fallback as count_apartments.
    """
    conn = get_conn()
    strict_r, strict_f, total = _resolve_filter_level(conn, filters, vip, exclude_ids)
    if total == 0:
        conn.close()
        return []

    safe_offset = min(offset, max(0, total - 1))
    q, p = build_filter_query(filters, strict_r, strict_f, vip, exclude_ids)
    f = filters or {}
    primary = f.get("city", "Warszawa")
    try:
        from config import resolve_search_cities
        radius_km = f.get("search_radius_km")
        multi_city = len(resolve_search_cities(primary, radius_km)) > 1
    except Exception:
        multi_city = False
    if multi_city:
        q += " ORDER BY CASE WHEN city = ? THEN 0 ELSE 1 END, created_at DESC LIMIT ? OFFSET ?"
        p += [primary, limit, safe_offset]
    else:
        q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        p += [limit, safe_offset]
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_apartments(filters: dict = None, vip: bool = False, exclude_ids: list = None) -> int:
    """Count apartments — identical fallback logic as get_apartments."""
    conn = get_conn()
    _, _, total = _resolve_filter_level(conn, filters, vip, exclude_ids)
    conn.close()
    return total


def get_latest_apartments(since: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM apartments WHERE created_at > ? ORDER BY created_at DESC",
        (since,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_price_drop(apartment_id: int):
    """Returns price drop info if price decreased."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT price, recorded_at FROM price_history WHERE apartment_id=? ORDER BY id DESC LIMIT 2",
        (apartment_id,)
    ).fetchall()
    conn.close()
    if len(rows) >= 2:
        new_price, old_price = rows[0]["price"], rows[1]["price"]
        if new_price < old_price:
            return {"old": old_price, "new": new_price, "drop": old_price - new_price}
    return None


# ── Users ────────────────────────────────────────────────────

def _gen_ref_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def get_or_create_user(user_id: int) -> dict:
    conn = get_conn()
    c = conn.cursor()
    row = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        ref_code = _gen_ref_code()
        c.execute(
            "INSERT INTO users (user_id, vip, views, ref_code, ref_count, created_at) VALUES (?,0,0,?,0,?)",
            (user_id, ref_code, datetime.now().isoformat())
        )
        conn.commit()
        row = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        return dict(row)

    conn.close()
    return dict(row)


def increment_views(user_id: int):
    conn = get_conn()
    conn.execute("UPDATE users SET views=views+1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def increment_apt_views(apt_id: int):
    """Track how many times an apartment was shown to users."""
    conn = get_conn()
    try:
        conn.execute("UPDATE apartments SET apt_views=COALESCE(apt_views,0)+1 WHERE id=?", (apt_id,))
        conn.commit()
    except Exception:
        pass
    conn.close()


def set_vip(user_id: int, status: int = 1, days: int = 30):
    conn = get_conn()
    vip_until = (datetime.now() + timedelta(days=days)).isoformat() if status else None
    conn.execute("UPDATE users SET vip=?, vip_until=? WHERE user_id=?",
                 (status, vip_until, user_id))
    conn.commit()
    conn.close()


def check_vip_expiry():
    """Call periodically to auto-expire VIP."""
    conn = get_conn()
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE users SET vip=0, vip_until=NULL WHERE vip=1 AND vip_until IS NOT NULL AND vip_until < ?",
        (now,)
    )
    conn.commit()
    conn.close()


def get_all_user_ids() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


def get_all_vip_user_ids() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT user_id FROM users WHERE vip=1").fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


# ── Referrals ────────────────────────────────────────────────

def apply_referral(new_user_id: int, ref_code: str) -> bool:
    """Apply referral code. Returns True if successful."""
    conn = get_conn()
    c = conn.cursor()
    referrer = c.execute("SELECT * FROM users WHERE ref_code=?", (ref_code,)).fetchone()
    if not referrer or referrer["user_id"] == new_user_id:
        conn.close()
        return False
    # Mark new user as referred
    c.execute("UPDATE users SET referred_by=? WHERE user_id=?",
              (referrer["user_id"], new_user_id))
    # Increment referrer count
    c.execute("UPDATE users SET ref_count=ref_count+1 WHERE user_id=?",
              (referrer["user_id"],))
    new_count = c.execute(
        "SELECT ref_count FROM users WHERE user_id=?", (referrer["user_id"],)
    ).fetchone()["ref_count"]
    conn.commit()
    conn.close()

    from config import REFERRAL_REQUIRED
    return new_count % REFERRAL_REQUIRED == 0


def get_ref_stats(user_id: int) -> dict:
    conn = get_conn()
    row = conn.execute(
        "SELECT ref_code, ref_count FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


# ── Favorites ────────────────────────────────────────────────

def add_favorite(user_id: int, apartment_id: int):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO favorites (user_id, apartment_id) VALUES (?,?)",
                     (user_id, apartment_id))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()


def remove_favorite(user_id: int, apartment_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM favorites WHERE user_id=? AND apartment_id=?",
                 (user_id, apartment_id))
    conn.commit()
    conn.close()


def get_favorites(user_id: int) -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT a.* FROM apartments a
        JOIN favorites f ON a.id = f.apartment_id
        WHERE f.user_id=? ORDER BY a.created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Subscriptions ────────────────────────────────────────────

def subscribe_district(user_id: int, district: str):
    conn = get_conn()
    try:
        conn.execute("INSERT INTO subscriptions (user_id, district) VALUES (?,?)",
                     (user_id, district))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()


def unsubscribe_district(user_id: int, district: str):
    conn = get_conn()
    conn.execute("DELETE FROM subscriptions WHERE user_id=? AND district=?",
                 (user_id, district))
    conn.commit()
    conn.close()


def get_user_subscriptions(user_id: int) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT district FROM subscriptions WHERE user_id=?", (user_id,)
    ).fetchall()
    conn.close()
    return [r["district"] for r in rows]


def get_subscribers_for_district(district: str) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT user_id FROM subscriptions WHERE ? LIKE '%' || district || '%' OR district = 'все'",
        (district,)
    ).fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


# ── Smart Alerts ─────────────────────────────────────────────

def get_alert_limit(vip: bool = False) -> int:
    from config import FREE_ALERT_LIMIT
    return FREE_ALERT_LIMIT


def create_alert(
    user_id: int,
    district: str = None,
    price_min: int = None,
    price_max: int = None,
    rooms: int = None,
    city: str = None,
):
    conn = get_conn()
    conn.execute("""
        INSERT INTO alerts (user_id, district, price_min, price_max, rooms, city, active, created_at)
        VALUES (?,?,?,?,?,?,1,?)
    """, (user_id, district, price_min, price_max, rooms, city, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_user_alerts(user_id: int) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM alerts WHERE user_id=? AND active=1", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_alert(alert_id: int, user_id: int):
    conn = get_conn()
    conn.execute("UPDATE alerts SET active=0 WHERE id=? AND user_id=?",
                 (alert_id, user_id))
    conn.commit()
    conn.close()


def match_alerts(apartment: dict) -> list:
    """Returns user_ids whose alerts match this apartment."""
    conn = get_conn()
    query = "SELECT user_id FROM alerts WHERE active=1"
    params = []
    apt_city = apartment.get("city")
    if apt_city:
        query += " AND (city IS NULL OR city = ?)"
        params.append(apt_city)
    if apartment.get("district"):
        query += " AND (district IS NULL OR district = '' OR district = 'все' OR ? LIKE '%' || district || '%')"
        params.append(apartment["district"])
    if apartment.get("price"):
        query += " AND (price_min IS NULL OR price_min <= ?)"
        params.append(apartment["price"])
        query += " AND (price_max IS NULL OR price_max >= ?)"
        params.append(apartment["price"])
    if apartment.get("rooms"):
        query += " AND (rooms IS NULL OR rooms = ?)"
        params.append(apartment["rooms"])
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


# ── Stats ────────────────────────────────────────────────────

def log_parse(source: str, count: int):
    conn = get_conn()
    conn.execute("INSERT INTO parse_log (source, count, logged_at) VALUES (?,?,?)",
                 (source, count, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def log_validation_reject(reason: str, target_city: str, link: str = "") -> None:
    """Track rejected listings for admin /stats."""
    try:
        conn = get_conn()
        conn.execute(
            """CREATE TABLE IF NOT EXISTS validation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reason TEXT NOT NULL,
                target_city TEXT,
                link TEXT,
                logged_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            "INSERT INTO validation_log (reason, target_city, link, logged_at) VALUES (?,?,?,?)",
            (reason, target_city, (link or "")[:300], datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_admin_city_stats() -> dict:
    """Per-city inventory, parse times, validation rejects — for /stats."""
    from config import CITIES
    from validation.geographic import city_from_link

    conn = get_conn()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS validation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reason TEXT NOT NULL,
            target_city TEXT,
            link TEXT,
            logged_at TEXT NOT NULL
        )"""
    )
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    cities = []
    for city_key, info in CITIES.items():
        count = conn.execute(
            """
            SELECT COUNT(*) FROM apartments
            WHERE city = ? AND duplicate_of IS NULL AND reported < 10
            """,
            (city_key,),
        ).fetchone()[0]
        last_parse = conn.execute(
            """
            SELECT MAX(logged_at) FROM parse_log
            WHERE source LIKE ? OR source LIKE ?
            """,
            (f"%/{city_key}", f"%/{city_key}/%"),
        ).fetchone()[0]
        cities.append({
            "key": city_key,
            "label": info.get("label", city_key),
            "count": count,
            "last_parse": (last_parse or "")[:16] or "—",
        })

    rejects = conn.execute(
        """
        SELECT reason, target_city, COUNT(*) AS cnt FROM validation_log
        WHERE logged_at >= ? GROUP BY reason, target_city
        ORDER BY cnt DESC LIMIT 20
        """,
        (cutoff,),
    ).fetchall()

    mislabeled = 0
    sample = conn.execute(
        "SELECT link, city FROM apartments WHERE link IS NOT NULL AND link != '' LIMIT 3000"
    ).fetchall()
    for row in sample:
        detected = city_from_link(row["link"])
        if detected and detected != (row["city"] or ""):
            mislabeled += 1

    total = conn.execute(
        "SELECT COUNT(*) FROM apartments WHERE duplicate_of IS NULL AND reported < 10"
    ).fetchone()[0]
    conn.close()
    return {
        "cities": cities,
        "rejects": [dict(r) for r in rejects],
        "mislabeled_sample": mislabeled,
        "total": total,
    }


# ── Language ─────────────────────────────────────────────────

def set_user_lang(user_id: int, lang: str):
    conn = get_conn()
    conn.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
    conn.commit()
    conn.close()


def get_user_lang(user_id: int) -> str:
    conn = get_conn()
    row = conn.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row["lang"] if row and row["lang"] else "ru"


def set_user_city(user_id: int, city: str):
    """Persist user's selected city to DB so it survives /start."""
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET city=? WHERE user_id=?", (city, user_id))
        conn.commit()
    except Exception:
        pass
    conn.close()


def get_user_city_db(user_id: int) -> str:
    """Get user's saved city from DB."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT city FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        return (row["city"] or "Warszawa") if row else "Warszawa"
    except Exception:
        conn.close()
        return "Warszawa"


# ── Ratings ──────────────────────────────────────────────────

def rate_apartment(user_id: int, apartment_id: int, rating: int):
    """rating: 1 = like, -1 = dislike"""
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO ratings (user_id, apartment_id, rating) VALUES (?,?,?)",
        (user_id, apartment_id, rating)
    )
    conn.execute("""
        UPDATE apartments SET score = (
            SELECT COALESCE(SUM(rating), 0) FROM ratings WHERE apartment_id=?
        ) WHERE id=?
    """, (apartment_id, apartment_id))
    conn.commit()
    conn.close()


# ── Deduplication ─────────────────────────────────────────────

def find_duplicate(title: str, price: int, source: str = "") -> bool:
    """
    Cross-source deduplication: same title+price from ANY source = duplicate.
    Improved: normalize title more aggressively to catch duplicates.
    """
    if not title or not price:
        return False
    conn = get_conn()
    # Normalize: lowercase, strip extra spaces, remove special chars, take first 40 chars
    normalized = " ".join(re.sub(r'[^\w\s]', '', title.lower()).split())[:40]
    
    # Check across ALL sources with fuzzy price match (±50 zł)
    row = conn.execute(
        """SELECT id FROM apartments 
           WHERE LOWER(REPLACE(REPLACE(title, '-', ' '), '|', ' ')) LIKE ? 
           AND ABS(price - ?) <= 50 
           AND duplicate_of IS NULL
           LIMIT 1""",
        (f"%{normalized[:30]}%", price)
    ).fetchone()
    conn.close()
    return row is not None


def get_stats() -> dict:
    conn = get_conn()
    from datetime import date
    today = date.today().isoformat()
    yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()

    total_apts = conn.execute("SELECT COUNT(*) FROM apartments").fetchone()[0]
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    vip_users = conn.execute("SELECT COUNT(*) FROM users WHERE vip=1").fetchone()[0]
    total_favs = conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]
    new_today = conn.execute(
        "SELECT COUNT(*) FROM apartments WHERE created_at >= ?", (today,)
    ).fetchone()[0]
    new_users_today = conn.execute(
        "SELECT COUNT(*) FROM users WHERE created_at >= ?", (today,)
    ).fetchone()[0]
    active_today = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM user_activity WHERE date = ?", (today,)
    ).fetchone()[0]
    active_yesterday = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM user_activity WHERE date = ?", (yesterday,)
    ).fetchone()[0]
    last_parse = conn.execute(
        "SELECT logged_at FROM parse_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return {
        "apartments": total_apts,
        "users": total_users,
        "vip": vip_users,
        "favorites": total_favs,
        "new_today": new_today,
        "new_users_today": new_users_today,
        "active_today": active_today,
        "active_yesterday": active_yesterday,
        "last_parse": last_parse["logged_at"] if last_parse else "никогда",
    }


# ── Auto VIP conditions ───────────────────────────────────────

def check_auto_vip_conditions(user_id: int) -> str | None:
    """Legacy hook — public VIP disabled; no auto grants."""
    return None


def get_leaderboard() -> list:
    """Top users by referral count."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT user_id, ref_count FROM users
        WHERE ref_count > 0 ORDER BY ref_count DESC LIMIT 10
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_digest() -> dict:
    """Stats for daily digest message."""
    from datetime import date
    today = date.today().isoformat()
    conn = get_conn()
    new_today = conn.execute(
        "SELECT COUNT(*) FROM apartments WHERE created_at >= ?", (today,)
    ).fetchone()[0]
    cheapest = conn.execute(
        "SELECT * FROM apartments WHERE price > 0 AND created_at >= ? ORDER BY price ASC LIMIT 1",
        (today,)
    ).fetchone()
    avg_price = conn.execute(
        "SELECT AVG(price) FROM apartments WHERE price > 0 AND created_at >= ?", (today,)
    ).fetchone()[0]
    conn.close()
    return {
        "new_today": new_today,
        "cheapest": dict(cheapest) if cheapest else None,
        "avg_price": int(avg_price) if avg_price else 0,
    }


def get_top_new_apartments(limit: int = 5) -> list:
    """Top new apartments today sorted by price (cheapest first, with photo preferred)."""
    from datetime import date
    today = date.today().isoformat()
    conn = get_conn()
    # Prefer apartments with photos
    rows = conn.execute("""
        SELECT * FROM apartments
        WHERE price > 0 AND price <= 4000 AND created_at >= ?
        ORDER BY (image IS NOT NULL AND image != '') DESC, price ASC
        LIMIT ?
    """, (today, limit)).fetchall()
    if not rows:
        rows = conn.execute("""
            SELECT * FROM apartments WHERE price > 0 AND created_at >= ?
            ORDER BY price ASC LIMIT ?
        """, (today, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_new_since(since_iso: str) -> int:
    """Count apartments added since a given ISO datetime."""
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM apartments WHERE created_at > ?", (since_iso,)
    ).fetchone()[0]
    conn.close()
    return count


def update_last_visit(user_id: int):
    """Store user's last visit time."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET last_visit=? WHERE user_id=?",
            (datetime.now().isoformat(), user_id)
        )
        conn.commit()
    except Exception:
        pass
    conn.close()


def get_last_visit(user_id: int) -> str | None:
    """Get user's last visit time."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT last_visit FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        conn.close()
        return row["last_visit"] if row and row.get("last_visit") else None
    except Exception:
        conn.close()
        return None


def get_user_streak(user_id: int) -> int:
    """How many days in a row user has been active (viewed apartments)."""
    # Simplified: return views count as activity proxy
    conn = get_conn()
    row = conn.execute("SELECT views FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row["views"] if row else 0


def get_hot_apartments(limit: int = 5, city: str | None = None, radius_km: int | None = None) -> list:
    """Apartments with most likes in last 24h, optionally scoped to city + radius."""
    conn = get_conn()
    from datetime import timedelta
    since = (datetime.now() - timedelta(hours=24)).isoformat()
    city_sql = ""
    city_params: list = []
    if city:
        try:
            from config import resolve_search_cities, SEARCH_RADIUS_KM_DEFAULT
            if radius_km is None:
                radius_km = SEARCH_RADIUS_KM_DEFAULT
            cities = resolve_search_cities(city, radius_km)
            ph = ",".join("?" * len(cities))
            city_sql = f" AND a.city IN ({ph})"
            city_params = list(cities)
        except Exception:
            city_sql = " AND a.city = ?"
            city_params = [city]
    rows = conn.execute(f"""
        SELECT a.*, COALESCE(SUM(r.rating), 0) as hot_score
        FROM apartments a
        LEFT JOIN ratings r ON a.id = r.apartment_id
        WHERE a.created_at >= ?{city_sql}
        GROUP BY a.id
        HAVING hot_score > 0
        ORDER BY hot_score DESC
        LIMIT ?
    """, (since, *city_params, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_price_drops_today(limit: int = 5, city: str | None = None, radius_km: int | None = None) -> list:
    """Apartments where price dropped. Returns only apartments still in DB with valid links."""
    conn = get_conn()
    from datetime import timedelta
    since = (datetime.now() - timedelta(hours=48)).isoformat()
    city_sql = ""
    city_params: list = []
    if city:
        try:
            from config import resolve_search_cities, SEARCH_RADIUS_KM_DEFAULT
            if radius_km is None:
                radius_km = SEARCH_RADIUS_KM_DEFAULT
            cities = resolve_search_cities(city, radius_km)
            ph = ",".join("?" * len(cities))
            city_sql = f" AND a.city IN ({ph})"
            city_params = list(cities)
        except Exception:
            city_sql = " AND a.city = ?"
            city_params = [city]
    rows = conn.execute(f"""
        SELECT DISTINCT a.*,
               ph.price as new_price,
               (SELECT price FROM price_history
                WHERE apartment_id=a.id ORDER BY id ASC LIMIT 1) as old_price
        FROM apartments a
        JOIN price_history ph ON a.id = ph.apartment_id
        WHERE ph.recorded_at >= ?
          AND a.price >= 500 AND a.price <= 25000{city_sql}
        GROUP BY a.id
        HAVING old_price IS NOT NULL AND old_price > a.price
        ORDER BY (old_price - a.price) DESC
        LIMIT ?
    """, (since, *city_params, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def record_user_activity(user_id: int):
    """Record today's activity for streak tracking."""
    conn = get_conn()
    today = datetime.now().date().isoformat()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO user_activity (user_id, date) VALUES (?,?)",
            (user_id, today)
        )
        conn.commit()
    except Exception:
        pass
    conn.close()


def get_user_streak_days(user_id: int) -> int:
    """Count consecutive days user was active."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT date FROM user_activity WHERE user_id=? ORDER BY date DESC LIMIT 30",
            (user_id,)
        ).fetchall()
    except Exception:
        conn.close()
        return 0
    conn.close()
    if not rows:
        return 0
    from datetime import date, timedelta
    streak = 0
    check_date = date.today()
    for row in rows:
        try:
            row_date = date.fromisoformat(row["date"])
            if row_date == check_date or row_date == check_date - timedelta(days=1):
                streak += 1
                check_date = row_date - timedelta(days=1)
            else:
                break
        except Exception:
            break
    return streak


# ── Roles & Moderation ────────────────────────────────────────

def set_user_role(user_id: int, role: str):
    """role: 'user', 'moderator', 'admin'"""
    conn = get_conn()
    conn.execute("UPDATE users SET role=? WHERE user_id=?", (role, user_id))
    conn.commit()
    conn.close()
    # Moderators get free VIP
    if role == "moderator":
        set_vip(user_id, 1, days=36500)  # ~100 years = permanent


def get_user_role(user_id: int) -> str:
    from config import ADMIN_IDS, MODERATOR_IDS
    if user_id in ADMIN_IDS:
        return "admin"
    if user_id in MODERATOR_IDS:
        return "moderator"
    conn = get_conn()
    row = conn.execute("SELECT role FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if row and row["role"] in ("moderator", "admin"):
        return row["role"]
    return "user"


def is_moderator(user_id: int) -> bool:
    return get_user_role(user_id) in ("moderator", "admin")


def report_apartment(user_id: int, apartment_id: int, reason: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO reports (user_id, apartment_id, reason, created_at) VALUES (?,?,?,?)",
        (user_id, apartment_id, reason, datetime.now().isoformat())
    )
    conn.execute("UPDATE apartments SET reported=reported+1 WHERE id=?", (apartment_id,))
    conn.commit()
    conn.close()


def get_pending_reports(limit: int = 20) -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT r.*, a.title, a.link, a.price, a.district
        FROM reports r JOIN apartments a ON r.apartment_id = a.id
        ORDER BY r.id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def verify_apartment(apartment_id: int, mod_id: int = 0):
    conn = get_conn()
    conn.execute("UPDATE apartments SET verified=1 WHERE id=?", (apartment_id,))
    conn.execute(
        "INSERT INTO mod_log (mod_id, action, target_id, created_at) VALUES (?,?,?,?)",
        (mod_id, "verify", apartment_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def delete_apartment(apartment_id: int, mod_id: int = 0, note: str = ""):
    conn = get_conn()
    conn.execute("DELETE FROM apartments WHERE id=?", (apartment_id,))
    conn.execute(
        "INSERT INTO mod_log (mod_id, action, target_id, note, created_at) VALUES (?,?,?,?,?)",
        (mod_id, "delete", apartment_id, note, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_mod_stats(mod_id: int) -> dict:
    conn = get_conn()
    verified = conn.execute(
        "SELECT COUNT(*) FROM mod_log WHERE mod_id=? AND action='verify'", (mod_id,)
    ).fetchone()[0]
    deleted = conn.execute(
        "SELECT COUNT(*) FROM mod_log WHERE mod_id=? AND action='delete'", (mod_id,)
    ).fetchone()[0]
    conn.close()
    return {"verified": verified, "deleted": deleted}


def get_reported_apartments(limit: int = 10) -> list:
    """Apartments with most reports."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM apartments WHERE reported > 0
        ORDER BY reported DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── New features ──────────────────────────────────────────────

def get_price_stats() -> dict:
    """Price analytics: avg, min, max by district. Filters junk prices."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT district,
               COUNT(*) as cnt,
               AVG(price) as avg,
               MIN(price) as min,
               MAX(price) as max
        FROM apartments
        WHERE price >= 500 AND price <= 25000 AND district != '' AND district IS NOT NULL
        GROUP BY district
        HAVING cnt >= 2
        ORDER BY avg ASC
    """).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM apartments WHERE price >= 500 AND price <= 25000"
    ).fetchone()[0]
    overall_avg = conn.execute(
        "SELECT AVG(price) FROM apartments WHERE price >= 500 AND price <= 25000"
    ).fetchone()[0]
    conn.close()
    return {
        "by_district": [dict(r) for r in rows],
        "total": total,
        "overall_avg": int(overall_avg) if overall_avg else 0,
    }


def get_new_today_count() -> int:
    from datetime import date
    today = date.today().isoformat()
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM apartments WHERE created_at >= ?", (today,)
    ).fetchone()[0]
    conn.close()
    return count


def _migrate_city_field():
    """One-time: detect and set city for all existing apartments without city."""
    try:
        conn = get_conn()
        # Get all apartments without city
        rows = conn.execute(
            "SELECT id, title, district FROM apartments WHERE city IS NULL OR city = ''"
        ).fetchall()
        
        updated = 0
        for row in rows:
            apt_id = row["id"]
            title = row["title"] or ""
            district = row["district"] or ""
            # Detect city from title and district
            city = _detect_city(title, district, "")
            conn.execute("UPDATE apartments SET city=? WHERE id=?", (city, apt_id))
            updated += 1
        
        conn.commit()
        conn.close()
        if updated > 0:
            print(f"[Migration] Detected and set city for {updated} existing apartments")
    except Exception as e:
        print(f"[Migration] city field: {e}")


def _city_from_listing_link(link: str) -> str | None:
    """Detect city from listing URL (all major sources)."""
    from validation.geographic import city_from_link
    return city_from_link(link)


def sync_apartments_city_from_links() -> int:
    """Fix listings saved with wrong city (e.g. all Warszawa)."""
    from config import CITIES
    conn = get_conn()
    updated = 0
    rows = conn.execute(
        "SELECT id, link, city, source_city FROM apartments"
    ).fetchall()
    for row in rows:
        detected = _city_from_listing_link(row["link"] or "")
        if not detected:
            continue
        cur_city = row["city"] or ""
        if cur_city != detected:
            conn.execute(
                "UPDATE apartments SET city=?, source_city=? WHERE id=?",
                (detected, detected, row["id"]),
            )
            updated += 1
    conn.commit()
    conn.close()
    if updated:
        print(f"[Migration] Fixed city for {updated} apartments from URLs")
    return updated


def get_daily_listings_from_db(city, limit: int = 15) -> list[dict]:
    """Short-term listings already in DB for one city or a list of cities."""
    if isinstance(city, str):
        cities = [city]
    else:
        cities = list(city) or ["Warszawa"]
    placeholders = ",".join("?" * len(cities))
    conn = get_conn()
    rows = conn.execute(
        f"""
        SELECT title, price, district, link, image, source, city
        FROM apartments
        WHERE city IN ({placeholders}) AND duplicate_of IS NULL AND reported < 10
          AND price BETWEEN 50 AND 5000
          AND (
            LOWER(title) LIKE '%doby%' OR LOWER(title) LIKE '%nocleg%'
            OR LOWER(title) LIKE '%krótko%' OR LOWER(title) LIKE '%krótkotermin%'
            OR LOWER(title) LIKE '%weekend%' OR LOWER(title) LIKE '%pobyt%'
            OR LOWER(title) LIKE '%na doby%' OR LOWER(title) LIKE '%short%'
          )
        ORDER BY price ASC LIMIT ?
        """,
        (*cities, limit),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        apt_city = r["city"] or cities[0]
        result.append({
            "title": r["title"],
            "price_per_night": r["price"],
            "district": r["district"] or apt_city,
            "city": apt_city,
            "link": r["link"],
            "image": r["image"] or "",
            "source": r["source"] or "DB",
            "rating": None,
            "reviews": None,
        })
    return result


def _backfill_city_from_source():
    """Set city from source_city for legacy rows."""
    try:
        conn = get_conn()
        cur = conn.execute(
            "UPDATE apartments SET city = source_city "
            "WHERE (city IS NULL OR city = '') AND source_city IS NOT NULL AND source_city != ''"
        )
        conn.commit()
        if cur.rowcount:
            print(f"[Migration] Backfilled city from source_city for {cur.rowcount} rows")
        conn.close()
    except Exception as e:
        print(f"[Migration] source_city backfill: {e}")


def cleanup_junk_listings():
    """Remove junk from DB on startup — never delete valid multi-city rows."""
    conn = get_conn()
    junk_keywords = [
        "osuszacz", "osuszanie", "pochłaniacz",
        "godz/", "/doby",
    ]
    for kw in junk_keywords:
        conn.execute(
            "DELETE FROM apartments WHERE LOWER(title) LIKE ?",
            (f"%{kw}%",),
        )
    # Short-term in title — remove from long-term pool only
    for kw in ("na doby", "noclegi", "krótkoterminow"):
        conn.execute(
            "DELETE FROM apartments WHERE LOWER(title) LIKE ? AND (city IS NULL OR city = 'Warszawa')",
            (f"%{kw}%",),
        )
    conn.execute("DELETE FROM apartments WHERE price > 0 AND price < 200")
    conn.execute("DELETE FROM apartments WHERE price > 50000")
    conn.commit()
    conn.close()


def search_by_keyword(keyword: str, limit: int = 20) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM apartments WHERE title LIKE ? OR district LIKE ? ORDER BY created_at DESC LIMIT ?",
        (f"%{keyword}%", f"%{keyword}%", limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_count() -> int:
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return count


def get_apartment_by_id(apt_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM apartments WHERE id=?", (apt_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_user_note(user_id: int, apt_id: int, note: str):
    """User can add a personal note to an apartment."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO user_notes (user_id, apt_id, note, created_at) VALUES (?,?,?,?)",
            (user_id, apt_id, note[:500], datetime.now().isoformat())
        )
        conn.commit()
    except Exception:
        pass
    conn.close()


def get_user_notes(user_id: int) -> list:
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT n.note, n.apt_id, n.created_at, a.title, a.price, a.link
            FROM user_notes n JOIN apartments a ON n.apt_id = a.id
            WHERE n.user_id = ? ORDER BY n.created_at DESC
        """, (user_id,)).fetchall()
    except Exception:
        rows = []
    conn.close()
    return [dict(r) for r in rows]


def get_similar_apartments(apt_id: int, limit: int = 3) -> list:
    """Find similar apartments by price range and district."""
    conn = get_conn()
    apt = conn.execute("SELECT * FROM apartments WHERE id=?", (apt_id,)).fetchone()
    if not apt:
        conn.close()
        return []
    price = apt["price"] or 0
    district = apt["district"] or ""
    rows = conn.execute("""
        SELECT * FROM apartments
        WHERE id != ? AND price BETWEEN ? AND ? AND district LIKE ?
        ORDER BY created_at DESC LIMIT ?
    """, (apt_id, price * 0.8, price * 1.2, f"%{district[:10]}%", limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_cheapest_apartments(
    limit: int = 5,
    price_max: int = 2500,
    city: str | None = None,
    radius_km: int | None = None,
) -> list:
    """Cheapest apartments for a city (and radius), filtering junk listings."""
    junk_sql = " AND ".join([
        "LOWER(title) NOT LIKE '%osuszacz%'",
        "LOWER(title) NOT LIKE '%garaż%'",
        "LOWER(title) NOT LIKE '%parking%'",
        "LOWER(title) NOT LIKE '%na doby%'",
        "LOWER(title) NOT LIKE '%noclegi%'",
        "LOWER(title) NOT LIKE '%osuszanie%'",
        "LOWER(title) NOT LIKE '%pochłaniacz%'",
        "LOWER(title) NOT LIKE '%klimatyzator%'",
        "LOWER(title) NOT LIKE '%sprzedaż%'",
        "LOWER(title) NOT LIKE '%na sprzedaż%'",
    ])
    # Explicitly block known non-Warsaw districts/cities
    non_warsaw_sql = (
        "LOWER(district) NOT LIKE '%widzew%' AND "
        "LOWER(district) NOT LIKE '%górna%' AND LOWER(district) NOT LIKE '%gorna%' AND "
        "LOWER(district) NOT LIKE '%bałuty%' AND LOWER(district) NOT LIKE '%baluty%' AND "
        "LOWER(district) NOT LIKE '%polesie%' AND "
        "LOWER(district) NOT LIKE '%retkinia%' AND "
        "LOWER(district) NOT LIKE '%łódź%' AND LOWER(district) NOT LIKE '%lodz%' AND "
        "LOWER(district) NOT LIKE '%gdańsk%' AND LOWER(district) NOT LIKE '%gdansk%' AND "
        "LOWER(district) NOT LIKE '%kraków%' AND LOWER(district) NOT LIKE '%krakow%' AND "
        "LOWER(district) NOT LIKE '%wrocław%' AND LOWER(district) NOT LIKE '%wroclaw%' AND "
        "LOWER(district) NOT LIKE '%poznań%' AND LOWER(district) NOT LIKE '%poznan%' AND "
        "LOWER(district) NOT LIKE '%katowice%' AND "
        "LOWER(district) NOT LIKE '%lublin%' AND "
        "LOWER(district) NOT LIKE '%szczecin%' AND "
        "LOWER(district) NOT LIKE '%bydgoszcz%' AND "
        "LOWER(district) NOT LIKE '%białystok%' AND LOWER(district) NOT LIKE '%bialystok%'"
    )
    # Warsaw districts/keywords — exclude listings clearly from other cities
    warsaw_sql = (
        "("
        "district IS NULL OR district = '' OR "
        "LOWER(district) LIKE '%warszawa%' OR "
        "LOWER(district) LIKE '%mokotów%' OR LOWER(district) LIKE '%mokotow%' OR "
        "LOWER(district) LIKE '%ursynów%' OR LOWER(district) LIKE '%ursynow%' OR "
        "LOWER(district) LIKE '%wilanów%' OR LOWER(district) LIKE '%wilanow%' OR "
        "LOWER(district) LIKE '%wola%' OR "
        "LOWER(district) LIKE '%śródmieście%' OR LOWER(district) LIKE '%srodmiescie%' OR "
        "LOWER(district) LIKE '%praga%' OR "
        "LOWER(district) LIKE '%żoliborz%' OR LOWER(district) LIKE '%zoliborz%' OR "
        "LOWER(district) LIKE '%bielany%' OR "
        "LOWER(district) LIKE '%bemowo%' OR "
        "LOWER(district) LIKE '%ochota%' OR "
        "LOWER(district) LIKE '%targówek%' OR LOWER(district) LIKE '%targowek%' OR "
        "LOWER(district) LIKE '%białołęka%' OR LOWER(district) LIKE '%bialoleka%' OR "
        "LOWER(district) LIKE '%ursus%' OR "
        "LOWER(district) LIKE '%włochy%' OR LOWER(district) LIKE '%wlochy%' OR "
        "LOWER(district) LIKE '%wawer%' OR "
        "LOWER(district) LIKE '%rembertów%' OR LOWER(district) LIKE '%rembertow%' OR "
        "LOWER(district) LIKE '%wesoła%' OR LOWER(district) LIKE '%wesola%' OR "
        "LOWER(district) LIKE '%kabaty%' OR LOWER(district) LIKE '%natolin%' OR "
        "LOWER(district) LIKE '%służew%' OR LOWER(district) LIKE '%sluzew%' OR "
        "LOWER(district) LIKE '%sadyba%'"
        ")"
    )
    conn = get_conn()
    if city:
        try:
            from config import resolve_search_cities, SEARCH_RADIUS_KM_DEFAULT
            if radius_km is None:
                radius_km = SEARCH_RADIUS_KM_DEFAULT
            cities = resolve_search_cities(city, radius_km)
            ph = ",".join("?" * len(cities))
            rows = conn.execute(f"""
                SELECT * FROM apartments
                WHERE city IN ({ph}) AND price > 300 AND price <= ?
                  AND reported < 10 AND duplicate_of IS NULL AND {junk_sql}
                ORDER BY CASE WHEN city = ? THEN 0 ELSE 1 END, price ASC LIMIT ?
            """, (*cities, price_max, city, limit)).fetchall()
        except Exception:
            rows = []
    else:
        rows = conn.execute(f"""
            SELECT * FROM apartments
            WHERE price > 300 AND price <= ? AND reported < 10
              AND {junk_sql} AND {warsaw_sql} AND {non_warsaw_sql}
            ORDER BY price ASC LIMIT ?
        """, (price_max, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Seen apartments ───────────────────────────────────────────

def mark_seen(user_id: int, apt_id: int):
    """Mark apartment as already seen by user."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO user_seen (user_id, apt_id, seen_at) VALUES (?,?,?)",
            (user_id, apt_id, datetime.now().isoformat())
        )
        conn.commit()
    except Exception:
        pass
    conn.close()


def get_seen_ids(user_id: int) -> list:
    """Get list of apartment IDs already seen by user."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT apt_id FROM user_seen WHERE user_id=?", (user_id,)
        ).fetchall()
    except Exception:
        rows = []
    conn.close()
    return [r["apt_id"] for r in rows]


def get_user_hide_seen(user_id: int) -> bool:
    """True = hide already viewed listings from search."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT hide_seen FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if row is not None and row["hide_seen"] is not None:
            return bool(row["hide_seen"])
    except Exception:
        pass
    finally:
        conn.close()
    return True


def get_user_search_radius(user_id: int) -> int:
    """0 = city only; default 100 km."""
    try:
        from config import SEARCH_RADIUS_KM_DEFAULT
        conn = get_conn()
        row = conn.execute(
            "SELECT search_radius_km FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        conn.close()
        if row is not None and row["search_radius_km"] is not None:
            return int(row["search_radius_km"])
    except Exception:
        pass
    try:
        from config import SEARCH_RADIUS_KM_DEFAULT
        return SEARCH_RADIUS_KM_DEFAULT
    except Exception:
        return 100


def set_user_search_radius(user_id: int, radius_km: int) -> None:
    get_or_create_user(user_id)
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET search_radius_km=? WHERE user_id=?",
            (max(0, int(radius_km)), user_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_user_hide_seen(user_id: int, hide: bool) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET hide_seen=? WHERE user_id=?",
            (1 if hide else 0, user_id),
        )
        conn.commit()
    except Exception:
        pass
    conn.close()


def hide_apartment(user_id: int, apt_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO hidden_apartments (user_id, apt_id, hidden_at) VALUES (?,?,?)",
            (user_id, apt_id, datetime.now().isoformat()),
        )
        conn.commit()
    except Exception:
        pass
    conn.close()


def get_hidden_ids(user_id: int) -> list:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT apt_id FROM hidden_apartments WHERE user_id=?", (user_id,)
        ).fetchall()
    except Exception:
        rows = []
    conn.close()
    return [r["apt_id"] for r in rows]


def get_search_exclude_ids(user_id: int, hide_seen: bool | None = None) -> list | None:
    """IDs to exclude from search: hidden always; seen if hide_seen enabled."""
    if hide_seen is None:
        hide_seen = get_user_hide_seen(user_id)
    ids: list[int] = list(get_hidden_ids(user_id))
    if hide_seen:
        ids.extend(get_seen_ids(user_id))
    if not ids:
        return None
    return list(dict.fromkeys(ids))


# ── Conversion tracking ───────────────────────────────────────

def record_conversion(user_id: int, apt_id: int = None, source: str = ""):
    """User found an apartment — record conversion."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO conversions (user_id, apt_id, source, created_at) VALUES (?,?,?,?)",
            (user_id, apt_id, source, datetime.now().isoformat())
        )
        conn.commit()
    except Exception:
        pass
    conn.close()


def get_conversion_stats() -> dict:
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM conversions").fetchone()[0]
    today = datetime.now().date().isoformat()
    today_count = conn.execute(
        "SELECT COUNT(*) FROM conversions WHERE created_at >= ?", (today,)
    ).fetchone()[0]
    by_source = conn.execute("""
        SELECT a.source, COUNT(*) as cnt
        FROM conversions c LEFT JOIN apartments a ON c.apt_id = a.id
        GROUP BY a.source ORDER BY cnt DESC
    """).fetchall()
    conn.close()
    return {
        "total": total,
        "today": today_count,
        "by_source": [dict(r) for r in by_source],
    }


# ── Stale listings ────────────────────────────────────────────

def get_apt_age_days(apt: dict) -> int:
    """Return how many days ago apartment was added."""
    try:
        created = apt.get("created_at", "")
        if not created:
            return 0
        return (datetime.now() - datetime.fromisoformat(created)).days
    except Exception:
        return 0


def is_stale(apt: dict, days: int = 7) -> bool:
    """Return True if apartment is older than N days."""
    return get_apt_age_days(apt) >= days


def get_stale_count() -> int:
    """Count apartments older than 7 days still in DB."""
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM apartments WHERE created_at < ?", (cutoff,)
    ).fetchone()[0]
    conn.close()
    return count


def block_apartment(apt_id: int, reason: str = "scam"):
    """Mark apartment as blocked (scam/fraud report)."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE apartments SET reported=999, score=-100 WHERE id=?", (apt_id,)
        )
        conn.execute(
            "INSERT INTO reports (user_id, apartment_id, reason, created_at) VALUES (0,?,?,?)",
            (apt_id, f"BLOCKED:{reason}", datetime.now().isoformat())
        )
        conn.commit()
    except Exception:
        pass
    conn.close()


def get_apt_views_today(apt_id: int) -> int:
    """Get how many times apartment was viewed today."""
    conn = get_conn()
    today = datetime.now().date().isoformat()
    try:
        row = conn.execute(
            "SELECT apt_views FROM apartments WHERE id=?", (apt_id,)
        ).fetchone()
        conn.close()
        return row["apt_views"] if row else 0
    except Exception:
        conn.close()
        return 0


def get_morning_push_apts(limit: int = 3) -> list:
    """Top N cheapest new apartments added in last 24h for morning push."""
    since = (datetime.now() - timedelta(hours=24)).isoformat()
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM apartments
        WHERE price > 0 AND price <= 5000
          AND created_at >= ?
          AND reported < 3
        ORDER BY price ASC
        LIMIT ?
    """, (since, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Price fairness evaluation ─────────────────────────────────

def get_district_avg_price(district: str, rooms: int = None) -> dict:
    """Get avg/min/max price for a district (optionally filtered by rooms)."""
    conn = get_conn()
    base = "SELECT AVG(price), MIN(price), MAX(price), COUNT(*) FROM apartments WHERE price >= 500 AND price <= 25000"
    params = []
    if district and district.lower() not in ("warszawa", ""):
        base += " AND district LIKE ?"
        params.append(f"%{district}%")
    if rooms:
        base += " AND rooms = ?"
        params.append(rooms)
    row = conn.execute(base, params).fetchone()
    conn.close()
    if not row or not row[0]:
        return {}
    return {
        "avg": int(row[0]),
        "min": int(row[1]),
        "max": int(row[2]),
        "count": row[3],
    }


def evaluate_price(price: int, district: str, rooms: int = None) -> dict:
    """
    Compare apartment price to district average.
    Returns: verdict (cheap/fair/expensive/overpriced), diff_pct, avg_price
    """
    stats = get_district_avg_price(district, rooms)
    if not stats or stats["count"] < 3:
        # Fallback: use overall Warsaw stats
        stats = get_district_avg_price("", rooms)
    if not stats or not stats.get("avg"):
        return {"verdict": "unknown", "diff_pct": 0, "avg": 0}

    avg = stats["avg"]
    diff_pct = round((price - avg) / avg * 100)

    if diff_pct <= -20:
        verdict = "cheap"       # 🟢 Очень дёшево
    elif diff_pct <= -5:
        verdict = "below_avg"   # 🟡 Ниже среднего
    elif diff_pct <= 10:
        verdict = "fair"        # ✅ Справедливая цена
    elif diff_pct <= 30:
        verdict = "above_avg"   # 🟠 Выше среднего
    else:
        verdict = "overpriced"  # 🔴 Завышена

    return {
        "verdict": verdict,
        "diff_pct": diff_pct,
        "avg": avg,
        "count": stats["count"],
    }


# ── NLP filter parsing ────────────────────────────────────────

def parse_natural_query(text: str) -> dict:
    """
    Parse natural language query into filters.
    Examples:
      "2 комнаты Мокотув до 3000" → {rooms:2, district:"Mokotów", price_max:3000}
      "однушка Воля 2500 zł"      → {rooms:1, district:"Wola", price_max:2500}
      "studio centrum"            → {rooms:1, district:"Śródmieście"}
    """
    import re
    from config import DISTRICTS

    text_lower = text.lower()
    filters = {}

    # Rooms
    room_patterns = [
        (r'\b1\s*(?:pok|комн|комнат|room|pokój|studio|однушк|kawalerka)\b', 1),
        (r'\b(?:studio|kawalerka|однушк|студи)\b', 1),
        (r'\b2\s*(?:pok|комн|комнат|room|pokój|pokoje|pokoi)\b', 2),
        (r'\b(?:двушк|двухкомнат|двокімнат)\b', 2),
        (r'\b3\s*(?:pok|комн|комнат|room|pokój|pokoje|pokoi)\b', 3),
        (r'\b(?:трёшк|трехкомнат|трьохкімнат)\b', 3),
        (r'\b4\s*(?:pok|комн|комнат|room|pokój|pokoje|pokoi)\b', 4),
        # standalone digit + комнат(ы) — e.g. "2 комнаты"
        (r'\b2\s+комнат', 2),
        (r'\b3\s+комнат', 3),
        (r'\b4\s+комнат', 4),
        (r'\b1\s+комнат', 1),
    ]
    for pattern, rooms in room_patterns:
        if re.search(pattern, text_lower):
            filters["rooms"] = rooms
            break

    # Price max — look for numbers near zł/pln/zl or standalone
    price_m = re.search(r'(?:do|max|до|не\s*более|не\s*дороже|poniżej)\s*(\d{3,5})', text_lower)
    if not price_m:
        price_m = re.search(r'(\d{3,5})\s*(?:zł|zl|pln|злот)', text_lower)
    if not price_m:
        # standalone number that looks like a price
        nums = re.findall(r'\b(\d{3,5})\b', text_lower)
        for n in nums:
            if 500 <= int(n) <= 20000:
                price_m = type('m', (), {'group': lambda self, x: n})()
                break
    if price_m:
        try:
            filters["price_max"] = int(price_m.group(1))
        except Exception:
            pass

    # District — match against known districts
    district_aliases = {
        "mokotów": "Mokotów", "mokotow": "Mokotów", "мокотув": "Mokotów",
        "wola": "Wola", "воля": "Wola",
        "śródmieście": "Śródmieście", "srodmiescie": "Śródmieście",
        "centrum": "Śródmieście", "центр": "Śródmieście", "центру": "Śródmieście",
        "ursynów": "Ursynów", "ursynow": "Ursynów", "урсинув": "Ursynów",
        "wilanów": "Wilanów", "wilanow": "Wilanów", "виланув": "Wilanów",
        "żoliborz": "Żoliborz", "zoliborz": "Żoliborz", "жолибож": "Żoliborz",
        "bielany": "Bielany", "беляны": "Bielany",
        "bemowo": "Bemowo", "бемово": "Bemowo",
        "ochota": "Ochota", "охота": "Ochota",
        "targówek": "Targówek", "targowek": "Targówek", "таргувек": "Targówek",
        "białołęka": "Białołęka", "bialoleka": "Białołęka", "бяловека": "Białołęka",
        "ursus": "Ursus", "урсус": "Ursus",
        "włochy": "Włochy", "wlochy": "Włochy",
        "praga": "Praga-Południe", "прага": "Praga-Południe",
        "rembertów": "Rembertów", "rembertow": "Rembertów",
        "wawer": "Wawer", "вавер": "Wawer",
    }
    for alias, district in district_aliases.items():
        if alias in text_lower:
            filters["district"] = district
            break

    # Furnished
    if re.search(r'\b(?:umeblowane|meblowane|furnished|меблирован|з меблями)\b', text_lower):
        filters["furnished"] = 1
    elif re.search(r'\b(?:bez mebli|unfurnished|без мебели|без меблів)\b', text_lower):
        filters["furnished"] = 0

    return filters
