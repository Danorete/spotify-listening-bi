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

- [x] 7b. Browser interface: `src/companion/static/` (checked in headless Chromium, no console errors)
- [x] 8. `README.md` (setup, live-AI steps, test results, limitations), `requirements.lock`

- [x] 9. Design pass (decisions D19 to D23): dedicated onboarding, focused Today with session ring, companion
  identity and states, resizable and collapsible panel, sidebar navigation, bundled fonts, loading and error
  states, keyboard and reduced-motion support. Interface files: `static/index.html`, `static/style.css`,
  `static/app.js`. Backend additions: `POST /api/session/end`, `session` and `today` in `/api/today`,
  onboarding hints, `font-src 'self'` in the CSP.

- [x] 10. Starter-file import (decision D24): `POST /api/starter/import`, preview and confirm in Settings & data,
  third first-step on the empty Today page.

State at last update (2026-11-10): 122 tests pass on Linux, Python 3.13. Mock AI only. The interface was
checked in headless Chromium at 1470 x 860, 1710 x 1010 and 390 x 844.

Design reference (two directions, private to the owner): https://claude.ai/artifact/BNv3bCGtPEPwBRF5jZtMUG

## Next, in order

1. Run the test suite and the app on the Mac. Note anything macOS-specific in README limitations.
2. Enter real evidence, voice samples, and to-dos. Use it in mock mode for a few sessions.
3. First live call, following "Turning on live AI" in the README.
4. Design follow-ups, if wanted: a dark theme, a different companion name, streaming replies.
5. After about two weeks of real sessions, review: ranking weights, the strong-word list in
   `validate.py`, and whether the onboarding questions were the right four.

## Not started, deliberately

- First live API call. The live client's request shape is tested against a fake transport only.
  Before enabling: re-check prices if `PRICES_VERIFIED_ON` in `budget.py` is over 45 days old, set a
  workspace spend limit in the provider Console, run `companion set-key`, start with
  `COMPANION_AI_MODE=live`, send one chat message, and compare the Budget tab with the Console.
- Everything listed as out of scope in decision D18.
