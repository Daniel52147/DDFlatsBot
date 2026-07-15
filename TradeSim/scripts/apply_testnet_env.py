#!/usr/bin/env python3
"""Patch TradeSim/.env for Binance TESTNET phase — keeps API keys, fixes common mistakes."""

from __future__ import annotations

import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"

# Keys we set/overwrite for the testnet phase (order preserved in output)
TESTNET_DEFAULTS: dict[str, str] = {
    "EXCHANGE_ENABLED": "true",
    "EXCHANGE_TESTNET": "true",
    "EXCHANGE_SYNC_TO_PAPER": "true",
    "EXCHANGE_SYNC_FROM_PAPER": "true",
    "EXCHANGE_MAX_ORDER_USD": "25",
    "TRADING_MODE_DEFAULT": "testnet",
    "AUTO_APPLY_TRADING_MODE_ON_START": "true",
    "PAPER_LEARN_ENABLED": "false",
    "TRADE_MODE": "normal",
    "ACTIVE_TRADE_ON_START": "false",
    "TRADESIM_BIND_HOST": "0.0.0.0",
    "TRADESIM_PHONE_ACCESS": "true",
    "TELEGRAM_FREE_CHAT": "true",
    "WALLET_BRIDGE_ENABLED": "true",
    "LIVE_MAX_ORDER_USD": "25",
    "PROTECTIONS_ENABLED": "true",
}


def _parse_env(text: str) -> tuple[list[str], dict[str, str]]:
    """Return (raw lines, key -> value). Comments and blanks stay in lines."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if m:
            key, raw = m.group(1), m.group(2).strip()
            if raw.startswith('"') and raw.endswith('"'):
                raw = raw[1:-1]
            elif raw.startswith("'") and raw.endswith("'"):
                raw = raw[1:-1]
            values[key] = raw
    return text.splitlines(keepends=True), values


def _render(lines: list[str], values: dict[str, str]) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        m = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line.rstrip("\n"))
        if m:
            key = m.group(2)
            if key in values:
                out.append(f"{m.group(1)}{key}={values[key]}\n")
                seen.add(key)
                continue
        out.append(line if line.endswith("\n") else line + "\n")

    missing = [k for k in TESTNET_DEFAULTS if k not in seen and k in values]
    if missing or any(k not in values for k in TESTNET_DEFAULTS):
        out.append("\n# --- Testnet phase (apply_testnet_env.py) ---\n")
        for key in TESTNET_DEFAULTS:
            if key not in seen:
                out.append(f"{key}={values.get(key, TESTNET_DEFAULTS[key])}\n")
    return "".join(out)


def main() -> int:
    if not ENV_PATH.exists():
        if EXAMPLE_PATH.exists():
            ENV_PATH.write_text(EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Создан {ENV_PATH.name} из .env.example")
        else:
            ENV_PATH.write_text("# TradeSim .env\n", encoding="utf-8")
            print(f"Создан пустой {ENV_PATH.name}")

    raw = ENV_PATH.read_text(encoding="utf-8-sig")  # strip UTF-8 BOM (Windows Notepad)
    lines, values = _parse_env(raw)

    changed: list[str] = []
    for key, want in TESTNET_DEFAULTS.items():
        old = values.get(key)
        if old != want:
            values[key] = want
            changed.append(f"  {key}: {old!r} → {want!r}" if old is not None else f"  + {key}={want}")

    if not values.get("TRADESIM_API_TOKEN", "").strip():
        token = secrets.token_urlsafe(24)
        values["TRADESIM_API_TOKEN"] = token
        changed.append(f"  + TRADESIM_API_TOKEN=<сгенерирован, {len(token)} символов>")

    if not values.get("BINANCE_API_KEY", "").strip():
        print("⚠️  BINANCE_API_KEY пустой — вставь ключи с https://testnet.binance.vision/")
    if values.get("EXCHANGE_TESTNET", "").lower() in ("false", "0", "no"):
        print("⚠️  Было EXCHANGE_TESTNET=false — для Testnet нужно true (исправлено).")

    ENV_PATH.write_text(_render(lines, values), encoding="utf-8", newline="\n")

    print(f"\n✅ {ENV_PATH} обновлён для фазы Testnet")
    if changed:
        print("Изменения:")
        print("\n".join(changed))
    else:
        print("Все testnet-переменные уже были корректны.")

    print(
        "\nДальше:\n"
        "  1. Проверь BINANCE_API_KEY и BINANCE_API_SECRET в .env\n"
        "  2. API-токен в браузер: python scripts/show_api_token.py → внизу UI → 🔐\n"
        "  3. Перезапусти: python main.py  (или start.bat)\n"
        "  3. В UI: 🧪 Testnet + Ctrl+Shift+R\n"
        "\n"
        "Красный пункт «Live API» в readiness — норма на Testnet.\n"
        "Перед Live (день 7): EXCHANGE_TESTNET=false + ключи api.binance.com"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
