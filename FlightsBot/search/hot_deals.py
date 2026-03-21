"""
Hot deals scanner — runs on schedule, finds flights under HOT_DEAL_MAX_PRICE EUR.
"""
from config import POPULAR_ORIGINS, HOT_DEAL_MAX_PRICE
from search.flights import get_hot_deals
from database.db import save_hot_deal


def scan_hot_deals() -> list:
    """Fetch hot deals and save new ones to DB. Returns list of new deals."""
    print(f"[HotDeals] Scanning from {POPULAR_ORIGINS}...")
    flights = get_hot_deals(origins=POPULAR_ORIGINS, price_max=HOT_DEAL_MAX_PRICE, limit=30)
    new = []
    for f in flights:
        if save_hot_deal(f):
            new.append(f)
    print(f"[HotDeals] Found {len(flights)} deals, {len(new)} new")
    return new
