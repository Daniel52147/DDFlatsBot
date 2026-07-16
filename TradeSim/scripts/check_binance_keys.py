#!/usr/bin/env python3
"""Проверка Binance TESTNET ключей — запуск: python scripts/check_binance_keys.py"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from exchange.binance_live import BinanceLiveExchange  # noqa: E402


async def main() -> int:
    ex = BinanceLiveExchange()
    print("=== Binance API check ===")
    print(f"  EXCHANGE_ENABLED: {ex.enabled}")
    print(f"  testnet: {ex.testnet}")
    print(f"  base_url: {ex.base_url}")
    print(f"  api_key: {'***' + ex.api_key[-6:] if len(ex.api_key) > 6 else '(пусто)'}")
    if not ex.enabled:
        print("\n❌ Ключи не заданы — заполни .env и запусти: python scripts/apply_testnet_env.py")
        return 1

    try:
        ping = await ex._request("GET", "/api/v3/ping")
        print(f"\n✅ ping: {ping}")
    except Exception as e:
        print(f"\n❌ ping failed: {e}")
        return 1

    try:
        await ex._sync_server_time()
        print(f"✅ time sync offset: {ex._time_offset_ms} ms")
    except Exception as e:
        print(f"⚠️  time sync: {e}")

    result = await ex.verify_connection()
    if result.get("ok"):
        print(f"\n✅ API OK — USDT free ${result.get('usdt_free', 0):.2f}")
        print(f"   {result.get('note', '')}")
        return 0

    print(f"\n❌ API failed: {result.get('error', result.get('note', 'unknown'))}")
    print(
        "\nЧто делать:\n"
        "  1. https://testnet.binance.vision/ → Log In → Generate HMAC key\n"
        "  2. Вставь в .env БЕЗ пробелов и кавычек\n"
        "  3. EXCHANGE_TESTNET=true\n"
        "  4. Синхронизируй время Windows: Параметры → Время → Синхронизировать\n"
        "  5. Перезапусти: python main.py"
    )
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
