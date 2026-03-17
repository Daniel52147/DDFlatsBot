import sqlite3
import random
import string
from datetime import datetime, timedelta
from database.models import (
    CREATE_APARTMENTS, CREATE_USERS, CREATE_FAVORITES,
    CREATE_SUBSCRIPTIONS, CREATE_ALERTS, CREATE_STATS, CREATE_PRICE_HISTORY,
    CREATE_RATINGS,
)
from config import DB_PATH, VIP_EARLY_ACCESS_MINUTES, REFERRAL_REWARD_DAYS, EARLY_ADOPTER_LIMIT


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    for sql in [CREATE_APARTMENTS, CREATE_USERS, CREATE_FAVORITES,
                CREATE_SUBSCRIPTIONS, CREATE_ALERTS, CREATE_STATS,
                CREATE_PRICE_HISTORY, CREATE_RATINGS]:
        c.execute(sql)

    migrations = [
        "ALTER TABLE users ADD COLUMN vip_until TEXT",
        "ALTER TABLE users ADD COLUMN ref_code TEXT",
        "ALTER TABLE users ADD COLUMN referred_by INTEGER",
        "ALTER TABLE users ADD COLUMN ref_count INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'ru'",
        "ALTER TABLE apartments ADD COLUMN rooms INTEGER",
        "ALTER TABLE apartments ADD COLUMN area REAL",
        "ALTER TABLE apartments ADD COLUMN floor TEXT",
        "ALTER TABLE apartments ADD COLUMN furnished INTEGER DEFAULT 0",
        "ALTER TABLE apartments ADD COLUMN image TEXT",
        "ALTER TABLE apartments ADD COLUMN score REAL DEFAULT 0",
    ]
    for sql in migrations:
        try:
            c.execute(sql)
        except Exception:
            pass  # Column already exists — skip

    conn.commit()
    conn.close()


# ── Apartments ───────────────────────────────────────────────

def save_apartment(data: dict) -> bool:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, price FROM apartments WHERE link=?", (data["link"],))
    existing = c.fetchone()
    if existing:
        # Track price change
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
    conn.close()
    # Deduplication: skip if very similar apartment already exists from another source
    if find_duplicate(data.get("title", ""), data.get("price", 0)):
        return False
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO apartments
        (title, price, district, rooms, area, floor, furnished, link, image, source, created_at)
        VALUES (:title,:price,:district,:rooms,:area,:floor,:furnished,:link,:image,:source,:created_at)
    """, {**data, "created_at": datetime.now().isoformat()})
    conn.commit()
    conn.close()
    return True


def get_apartments(filters: dict = None, offset: int = 0, limit: int = 1,
                   vip: bool = False) -> list[dict]:
    conn = get_conn()
    c = conn.cursor()
    query = "SELECT * FROM apartments WHERE 1=1"
    params = []

    # Early access: free users only see apartments older than N minutes
    if not vip and VIP_EARLY_ACCESS_MINUTES > 0:
        cutoff = (datetime.now() - timedelta(minutes=VIP_EARLY_ACCESS_MINUTES)).isoformat()
        query += " AND created_at <= ?"
        params.append(cutoff)

    if filters:
        if filters.get("district"):
            query += " AND district LIKE ?"
            params.append(f"%{filters['district']}%")
        if filters.get("price_max"):
            query += " AND price <= ? AND price > 0"
            params.append(filters["price_max"])
        if filters.get("price_min"):
            query += " AND price >= ?"
            params.append(filters["price_min"])
        if filters.get("rooms"):
            query += " AND rooms = ?"
            params.append(filters["rooms"])
        if filters.get("keyword"):
            query += " AND title LIKE ?"
            params.append(f"%{filters['keyword']}%")
        if filters.get("today"):
            query += " AND created_at >= ?"
            params.append(filters["today"])

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    rows = c.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_apartments(filters: dict = None, vip: bool = False) -> int:
    conn = get_conn()
    c = conn.cursor()
    query = "SELECT COUNT(*) FROM apartments WHERE 1=1"
    params = []
    if not vip and VIP_EARLY_ACCESS_MINUTES > 0:
        cutoff = (datetime.now() - timedelta(minutes=VIP_EARLY_ACCESS_MINUTES)).isoformat()
        query += " AND created_at <= ?"
        params.append(cutoff)
    if filters:
        if filters.get("district"):
            query += " AND district LIKE ?"
            params.append(f"%{filters['district']}%")
        if filters.get("price_max"):
            query += " AND price <= ? AND price > 0"
            params.append(filters["price_max"])
        if filters.get("price_min"):
            query += " AND price >= ?"
            params.append(filters["price_min"])
        if filters.get("rooms"):
            query += " AND rooms = ?"
            params.append(filters["rooms"])
        if filters.get("keyword"):
            query += " AND title LIKE ?"
            params.append(f"%{filters['keyword']}%")
        if filters.get("today"):
            query += " AND created_at >= ?"
            params.append(filters["today"])
    count = c.execute(query, params).fetchone()[0]
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
        total_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        if total_users <= EARLY_ADOPTER_LIMIT:
            set_vip(user_id, 1, days=7)
            return get_or_create_user(user_id)  # re-fetch with vip=1
        return dict(row)

    conn.close()
    return dict(row)


def increment_views(user_id: int):
    conn = get_conn()
    conn.execute("UPDATE users SET views=views+1 WHERE user_id=?", (user_id,))
    conn.commit()
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
        "SELECT DISTINCT user_id FROM subscriptions WHERE ? LIKE '%' || district || '%'",
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
        query += " AND (district IS NULL OR ? LIKE '%' || district || '%')"
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

def find_duplicate(title: str, price: int) -> bool:
    """Check if very similar apartment already exists (same title+price from different source)."""
    if not title or not price:
        return False
    conn = get_conn()
    short_title = title[:50]
    row = conn.execute(
        "SELECT id FROM apartments WHERE title LIKE ? AND price=? LIMIT 1",
        (f"{short_title}%", price)
    ).fetchone()
    conn.close()
    return row is not None


def get_stats() -> dict:
    conn = get_conn()
    total_apts = conn.execute("SELECT COUNT(*) FROM apartments").fetchone()[0]
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    vip_users = conn.execute("SELECT COUNT(*) FROM users WHERE vip=1").fetchone()[0]
    total_favs = conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]
    last_parse = conn.execute(
        "SELECT logged_at FROM parse_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return {
        "apartments": total_apts,
        "users": total_users,
        "vip": vip_users,
        "favorites": total_favs,
        "last_parse": last_parse["logged_at"] if last_parse else "никогда",
    }


# ── Auto VIP conditions ───────────────────────────────────────

def check_auto_vip_conditions(user_id: int) -> str | None:
    """
    Check if user qualifies for automatic VIP.
    Returns reason string if VIP should be granted, None otherwise.
    Conditions:
      - 10+ favorites saved → 3 days VIP
      - 5+ referrals → 14 days VIP (handled separately in apply_referral)
      - Active 7+ days → 2 days VIP trial
    """
    conn = get_conn()
    c = conn.cursor()

    # Already VIP — skip
    user = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user or user["vip"]:
        conn.close()
        return None

    # Condition 1: saved 10+ favorites
    fav_count = c.execute(
        "SELECT COUNT(*) FROM favorites WHERE user_id=?", (user_id,)
    ).fetchone()[0]
    if fav_count >= 10:
        conn.close()
        set_vip(user_id, 1, days=3)
        return "fav10"

    # Condition 2: active user (registered 7+ days ago, viewed 20+ apartments)
    created = user["created_at"] or ""
    views = user["views"] or 0
    if created and views >= 20:
        from datetime import datetime
        try:
            days_since = (datetime.now() - datetime.fromisoformat(created)).days
            if days_since >= 7:
                conn.close()
                set_vip(user_id, 1, days=2)
                return "loyal"
        except Exception:
            pass

    conn.close()
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


def get_user_streak(user_id: int) -> int:
    """How many days in a row user has been active (viewed apartments)."""
    # Simplified: return views count as activity proxy
    conn = get_conn()
    row = conn.execute("SELECT views FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row["views"] if row else 0
