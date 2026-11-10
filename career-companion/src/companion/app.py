"""HTTP API and static interface. Every /api route sits behind the guard in security.py."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from . import services, store
from .ai import AIClient, AIUnavailable, Gateway, build_client
from .budget import Budget
from .config import Settings
from .db import Database, now
from .security import COOKIE_NAME, Security, make_guard

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("companion")

Short = Field(max_length=300)
Long = Field(default="", max_length=8000)


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TokenIn(In):
    token: str = Field(max_length=200)


class MemoryIn(In):
    kind: Literal[store.MEMORY_KINDS]  # type: ignore[valid-type]
    text: str = Field(min_length=1, max_length=4000)
    audience: str = Field(default="", max_length=60)


class Metric(In):
    value: str = Field(max_length=40)
    unit: str = Field(default="", max_length=40)
    label: str = Field(default="", max_length=200)


class EvidenceIn(In):
    title: str = Field(min_length=1, max_length=200)
    claim: str = Field(min_length=1, max_length=2000)
    metrics: list[Metric] = Field(default_factory=list, max_length=20)
    source_ref: str = Field(default="", max_length=500)
    status: Literal[store.EVIDENCE_STATUSES] = "unverified_user_claim"  # type: ignore[valid-type]
    permitted_uses: list[Literal[store.USES]] = Field(default_factory=list)  # type: ignore[valid-type]
    do_not_claim: str = Field(default="", max_length=1000)
    confidential: bool = False


class ItemIn(In):
    kind: Literal[store.ITEM_KINDS]  # type: ignore[valid-type]
    title: str = Field(min_length=1, max_length=200)
    org: str = Field(default="", max_length=200)
    private_notes: str = Long
    shareable_context: str = Field(default="", max_length=2000)
    status: Literal[store.ITEM_STATUSES] = "active"  # type: ignore[valid-type]


class ActionIn(In):
    item_id: int | None = None
    kind: Literal[store.ACTION_KINDS] = "other"  # type: ignore[valid-type]
    title: str = Field(min_length=1, max_length=200)
    commitment: bool = False
    importance: int = Field(default=2, ge=1, le=3)
    effort_min: int = Field(default=15, ge=5, le=240)
    deadline: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    where_left_off: str = Field(default="", max_length=500)


class StateIn(In):
    state: Literal[store.ACTION_STATES]  # type: ignore[valid-type]


class NoteIn(In):
    where_left_off: str = Field(max_length=500)


class OutcomeIn(In):
    item_id: int
    action_id: int | None = None
    type: Literal[store.OUTCOME_TYPES]  # type: ignore[valid-type]
    note: str = Field(default="", max_length=1000)
    occurred_on: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class ReminderIn(In):
    action_id: int | None = None
    text: str = Field(min_length=1, max_length=300)
    due_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class SnoozeIn(In):
    days: int = Field(ge=1, le=30)


class TextIn(In):
    text: str = Field(default="", max_length=4000)


class ImportIn(In):
    kind: Literal[store.IMPORT_KINDS]  # type: ignore[valid-type]
    label: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=60_000)


class ChatIn(In):
    message: str = Field(min_length=1, max_length=4000)
    import_id: int | None = None


class SessionIn(In):
    minutes: int = Field(default=20, ge=5, le=120)
    action_id: int | None = None


Purpose = Literal["profile", "application", "outreach", "follow_up", "post", "interview_prep"]


class DraftGenIn(In):
    action_id: int | None = None
    purpose: Purpose
    audience: str = Field(default="", max_length=60)
    evidence_ids: list[int] = Field(default_factory=list, max_length=12)
    instruction: str = Field(default="", max_length=1500)
    shareable_note: str = Field(default="", max_length=1500)
    include_item_context: bool = False


class DraftSaveIn(In):
    draft_id: int | None = None
    action_id: int | None = None
    purpose: Purpose
    audience: str = Field(default="", max_length=60)
    body: str = Field(max_length=20_000)


class CompareIn(In):
    import_id: int


class ReconcileIn(In):
    console_total_usd: float = Field(ge=0, le=10_000)


class WipeIn(In):
    confirm: Literal["DELETE EVERYTHING"]


def create_app(settings: Settings, ai_client: AIClient | None = None) -> FastAPI:
    db = Database(settings.db_path)
    store.purge_old_messages(db, settings.transcript_days)
    security = Security(settings.port)
    budget = Budget(db, settings)
    if ai_client is not None:
        client, reason = ai_client, "Injected client."
    else:
        client, reason = build_client(settings)
    if client is not None and client.name == "mock":
        reason = "Mock AI: replies are canned and nothing leaves this Mac."
    gateway = Gateway(db, budget, client, reason)

    app = FastAPI(title="Career Companion", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db, app.state.security, app.state.budget, app.state.gateway = db, security, budget, gateway
    app.state.settings = settings
    app.middleware("http")(make_guard(security))
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.exception_handler(store.RuleError)
    async def rule_error(_: Request, exc: store.RuleError) -> JSONResponse:
        return JSONResponse({"error": str(exc)}, status_code=422)

    @app.exception_handler(AIUnavailable)
    async def ai_unavailable(_: Request, exc: AIUnavailable) -> JSONResponse:
        return JSONResponse({"error": exc.reason, "ai_unavailable": True, "kind": exc.kind}, status_code=503)

    def need(table: str, row_id: int) -> dict:
        row = store.get(db, table, row_id)
        if not row:
            raise HTTPException(404, "not found")
        return row

    # ---- shell and sign-in ------------------------------------------------------------
    @app.get("/")
    def index(request: Request) -> Response:
        signed_in = security.csrf_for(request.cookies.get(COOKIE_NAME)) is not None
        return FileResponse(STATIC / ("index.html" if signed_in else "login.html"))

    @app.post("/auth/exchange")
    def exchange(body: TokenIn) -> Response:
        pair = security.exchange(body.token)
        if not pair:
            return JSONResponse({"error": "That link was already used or is wrong. Restart the app for a new one."},
                                status_code=403)
        resp = JSONResponse({"ok": True})
        resp.set_cookie(COOKIE_NAME, pair[0], httponly=True, samesite="strict", path="/")
        return resp

    @app.get("/api/bootstrap")
    def bootstrap(request: Request) -> dict:
        return {"csrf": security.csrf_for(request.cookies.get(COOKIE_NAME)), "ai": gateway.availability(),
                "budget": budget.status(), "onboarding": services.onboarding_state(db),
                "has_sample": bool(db.one("SELECT 1 FROM evidence WHERE is_sample=1 UNION SELECT 1 FROM actions WHERE is_sample=1")),
                "enums": {"memory_private": store.PRIVATE_MEMORY_KINDS, "memory_public": store.PUBLIC_VOICE_KINDS,
                          "uses": store.USES, "evidence_statuses": store.EVIDENCE_STATUSES,
                          "action_kinds": store.ACTION_KINDS, "outcome_types": store.OUTCOME_TYPES,
                          "import_kinds": store.IMPORT_KINDS}}

    # ---- today, sessions, onboarding, chat --------------------------------------------
    @app.get("/api/today")
    def today(minutes: int = 20) -> dict:
        return services.today_view(db, settings, max(5, min(120, minutes)))

    @app.post("/api/session/start")
    def session_start(body: SessionIn) -> dict:
        if body.action_id:
            need("actions", body.action_id)
        return services.start_session(db, body.minutes, body.action_id)

    @app.post("/api/session/end")
    def session_end() -> dict:
        services.end_session(db)
        return {"ok": True}

    @app.post("/api/onboarding/answer")
    def onboarding_answer(body: TextIn) -> dict:
        return services.onboarding_answer(db, body.text)

    @app.post("/api/chat")
    def chat(body: ChatIn) -> dict:
        if body.import_id:
            need("imports", body.import_id)
        return services.chat_turn(db, gateway, settings, body.message, body.import_id)

    @app.get("/api/proposals")
    def proposals() -> list[dict]:
        return store.rows(db, "proposals", "state='pending'")

    @app.post("/api/proposals/{pid}/{decision}")
    def proposal_decide(pid: int, decision: Literal["accept", "reject"]) -> dict:
        return services.decide_proposal(db, pid, decision == "accept")

    # ---- memory -----------------------------------------------------------------------
    @app.get("/api/memory")
    def memory_list() -> list[dict]:
        return store.rows(db, "memory", order="kind ASC, id ASC")

    @app.post("/api/memory")
    def memory_add(body: MemoryIn) -> dict:
        return store.insert(db, "memory", provenance="user_typed", **body.model_dump())

    @app.put("/api/memory/{mid}")
    def memory_edit(mid: int, body: MemoryIn) -> dict:
        need("memory", mid)
        return store.update(db, "memory", mid, provenance="user_typed", **body.model_dump())  # type: ignore[return-value]

    @app.delete("/api/memory/{mid}")
    def memory_delete(mid: int) -> dict:
        db.log("memory_deleted", f"id={mid}")
        return {"deleted": store.delete(db, "memory", mid)}

    # ---- evidence ---------------------------------------------------------------------
    @app.get("/api/evidence")
    def evidence_list() -> list[dict]:
        return store.rows(db, "evidence")

    @app.post("/api/evidence")
    def evidence_add(body: EvidenceIn) -> dict:
        fields = body.model_dump()
        store.check_evidence(fields)
        return store.insert(db, "evidence", provenance="user_typed", **fields)

    @app.put("/api/evidence/{eid}")
    def evidence_edit(eid: int, body: EvidenceIn) -> dict:
        need("evidence", eid)
        fields = body.model_dump()
        store.check_evidence(fields)
        return store.update(db, "evidence", eid, is_sample=0, **fields)  # type: ignore[return-value]

    @app.delete("/api/evidence/{eid}")
    def evidence_delete(eid: int) -> dict:
        return {"deleted": store.delete(db, "evidence", eid)}

    # ---- opportunities and relationships ----------------------------------------------
    @app.get("/api/items")
    def items_list() -> list[dict]:
        items = store.rows(db, "items", order="status ASC, id DESC")
        for it in items:
            it["outcomes"] = store.rows(db, "outcomes", "item_id=?", (it["id"],))
            it["actions"] = store.rows(db, "actions", "item_id=?", (it["id"],))
        return items

    @app.post("/api/items")
    def item_add(body: ItemIn) -> dict:
        return store.insert(db, "items", **body.model_dump())

    @app.put("/api/items/{iid}")
    def item_edit(iid: int, body: ItemIn) -> dict:
        need("items", iid)
        return store.update(db, "items", iid, is_sample=0, **body.model_dump())  # type: ignore[return-value]

    @app.delete("/api/items/{iid}")
    def item_delete(iid: int) -> dict:
        return {"deleted": store.delete(db, "items", iid)}

    # ---- actions ----------------------------------------------------------------------
    @app.get("/api/actions")
    def actions_list() -> list[dict]:
        return store.rows(db, "actions")

    @app.post("/api/actions")
    def action_add(body: ActionIn) -> dict:
        if body.item_id:
            need("items", body.item_id)
        fields = body.model_dump()
        fields["where_left_off"] = fields["where_left_off"] or "Not started."
        return store.insert(db, "actions", **fields)

    @app.put("/api/actions/{aid}")
    def action_edit(aid: int, body: ActionIn) -> dict:
        need("actions", aid)
        return store.update(db, "actions", aid, is_sample=0, **body.model_dump())  # type: ignore[return-value]

    @app.post("/api/actions/{aid}/state")
    def action_state(aid: int, body: StateIn) -> dict:
        return store.set_action_state(db, aid, body.state)

    @app.post("/api/actions/{aid}/note")
    def action_note(aid: int, body: NoteIn) -> dict:
        need("actions", aid)
        return store.update(db, "actions", aid, where_left_off=body.where_left_off)  # type: ignore[return-value]

    @app.delete("/api/actions/{aid}")
    def action_delete(aid: int) -> dict:
        return {"deleted": store.delete(db, "actions", aid)}

    # ---- outcomes, reminders, ideas ---------------------------------------------------
    @app.post("/api/outcomes")
    def outcome_add(body: OutcomeIn) -> dict:
        need("items", body.item_id)
        fields = body.model_dump()
        fields["occurred_on"] = fields["occurred_on"] or services.local_today(settings).isoformat()
        return store.insert(db, "outcomes", **fields)

    @app.delete("/api/outcomes/{oid}")
    def outcome_delete(oid: int) -> dict:
        return {"deleted": store.delete(db, "outcomes", oid)}

    @app.get("/api/reminders")
    def reminders_list() -> list[dict]:
        return store.rows(db, "reminders", "state='pending'", order="due_on ASC")

    @app.post("/api/reminders")
    def reminder_add(body: ReminderIn) -> dict:
        if body.action_id:
            need("actions", body.action_id)
        return store.insert(db, "reminders", **body.model_dump())

    @app.post("/api/reminders/{rid}/done")
    def reminder_done(rid: int) -> dict:
        need("reminders", rid)
        return store.update(db, "reminders", rid, state="done")  # type: ignore[return-value]

    @app.post("/api/reminders/{rid}/snooze")
    def reminder_snooze(rid: int, body: SnoozeIn) -> dict:
        from datetime import timedelta

        need("reminders", rid)
        due = (services.local_today(settings) + timedelta(days=body.days)).isoformat()
        return store.update(db, "reminders", rid, due_on=due)  # type: ignore[return-value]

    @app.get("/api/ideas")
    def ideas_list() -> list[dict]:
        return store.rows(db, "ideas", "state='parked'")

    @app.post("/api/ideas")
    def idea_add(body: TextIn) -> dict:
        if not body.text:
            raise HTTPException(422, "empty")
        return store.insert(db, "ideas", text=body.text)

    @app.post("/api/ideas/{iid}/{what}")
    def idea_decide(iid: int, what: Literal["promote", "drop"]) -> dict:
        idea = need("ideas", iid)
        action = None
        if what == "promote":  # the user's click is what turns an idea into work
            action = store.insert(db, "actions", kind="other", title=idea["text"][:200], where_left_off="Not started.")
        store.update(db, "ideas", iid, state="promoted" if what == "promote" else "dropped")
        return {"action": action}

    # ---- pasted material, drafts, comparison ------------------------------------------
    @app.get("/api/imports")
    def imports_list() -> list[dict]:
        return [{**r, "content": r["content"][:300], "length": len(r["content"])} for r in store.rows(db, "imports")]

    @app.post("/api/imports")
    def import_add(body: ImportIn) -> dict:
        row = store.insert(db, "imports", **body.model_dump())
        db.log("import_added", f"id={row['id']} kind={row['kind']} chars={len(row['content'])}")
        return {**row, "content": row["content"][:300], "length": len(row["content"])}

    @app.delete("/api/imports/{iid}")
    def import_delete(iid: int) -> dict:
        return {"deleted": store.delete(db, "imports", iid)}

    @app.get("/api/drafts")
    def drafts_list(action_id: int | None = None) -> list[dict]:
        if action_id is None:
            return store.rows(db, "drafts", order="updated_at DESC, id DESC")
        return store.rows(db, "drafts", "action_id=?", (action_id,), "updated_at DESC, id DESC")

    @app.post("/api/drafts/generate")
    def draft_generate(body: DraftGenIn) -> dict:
        if body.action_id:
            need("actions", body.action_id)
        return services.generate_draft(db, gateway, **body.model_dump())

    @app.post("/api/drafts/save")
    def draft_save(body: DraftSaveIn) -> dict:
        if body.draft_id:
            need("drafts", body.draft_id)
        return services.save_draft(db, body.draft_id, action_id=body.action_id, purpose=body.purpose,
                                   audience=body.audience, body=body.body)

    @app.post("/api/drafts/{did}/copied")
    def draft_copied(did: int) -> dict:
        """Copying is recorded as activity only. It never changes any state (D12)."""
        need("drafts", did)
        db.log("draft_copied", f"id={did}")
        return {"ok": True}

    @app.delete("/api/drafts/{did}")
    def draft_delete(did: int) -> dict:
        return {"deleted": store.delete(db, "drafts", did)}

    @app.post("/api/compare")
    def compare(body: CompareIn) -> dict:
        return services.run_compare(db, gateway, body.import_id)

    # ---- budget, activity, data -------------------------------------------------------
    @app.get("/api/budget")
    def budget_status() -> dict:
        return {"status": budget.status(), "ai": gateway.availability(),
                "recent": db.q("SELECT ts,call_type,model,status,reserved_usd,cost_usd,in_tok,out_tok,note "
                               "FROM ledger ORDER BY id DESC LIMIT 25")}

    @app.post("/api/budget/reconcile")
    def budget_reconcile(body: ReconcileIn) -> dict:
        return budget.reconcile(body.console_total_usd)

    @app.get("/api/activity")
    def activity() -> list[dict]:
        return db.q("SELECT ts,event,detail FROM activity ORDER BY id DESC LIMIT 100")

    @app.get("/api/export")
    def export() -> Response:
        db.log("export")
        return Response(json.dumps(services.export_all(db), indent=1), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="career-companion-export.json"'})

    @app.post("/api/sample/{what}")
    def sample(what: Literal["load", "remove"]) -> dict:
        if what == "load":
            store.load_sample(db, services.local_today(settings))
        else:
            store.remove_sample(db)
        return {"ok": True}

    @app.post("/api/wipe")
    def wipe(body: WipeIn) -> dict:
        # Spend already committed this month survives the wipe, so deleting data can't reset the cap.
        carried = budget.month_committed()
        db.wipe()
        if carried > 0:
            status = budget.status()
            db.run("INSERT INTO ledger(ts,month,day,call_type,model,status,cost_usd,note) "
                   "VALUES(?,?,'','carried','-','adjustment',?,'spend carried over a data wipe')",
                   (now(), status["month"], carried))
        db.log("wiped")
        return {"ok": True}

    return app
