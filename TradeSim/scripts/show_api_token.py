#!/usr/bin/env python3
"""Показать TRADESIM_API_TOKEN из .env — для вставки в браузер."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import os  # noqa: E402

token = os.environ.get("TRADESIM_API_TOKEN", "").strip()
if not token:
    print("❌ TRADESIM_API_TOKEN пустой в .env")
    print("   Запусти: python scripts/apply_testnet_env.py")
    sys.exit(1)

print("=== API-токен для браузера ===")
print()
print(token)
print()
print("1. Скопируй строку выше")
print("2. В TradeSim внизу страницы → поле «API-токен» → вставь → кнопка 🔐")
print("3. Повтори Smoke test / Sync paper")
