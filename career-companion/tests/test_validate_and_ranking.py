from datetime import date, timedelta

from companion.ranking import rank
from companion.validate import quantities, validate_draft

TODAY = date(2026, 11, 10)


def ev(**kw):
    base = {"id": 1, "title": "Synthetic dashboard", "claim": "Built a dashboard that groups customers into 4 segments.",
            "metrics": [{"value": "4", "unit": "segments", "label": "customer groups"},
                        {"value": "12", "unit": "%", "label": "sample share of top group"}],
            "status": "user_verified_with_artifact", "permitted_uses": ["outreach", "profile"],
            "do_not_claim": "production system; increased revenue", "confidential": 0}
    return {**base, **kw}


def check(body, claims=None, evidence=None, purpose="outreach"):
    e = evidence or ev()
    claims = claims if claims is not None else [{"text": body, "evidence_id": e["id"]}]
    return validate_draft(body, claims, {e["id"]: e}, purpose)


def codes(report):
    return [i["code"] for c in report["claims"] for i in c["issues"]] + [i["code"] for i in report["body_issues"]]


# ---- numbers --------------------------------------------------------------------------

def test_quantity_extraction_understands_units_and_skips_years():
    q = {x["text"]: x for x in quantities("In 2025 I cut 12% of costs, saved $3,500 and built 4 customer segments, 10k rows")}
    assert "2025" not in q
    assert q["12%"]["units"] >= {"%"}
    assert q["$3,500"]["value"] == 3500 and "$" in q["$3,500"]["units"]
    assert "segment" in q["4"]["units"] or "customer" in q["4"]["units"]
    assert q["10k"]["value"] == 10_000


def test_supported_claim_passes():
    r = check("Built a dashboard that groups customers into 4 segments.")
    assert r["overall"] == "passed" and codes(r) == []


def test_number_absent_from_evidence_blocks():
    r = check("Built a dashboard with 9 segments.")
    assert r["overall"] == "blocked" and "number_not_in_evidence" in codes(r)


def test_right_number_wrong_meaning_is_flagged():
    """4 segments is in the evidence; '4 clients' reuses the number for something else."""
    r = check("Delivered the dashboard to 4 clients.")
    assert "number_meaning_differs" in codes(r) and r["overall"] != "passed"


def test_percent_must_stay_a_percent():
    assert "number_meaning_differs" in codes(check("The top group has 12 customers."))
    assert codes(check("The top group is 12% of the sample share.")) == []


def test_untagged_number_in_body_is_flagged():
    r = check("I built a dashboard. It served 500 users.", claims=[{"text": "I built a dashboard.", "evidence_id": 1}])
    assert "untracked_number" in codes(r) and r["overall"] == "review"


# ---- references and permissions -------------------------------------------------------

def test_unknown_evidence_blocks():
    r = validate_draft("x", [{"text": "x", "evidence_id": 99}], {}, "outreach")
    assert r["overall"] == "blocked" and codes(r) == ["unknown_evidence"]


def test_do_not_claim_confidential_and_wrong_use_block():
    assert "do_not_claim" in codes(check("Built a dashboard.", evidence=ev(status="do_not_claim")))
    assert "confidential" in codes(check("Built a dashboard.", evidence=ev(confidential=1)))
    assert "not_permitted" in codes(check("Built a dashboard.", purpose="post"))


def test_banned_phrase_blocks_in_claim_and_in_body():
    assert "banned_phrase" in codes(check("Built a production system dashboard."))
    r = check("Built a dashboard. It increased revenue.", claims=[{"text": "Built a dashboard.", "evidence_id": 1}])
    assert "banned_phrase" in codes(r) and r["overall"] == "blocked"


def test_banned_phrase_matches_whole_words_only():
    e = ev(claim="Contributed using knowledge graphs.", do_not_claim="led; graph", metrics=[])
    assert "banned_phrase" not in codes(check("Contributed using knowledge graphs.", evidence=e))
    assert "banned_phrase" in codes(check("Led the work using knowledge graphs.", evidence=e))


def test_unverified_evidence_needs_review():
    r = check("Built a dashboard.", evidence=ev(status="unverified_user_claim"))
    assert r["overall"] == "review" and "unverified_evidence" in codes(r)


# ---- overclaims -----------------------------------------------------------------------

def test_strong_wording_not_in_evidence_is_flagged_for_a_human():
    r = check("Led an enterprise dashboard that significantly improved retention.")
    issue = [i for c in r["claims"] for i in c["issues"] if i["code"] == "strong_wording"][0]
    assert issue["severity"] == "review"
    for word in ("led", "enterprise", "significantly", "improved"):
        assert word in issue["message"]


def test_report_states_what_is_not_checked():
    r = check("Built a dashboard that groups customers into 4 segments.")
    assert "Not checked" in r["not_checked"] and r["checked"]


def test_edited_out_claim_is_reported():
    r = check("Something else entirely.", claims=[{"text": "Built a dashboard.", "evidence_id": 1}])
    assert "claim_not_in_body" in codes(r)


# ---- ranking --------------------------------------------------------------------------

def action(i, **kw):
    base = {"id": i, "title": f"a{i}", "state": "suggested", "commitment": 0, "importance": 2,
            "effort_min": 15, "deadline": None, "item_id": None}
    return {**base, **kw}


def ids(options):
    return [o.action["id"] for o in options]


def test_at_most_three_options_and_closed_actions_excluded():
    acts = [action(i) for i in range(1, 7)] + [action(7, state="done", importance=3), action(8, state="dropped")]
    out = rank(acts, 20, TODAY)
    assert len(out) == 3 and 7 not in ids(out) and 8 not in ids(out)


def test_overdue_beats_everything():
    acts = [action(1, importance=3, commitment=1),
            action(2, importance=1, deadline=(TODAY - timedelta(days=1)).isoformat())]
    out = rank(acts, 20, TODAY)
    assert ids(out)[0] == 2 and "Overdue" in out[0].reasons[0]


def test_existing_commitment_beats_a_more_important_new_idea():
    acts = [action(1, importance=3), action(2, importance=1, commitment=1)]
    assert ids(rank(acts, 20, TODAY))[0] == 2


def test_started_work_beats_unstarted_work():
    acts = [action(1, importance=2), action(2, importance=2, state="drafted")]
    assert ids(rank(acts, 20, TODAY))[0] == 2


def test_importance_breaks_ties_among_commitments():
    acts = [action(1, commitment=1, importance=1), action(2, commitment=1, importance=3)]
    assert ids(rank(acts, 20, TODAY))[0] == 2


def test_fit_to_available_time_and_reasons():
    acts = [action(1, commitment=1, effort_min=60), action(2, commitment=1, effort_min=10)]
    out = rank(acts, 15, TODAY)
    assert ids(out)[0] == 2
    assert any("Fits your 15 minutes" in r for r in out[0].reasons)
    assert any("save your place" in r for r in out[1].reasons)


def test_ranking_is_deterministic():
    acts = [action(i, commitment=i % 2, importance=1 + i % 3) for i in range(1, 9)]
    assert ids(rank(acts, 20, TODAY)) == ids(rank(list(reversed(acts)), 20, TODAY))
