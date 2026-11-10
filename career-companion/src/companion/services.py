"""Workflows: the session briefing, onboarding, chat turns, proposals, drafting, comparison."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import context, store
from .ai import AIUnavailable, CompanionTurn, CompareOut, DraftOut, Gateway
from .config import Settings
from .db import Database, now
from .ranking import Option, rank
from .validate import validate_draft

MAX_PROPOSALS_PER_TURN = 3

ONBOARDING = [
    ("goal", "First, what are you working toward over the next few months? One or two sentences is plenty."),
    ("constraint", "What gets in the way? Tell me about your time and energy in whatever detail you're "
                   "comfortable with. Skip anything sensitive: I only need enough to plan around it."),
    ("preference", "How do you like to be worked with? Blunt or gentle, short or detailed, anything that annoys you."),
    ("boundary", "Last one: is there anything I should never suggest or never put in writing for you?"),
]


def local_today(settings: Settings) -> date:
    return datetime.now(timezone.utc).astimezone(ZoneInfo(settings.timezone)).date()


# ---- sessions -------------------------------------------------------------------------

def active_session(db: Database) -> dict | None:
    return db.one("SELECT * FROM sessions WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1")


def start_session(db: Database, minutes: int, action_id: int | None) -> dict:
    db.run("UPDATE sessions SET ended_at=? WHERE ended_at IS NULL", (now(),))
    sid = db.run("INSERT INTO sessions(started_at,minutes,focus_action_id) VALUES(?,?,?)", (now(), minutes, action_id))
    return db.one("SELECT * FROM sessions WHERE id=?", (sid,))  # type: ignore[return-value]


def ensure_session(db: Database) -> dict:
    return active_session(db) or start_session(db, 20, None)


# ---- briefing: code-generated, costs nothing ------------------------------------------

def _option(o: Option, db: Database) -> dict:
    item = store.get(db, "items", o.action["item_id"]) if o.action["item_id"] else None
    return {"action": o.action, "reasons": o.reasons,
            "item": {"id": item["id"], "title": item["title"], "org": item["org"]} if item else None}


def today_view(db: Database, settings: Settings, minutes: int) -> dict:
    today = local_today(settings)
    reminders = store.due_reminders(db, today)
    last = db.one("SELECT * FROM sessions ORDER BY id DESC LIMIT 1")
    options = rank(store.rows(db, "actions"), minutes, today,
                   last_focus_id=last["focus_action_id"] if last else None,
                   reminder_action_ids={r["action_id"] for r in reminders if r["action_id"]})
    days_away = None
    if last:
        days_away = (datetime.now(timezone.utc) - datetime.fromisoformat(last["started_at"])).days

    if not options:
        greeting = ("Nothing is waiting on you. Add an opportunity or a follow-up when one comes up, "
                    "or park an idea. No need to invent work.")
    else:
        top = options[0]
        opener = "Welcome back." if not days_away else (
            f"Welcome back. It's been {days_away} day{'s' if days_away != 1 else ''}, and nothing needs catching up.")
        greeting = (f"{opener} With {minutes} minutes, I'd do one thing: {top.action['title']}. "
                    + " ".join(top.reasons[:3])
                    + (f" Where you left it: {top.action['where_left_off']}" if top.action["where_left_off"] else ""))
    return {
        "minutes": minutes, "greeting": greeting, "days_away": days_away,
        "recommended": _option(options[0], db) if options else None,
        "alternatives": [_option(o, db) for o in options[1:]],
        "reminders": reminders,
        "parked_ideas": db.one("SELECT COUNT(*) AS n FROM ideas WHERE state='parked'")["n"],
    }


def options_text(db: Database, settings: Settings, minutes: int) -> str:
    view = today_view(db, settings, minutes)
    opts = ([view["recommended"]] if view["recommended"] else []) + view["alternatives"]
    return "\n".join(f"- {o['action']['title']} ({o['action']['state']}): {' '.join(o['reasons'])}" for o in opts)


# ---- onboarding: scripted, works without AI -------------------------------------------

def onboarding_state(db: Database) -> dict:
    row = db.one("SELECT value FROM kv WHERE key='onboarding_step'")
    step = int(row["value"]) if row else 0
    done = step >= len(ONBOARDING)
    return {"done": done, "step": step, "total": len(ONBOARDING),
            "question": None if done else ONBOARDING[step][1]}


def onboarding_answer(db: Database, text: str) -> dict:
    state = onboarding_state(db)
    if state["done"]:
        return state
    kind = ONBOARDING[state["step"]][0]
    if text.strip():
        store.insert(db, "memory", kind=kind, text=text.strip(), provenance="user_typed")
    db.run("INSERT INTO kv(key,value) VALUES('onboarding_step',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
           (str(state["step"] + 1),))
    return onboarding_state(db)


# ---- chat -----------------------------------------------------------------------------

def _valid_proposal(p) -> dict | None:
    text = p.text.strip()[:500]
    if not text:
        return None
    if p.kind == "memory":
        if p.memory_kind not in store.MEMORY_KINDS:
            return None
        return {"memory_kind": p.memory_kind, "text": text}
    if p.kind == "reminder":
        try:
            due = date.fromisoformat(p.due_on)
        except ValueError:
            due = date.today() + timedelta(days=3)
        return {"text": text, "due_on": due.isoformat()}
    if p.kind == "idea":
        return {"text": text}
    return None


def chat_turn(db: Database, gateway: Gateway, settings: Settings, message: str, import_id: int | None) -> dict:
    session = ensure_session(db)
    import_row = store.get(db, "imports", import_id) if import_id else None
    tainted = int(bool(import_row))
    system, user, meta = context.planning_context(
        db, session, message, import_row, options_text(db, settings, session["minutes"]))
    store.insert(db, "messages", session_id=session["id"], role="user", content=message, has_import=tainted)
    try:
        turn = gateway.call("companion_turn", system, user, CompanionTurn, session_id=session["id"], meta=meta)
    except AIUnavailable as e:
        return {"reply": None, "unavailable": e.reason, "proposals": [], "dropped_proposals": 0}
    assert isinstance(turn, CompanionTurn)
    store.insert(db, "messages", session_id=session["id"], role="assistant", content=turn.reply, has_import=tainted)

    created, dropped = [], 0
    if tainted:
        # Structural rule (D4): a turn that read pasted material cannot propose anything.
        dropped = len(turn.proposals)
        if dropped:
            db.log("proposals_dropped_import_turn", f"count={dropped}")
    else:
        for p in turn.proposals[:MAX_PROPOSALS_PER_TURN]:
            payload = _valid_proposal(p)
            if payload is None:
                dropped += 1
                continue
            created.append(store.insert(db, "proposals", kind=p.kind, payload=payload,
                                        rationale=p.rationale[:300], session_id=session["id"]))
        dropped += max(0, len(turn.proposals) - MAX_PROPOSALS_PER_TURN)
    return {"reply": turn.reply, "unavailable": None, "proposals": created, "dropped_proposals": dropped}


def decide_proposal(db: Database, proposal_id: int, accept: bool) -> dict:
    """Only reachable from an authenticated, CSRF-checked user request."""
    with db.tx():
        p = store.get(db, "proposals", proposal_id)
        if not p or p["state"] != "pending":
            raise store.RuleError("That suggestion was already handled.")
        result = None
        if accept:
            payload = p["payload"]
            if p["kind"] == "memory":
                result = store.insert(db, "memory", kind=payload["memory_kind"], text=payload["text"],
                                      provenance="user_confirmed")
            elif p["kind"] == "reminder":
                result = store.insert(db, "reminders", text=payload["text"], due_on=payload["due_on"])
            elif p["kind"] == "idea":
                result = store.insert(db, "ideas", text=payload["text"])
        store.update(db, "proposals", proposal_id, state="accepted" if accept else "rejected", decided_at=now())
    db.log("proposal_decided", f"id={proposal_id} kind={p['kind']} accepted={accept}")
    return {"proposal": store.get(db, "proposals", proposal_id), "created": result}


# ---- drafting -------------------------------------------------------------------------

def _evidence_map(db: Database) -> dict[int, dict]:
    return {e["id"]: e for e in store.rows(db, "evidence")}


def _note_draft_saved(db: Database, action_id: int | None) -> None:
    """Autosave is allowed to move suggested -> drafted. It never goes further."""
    if not action_id:
        return
    action = store.get(db, "actions", action_id)
    if action and action["state"] == "suggested":
        store.set_action_state(db, action_id, "drafted")


def generate_draft(db: Database, gateway: Gateway, *, action_id: int | None, purpose: str, audience: str,
                   evidence_ids: list[int], instruction: str, shareable_note: str,
                   include_item_context: bool) -> dict:
    action = store.get(db, "actions", action_id) if action_id else None
    ctx = context.draft_context(db, purpose, audience, evidence_ids, instruction, shareable_note,
                                action["item_id"] if action else None, include_item_context)
    session = active_session(db)
    out = gateway.call("draft", ctx.system, ctx.user, DraftOut, session_id=session["id"] if session else None,
                       meta=ctx.meta)
    assert isinstance(out, DraftOut)
    claims = [c.model_dump() for c in out.claims]
    # Validate against the whole library, so a reference to an entry that was held back is caught as such.
    report = validate_draft(out.body, claims, _evidence_map(db), purpose)
    draft = store.insert(db, "drafts", action_id=action_id, purpose=purpose, audience=audience, body=out.body,
                         claims=claims, gaps=[g[:300] for g in out.gaps[:10]], report=report, source="ai")
    _note_draft_saved(db, action_id)
    return {"draft": draft, "excluded_evidence": ctx.excluded}


def save_draft(db: Database, draft_id: int | None, *, action_id: int | None, purpose: str, audience: str,
               body: str) -> dict:
    """Manual writing and autosave. Works with AI off. Re-checks numbers and banned phrases on every save."""
    existing = store.get(db, "drafts", draft_id) if draft_id else None
    claims = existing["claims"] if existing else []
    report = validate_draft(body, claims, _evidence_map(db), purpose)
    if existing:
        draft = store.update(db, "drafts", existing["id"], body=body, report=report, audience=audience)
    else:
        draft = store.insert(db, "drafts", action_id=action_id, purpose=purpose, audience=audience, body=body,
                             claims=[], gaps=[], report=report, source="user")
    _note_draft_saved(db, (existing or {}).get("action_id") or action_id)
    return draft  # type: ignore[return-value]


def run_compare(db: Database, gateway: Gateway, import_id: int) -> dict:
    import_row = store.get(db, "imports", import_id)
    if not import_row:
        raise store.RuleError("No such pasted material.")
    ctx = context.compare_context(db, import_row)
    session = active_session(db)
    out = gateway.call("compare", ctx.system, ctx.user, CompareOut,
                       session_id=session["id"] if session else None, meta=ctx.meta)
    assert isinstance(out, CompareOut)
    known = {e["id"]: e for e in ctx.evidence}
    rows = []
    for r in out.requirements[:8]:
        valid = [i for i in r.evidence_ids if i in known]  # drop ids the model made up
        rows.append({
            "requirement": r.requirement[:300],
            "evidence": [{"id": i, "title": known[i]["title"], "status": known[i]["status"]} for i in valid],
            "invented_ids": [i for i in r.evidence_ids if i not in known],
            "gap": r.gap[:300] if r.gap else ("" if valid else "No supporting evidence."),
        })
    return {"summary": out.summary[:600], "requirements": rows}


# ---- export ---------------------------------------------------------------------------

def export_all(db: Database) -> dict:
    from .db import USER_TABLES

    return {"exported_at": now(), "note": "Everything Career Companion stores, including private notes.",
            "tables": {t: store.rows(db, t, order="rowid ASC") for t in USER_TABLES}}
