"""Deterministic recommendation (decision D10). The model never ranks.

Order of concern: deadlines, importance, existing commitments, work already started,
then whether it fits the time available. Exploratory actions never outrank a commitment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .store import OPEN_STATES


@dataclass
class Option:
    action: dict
    score: int
    reasons: list[str] = field(default_factory=list)


def _score(action: dict, minutes: int, today: date, last_focus_id: int | None, reminder_ids: set[int]) -> Option:
    score, reasons = 0, []
    if action["deadline"]:
        days = (date.fromisoformat(action["deadline"]) - today).days
        if days < 0:
            score += 100
            reasons.append(f"Overdue by {-days} day{'s' if days != -1 else ''}.")
        elif days <= 2:
            score += 60
            reasons.append("Due today." if days == 0 else f"Due in {days} day{'s' if days != 1 else ''}.")
        elif days <= 7:
            score += 30
            reasons.append(f"Due in {days} days.")
        else:
            score += 5
    score += 15 * int(action["importance"])
    if int(action["importance"]) >= 3:
        reasons.append("You marked it high importance.")
    if action["commitment"]:
        score += 40
        reasons.append("You already committed to this.")
    if action["state"] in ("drafted", "reviewed"):
        score += 25
        reasons.append("Already started: finishing beats starting something new.")
    if action["id"] in reminder_ids:
        score += 20
        reasons.append("A reminder you set is due.")
    if action["id"] == last_focus_id:
        score += 15
        reasons.append("You were on this last time.")
    if int(action["effort_min"]) <= minutes:
        score += 10
        reasons.append(f"Fits your {minutes} minutes (about {action['effort_min']}).")
    else:
        score -= 30
        reasons.append(f"Needs about {action['effort_min']} minutes: start it and save your place.")
    return Option(action, score, reasons)


def rank(actions: list[dict], minutes: int, today: date, last_focus_id: int | None = None,
         reminder_action_ids: set[int] | None = None, limit: int = 3) -> list[Option]:
    """Return at most `limit` options, best first."""
    open_actions = [a for a in actions if a["state"] in OPEN_STATES]
    options = [_score(a, minutes, today, last_focus_id, reminder_action_ids or set()) for a in open_actions]

    def is_commitment(o: Option) -> bool:
        a = o.action
        return bool(a["commitment"] or a["deadline"] or a["state"] in ("drafted", "reviewed"))

    # Commitments first as a group, then exploratory work, each by score. Ties: oldest first.
    options.sort(key=lambda o: (not is_commitment(o), -o.score, o.action["id"]))
    return options[:limit]
