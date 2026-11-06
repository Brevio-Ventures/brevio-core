"""Savings receipt: the local ledger behind `cli.py gain` (Master Growth Plan G13 / S7).

Counts the defects intercepted locally before they cost an LLM build/test retry loop. Interceptions
are counts. Tokens or money saved are recorded only when the caller passes a measured value (for
example the real token cost of the retry the hook prevented); there is no per-interception estimate
(owner decision, 2026-11-04). Computes the shareable SVG receipt URL.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import os
from typing import Any

from brevio.pipeline.agent_host import config, jsonstore
from brevio.pipeline.code_rules import PR_RULES_122
from brevio.pipeline.gates import defect_compiler

STATS_DIR = ".brevio"
STATS_FILE = "stats.json"

RECEIPT_SALT = "brevio_public_community_receipt_salt"


def get_stats_path(cwd: str | None = None) -> str:
    root = cwd or config.WORKSPACE_DIR
    return os.path.join(root, STATS_DIR, STATS_FILE)


def load_stats(cwd: str | None = None) -> dict[str, Any]:
    path = get_stats_path(cwd)
    data = jsonstore.read_or(path, {
        "version": 2,
        "total_interceptions": 0,
        "measured_events": 0,
        "tokens_saved": 0,
        "cost_saved_usd": 0.0,
        "events": [],
    })
    if data.get("version", 1) < 2:      # v1 files carried a fixed estimate per interception: drop it
        data = data | {"version": 2, "measured_events": 0, "tokens_saved": 0, "cost_saved_usd": 0.0}
    return data


def save_stats(data: dict[str, Any], cwd: str | None = None) -> None:
    path = get_stats_path(cwd)
    jsonstore.write(path, data, indent=2, lock=False)


def record_interception(
    rule_id: str,
    file_path: str,
    tokens_saved: int | None = None,
    cost_saved_usd: float | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Record a defect intercepted by zero-token rules/guards.

    ``tokens_saved`` and ``cost_saved_usd`` are the caller's measured values; left out, only the
    count moves.
    """
    data = load_stats(cwd)
    events = data.setdefault("events", [])

    event = {
        "rule_id": rule_id,
        "file": file_path,
        "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    data["total_interceptions"] = int(data.get("total_interceptions", 0)) + 1
    if tokens_saved is not None or cost_saved_usd is not None:
        event["tokens_saved"] = int(tokens_saved or 0)
        event["cost_saved_usd"] = float(cost_saved_usd or 0.0)
        data["measured_events"] = int(data.get("measured_events", 0)) + 1
        data["tokens_saved"] = int(data.get("tokens_saved", 0)) + event["tokens_saved"]
        data["cost_saved_usd"] = round(float(data.get("cost_saved_usd", 0.0)) + event["cost_saved_usd"], 2)
    events.append(event)

    save_stats(data, cwd)
    return event


def generate_receipt_url(
    interceptions: int,
    tokens_saved: int | None,
    active_guards: int,
    aeo_score: int = 100,
) -> str:
    """Generate deterministic HMAC-signed shareable SVG receipt URL."""
    payload = {
        "i": interceptions,
        "g": active_guards,
        "aeo": aeo_score,
        "ts": int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
    }
    if tokens_saved:                    # only a measured figure goes on the receipt
        payload["t"] = tokens_saved
        payload["measured"] = True
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii")
    sig = hmac.new(RECEIPT_SALT.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()[:16]
    return f"https://brevio.pro/api/receipt.svg?d={b64}&sig={sig}"


def get_gain_summary(cwd: str | None = None) -> dict[str, Any]:
    """Compute the savings receipt: counts always, savings only when measured."""
    stats = load_stats(cwd)
    guards_data = defect_compiler.load_guards(cwd)
    guards = guards_data.get("guards", {})

    active_guards = sum(1 for g in guards.values() if g.get("status") in ("active", "trial"))
    interceptions = int(stats.get("total_interceptions", 0))
    measured = int(stats.get("measured_events", 0)) > 0   # v1 files held estimates: they never count
    tokens_saved = int(stats.get("tokens_saved", 0)) if measured else 0
    cost_saved = float(stats.get("cost_saved_usd", 0.0)) if measured else 0.0

    receipt_url = generate_receipt_url(
        interceptions=interceptions,
        tokens_saved=tokens_saved if measured else None,
        active_guards=active_guards,
        aeo_score=100,
    )

    return {
        "total_interceptions": interceptions,
        "active_learned_guards": active_guards,
        "base_rules_enforced": len(PR_RULES_122),
        "savings_measured": measured,
        "tokens_saved": tokens_saved,
        "cost_saved_usd": cost_saved,
        "aeo_score": 100,
        "receipt_url": receipt_url,
    }
