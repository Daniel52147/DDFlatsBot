import sqlite3
from datetime import datetime, date
from config import DB_PATH
from database.models import ALL_TABLES, CREATE_INDEXES


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    for sql in ALL_TABLES:
        conn.execute(sql)
    for stmt in CREATE_INDEXES.strip().split("\n"):
        if stmt.strip():
            conn.execute(stmt.strip())
    # Migrations — add new columns if they don't exist
    _migrate(conn)
    conn.commit()
    conn.close()
    print("[DB] Initialized")


def _migrate(conn: sqlite3.Connection):
    """Add new columns to existing tables without breaking old data."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    migrations = [
        ("is_early_adopter", "ALTER TABLE users ADD COLUMN is_early_adopter INTEGER DEFAULT 0"),
        ("banned",           "ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0"),
    ]
    for col, sql in migrations:
        if col not in existing:
            try:
                conn.execute(sql)
                print(f"[DB] Migration: added column {col}")
            except Exception as e:
                print(f"[DB] Migration skip {col}: {e}")


# ── Users ──────────────────────────────────────────────────────────────────────

def get_or_create_user(user_id: int, username: str = "", first_name: str = "") -> dict:
    from config import EARLY_ADOPTERS_LIMIT
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        # Check if this user qualifies as early adopter
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        is_early = 1 if total < EARLY_ADOPTERS_LIMIT else 0
        conn.execute(
            "INSERT INTO users (user_id, username, first_name, is_early_adopter) VALUES (?,?,?,?)",
            (user_id, username or "", first_name or "", is_early)
        )
        conn.commit()
        # Give early adopters permanent VIP
        if is_early:
            conn.execute(
                "UPDATE users SET vip=1, vip_until=NULL WHERE user_id=?", (user_id,)
            )
            conn.commit()
            print(f"[DB] Early adopter #{total+1}: user {user_id} — VIP granted")
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    else:
        conn.execute(
            "UPDATE users SET last_seen=datetime('now'), username=?, first_name=? WHERE user_id=?",
            (username or row["username"], first_name or row["first_name"], user_id)
        )
        conn.commit()
    result = dict(row)
    conn.close()
    return result


def is_vip(user_id: int) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT vip, vip_until, is_early_adopter FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return False
    # Early adopters have permanent VIP
    if row["is_early_adopter"]:
        return True
    if not row["vip"]:
        return False
    if row["vip_until"]:
        try:
            return datetime.fromisoformat(row["vip_until"]) > datetime.now()
        except Exception:
            return False
    return True


def set_vip(user_id: int, days: int = 30):
    from datetime import timedelta
    until = (datetime.now() + timedelta(days=days)).isoformat()
    conn = get_conn()
    conn.execute(
        "UPDATE users SET vip=1, vip_until=? WHERE user_id=?",
        (until, user_id)
    )
    conn.commit()
    conn.close()


def can_search(user_id: int) -> bool:
    """Check if user has free searches left today."""
    if is_vip(user_id):
        return True
    conn = get_conn()
    row = conn.execute(
        "SELECT searches_today, searches_date FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        return True
    today = date.today().isoformat()
    if row["searches_date"] != today:
        return True  # new day — reset
    from config import FREE_SEARCHES
    return (row["searches_today"] or 0) < FREE_SEARCHES


def increment_searches(user_id: int):
    today = date.today().isoformat()
    conn = get_conn()
    row = conn.execute(
        "SELECT searches_today, searches_date FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    if row and row["searches_date"] == today:
        conn.execute(
            "UPDATE users SET searches_today=searches_today+1, total_searches=total_searches+1 WHERE user_id=?",
            (user_id,)
        )
    else:
        conn.execute(
            "UPDATE users SET searches_today=1, searches_date=?, total_searches=total_searches+1 WHERE user_id=?",
            (today, user_id)
        )
    conn.commit()
    conn.close()


def searches_left(user_id: int) -> int:
    from config import FREE_SEARCHES
    if is_vip(user_id):
        return 999
    conn = get_conn()
    row = conn.execute(
        "SELECT searches_today, searches_date FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        return FREE_SEARCHES
    today = date.today().isoformat()
    if row["searches_date"] != today:
        return FREE_SEARCHES
    return max(0, FREE_SEARCHES - (row["searches_today"] or 0))


# ── Alerts ─────────────────────────────────────────────────────────────────────

def save_alert(user_id: int, origin: str, destination: str,
               price_max: int = None, date_from: str = None, date_to: str = None) -> int:
    conn = get_conn()
    # Deactivate old alert for same route
    conn.execute(
        "UPDATE alerts SET active=0 WHERE user_id=? AND origin=? AND destination=?",
        (user_id, origin, destination)
    )
    cur = conn.execute(
        "INSERT INTO alerts (user_id, origin, destination, price_max, date_from, date_to) VALUES (?,?,?,?,?,?)",
        (user_id, origin, destination, price_max, date_from, date_to)
    )
    alert_id = cur.lastrowid
    conn.commit()
    conn.close()
    return alert_id


def get_user_alerts(user_id: int) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM alerts WHERE user_id=? AND active=1 ORDER BY created_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_alert(alert_id: int, user_id: int):
    conn = get_conn()
    conn.execute("UPDATE alerts SET active=0 WHERE id=? AND user_id=?", (alert_id, user_id))
    conn.commit()
    conn.close()


def get_all_active_alerts() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM alerts WHERE active=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Favorites ──────────────────────────────────────────────────────────────────

def save_favorite(user_id: int, flight: dict) -> bool:
    conn = get_conn()
    exists = conn.execute(
        "SELECT id FROM favorites WHERE user_id=? AND link=?",
        (user_id, flight.get("link", ""))
    ).fetchone()
    if exists:
        conn.close()
        return False
    conn.execute(
        """INSERT INTO favorites (user_id, origin, destination, price, airline, depart_at, arrive_at, link)
           VALUES (?,?,?,?,?,?,?,?)""",
        (user_id, flight.get("origin"), flight.get("destination"),
         flight.get("price"), flight.get("airline"),
         flight.get("depart_at"), flight.get("arrive_at"), flight.get("link"))
    )
    conn.commit()
    conn.close()
    return True


def get_favorites(user_id: int) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM favorites WHERE user_id=? ORDER BY saved_at DESC LIMIT 20",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_favorite(fav_id: int, user_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM favorites WHERE id=? AND user_id=?", (fav_id, user_id))
    conn.commit()
    conn.close()


# ── Hot deals ──────────────────────────────────────────────────────────────────

def save_hot_deal(deal: dict) -> bool:
    conn = get_conn()
    # Don't duplicate same route+price found today
    today = date.today().isoformat()
    exists = conn.execute(
        "SELECT id FROM hot_deals WHERE origin=? AND destination=? AND price=? AND found_at >= ?",
        (deal["origin"], deal["destination"], deal["price"], today)
    ).fetchone()
    if exists:
        conn.close()
        return False
    conn.execute(
        "INSERT INTO hot_deals (origin, destination, price, airline, depart_at, link) VALUES (?,?,?,?,?,?)",
        (deal["origin"], deal["destination"], deal["price"],
         deal.get("airline", ""), deal.get("depart_at", ""), deal.get("link", ""))
    )
    conn.commit()
    conn.close()
    return True


def get_unnotified_hot_deals() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM hot_deals WHERE notified=0 ORDER BY price ASC LIMIT 10"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_deal_notified(deal_id: int):
    conn = get_conn()
    conn.execute("UPDATE hot_deals SET notified=1 WHERE id=?", (deal_id,))
    conn.commit()
    conn.close()


def get_recent_hot_deals(limit: int = 5) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM hot_deals ORDER BY found_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Stats ──────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    conn = get_conn()
    users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    vip = conn.execute("SELECT COUNT(*) FROM users WHERE vip=1").fetchone()[0]
    searches = conn.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
    alerts = conn.execute("SELECT COUNT(*) FROM alerts WHERE active=1").fetchone()[0]
    conn.close()
    return {"users": users, "vip": vip, "searches": searches, "alerts": alerts}


def get_all_user_ids() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return [r[0] for r in rows]


def save_search(user_id: int, origin: str, destination: str,
                date_from: str, date_to: str, results: int):
    conn = get_conn()
    conn.execute(
        "INSERT INTO searches (user_id, origin, destination, date_from, date_to, results) VALUES (?,?,?,?,?,?)",
        (user_id, origin, destination, date_from, date_to, results)
    )
    conn.commit()
    conn.close()


def get_top_routes(limit: int = 5) -> list:
    """Most searched routes in last 7 days."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT origin, destination, COUNT(*) as cnt
        FROM searches
        WHERE created_at >= datetime('now', '-7 days')
        GROUP BY origin, destination
        ORDER BY cnt DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_vip_user_ids() -> list:
    """Get all active VIP user IDs."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT user_id FROM users WHERE vip=1 AND (vip_until IS NULL OR vip_until > datetime('now'))"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


# ── Admin functions ────────────────────────────────────────────────────────────

def get_user_info(user_id: int) -> dict | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_recent_users(limit: int = 10) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_early_adopters() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM users WHERE is_early_adopter=1 ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def revoke_vip(user_id: int):
    conn = get_conn()
    conn.execute("UPDATE users SET vip=0, vip_until=NULL WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def ban_user(user_id: int):
    conn = get_conn()
    conn.execute("UPDATE users SET banned=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def unban_user(user_id: int):
    conn = get_conn()
    conn.execute("UPDATE users SET banned=0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def is_banned(user_id: int) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT banned FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return bool(row and row["banned"])


def get_top_users(limit: int = 10) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM users ORDER BY total_searches DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_full_stats() -> dict:
    conn = get_conn()
    users       = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    vip         = conn.execute("SELECT COUNT(*) FROM users WHERE vip=1").fetchone()[0]
    early       = conn.execute("SELECT COUNT(*) FROM users WHERE is_early_adopter=1").fetchone()[0]
    banned      = conn.execute("SELECT COUNT(*) FROM users WHERE banned=1").fetchone()[0]
    searches    = conn.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
    alerts      = conn.execute("SELECT COUNT(*) FROM alerts WHERE active=1").fetchone()[0]
    deals       = conn.execute("SELECT COUNT(*) FROM hot_deals").fetchone()[0]
    today_users = conn.execute(
        "SELECT COUNT(*) FROM users WHERE last_seen >= date('now')"
    ).fetchone()[0]
    today_searches = conn.execute(
        "SELECT COUNT(*) FROM searches WHERE created_at >= date('now')"
    ).fetchone()[0]
    conn.close()
    return {
        "users": users, "vip": vip, "early": early, "banned": banned,
        "searches": searches, "alerts": alerts, "deals": deals,
        "today_users": today_users, "today_searches": today_searches,
    }
