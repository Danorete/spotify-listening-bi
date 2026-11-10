"""Storage helpers and domain rules. Table and column names come from code, never from input."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from .db import Database, now

# Memory kinds decide visibility (decision D5). Private kinds never reach outward drafting.
PRIVATE_MEMORY_KINDS = ("goal", "constraint", "preference", "boundary")
PUBLIC_VOICE_KINDS = ("voice_note", "voice_sample", "drafting_rule")
MEMORY_KINDS = PRIVATE_MEMORY_KINDS + PUBLIC_VOICE_KINDS

EVIDENCE_STATUSES = ("unverified_user_claim", "user_verified_with_artifact", "do_not_claim")
USES = ("profile", "resume", "outreach", "post", "interview")
PURPOSE_TO_USE = {"profile": "profile", "application": "resume", "outreach": "outreach",
                  "follow_up": "outreach", "post": "post", "interview_prep": "interview"}
ITEM_KINDS = ("opportunity", "relationship")
ITEM_STATUSES = ("active", "waiting", "closed")
ACTION_KINDS = ("profile_edit", "job_compare", "outreach", "follow_up", "interview_prep", "application", "other")
ACTION_STATES = ("suggested", "drafted", "reviewed", "done", "dropped")
OPEN_STATES = ("suggested", "drafted", "reviewed")
OUTCOME_TYPES = ("reply", "interview", "no_response", "rejection", "offer", "other")
IMPORT_KINDS = ("job_description", "conversation", "resume", "profile_text", "other")

# User-driven transitions. The model has no path to any of them.
TRANSITIONS = {
    "suggested": {"drafted", "reviewed", "done", "dropped"},
    "drafted": {"suggested", "reviewed", "done", "dropped"},
    "reviewed": {"drafted", "done", "dropped"},
    "done": {"reviewed"},  # undo
    "dropped": {"suggested"},
}
STATE_NOTES = {
    "suggested": "Not started.",
    "drafted": "Draft saved. Not reviewed yet.",
    "reviewed": "Reviewed. Not sent or applied yet: that step is yours, outside this app.",
    "done": "You confirmed this is done.",
    "dropped": "Dropped.",
}

JSON_COLS = {
    "evidence": ("metrics", "permitted_uses"),
    "drafts": ("claims", "gaps", "report"),
    "proposals": ("payload",),
}
STAMPED = {"memory", "evidence", "items", "actions", "drafts"}  # tables with updated_at


class RuleError(ValueError):
    """A domain rule was broken. The message is safe to show."""


def _decode(table: str, row: dict | None) -> dict | None:
    if row:
        for col in JSON_COLS.get(table, ()):
            row[col] = json.loads(row[col])
    return row


def _encode(table: str, fields: dict[str, Any]) -> dict[str, Any]:
    out = dict(fields)
    for col in JSON_COLS.get(table, ()):
        if col in out:
            out[col] = json.dumps(out[col])
    for k, v in out.items():
        if isinstance(v, bool):
            out[k] = int(v)
    return out


def get(db: Database, table: str, row_id: int) -> dict | None:
    return _decode(table, db.one(f"SELECT * FROM {table} WHERE id=?", (row_id,)))


def rows(db: Database, table: str, where: str = "1=1", params: tuple = (), order: str = "id DESC") -> list[dict]:
    return [_decode(table, r) for r in db.q(f"SELECT * FROM {table} WHERE {where} ORDER BY {order}", params)]


def insert(db: Database, table: str, **fields: Any) -> dict:
    f = _encode(table, fields)
    f.setdefault("created_at", now())
    if table in STAMPED:
        f.setdefault("updated_at", f["created_at"])
    cols = ",".join(f)
    row_id = db.run(f"INSERT INTO {table}({cols}) VALUES({','.join('?' * len(f))})", tuple(f.values()))
    return get(db, table, row_id)  # type: ignore[return-value]


def update(db: Database, table: str, row_id: int, **fields: Any) -> dict | None:
    f = _encode(table, fields)
    if table in STAMPED:
        f["updated_at"] = now()
    if f:
        sets = ",".join(f"{k}=?" for k in f)
        db.run(f"UPDATE {table} SET {sets} WHERE id=?", (*f.values(), row_id))
    return get(db, table, row_id)


def delete(db: Database, table: str, row_id: int) -> bool:
    return db.run(f"DELETE FROM {table} WHERE id=?", (row_id,)) > 0


# ---- rules ----------------------------------------------------------------------------

def check_evidence(fields: dict) -> None:
    if fields.get("status") == "user_verified_with_artifact" and not str(fields.get("source_ref", "")).strip():
        raise RuleError("Verified evidence needs a source: a link, file name, or note saying where the proof is.")


def set_action_state(db: Database, action_id: int, new_state: str) -> dict:
    action = get(db, "actions", action_id)
    if not action:
        raise RuleError("No such action.")
    if new_state == action["state"]:
        return action
    if new_state not in TRANSITIONS[action["state"]]:
        raise RuleError(f"Can't go from {action['state']} to {new_state}.")
    done_at = now() if new_state == "done" else None
    db.log("action_state", f"id={action_id} {action['state']}->{new_state}")
    return update(db, "actions", action_id, state=new_state, completed_at=done_at,
                  where_left_off=STATE_NOTES[new_state])  # type: ignore[return-value]


def due_reminders(db: Database, today: date) -> list[dict]:
    return rows(db, "reminders", "state='pending' AND due_on<=?", (today.isoformat(),), "due_on ASC")


def purge_old_messages(db: Database, days: int) -> int:
    return db.run("DELETE FROM messages WHERE created_at < datetime('now', ?)", (f"-{int(days)} days",))


# ---- labelled sample data (fictional; removable in one click) -------------------------

def load_sample(db: Database, today: date) -> None:
    if db.one("SELECT 1 FROM evidence WHERE is_sample=1"):
        return
    from datetime import timedelta

    ev = insert(db, "evidence", title="[SAMPLE] Example dashboard project",
                claim="Built a sales dashboard in Python that groups customers into 4 segments.",
                metrics=[{"value": "4", "unit": "segments", "label": "customer groups in the example"}],
                source_ref="", status="unverified_user_claim", permitted_uses=["profile", "outreach", "resume"],
                do_not_claim="production system; increased revenue", confidential=0,
                provenance="sample", is_sample=1)
    item = insert(db, "items", kind="opportunity", title="[SAMPLE] Data Analyst Intern", org="Example Co",
                  private_notes="[SAMPLE] Private note: only planning can see this.",
                  shareable_context="[SAMPLE] Posting asks for Python and dashboards.", is_sample=1)
    person = insert(db, "items", kind="relationship", title="[SAMPLE] Alex Example", org="Example Co",
                    private_notes="[SAMPLE] Met at a fictional campus event.", is_sample=1)
    a1 = insert(db, "actions", item_id=person["id"], kind="follow_up", title="[SAMPLE] Send the follow-up you promised Alex",
                commitment=1, importance=3, effort_min=10, deadline=(today + timedelta(days=2)).isoformat(),
                where_left_off="Not started.", is_sample=1)
    insert(db, "actions", item_id=item["id"], kind="job_compare", title="[SAMPLE] Compare the intern posting with your evidence",
           commitment=0, importance=2, effort_min=20, where_left_off="Not started.", is_sample=1)
    insert(db, "actions", kind="profile_edit", title="[SAMPLE] Refresh your profile headline",
           commitment=0, importance=1, effort_min=15, where_left_off="Not started.", is_sample=1)
    insert(db, "reminders", action_id=a1["id"], text="[SAMPLE] Alex said to follow up this week", due_on=today.isoformat())
    insert(db, "memory", kind="voice_sample", audience="peer",
           text="[SAMPLE] Hi Alex, good meeting you on Thursday. I looked at the tool you mentioned and had one question.",
           provenance="sample", is_sample=1)
    db.log("sample_loaded", f"evidence_id={ev['id']}")


def remove_sample(db: Database) -> None:
    db.run("DELETE FROM reminders WHERE action_id IN (SELECT id FROM actions WHERE is_sample=1)")
    for table in ("actions", "items", "evidence", "memory"):
        db.run(f"DELETE FROM {table} WHERE is_sample=1")
    db.log("sample_removed")
