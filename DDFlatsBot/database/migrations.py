"""
Database migration utilities for DDFlatsBot.

Handles schema updates and data migrations safely.
"""

import sqlite3
from datetime import datetime
from typing import List, Tuple


class Migration:
    """Base class for database migrations."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def execute(self, sql: str, params: tuple = ()) -> None:
        """Execute SQL statement."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()
    
    def column_exists(self, table: str, column: str) -> bool:
        """Check if column exists in table."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]
            return column in columns
        finally:
            conn.close()
    
    def table_exists(self, table: str) -> bool:
        """Check if table exists."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()


def migrate_add_geographic_fields(db_path: str) -> None:
    """Add geographic validation fields to apartments table."""
    migration = Migration(db_path)
    
    # Add lat, lon, postal_code fields
    if not migration.column_exists('apartments', 'lat'):
        migration.execute("ALTER TABLE apartments ADD COLUMN lat REAL")
        print("[Migration] Added lat column to apartments")
    
    if not migration.column_exists('apartments', 'lon'):
        migration.execute("ALTER TABLE apartments ADD COLUMN lon REAL")
        print("[Migration] Added lon column to apartments")
    
    if not migration.column_exists('apartments', 'postal_code'):
        migration.execute("ALTER TABLE apartments ADD COLUMN postal_code TEXT")
        print("[Migration] Added postal_code column to apartments")
    
    if not migration.column_exists('apartments', 'source_city'):
        migration.execute("ALTER TABLE apartments ADD COLUMN source_city TEXT")
        print("[Migration] Added source_city column to apartments")


def migrate_add_duplicate_fields(db_path: str) -> None:
    """Add duplicate detection fields to apartments table."""
    migration = Migration(db_path)
    
    if not migration.column_exists('apartments', 'duplicate_of'):
        migration.execute("ALTER TABLE apartments ADD COLUMN duplicate_of INTEGER")
        print("[Migration] Added duplicate_of column to apartments")
        
        # Add index
        migration.execute(
            "CREATE INDEX IF NOT EXISTS idx_apartments_duplicate ON apartments(duplicate_of)"
        )
        print("[Migration] Created index on duplicate_of")


def migrate_add_quality_fields(db_path: str) -> None:
    """Add quality and verification fields to apartments table."""
    migration = Migration(db_path)
    
    if not migration.column_exists('apartments', 'verified'):
        migration.execute("ALTER TABLE apartments ADD COLUMN verified INTEGER DEFAULT 0")
        print("[Migration] Added verified column to apartments")
    
    if not migration.column_exists('apartments', 'quality_score'):
        migration.execute("ALTER TABLE apartments ADD COLUMN quality_score INTEGER DEFAULT 50")
        print("[Migration] Added quality_score column to apartments")
    
    if not migration.column_exists('apartments', 'apt_views'):
        migration.execute("ALTER TABLE apartments ADD COLUMN apt_views INTEGER DEFAULT 0")
        print("[Migration] Added apt_views column to apartments")


def migrate_add_performance_indexes(db_path: str) -> None:
    """Add performance indexes to apartments table."""
    migration = Migration(db_path)
    
    indexes = [
        ("idx_apartments_city_district", "CREATE INDEX IF NOT EXISTS idx_apartments_city_district ON apartments(city, district)"),
        ("idx_apartments_city_price", "CREATE INDEX IF NOT EXISTS idx_apartments_city_price ON apartments(city, price)"),
        ("idx_apartments_quality", "CREATE INDEX IF NOT EXISTS idx_apartments_quality ON apartments(quality_score DESC)"),
        ("idx_apartments_verified", "CREATE INDEX IF NOT EXISTS idx_apartments_verified ON apartments(verified, created_at DESC)"),
    ]
    
    for name, sql in indexes:
        migration.execute(sql)
        print(f"[Migration] Created index {name}")


def migrate_add_user_preferences(db_path: str) -> None:
    """User search preferences and hidden listings."""
    migration = Migration(db_path)

    if not migration.column_exists("users", "hide_seen"):
        migration.execute("ALTER TABLE users ADD COLUMN hide_seen INTEGER DEFAULT 1")
        print("[Migration] Added hide_seen column to users")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hidden_apartments (
                user_id INTEGER NOT NULL,
                apt_id INTEGER NOT NULL,
                hidden_at TEXT,
                UNIQUE(user_id, apt_id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hidden_user ON hidden_apartments(user_id)"
        )
        conn.commit()
        print("[Migration] Ensured hidden_apartments table")
    finally:
        conn.close()


def migrate_district_all_sentinel(db_path: str) -> None:
    """Normalize legacy Cyrillic 'все' district sentinel to __all__."""
    conn = sqlite3.connect(db_path)
    try:
        for table in ("subscriptions", "alerts"):
            conn.execute(
                f"UPDATE {table} SET district = ? WHERE district = ?",
                ("__all__", "все"),
            )
        conn.commit()
        print("[Migration] Normalized district sentinel to __all__")
    finally:
        conn.close()


def run_all_migrations(db_path: str) -> None:
    """Run all pending migrations."""
    print(f"[Migration] Running migrations on {db_path}")
    
    migrate_add_geographic_fields(db_path)
    migrate_add_duplicate_fields(db_path)
    migrate_add_quality_fields(db_path)
    migrate_add_performance_indexes(db_path)
    migrate_add_user_preferences(db_path)
    migrate_district_all_sentinel(db_path)
    
    print("[Migration] All migrations completed successfully")


if __name__ == "__main__":
    from config import DB_PATH
    run_all_migrations(DB_PATH)
