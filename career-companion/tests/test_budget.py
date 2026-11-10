from datetime import date, timedelta

import pytest

from companion import budget as b
from companion.budget import Budget, BudgetBlocked, Usage, cost_usd, worst_case_usd

SONNET = "claude-sonnet-5-5"


def test_cost_matches_published_prices():
    u = Usage(input_tokens=1_000_000, output_tokens=1_000_000, cache_write_tokens=1_000_000,
              cache_read_tokens=1_000_000)
    assert cost_usd(SONNET, u) == pytest.approx(2 + 10 + 2.5 + 0.10)
    assert cost_usd("claude-haiku-5-5", Usage(input_tokens=50_000, output_tokens=1_000)) == pytest.approx(0.0055)


def test_haiku_long_prompt_is_five_times_dearer():
    short = cost_usd("claude-haiku-5-5", Usage(input_tokens=100_000))
    long = cost_usd("claude-haiku-5-5", Usage(input_tokens=100_001))
    assert long == pytest.approx(short * 5, rel=1e-3)


def test_unknown_model_is_refused():
    with pytest.raises(BudgetBlocked):
        worst_case_usd("claude-some-future-model", 1000, 1000)


def test_worst_case_is_never_below_actual():
    actual = cost_usd(SONNET, Usage(input_tokens=3000, output_tokens=1200, cache_write_tokens=2000))
    assert worst_case_usd(SONNET, 5000, 1200) >= actual


def test_reserve_settle_reduces_to_actual(db, settings):
    bud = Budget(db, settings)
    lid = bud.reserve("draft", SONNET, 5000, 1800)
    reserved = bud.month_committed()
    assert reserved == pytest.approx(worst_case_usd(SONNET, 5000, 1800))
    bud.settle(lid, SONNET, Usage(input_tokens=4000, output_tokens=500))
    assert bud.month_committed() == pytest.approx(0.008 + 0.005)
    assert bud.month_committed() < reserved


def test_hard_stop_blocks_new_calls_at_16(db, settings):
    bud = Budget(db, settings)
    month, day = bud._keys()
    db.run("INSERT INTO ledger(ts,month,day,call_type,model,status,cost_usd) VALUES('t',?,'earlier','x',?,'settled',15.99)",
           (month, SONNET))
    with pytest.raises(BudgetBlocked) as e:
        bud.reserve("draft", SONNET, 5000, 1800)
    assert "limit" in e.value.reason.lower()
    assert bud.status()["level"] == "warn"
    db.run("UPDATE ledger SET cost_usd=16.0")
    assert bud.status()["level"] == "hard_stop"


def test_reservation_counts_before_settlement(db, settings):
    """Open reservations are committed spend, so parallel calls cannot overshoot the stop."""
    settings.hard_stop_usd, settings.day_cap_usd = 0.05, 100
    bud = Budget(db, settings)
    need = worst_case_usd(SONNET, 5000, 1800)  # about 0.0305
    bud.reserve("draft", SONNET, 5000, 1800)
    with pytest.raises(BudgetBlocked):
        bud.reserve("draft", SONNET, 5000, 1800)
    assert bud.month_committed() == pytest.approx(need)


def test_unknown_outcome_stays_charged_at_reservation(db, settings):
    bud = Budget(db, settings)
    lid = bud.reserve("draft", SONNET, 5000, 1800)
    bud.mark_unknown(lid, "APITimeoutError")
    assert bud.month_committed() == pytest.approx(worst_case_usd(SONNET, 5000, 1800))
    assert bud.status()["unknown_calls"] == 1


def test_release_only_frees_never_sent_calls(db, settings):
    bud = Budget(db, settings)
    bud.release(bud.reserve("draft", SONNET, 5000, 1800))
    assert bud.month_committed() == 0


def test_crash_leftover_reservation_becomes_unknown(db, settings):
    Budget(db, settings).reserve("draft", SONNET, 5000, 1800)
    restarted = Budget(db, settings)
    assert restarted.status()["unknown_calls"] == 1
    assert restarted.month_committed() > 0


def test_day_and_session_caps(db, settings):
    settings.day_cap_usd, settings.session_cap_usd = 0.07, 0.04
    bud = Budget(db, settings)
    db.run("INSERT INTO sessions(id,started_at) VALUES(1,'t')")
    bud.reserve("draft", SONNET, 5000, 1800, session_id=1)
    with pytest.raises(BudgetBlocked) as e:
        bud.reserve("draft", SONNET, 5000, 1800, session_id=1)
    assert "session" in e.value.reason.lower()
    bud.reserve("draft", SONNET, 5000, 1800, session_id=None)
    with pytest.raises(BudgetBlocked) as e:
        bud.reserve("draft", SONNET, 5000, 1800, session_id=None)
    assert "daily" in e.value.reason.lower()


def test_oversized_input_is_refused(db, settings):
    with pytest.raises(BudgetBlocked):
        Budget(db, settings).reserve("draft", SONNET, b.MAX_INPUT_TOKENS + 1, 100)


def test_reconcile_sets_total_to_console_figure(db, settings):
    bud = Budget(db, settings)
    bud.mark_unknown(bud.reserve("draft", SONNET, 5000, 1800))
    bud.settle(bud.reserve("draft", SONNET, 5000, 1800), SONNET, Usage(input_tokens=1000, output_tokens=100))
    assert bud.reconcile(3.25)["committed_usd"] == pytest.approx(3.25)
    assert bud.status()["unknown_calls"] == 0
    assert bud.reconcile(0.5)["committed_usd"] == pytest.approx(0.5)


def test_price_table_goes_stale():
    assert b.prices_are_fresh(b.PRICES_VERIFIED_ON + timedelta(days=45))
    assert not b.prices_are_fresh(b.PRICES_VERIFIED_ON + timedelta(days=46))


def test_estimate_is_conservative():
    text = "The quick brown fox jumps over the lazy dog. " * 100
    assert b.estimate_tokens(text) > len(text) / 4  # well above the usual ~4 chars per token
