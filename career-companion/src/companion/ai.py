"""AI layer (decisions D3, D8, D9, D15).

The model has no tools. Every call returns one schema-validated object. All calls go through
`Gateway`, which enforces the budget before anything is sent.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal, Protocol

import httpx2 as httpx  # the anthropic SDK 2.x is built on httpx2, not httpx
from pydantic import BaseModel

from .budget import MOCK_MODEL, Budget, BudgetBlocked, Usage, estimate_tokens, prices_are_fresh
from .config import Settings
from .db import Database

log = logging.getLogger("companion.ai")

ALLOWED_EGRESS_HOSTS = frozenset({"api.anthropic.com"})
SCHEMA_OVERHEAD_TOKENS = 500  # the API adds a format prompt for structured output


# ---- output schemas (all fields required: keeps the grammar simple) -------------------

class ProposalOut(BaseModel):
    kind: Literal["memory", "reminder", "idea"]
    memory_kind: Literal["goal", "constraint", "preference", "boundary", "voice_note", "drafting_rule", "none"]
    text: str
    due_on: str  # YYYY-MM-DD for reminders, otherwise ""
    rationale: str


class CompanionTurn(BaseModel):
    reply: str
    proposals: list[ProposalOut]


class Claim(BaseModel):
    text: str
    evidence_id: int


class DraftOut(BaseModel):
    body: str
    claims: list[Claim]
    gaps: list[str]


class Requirement(BaseModel):
    requirement: str
    evidence_ids: list[int]
    gap: str


class CompareOut(BaseModel):
    summary: str
    requirements: list[Requirement]


# ---- call profiles --------------------------------------------------------------------

@dataclass(frozen=True)
class Profile:
    model: str
    max_tokens: int  # includes thinking tokens, which bill as output
    effort: str


PROFILES: dict[str, Profile] = {
    "companion_turn": Profile("claude-sonnet-5-5", 1200, "medium"),
    "draft": Profile("claude-sonnet-5-5", 1800, "medium"),
    "compare": Profile("claude-sonnet-5-5", 1800, "medium"),
}
# Cheapest thinking setting each model accepts (verified 2026-11-10).
THINKING: dict[str, dict[str, str]] = {
    "claude-sonnet-5-5": {"type": "between_tools"},
    "claude-haiku-5-5": {"type": "disabled"},
}


@dataclass
class AIRequest:
    call_type: str
    system: str
    user: str
    schema: type[BaseModel]
    max_tokens: int
    model: str
    effort: str
    meta: dict[str, Any] = field(default_factory=dict)  # for the mock only; never sent anywhere


@dataclass
class AIResult:
    parsed: BaseModel | None
    usage: Usage
    stop_reason: str = "end_turn"


class AIClient(Protocol):
    name: str

    def model_for(self, profile: Profile) -> str: ...
    def complete(self, req: AIRequest) -> AIResult: ...


class AIUnavailable(Exception):
    """AI could not be used. `reason` is safe to show. Saved work is unaffected."""

    def __init__(self, reason: str, kind: str = "error"):
        super().__init__(reason)
        self.reason = reason
        self.kind = kind


class NeverSent(Exception):
    """The request provably did not leave this machine, so nothing can have been billed."""


# ---- mock client ----------------------------------------------------------------------

class MockAI:
    """Deterministic stand-in. Every visible reply is labelled as mock output."""

    name = "mock"

    def __init__(self, script: list[Any] | None = None, model: str = MOCK_MODEL,
                 usage: Usage | None = None):
        self.script = list(script or [])  # tests queue results or exceptions here
        self.requests: list[AIRequest] = []
        self.model = model
        self.usage = usage or Usage(input_tokens=900, output_tokens=250)

    def model_for(self, profile: Profile) -> str:
        return self.model

    def complete(self, req: AIRequest) -> AIResult:
        self.requests.append(req)
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            if isinstance(item, AIResult):
                return item
            return AIResult(parsed=item, usage=self.usage)
        return AIResult(parsed=getattr(self, f"_{req.call_type}")(req), usage=self.usage)

    def _companion_turn(self, req: AIRequest) -> CompanionTurn:
        msg = str(req.meta.get("user_message", ""))
        focus = req.meta.get("focus_title") or "what you picked"
        proposals: list[ProposalOut] = []
        low = msg.lower()
        if re.search(r"\b(i prefer|i'd rather|from now on|remember that)\b", low):
            proposals.append(ProposalOut(kind="memory", memory_kind="preference", text=msg[:300], due_on="",
                                         rationale="You stated a lasting preference."))
        if "remind me" in low:
            due = (date.today() + timedelta(days=3)).isoformat()
            proposals.append(ProposalOut(kind="reminder", memory_kind="none", text=msg[:200], due_on=due,
                                         rationale="You asked for a reminder."))
        if low.startswith("idea:"):
            proposals.append(ProposalOut(kind="idea", memory_kind="none", text=msg[5:].strip()[:300], due_on="",
                                         rationale="Parked so it doesn't become an obligation."))
        reply = (f"[mock AI] I'd keep going on \"{focus}\". Tell me what's blocking you, or open the "
                 "draft panel and I'll check the claims against your evidence.")
        if req.meta.get("has_import"):
            reply = "[mock AI] I read the pasted material as reference only. What do you want to do with it?"
        return CompanionTurn(reply=reply, proposals=proposals)

    def _draft(self, req: AIRequest) -> DraftOut:
        ev = req.meta.get("evidence", [])
        lines = ["[MOCK DRAFT, not real AI output]"]
        claims = []
        for e in ev[:3]:
            lines.append(e["claim"])
            claims.append(Claim(text=e["claim"], evidence_id=e["id"]))
        gaps = [] if ev else ["No eligible evidence was selected, so this draft makes no factual claims."]
        return DraftOut(body="\n\n".join(lines), claims=claims, gaps=gaps)

    def _compare(self, req: AIRequest) -> CompareOut:
        ev = req.meta.get("evidence", [])
        reqs = []
        for line in [ln.strip(" -*\t") for ln in str(req.meta.get("material", "")).splitlines() if ln.strip()][:6]:
            words = {w for w in re.findall(r"[a-z]{4,}", line.lower())}
            hits = [e["id"] for e in ev if words & set(re.findall(r"[a-z]{4,}", (e["title"] + " " + e["claim"]).lower()))]
            reqs.append(Requirement(requirement=line[:200], evidence_ids=hits[:3],
                                    gap="" if hits else "No matching evidence yet."))
        return CompareOut(summary="[mock AI] Keyword comparison only.", requirements=reqs)


# ---- live client ----------------------------------------------------------------------

class AllowlistTransport(httpx.BaseTransport):
    """Outbound allowlist. Anything but HTTPS to the provider's API host is refused."""

    def __init__(self, inner: httpx.BaseTransport | None = None):
        self.inner = inner or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.scheme != "https" or request.url.host not in ALLOWED_EGRESS_HOSTS:
            raise NeverSent(f"blocked outbound request to {request.url.host}")
        return self.inner.handle_request(request)


class LiveAI:
    name = "live"

    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None):
        import anthropic  # imported here so mock mode never needs the SDK loaded

        self._client = anthropic.Anthropic(
            api_key=api_key,
            max_retries=0,  # a retry is a second billable request; the gateway meters one call at a time
            http_client=httpx.Client(transport=AllowlistTransport(transport), timeout=90.0, trust_env=False),
        )

    def model_for(self, profile: Profile) -> str:
        return profile.model

    def complete(self, req: AIRequest) -> AIResult:
        extra: dict[str, Any] = {}
        if req.model in THINKING:
            extra["thinking"] = THINKING[req.model]
        resp = self._client.messages.parse(
            model=req.model,
            max_tokens=req.max_tokens,
            system=[{"type": "text", "text": req.system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": req.user}],
            output_format=req.schema,
            output_config={"effort": req.effort},
            **extra,
        )
        u = resp.usage
        usage = Usage(
            input_tokens=u.input_tokens or 0, output_tokens=u.output_tokens or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0)
        parsed = resp.parsed_output if resp.stop_reason == "end_turn" else None
        return AIResult(parsed=parsed, usage=usage, stop_reason=resp.stop_reason or "")


def build_client(settings: Settings) -> tuple[AIClient | None, str]:
    """Return (client, reason). The client is None when AI is off or the live gate fails."""
    if settings.ai_mode == "off":
        return None, "AI is switched off."
    if settings.ai_mode == "mock":
        return MockAI(), "Mock AI: replies are canned and nothing leaves this Mac."
    if not prices_are_fresh():
        return None, "The price table is out of date. Re-verify prices before live AI calls (see README)."
    from .keys import get_api_key

    key = get_api_key()
    if not key:
        return None, "No API key in Keychain. Run `companion set-key`."
    return LiveAI(key), "Live AI: selected text is sent to the model provider."


# ---- gateway --------------------------------------------------------------------------

class Gateway:
    def __init__(self, db: Database, budget: Budget, client: AIClient | None, reason: str):
        self.db, self.budget, self.client, self.reason = db, budget, client, reason

    def availability(self) -> dict:
        if self.client is None:
            return {"available": False, "mode": "off", "reason": self.reason}
        level = self.budget.status()["level"]
        if level == "hard_stop":
            return {"available": False, "mode": self.client.name,
                    "reason": "Monthly AI limit reached. Your saved work is still available."}
        return {"available": True, "mode": self.client.name, "reason": self.reason}

    def call(self, call_type: str, system: str, user: str, schema: type[BaseModel],
             session_id: int | None = None, meta: dict | None = None) -> BaseModel:
        if self.client is None:
            raise AIUnavailable(self.reason, kind="off")
        profile = PROFILES[call_type]
        model = self.client.model_for(profile)
        est_in = estimate_tokens(system) + estimate_tokens(user) + SCHEMA_OVERHEAD_TOKENS
        try:
            ledger_id = self.budget.reserve(call_type, model, est_in, profile.max_tokens, session_id)
        except BudgetBlocked as e:
            self.db.log("ai_blocked_budget", f"type={call_type}")
            raise AIUnavailable(e.reason, kind="budget") from None

        req = AIRequest(call_type, system, user, schema, profile.max_tokens, model, profile.effort, meta or {})
        try:
            result = self.client.complete(req)
        except NeverSent:
            self.budget.release(ledger_id)
            raise AIUnavailable("The request was blocked before it left this Mac.") from None
        except Exception as e:  # outcome unknown: it may have been billed
            self.budget.mark_unknown(ledger_id, type(e).__name__)
            self.db.log("ai_call_failed", f"type={call_type} error={type(e).__name__}")
            log.warning("AI call failed: %s", type(e).__name__)  # class name only, never content
            raise AIUnavailable("The AI service didn't answer. Your work is saved; carry on manually "
                                "or try again.") from None

        cost = self.budget.settle(ledger_id, model, result.usage)
        self.db.log("ai_call", f"type={call_type} model={model} in={result.usage.input_tokens} "
                               f"out={result.usage.output_tokens} cost_usd={cost:.5f}")
        if not isinstance(result.parsed, schema):
            raise AIUnavailable("The AI reply was incomplete or refused, so nothing was changed.")
        return result.parsed
