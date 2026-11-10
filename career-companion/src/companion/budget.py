"""Spend control (decision D7).

Every AI call reserves its worst-case cost before it is sent and settles to actual usage
afterwards. Committed spend = settled costs + open reservations + unknown-outcome calls
(charged at their reservation) + manual adjustments. New calls are refused once committed
spend plus the new reservation would pass the hard stop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .config import Settings
from .db import Database, now

# USD per million tokens. Source: platform.claude.com/docs/en/about-claude/pricing
PRICES_VERIFIED_ON = date(2026, 11, 10)
PRICES_MAX_AGE_DAYS = 45
PRICES: dict[str, dict[str, float]] = {
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_write": 2.5, "cache_read": 0.10},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_write": 0.125, "cache_read": 0.01},
    "claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_write": 5.0, "cache_read": 0.20},
    "claude-fable-5-2": {"input": 8.0, "output": 40.0, "cache_write": 10.0, "cache_read": 0.20},
}
# Haiku 5.5 charges 5x for a request whose whole prompt is over 100,000 tokens.
LONG_PROMPT = {"claude-haiku-5-5": (100_000, 5.0)}
MAX_INPUT_TOKENS = 40_000  # per call; keeps every request far below any long-prompt tier
MOCK_MODEL = "mock"


class BudgetBlocked(Exception):
    """A new AI call was refused by a spending rule. `reason` is safe to show the user."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0


def estimate_tokens(text: str) -> int:
    """Deliberately high estimate (about 2.5 characters per token) so reservations over-reserve."""
    return math.ceil(len(text) / 2.5) + 16


def prices_are_fresh(today: date | None = None) -> bool:
    return ((today or date.today()) - PRICES_VERIFIED_ON).days <= PRICES_MAX_AGE_DAYS


def _rates(model: str, prompt_tokens: int) -> dict[str, float]:
    if model == MOCK_MODEL:
        return {"input": 0.0, "output": 0.0, "cache_write": 0.0, "cache_read": 0.0}
    if model not in PRICES:
        raise BudgetBlocked(f"No verified price for model '{model}', so its cost can't be capped.")
    rates = dict(PRICES[model])
    threshold = LONG_PROMPT.get(model)
    if threshold and prompt_tokens > threshold[0]:
        rates = {k: v * threshold[1] for k, v in rates.items()}
    return rates


def cost_usd(model: str, usage: Usage) -> float:
    prompt = usage.input_tokens + usage.cache_write_tokens + usage.cache_read_tokens
    r = _rates(model, prompt)
    return (
        usage.input_tokens * r["input"] + usage.output_tokens * r["output"]
        + usage.cache_write_tokens * r["cache_write"] + usage.cache_read_tokens * r["cache_read"]
    ) / 1_000_000


def worst_case_usd(model: str, input_tokens: int, max_output_tokens: int) -> float:
    """Upper bound: all input billed as a cache write (the dearest input rate), full output."""
    r = _rates(model, input_tokens)
    return (input_tokens * max(r["input"], r["cache_write"]) + max_output_tokens * r["output"]) / 1_000_000


class Budget:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.s = settings
        # A reservation left open by a crash has an unknown outcome: keep it charged.
        self.db.run("UPDATE ledger SET status='unknown', note='open at startup' WHERE status='reserved'")

    # -- time keys ---------------------------------------------------------
    def _keys(self) -> tuple[str, str]:
        utc = datetime.now(timezone.utc)
        local = utc.astimezone(ZoneInfo(self.s.timezone))
        return utc.strftime("%Y-%m"), local.strftime("%Y-%m-%d")  # provider month is UTC

    # -- totals ------------------------------------------------------------
    def _committed(self, where: str, params: tuple) -> float:
        row = self.db.one(
            "SELECT COALESCE(SUM(CASE WHEN status IN ('settled','adjustment') THEN cost_usd "
            "WHEN status IN ('reserved','unknown') THEN reserved_usd ELSE 0 END),0) AS total "
            f"FROM ledger WHERE {where}", params)
        return max(0.0, float(row["total"]))

    def month_committed(self) -> float:
        return self._committed("month=?", (self._keys()[0],))

    def status(self) -> dict:
        month, day = self._keys()
        committed = self.month_committed()
        unknown = self.db.one(
            "SELECT COUNT(*) AS n, COALESCE(SUM(reserved_usd),0) AS usd FROM ledger "
            "WHERE month=? AND status='unknown'", (month,))
        if committed >= self.s.hard_stop_usd:
            level = "hard_stop"
        elif any(committed >= w for w in self.s.warn_usd):
            level = "warn"
        else:
            level = "ok"
        return {
            "month": month, "committed_usd": round(committed, 4), "level": level,
            "hard_stop_usd": self.s.hard_stop_usd, "monthly_budget_usd": self.s.monthly_budget_usd,
            "remaining_before_stop_usd": round(max(0.0, self.s.hard_stop_usd - committed), 4),
            "today_usd": round(self._committed("day=?", (day,)), 4),
            "day_cap_usd": self.s.day_cap_usd, "session_cap_usd": self.s.session_cap_usd,
            "unknown_calls": unknown["n"], "unknown_usd": round(float(unknown["usd"]), 4),
            "prices_verified_on": PRICES_VERIFIED_ON.isoformat(), "prices_fresh": prices_are_fresh(),
        }

    # -- lifecycle of one call --------------------------------------------
    def reserve(self, call_type: str, model: str, input_tokens: int, max_output_tokens: int,
                session_id: int | None = None) -> int:
        if input_tokens > MAX_INPUT_TOKENS:
            raise BudgetBlocked("That request is too long to send. Shorten the pasted material and try again.")
        need = worst_case_usd(model, input_tokens, max_output_tokens)
        month, day = self._keys()
        with self.db.tx():  # check and insert atomically, so parallel calls cannot both slip through
            if self.month_committed() + need > self.s.hard_stop_usd:
                raise BudgetBlocked(
                    f"Monthly AI limit reached (${self.s.hard_stop_usd:.0f} of your "
                    f"${self.s.monthly_budget_usd:.0f} budget). Your saved work is still available.")
            if self._committed("day=?", (day,)) + need > self.s.day_cap_usd:
                raise BudgetBlocked(f"Daily AI limit of ${self.s.day_cap_usd:.2f} reached. It resets tomorrow.")
            if session_id is not None and (
                    self._committed("session_id=?", (session_id,)) + need > self.s.session_cap_usd):
                raise BudgetBlocked(f"This session reached its ${self.s.session_cap_usd:.2f} AI limit.")
            return self.db.run(
                "INSERT INTO ledger(ts,month,day,session_id,call_type,model,status,reserved_usd) "
                "VALUES(?,?,?,?,?,?,'reserved',?)",
                (now(), month, day, session_id, call_type, model, need))

    def settle(self, ledger_id: int, model: str, usage: Usage) -> float:
        cost = cost_usd(model, usage)
        self.db.run(
            "UPDATE ledger SET status='settled', cost_usd=?, in_tok=?, out_tok=?, cw_tok=?, cr_tok=? WHERE id=?",
            (cost, usage.input_tokens, usage.output_tokens, usage.cache_write_tokens,
             usage.cache_read_tokens, ledger_id))
        return cost

    def release(self, ledger_id: int) -> None:
        """Only for calls that provably never left this machine."""
        self.db.run("UPDATE ledger SET status='released' WHERE id=?", (ledger_id,))

    def mark_unknown(self, ledger_id: int, note: str = "") -> None:
        """The request may have been billed. Keep the full reservation charged."""
        self.db.run("UPDATE ledger SET status='unknown', note=? WHERE id=?", (note[:100], ledger_id))

    def reconcile(self, console_month_total_usd: float) -> dict:
        """Align the ledger with the figure the user reads from the provider's Console.

        Unknown-outcome calls are cleared and one adjustment makes the tracked total equal
        the Console total. The Console may lag behind recent calls, so the interface tells
        the user to reconcile well after their last AI call.
        """
        if console_month_total_usd < 0:
            raise ValueError("total must not be negative")
        month, _ = self._keys()
        with self.db.tx():
            self.db.run("UPDATE ledger SET status='released', note='reconciled' "
                        "WHERE month=? AND status='unknown'", (month,))
            tracked = self._committed("month=?", (month,))
            delta = console_month_total_usd - tracked
            if abs(delta) > 1e-9:
                self.db.run(
                    "INSERT INTO ledger(ts,month,day,call_type,model,status,cost_usd,note) "
                    "VALUES(?,?,'','reconcile','-','adjustment',?,'console total entered by user')",
                    (now(), month, delta))
        self.db.log("budget_reconciled", f"delta_usd={delta:.4f}")
        return self.status()
