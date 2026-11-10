# Progress

Read `DECISIONS.md` first. This file says where the build stands so a later session can resume.

## How to resume

```
cd career-companion
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q        # must be green before changing anything
COMPANION_DATA_DIR=/tmp/cc-dev .venv/bin/companion run --no-browser
```

## Done

- [x] 1. Foundation: `config.py`, `db.py` (schema v1)
- [x] 2. Local endpoint security: `security.py`, `tests/test_security.py`
- [x] 3. Budget ledger: `budget.py`, `tests/test_budget.py`
- [x] 4. AI layer: `ai.py` (mock client, gated live client, egress allowlist, gateway), `keys.py`, `tests/test_ai_gateway.py`
- [x] 5. Domain: `store.py`, `ranking.py`, `tests/test_validate_and_ranking.py`
- [x] 6. Context assembly and claim checks: `context.py`, `validate.py`, `services.py`, `tests/test_privacy_and_injection.py`
- [x] 7a. HTTP API: `app.py`, `cli.py`, `tests/test_workflows.py`

## In progress

- [ ] 7b. Browser interface in `src/companion/static/`
- [ ] 8. README (setup, limitations), browser check

## Not started, deliberately

- First live API call. The live client's request shape is tested against a fake transport only.
  Before enabling: re-check prices if `PRICES_VERIFIED_ON` in `budget.py` is over 45 days old, set a
  workspace spend limit in the provider Console, run `companion set-key`, start with
  `COMPANION_AI_MODE=live`, send one chat message, and compare the Budget tab with the Console.
- Everything listed as out of scope in decision D18.
