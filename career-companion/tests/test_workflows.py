"""End-to-end behaviour through the HTTP API, with the mock AI. Synthetic data only."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from companion.ai import MockAI
from companion.app import create_app
from companion.budget import Usage
from companion.security import COOKIE_NAME, CSRF_HEADER
from tests.conftest import BASE


def signed_in(app):
    sid, csrf = app.state.security.new_session_for_tests()
    c = TestClient(app, base_url=BASE, headers={CSRF_HEADER: csrf, "origin": BASE})
    c.cookies.set(COOKIE_NAME, sid)
    return c


def make_action(client, **kw):
    return client.post("/api/actions", json={"title": "Synthetic follow-up", "kind": "follow_up", **kw}).json()


def evidence(client, **kw):
    body = {"title": "Synthetic project", "claim": "Built a report with 3 charts.", "permitted_uses": ["outreach"],
            "metrics": [{"value": "3", "unit": "charts"}], **kw}
    return client.post("/api/evidence", json=body)


# ---- onboarding and preferences -------------------------------------------------------

def test_short_onboarding_stores_answers_without_ai(settings):
    settings.ai_mode = "off"
    client = signed_in(create_app(settings))
    state = client.get("/api/bootstrap").json()["onboarding"]
    assert state["step"] == 0 and state["total"] == 4 and not state["done"]
    for answer in ("Synthetic goal", "", "Be blunt", "Never mention X"):  # one question skipped
        state = client.post("/api/onboarding/answer", json={"text": answer}).json()
    assert state["done"]
    kinds = [m["kind"] for m in client.get("/api/memory").json()]
    assert sorted(kinds) == ["boundary", "goal", "preference"]


def test_preferences_can_be_corrected_in_conversation_and_edited_directly(client):
    r = client.post("/api/chat", json={"message": "From now on I prefer mornings"}).json()
    created = client.post(f"/api/proposals/{r['proposals'][0]['id']}/accept", json={}).json()["created"]
    assert created["kind"] == "preference"
    edited = client.put(f"/api/memory/{created['id']}", json={"kind": "preference", "text": "Evenings, actually"}).json()
    assert edited["text"] == "Evenings, actually"
    assert client.delete(f"/api/memory/{created['id']}").json()["deleted"]
    assert client.get("/api/memory").json() == []


# ---- completion states ----------------------------------------------------------------

def test_copying_or_saving_a_draft_never_marks_it_sent(client):
    ev = evidence(client).json()
    action = make_action(client)
    draft = client.post("/api/drafts/generate", json={"action_id": action["id"], "purpose": "outreach",
                                                      "evidence_ids": [ev["id"]]}).json()["draft"]
    state = lambda: [a for a in client.get("/api/actions").json() if a["id"] == action["id"]][0]["state"]
    assert state() == "drafted"                      # autosave may do this much
    assert client.post(f"/api/drafts/{draft['id']}/copied", json={}).status_code == 200
    client.post("/api/drafts/save", json={"draft_id": draft["id"], "purpose": "outreach", "body": "edited"})
    assert state() == "drafted"                      # copy and edit change nothing
    client.post(f"/api/actions/{action['id']}/state", json={"state": "reviewed"})
    assert state() == "reviewed"
    done = client.post(f"/api/actions/{action['id']}/state", json={"state": "done"}).json()
    assert done["state"] == "done" and done["completed_at"]
    assert client.post(f"/api/actions/{action['id']}/state", json={"state": "reviewed"}).json()["completed_at"] is None


def test_invalid_state_jump_is_refused(client):
    action = make_action(client)
    client.post(f"/api/actions/{action['id']}/state", json={"state": "dropped"})
    assert client.post(f"/api/actions/{action['id']}/state", json={"state": "done"}).status_code == 422


def test_draft_report_separates_supported_claims_from_gaps(client):
    ev = evidence(client).json()
    d = client.post("/api/drafts/generate", json={"purpose": "outreach", "evidence_ids": [ev["id"]]}).json()["draft"]
    assert d["claims"][0]["evidence_id"] == ev["id"]
    assert d["report"]["overall"] == "review"        # evidence is an unverified user claim
    empty = client.post("/api/drafts/generate", json={"purpose": "outreach", "evidence_ids": []}).json()["draft"]
    assert empty["claims"] == [] and empty["gaps"]


def test_manual_edit_is_rechecked(client):
    ev = evidence(client).json()
    d = client.post("/api/drafts/generate", json={"purpose": "outreach", "evidence_ids": [ev["id"]]}).json()["draft"]
    saved = client.post("/api/drafts/save", json={"draft_id": d["id"], "purpose": "outreach",
                                                  "body": d["body"] + " It reached 900 users."}).json()
    assert "untracked_number" in [i["code"] for i in saved["report"]["body_issues"]]


def test_verified_evidence_requires_a_source(client):
    assert evidence(client, status="user_verified_with_artifact").status_code == 422
    assert evidence(client, status="user_verified_with_artifact", source_ref="repo link").status_code == 200


# ---- today view: one recommendation, alternatives, resume note ------------------------

def test_today_opens_on_one_recommendation_with_alternatives(client):
    soon = (date.today() + timedelta(days=1)).isoformat()
    make_action(client, title="Idea A")
    promised = make_action(client, title="Promised follow-up", commitment=True, deadline=soon, effort_min=10)
    make_action(client, title="Idea B")
    make_action(client, title="Idea C")
    view = client.get("/api/today?minutes=15").json()
    assert view["recommended"]["action"]["id"] == promised["id"]
    assert len(view["alternatives"]) == 2
    assert "Promised follow-up" in view["greeting"] and view["recommended"]["reasons"]


def test_resume_note_survives_and_is_shown(client):
    a = make_action(client, commitment=True)
    client.post(f"/api/actions/{a['id']}/note", json={"where_left_off": "Wrote two lines, need the closing ask."})
    view = client.get("/api/today").json()
    assert "need the closing ask" in view["greeting"]
    assert view["recommended"]["action"]["where_left_off"].startswith("Wrote two lines")


def test_empty_today_does_not_invent_work(client):
    view = client.get("/api/today").json()
    assert view["recommended"] is None and "No need to invent work" in view["greeting"]


# ---- reminders, outcomes, ideas -------------------------------------------------------

def test_reminder_surfaces_when_due_and_can_be_snoozed_or_done(client):
    today = date.today().isoformat()
    r = client.post("/api/reminders", json={"text": "Check in", "due_on": today}).json()
    later = client.post("/api/reminders", json={"text": "Later", "due_on": "2099-01-01"}).json()
    due = [x["id"] for x in client.get("/api/today").json()["reminders"]]
    assert r["id"] in due and later["id"] not in due
    client.post(f"/api/reminders/{r['id']}/snooze", json={"days": 3})
    assert client.get("/api/today").json()["reminders"] == []
    client.post(f"/api/reminders/{later['id']}/done", json={})
    assert [x["id"] for x in client.get("/api/reminders").json()] == [r["id"]]


def test_quick_outcome_recording_and_undo(client):
    item = client.post("/api/items", json={"kind": "relationship", "title": "Synthetic Person"}).json()
    o = client.post("/api/outcomes", json={"item_id": item["id"], "type": "reply"}).json()
    assert o["occurred_on"] and o["type"] == "reply"
    assert client.get("/api/items").json()[0]["outcomes"][0]["id"] == o["id"]
    client.delete(f"/api/outcomes/{o['id']}")
    assert client.get("/api/items").json()[0]["outcomes"] == []
    assert client.post("/api/outcomes", json={"item_id": item["id"], "type": "hired!!"}).status_code == 422


def test_idea_is_not_an_obligation_until_promoted(client):
    idea = client.post("/api/ideas", json={"text": "Learn about dbt"}).json()
    assert client.get("/api/actions").json() == []
    assert client.get("/api/today").json()["recommended"] is None
    assert client.get("/api/today").json()["parked_ideas"] == 1
    client.post(f"/api/ideas/{idea['id']}/promote", json={})
    assert client.get("/api/actions").json()[0]["title"] == "Learn about dbt"


# ---- availability without AI ----------------------------------------------------------

def test_everything_manual_works_with_ai_off(settings):
    settings.ai_mode = "off"
    client = signed_in(create_app(settings))
    assert client.get("/api/bootstrap").json()["ai"]["available"] is False
    ev = evidence(client).json()
    action = make_action(client)
    chat = client.post("/api/chat", json={"message": "hello"}).json()
    assert chat["reply"] is None and chat["unavailable"]
    assert client.post("/api/drafts/generate", json={"purpose": "outreach", "evidence_ids": [ev["id"]]}).status_code == 503
    saved = client.post("/api/drafts/save", json={"action_id": action["id"], "purpose": "outreach",
                                                  "body": "Written by hand."})
    assert saved.status_code == 200 and saved.json()["source"] == "user"
    assert client.get("/api/today").json()["recommended"]["action"]["state"] == "drafted"
    assert client.get("/api/export").status_code == 200


def test_exhausted_budget_blocks_ai_but_not_saved_work(settings):
    settings.hard_stop_usd = 0.01
    mock = MockAI(model="claude-sonnet-5-5", usage=Usage(input_tokens=2000, output_tokens=500))
    client = signed_in(create_app(settings, ai_client=mock))
    ev = evidence(client).json()
    r = client.post("/api/drafts/generate", json={"purpose": "outreach", "evidence_ids": [ev["id"]]})
    assert r.status_code == 503 and r.json()["kind"] == "budget"
    assert mock.requests == []
    assert client.get("/api/evidence").json()[0]["id"] == ev["id"]
    assert client.post("/api/drafts/save", json={"purpose": "outreach", "body": "by hand"}).status_code == 200


def test_model_failure_keeps_the_users_message_and_work(settings):
    mock = MockAI(model="claude-sonnet-5-5", script=[RuntimeError("down")])
    client = signed_in(create_app(settings, ai_client=mock))
    r = client.post("/api/chat", json={"message": "are you there?"}).json()
    assert r["reply"] is None and "saved" in r["unavailable"]
    assert client.get("/api/budget").json()["status"]["unknown_calls"] == 1


# ---- persistence, export, deletion, sample data ---------------------------------------

def test_data_and_session_progress_survive_restart(settings):
    first = signed_in(create_app(settings))
    a = make_action(first, commitment=True)
    first.post("/api/session/start", json={"minutes": 30, "action_id": a["id"]})
    first.post(f"/api/actions/{a['id']}/note", json={"where_left_off": "Halfway through."})
    first.post("/api/drafts/save", json={"action_id": a["id"], "purpose": "follow_up", "body": "Draft text"})
    first.app.state.db.close()

    second = signed_in(create_app(settings))
    view = second.get("/api/today").json()
    assert view["recommended"]["action"]["id"] == a["id"]
    assert "You were on this last time." in view["recommended"]["reasons"]
    assert second.get(f"/api/drafts?action_id={a['id']}").json()[0]["body"] == "Draft text"


def test_export_contains_everything_and_wipe_removes_it(client, settings):
    evidence(client)
    client.post("/api/memory", json={"kind": "goal", "text": "EXPORT-ME"})
    export = client.get("/api/export")
    assert "attachment" in export.headers["content-disposition"] and "EXPORT-ME" in export.text
    assert client.post("/api/wipe", json={"confirm": "yes"}).status_code == 422
    assert client.post("/api/wipe", json={"confirm": "DELETE EVERYTHING"}).status_code == 200
    assert client.get("/api/memory").json() == [] and client.get("/api/evidence").json() == []
    assert b"EXPORT-ME" not in settings.db_path.read_bytes()


def test_wipe_does_not_reset_the_spending_cap(settings):
    mock = MockAI(model="claude-sonnet-5-5", usage=Usage(input_tokens=2000, output_tokens=500))
    client = signed_in(create_app(settings, ai_client=mock))
    client.post("/api/chat", json={"message": "hello"})
    before = client.get("/api/budget").json()["status"]["committed_usd"]
    assert before > 0
    client.post("/api/wipe", json={"confirm": "DELETE EVERYTHING"})
    assert client.get("/api/budget").json()["status"]["committed_usd"] == before


def test_sample_data_is_labelled_and_removable(client):
    client.post("/api/sample/load", json={})
    client.post("/api/sample/load", json={})  # idempotent
    titles = [e["title"] for e in client.get("/api/evidence").json()] + \
             [a["title"] for a in client.get("/api/actions").json()] + \
             [i["title"] for i in client.get("/api/items").json()]
    assert len(titles) == 6 and all(t.startswith("[SAMPLE]") for t in titles)
    assert client.get("/api/bootstrap").json()["has_sample"]
    client.post("/api/sample/remove", json={})
    assert client.get("/api/evidence").json() == [] and client.get("/api/actions").json() == []
    assert not client.get("/api/bootstrap").json()["has_sample"]


def test_old_transcripts_are_purged_on_start(settings):
    app = create_app(settings)
    db = app.state.db
    db.run("INSERT INTO sessions(id,started_at) VALUES(1,'2020-01-01T00:00:00+00:00')")
    db.run("INSERT INTO messages(session_id,role,content,created_at) VALUES(1,'user','old','2020-01-01T00:00:00+00:00')")
    db.run("INSERT INTO messages(session_id,role,content,created_at) VALUES(1,'user','new',datetime('now'))")
    db.close()
    assert [m["content"] for m in create_app(settings).state.db.q("SELECT content FROM messages")] == ["new"]


def test_database_file_is_private_to_the_user(client, settings):
    assert oct(settings.db_path.stat().st_mode)[-3:] == "600"


def test_session_timer_info_and_end(client):
    a = make_action(client, commitment=True)
    assert client.get("/api/today").json()["session"] is None
    client.post("/api/chat", json={"message": "hello"})          # a chat alone starts no timer
    assert client.get("/api/today").json()["session"] is None
    client.post("/api/session/start", json={"minutes": 30, "action_id": a["id"]})
    session = client.get("/api/today").json()["session"]
    assert session["minutes"] == 30 and session["focus_action_id"] == a["id"] and session["started_at"]
    client.post("/api/session/end", json={})
    assert client.get("/api/today").json()["session"] is None


def test_onboarding_questions_are_short_with_a_hint(client):
    state = client.get("/api/bootstrap").json()["onboarding"]
    assert len(state["question"]) < 70 and state["hint"]
