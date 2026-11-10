"""Claim checks for drafts (decision D6).

Machine-checked: evidence IDs exist and are permitted for the use; numbers match the evidence
in value and in unit; banned phrases are absent; numbers in the body are traceable.
Flagged for a human, not decided by code: strong wording the evidence does not contain.
Not checked at all: whether a paraphrase subtly overstates. The report says so.
"""

from __future__ import annotations

import re
from typing import Any

from .store import PURPOSE_TO_USE

BLOCK, REVIEW = "block", "review"

_NUM = re.compile(r"(?<![\w.])(\$)?(\d[\d,]*(?:\.\d+)?)\s?(%|percent\b|[kKmM]\b|[xX]\b)?")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_FILLER = {"of", "the", "a", "an", "in", "on", "for", "to", "and", "or", "over", "about", "than", "more",
           "different", "distinct", "unique", "total", "new", "key", "main", "major", "plus", "with", "by", "at"}
_UNIT_ALIASES = {"percent": "%", "percentage": "%", "pct": "%", "dollar": "$", "usd": "$", "hr": "hour", "hrs": "hour",
                 "min": "minute", "mins": "minute"}
# Words that assert impact, seniority, or scale. If the evidence doesn't use them, a human should look.
STRONG_WORDS = (
    "led", "lead", "managed", "spearheaded", "drove", "increased", "improved", "reduced", "boosted", "grew",
    "saved", "cut", "optimized", "expert", "advanced", "extensive", "proven", "significant", "significantly",
    "production", "enterprise", "scalable", "award", "published", "certified", "senior", "architected", "first",
    "best", "fastest", "leading", "revenue", "customers", "clients", "users",
)
NOT_CHECKED = ("Not checked by the app: whether the wording overstates what the evidence supports. "
               "Read every claim before you use it.")
CHECKED = ["evidence reference exists", "evidence is permitted for this use", "numbers match value and unit",
           "banned phrases absent", "numbers in the text are traceable", "strong wording flagged for review"]


def _unit(word: str) -> str:
    w = word.lower().strip("'-")
    w = _UNIT_ALIASES.get(w, w)
    if len(w) > 3 and w.endswith("ies"):
        w = w[:-3] + "y"
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return _UNIT_ALIASES.get(w, w)


def quantities(text: str) -> list[dict[str, Any]]:
    """Numbers in `text`, each with the units that give it meaning (symbol and following words)."""
    found = []
    for m in _NUM.finditer(text or ""):
        raw = m.group(2).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        suffix = (m.group(3) or "").lower()
        units: set[str] = set()
        if m.group(1):
            units.add("$")
        if suffix in ("%", "percent"):
            units.add("%")
        elif suffix == "k":
            value *= 1_000
        elif suffix == "m":
            value *= 1_000_000
        elif suffix == "x":
            units.add("x")
        if not units and not suffix and value.is_integer() and 1900 <= value <= 2100 and "," not in m.group(2):
            continue  # a bare year is a date, not a metric
        following = [w for w in _WORD.findall(text[m.end(): m.end() + 60])][:5]
        units |= {_unit(w) for w in [w for w in following if w.lower() not in _FILLER][:2]}
        found.append({"value": value, "units": units, "text": m.group(0).strip()})
    return found


def _evidence_quantities(ev: dict) -> list[dict[str, Any]]:
    out = quantities(ev.get("claim", ""))
    for metric in ev.get("metrics", []):
        for q in quantities(str(metric.get("value", ""))):
            unit_words = {_unit(w) for w in _WORD.findall(str(metric.get("unit", "")))}
            if "%" in str(metric.get("unit", "")):
                unit_words.add("%")
            if "$" in str(metric.get("unit", "")):
                unit_words.add("$")
            out.append({"value": q["value"], "units": q["units"] | unit_words, "text": q["text"]})
    return out


def _check_number(q: dict, pool: list[dict]) -> str | None:
    """None if supported; otherwise an issue code."""
    same_value = [p for p in pool if abs(p["value"] - q["value"]) < 1e-9]
    if not same_value:
        return "number_not_in_evidence"
    for p in same_value:
        if not p["units"] or (q["units"] & p["units"]):
            return None
    return "number_meaning_differs"


def _banned(ev: dict) -> list[str]:
    return [p.strip().lower() for p in re.split(r"[;\n]", ev.get("do_not_claim", "")) if p.strip()]


def _has_phrase(phrase: str, text: str) -> bool:
    """Whole-word match, so a banned "led" does not fire on "knowledge"."""
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text, flags=re.IGNORECASE) is not None


def _issue(code: str, severity: str, message: str) -> dict:
    return {"code": code, "severity": severity, "message": message}


def _strong_words(text: str, supported_text: str) -> list[str]:
    have = set(re.findall(r"[a-z]+", supported_text.lower()))
    return sorted({w for w in re.findall(r"[a-z]+", text.lower()) if w in STRONG_WORDS and w not in have})


def validate_draft(body: str, claims: list[dict], evidence_by_id: dict[int, dict], purpose: str) -> dict:
    use = PURPOSE_TO_USE.get(purpose, purpose)
    report_claims, linked = [], []
    for claim in claims:
        text, eid = str(claim.get("text", "")), claim.get("evidence_id")
        issues = []
        ev = evidence_by_id.get(eid) if isinstance(eid, int) else None
        if ev is None:
            issues.append(_issue("unknown_evidence", BLOCK, "This claim points to evidence that doesn't exist."))
        else:
            linked.append(ev)
            if ev["status"] == "do_not_claim":
                issues.append(_issue("do_not_claim", BLOCK, "You marked this evidence as do-not-claim."))
            if ev["confidential"]:
                issues.append(_issue("confidential", BLOCK, "This evidence is marked confidential."))
            if use not in ev["permitted_uses"]:
                issues.append(_issue("not_permitted", BLOCK, f"This evidence isn't approved for {use} use."))
            if ev["status"] == "unverified_user_claim":
                issues.append(_issue("unverified_evidence", REVIEW,
                                     "The evidence is your own unverified claim. Confirm it before relying on it."))
            pool = _evidence_quantities(ev)
            for q in quantities(text):
                code = _check_number(q, pool)
                if code == "number_not_in_evidence":
                    issues.append(_issue(code, BLOCK, f"\"{q['text']}\" is not in the evidence."))
                elif code:
                    issues.append(_issue(code, REVIEW, f"\"{q['text']}\" appears in the evidence, but "
                                                       "attached to something else. Check what it measures."))
            for phrase in _banned(ev):
                if _has_phrase(phrase, text):
                    issues.append(_issue("banned_phrase", BLOCK, f"Uses a phrase you banned: \"{phrase}\"."))
            strong = _strong_words(text, f"{ev['title']} {ev['claim']} " +
                                   " ".join(str(m.get("label", "")) for m in ev["metrics"]))
            if strong:
                issues.append(_issue("strong_wording", REVIEW, "Stronger wording than the evidence: "
                                     + ", ".join(strong) + ". Decide whether it's fair."))
        if text and " ".join(text.lower().split()) not in " ".join(body.lower().split()):
            issues.append(_issue("claim_not_in_body", REVIEW, "This tagged claim no longer appears in the text."))
        report_claims.append({"text": text, "evidence_id": eid, "issues": issues,
                              "evidence_status": ev["status"] if ev else None})

    body_issues = []
    pool = [q for ev in linked for q in _evidence_quantities(ev)]
    seen = set()
    for q in quantities(body):
        if q["text"] in seen:
            continue
        seen.add(q["text"])
        if _check_number(q, pool) is not None:
            body_issues.append(_issue("untracked_number", REVIEW,
                                      f"\"{q['text']}\" in the text isn't backed by the linked evidence."))
    for ev in linked:
        for phrase in _banned(ev):
            if _has_phrase(phrase, body):
                body_issues.append(_issue("banned_phrase", BLOCK, f"The text uses a phrase you banned: \"{phrase}\"."))
    tagged = " ".join(c["text"] for c in report_claims)
    untagged_strong = _strong_words(body, tagged + " " + " ".join(f"{e['title']} {e['claim']}" for e in linked))
    if untagged_strong:
        body_issues.append(_issue("strong_wording", REVIEW, "Untagged strong wording in the text: "
                                  + ", ".join(untagged_strong) + "."))

    severities = {i["severity"] for c in report_claims for i in c["issues"]} | {i["severity"] for i in body_issues}
    overall = "blocked" if BLOCK in severities else "review" if REVIEW in severities else "passed"
    return {"overall": overall, "claims": report_claims, "body_issues": body_issues,
            "checked": CHECKED, "not_checked": NOT_CHECKED}
