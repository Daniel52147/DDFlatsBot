"""Agent chatroom — per-cycle messages from all 12 agents + brain decision."""

from __future__ import annotations

from typing import Any

AGENT_KEYS: list[tuple[str, str]] = [
    ("mentor", "Наставник"),
    ("news", "Новостник"),
    ("schemer", "Исследователь"),
    ("volatility", "Волатильность"),
    ("risk", "Риск"),
    ("trend", "Тренд"),
    ("profit", "Коуч прибыли"),
    ("correlation", "Корреляция"),
    ("analyst", "Аналитик"),
    ("guardian", "Стоп-охранник"),
    ("allocator", "Аллокатор"),
    ("trader_watcher", "Следопыт"),
]


def _agent_message(key: str, report: dict[str, Any]) -> dict[str, Any]:
    rec = report.get("recommendation", "hold")
    conf = report.get("confidence", 0.5)
    text = report.get("summary") or report.get("action_for_brain") or "—"
    action = report.get("action_for_brain") or report.get("action") or ""
    return {
        "role": "agent",
        "agent_id": key,
        "emoji": report.get("emoji", "🤖"),
        "name": report.get("name", key),
        "text": text,
        "action": action[:200] if action else "",
        "recommendation": rec,
        "confidence": round(float(conf), 2),
        "vote_weight": round(float(conf), 2),
    }


def build_chatroom(cycle: dict[str, Any] | None) -> dict[str, Any]:
    if not cycle:
        return {"messages": [], "decision": None, "verdict": "", "ts": 0}

    messages: list[dict[str, Any]] = []
    for key, _label in AGENT_KEYS:
        report = cycle.get(key) or {}
        if not report:
            continue
        messages.append(_agent_message(key, report))

    decision = cycle.get("decision", "hold")
    verdict = cycle.get("verdict", "")
    messages.append({
        "role": "brain",
        "agent_id": "brain",
        "emoji": "🧠",
        "name": "Центральный мозг",
        "text": verdict,
        "decision": decision,
        "recommendation": decision,
        "confidence": 1.0,
    })

    return {
        "messages": messages,
        "decision": decision,
        "verdict": verdict,
        "summary": cycle.get("summary", ""),
        "ts": cycle.get("ts", 0),
        "agent_count": len(AGENT_KEYS),
    }


def build_chatroom_history(cycles: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    """Compact history for timeline tab."""
    rows = []
    for c in cycles[:limit]:
        if c.get("mentor") or c.get("decision"):
            if c.get("mentor"):
                room = build_chatroom(c)
            else:
                room = {
                    "ts": c.get("ts", 0),
                    "decision": c.get("decision"),
                    "verdict": c.get("verdict", ""),
                    "messages": [{
                        "role": "brain",
                        "emoji": "🧠",
                        "name": "Мозг",
                        "text": c.get("verdict", ""),
                        "decision": c.get("decision"),
                    }],
                }
        else:
            continue
        rows.append({
            "ts": room.get("ts", c.get("ts", 0)),
            "decision": room.get("decision"),
            "verdict": room.get("verdict", ""),
            "agent_snippets": [
                f"{m['emoji']} {m['name']}: {(m['text'] or '')[:60]}"
                for m in room.get("messages", [])
                if m.get("role") == "agent"
            ][:4],
            "messages": room.get("messages", []),
        })
    return rows
