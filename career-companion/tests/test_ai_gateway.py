import json

import httpx2 as httpx
import pytest

from companion import ai
from companion.ai import (AIResult, AIUnavailable, AllowlistTransport, CompanionTurn, DraftOut, Gateway,
                          LiveAI, MockAI, NeverSent, build_client)
from companion.budget import Budget, Usage, worst_case_usd
from companion.config import Settings

SONNET = "claude-sonnet-5-5"


def gateway(db, settings, client):
    return Gateway(db, Budget(db, settings), client, "test")


def priced_mock(**kw):
    return MockAI(model=SONNET, usage=Usage(input_tokens=2000, output_tokens=400), **kw)


def test_successful_call_is_settled_at_actual_cost(db, settings):
    g = gateway(db, settings, priced_mock())
    out = g.call("companion_turn", "sys", "hello", CompanionTurn, meta={"user_message": "hello"})
    assert isinstance(out, CompanionTurn)
    assert g.budget.month_committed() == pytest.approx(2000 * 2 / 1e6 + 400 * 10 / 1e6)


def test_no_client_means_unavailable_and_no_spend(db, settings):
    g = gateway(db, settings, None)
    with pytest.raises(AIUnavailable):
        g.call("draft", "s", "u", DraftOut)
    assert db.q("SELECT * FROM ledger") == []


def test_budget_block_never_reaches_the_client(db, settings):
    settings.hard_stop_usd = 0.001
    client = priced_mock()
    with pytest.raises(AIUnavailable) as e:
        gateway(db, settings, client).call("draft", "s", "u", DraftOut)
    assert e.value.kind == "budget"
    assert client.requests == []


def test_failed_call_is_charged_conservatively(db, settings):
    g = gateway(db, settings, priced_mock(script=[TimeoutError("boom")]))
    with pytest.raises(AIUnavailable):
        g.call("draft", "s", "u", DraftOut)
    assert g.budget.status()["unknown_calls"] == 1
    assert g.budget.month_committed() >= worst_case_usd(SONNET, 500, 1800)


def test_never_sent_call_is_released(db, settings):
    g = gateway(db, settings, priced_mock(script=[NeverSent("blocked")]))
    with pytest.raises(AIUnavailable):
        g.call("draft", "s", "u", DraftOut)
    assert g.budget.month_committed() == 0


def test_refusal_or_truncation_is_billed_but_changes_nothing(db, settings):
    bad = AIResult(parsed=None, usage=Usage(input_tokens=1000, output_tokens=1800), stop_reason="max_tokens")
    g = gateway(db, settings, priced_mock(script=[bad]))
    with pytest.raises(AIUnavailable):
        g.call("draft", "s", "u", DraftOut)
    assert g.budget.month_committed() == pytest.approx(1000 * 2 / 1e6 + 1800 * 10 / 1e6)


def test_wrong_schema_from_client_is_rejected(db, settings):
    g = gateway(db, settings, priced_mock(script=[DraftOut(body="x", claims=[], gaps=[])]))
    with pytest.raises(AIUnavailable):
        g.call("companion_turn", "s", "u", CompanionTurn)


def test_activity_log_holds_metadata_only(db, settings):
    g = gateway(db, settings, priced_mock())
    g.call("companion_turn", "SECRET-SYSTEM", "SECRET-USER", CompanionTurn, meta={"user_message": "SECRET-USER"})
    dump = json.dumps(db.q("SELECT * FROM activity") + db.q("SELECT * FROM ledger"))
    assert "SECRET" not in dump


# ---- egress allowlist -----------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/feed/", "https://api.linkedin.com/v2/me", "http://api.anthropic.com/v1/messages",
    "https://example.com/", "https://api.anthropic.com.evil.test/v1/messages", "http://127.0.0.1:9/",
])
def test_egress_refuses_everything_but_the_provider_api(url):
    inner = httpx.MockTransport(lambda r: httpx.Response(200))
    with pytest.raises(NeverSent):
        AllowlistTransport(inner).handle_request(httpx.Request("GET", url))


def test_egress_allows_the_provider_api():
    inner = httpx.MockTransport(lambda r: httpx.Response(204))
    resp = AllowlistTransport(inner).handle_request(httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    assert resp.status_code == 204


# ---- live client wiring, against a fake transport (no network, no spend) --------------

def fake_api(captured):
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        body = {"id": "msg_test", "type": "message", "role": "assistant", "model": SONNET,
                "content": [{"type": "text", "text": json.dumps({"reply": "hi", "proposals": []})}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 321, "output_tokens": 45, "cache_creation_input_tokens": 100,
                          "cache_read_input_tokens": 7}}
        return httpx.Response(200, json=body)
    return httpx.MockTransport(handler)


def test_live_client_request_shape_and_usage_mapping(db, settings):
    captured: list[httpx.Request] = []
    live = LiveAI("sk-test-not-a-real-key", transport=fake_api(captured))
    g = gateway(db, settings, live)
    out = g.call("companion_turn", "system text", "user text", CompanionTurn)
    assert out.reply == "hi"

    sent = json.loads(captured[0].content)
    assert captured[0].url.host == "api.anthropic.com"
    assert sent["model"] == SONNET
    assert sent["max_tokens"] == ai.PROFILES["companion_turn"].max_tokens
    assert sent["thinking"] == {"type": "between_tools"}
    assert sent["output_config"]["effort"] == "medium"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert "tools" not in sent  # the model has no tools
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}

    row = db.one("SELECT * FROM ledger")
    assert (row["in_tok"], row["out_tok"], row["cw_tok"], row["cr_tok"]) == (321, 45, 100, 7)
    assert row["status"] == "settled"


def test_live_client_does_not_retry(db, settings):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(529, json={"type": "error", "error": {"type": "overloaded_error", "message": "x"}})

    g = gateway(db, settings, LiveAI("sk-test-not-a-real-key", transport=httpx.MockTransport(handler)))
    with pytest.raises(AIUnavailable):
        g.call("companion_turn", "s", "u", CompanionTurn)
    assert len(calls) == 1
    assert g.budget.status()["unknown_calls"] == 1


# ---- live gate ------------------------------------------------------------------------

def test_default_mode_is_mock(tmp_path):
    client, _ = build_client(Settings(data_dir=tmp_path))
    assert client.name == "mock"


def test_live_mode_without_key_stays_off(tmp_path, monkeypatch):
    monkeypatch.setattr("companion.keys.get_api_key", lambda: None)
    client, reason = build_client(Settings(data_dir=tmp_path, ai_mode="live"))
    assert client is None and "key" in reason.lower()


def test_live_mode_with_stale_prices_stays_off(tmp_path, monkeypatch):
    monkeypatch.setattr("companion.keys.get_api_key", lambda: "sk-test-not-a-real-key")
    monkeypatch.setattr(ai, "prices_are_fresh", lambda: False)
    client, reason = build_client(Settings(data_dir=tmp_path, ai_mode="live"))
    assert client is None and "price" in reason.lower()
