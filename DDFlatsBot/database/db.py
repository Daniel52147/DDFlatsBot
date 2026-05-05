import sqlite3
import os
import random
import string
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
        "ALTER TABLE apartments ADD COLUMN rooms INTEGER",
        "ALTER TABLE apartments ADD COLUMN area REAL",
        "ALTER TABLE apartments ADD COLUMN floor TEXT",
        "ALTER TABLE apartments ADD COLUMN furnished INTEGER DEFAULT 0",
        "ALTER TABLE apartments ADD COLUMN image TEXT",
        "ALTER TABLE apartments ADD COLUMN score REAL DEFAULT 0",
        "ALTER TABLE apartments ADD COLUMN verified INTEGER DEFAULT 0",
        "ALTER TABLE apartments ADD COLUMN reported INTEGER DEFAULT 0",
        "ALTER TABLE apartments ADD COLUMN apt_views INTEGER DEFAULT 0",
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
    ]
    for sql in migrations:
        try:
            c.execute(sql)
        except Exception:
            pass  # Column already exists — skip

    conn.commit()
    conn.close()
    cleanup_junk_listings()


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


def save_apartment(data: dict) -> bool:
    if not _is_apartment_listing(data.get("title", ""), data.get("price", 0)):
        return False
    if not _is_warsaw(data.get("district", "")):
        return False
    # Deduplicate within same source only
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
        (title, price, district, rooms, area, floor, furnished, link, image, source, created_at)
        VALUES (:title,:price,:district,:rooms,:area,:floor,:furnished,:link,:image,:source,:created_at)
    """, {**data, "created_at": datetime.now().isoformat()})
    conn.commit()
    conn.close()
    return True


def get_apartments(filters: dict = None, offset: int = 0, limit: int = 1,
                   vip: bool = False, exclude_ids: list = None) -> list[dict]:
    """
    Fetch apartments with smart filter fallback.
    If strict filters return 0 results, progressively relax them:
    rooms/furnished are treated as soft filters (NULL values always pass).
    """
    conn = get_conn()
    c = conn.cursor()

    def _build_query(f: dict, strict_rooms: bool = True, strict_furnished: bool = True) -> tuple:
        q = "SELECT * FROM apartments WHERE reported < 10"
        p = []

        if not vip and VIP_EARLY_ACCESS_MINUTES > 0:
            cutoff = (datetime.now() - timedelta(minutes=VIP_EARLY_ACCESS_MINUTES)).isoformat()
            q += " AND created_at <= ?"
            p.append(cutoff)

        if f:
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
                # NULL rooms always pass — many parsers don't extract room count
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
                # NULL furnished always passes
                q += " AND (furnished = ? OR furnished IS NULL)"
                p.append(f["furnished"])

        if exclude_ids:
            placeholders = ",".join("?" * len(exclude_ids))
            q += f" AND id NOT IN ({placeholders})"
            p.extend(exclude_ids)

        return q, p

    # Try strict first, then progressively relax
    fallback_levels = [
        (True,  True),   # strict rooms + strict furnished
        (True,  False),  # strict rooms, ignore furnished
        (False, False),  # ignore both rooms and furnished
    ]

    for strict_r, strict_f in fallback_levels:
        q, p = _build_query(filters or {}, strict_r, strict_f)
        q_count = q.replace("SELECT *", "SELECT COUNT(*)")
        total = c.execute(q_count, p).fetchone()[0]
        if total > 0:
            q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            p += [limit, offset]
            rows = c.execute(q, p).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    conn.close()
    return []


def count_apartments(filters: dict = None, vip: bool = False) -> int:
    """Count apartments matching filters. Uses same soft-filter logic as get_apartments."""
    conn = get_conn()
    c = conn.cursor()
    q = "SELECT COUNT(*) FROM apartments WHERE reported < 10"
    p = []

    if not vip and VIP_EARLY_ACCESS_MINUTES > 0:
        cutoff = (datetime.now() - timedelta(minutes=VIP_EARLY_ACCESS_MINUTES)).isoformat()
        q += " AND created_at <= ?"
        p.append(cutoff)

    if filters:
        if filters.get("district"):
            q += " AND district LIKE ?"
            p.append(f"%{filters['district']}%")
        if filters.get("price_max"):
            q += " AND price <= ? AND price > 0"
            p.append(filters["price_max"])
        if filters.get("price_min"):
            q += " AND price >= ?"
            p.append(filters["price_min"])
        if filters.get("rooms"):
            q += " AND (rooms = ? OR rooms IS NULL)"
            p.append(filters["rooms"])
        if filters.get("keyword"):
            q += " AND (title LIKE ? OR district LIKE ?)"
            p.append(f"%{filters['keyword']}%")
            p.append(f"%{filters['keyword']}%")
        if filters.get("today"):
            q += " AND created_at >= ?"
            p.append(filters["today"])
        if filters.get("furnished") is not None:
            q += " AND (furnished = ? OR furnished IS NULL)"
            p.append(filters["furnished"])

    count = c.execute(q, p).fetchone()[0]
    conn.close()
    return count


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

        # Early adopter bonus: first N users get 7 days VIP free
        # Everyone else gets 1 day trial
        total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        if total_users <= EARLY_ADOPTER_LIMIT:
            set_vip(user_id, 1, days=7)
        else:
            set_vip(user_id, 1, days=1)  # 1 day trial for all new users
        return get_or_create_user(user_id)

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

    # Every 3 referrals = 7 days VIP
    from config import REFERRAL_REQUIRED
    if new_count % REFERRAL_REQUIRED == 0:
        set_vip(referrer["user_id"], 1, days=REFERRAL_REWARD_DAYS)
        return True
    return False


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

def create_alert(user_id: int, district: str = None, price_min: int = None,
                 price_max: int = None, rooms: int = None):
    conn = get_conn()
    conn.execute("""
        INSERT INTO alerts (user_id, district, price_min, price_max, rooms, active, created_at)
        VALUES (?,?,?,?,?,1,?)
    """, (user_id, district, price_min, price_max, rooms, datetime.now().isoformat()))
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
    if apartment.get("district"):
        query += " AND (district IS NULL OR ? LIKE '%' || district || '%' OR district = 'все')"
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
    """Cross-source deduplication: same title+price from ANY source = duplicate."""
    if not title or not price:
        return False
    conn = get_conn()
    # Normalize: lowercase, strip extra spaces, take first 50 chars
    short_title = " ".join(title.lower().split())[:50]
    # Check across ALL sources — same apartment listed on OLX and Otodom is still a duplicate
    row = conn.execute(
        "SELECT id FROM apartments WHERE LOWER(TRIM(title)) LIKE ? AND ABS(price - ?) <= 50 LIMIT 1",
        (f"{short_title[:35]}%", price)
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
    conn = get_conn()
    c = conn.cursor()

    user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user or user["vip"]:
        conn.close()
        return None

    # Condition 1: saved 10+ favorites
    fav_count = c.execute(
        "SELECT COUNT(*) FROM favorites WHERE user_id=?", (user_id,)
    ).fetchone()[0]

    # Condition 2: active user (registered 7+ days ago, viewed 20+ apartments)
    created = user["created_at"] or ""
    views = user["views"] or 0
    loyal = False
    if created and views >= 20:
        try:
            days_since = (datetime.now() - datetime.fromisoformat(created)).days
            if days_since >= 7:
                loyal = True
        except Exception:
            pass

    conn.close()

    if fav_count >= 10:
        set_vip(user_id, 1, days=3)
        return "fav10"

    if loyal:
        set_vip(user_id, 1, days=2)
        return "loyal"

    # Condition 3: 7-day activity streak → 1 day VIP
    streak = get_user_streak_days(user_id)
    if streak >= 7:
        set_vip(user_id, 1, days=1)
        return "streak7"

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


def get_hot_apartments(limit: int = 5) -> list:
    """Apartments with most likes in last 24h."""
    conn = get_conn()
    from datetime import timedelta
    since = (datetime.now() - timedelta(hours=24)).isoformat()
    rows = conn.execute("""
        SELECT a.*, COALESCE(SUM(r.rating), 0) as hot_score
        FROM apartments a
        LEFT JOIN ratings r ON a.id = r.apartment_id
        WHERE a.created_at >= ?
        GROUP BY a.id
        HAVING hot_score > 0
        ORDER BY hot_score DESC
        LIMIT ?
    """, (since, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_price_drops_today(limit: int = 5) -> list:
    """Apartments where price dropped. Returns only apartments still in DB with valid links."""
    conn = get_conn()
    from datetime import timedelta
    since = (datetime.now() - timedelta(hours=48)).isoformat()
    rows = conn.execute("""
        SELECT DISTINCT a.*,
               ph.price as new_price,
               (SELECT price FROM price_history
                WHERE apartment_id=a.id ORDER BY id ASC LIMIT 1) as old_price
        FROM apartments a
        JOIN price_history ph ON a.id = ph.apartment_id
        WHERE ph.recorded_at >= ?
          AND a.price >= 500 AND a.price <= 25000
        GROUP BY a.id
        HAVING old_price IS NOT NULL AND old_price > a.price
        ORDER BY (old_price - a.price) DESC
        LIMIT ?
    """, (since, limit)).fetchall()
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


def cleanup_junk_listings():
    """Remove obvious non-apartment listings from DB. Called once on startup."""
    conn = get_conn()
    junk_keywords = [
        "osuszacz", "osuszanie", "pochłaniacz",
        "na doby", "noclegi", "godz/", "/doby", "krótkoterminow",
    ]
    for kw in junk_keywords:
        conn.execute(
            "DELETE FROM apartments WHERE LOWER(title) LIKE ?",
            (f"%{kw}%",)
        )
    # Remove extreme price outliers
    conn.execute("DELETE FROM apartments WHERE price > 0 AND price < 200")
    conn.execute("DELETE FROM apartments WHERE price > 50000")
    # Remove non-Warsaw listings — these cities are NOT Warsaw districts
    non_warsaw_districts = [
        "Zgierz", "Łódź", "Częstochowa", "Radomsko", "Kutno", "Łęczyca",
        "Piotrków", "Łask", "Zduńska", "Zelów", "Sieradz", "Tomaszów",
        "Opoczno", "Ostrowy", "Retkinia", "Bałuty",
        "Widzew", "Górna", "Polesie", "Śródmieście-Wschód",
        "Gdańsk", "Kraków", "Wrocław", "Poznań", "Katowice",
        "Lublin", "Szczecin", "Bydgoszcz", "Białystok",
    ]
    for city in non_warsaw_districts:
        conn.execute(
            "DELETE FROM apartments WHERE district LIKE ?",
            (f"%{city}%",)
        )
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


def get_cheapest_apartments(limit: int = 5, price_max: int = 2500) -> list:
    """Get cheapest real Warsaw apartments, filtering junk."""
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
