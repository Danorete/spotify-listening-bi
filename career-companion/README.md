# Career Companion

A personal, local career tool: a workspace with a companion docked beside it. It tells you the one thing to do
next, keeps your place, checks draft claims against your own evidence, and never touches LinkedIn. You send,
post, apply, and edit your profile yourself.

Version one, single user. Decisions are in `DECISIONS.md`; build status is in `PROGRESS.md`.

## Setup on macOS

Requires Python 3.11 or newer. Don't use the system `/usr/bin/python3`; install one with Homebrew
(`brew install python@3.12`), `uv`, or `pyenv`.

```
cd career-companion
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q      # 116 tests, about 8 seconds
.venv/bin/companion run
```

`companion run` prints a link and opens it in your browser. The link works once; restart the app for a new
one. The app starts in **mock AI** mode: replies are canned, labelled as mock, and nothing leaves your Mac.
Use "Load labelled sample data" on the Today page to look around; every sample item is marked `[SAMPLE]`
and one click removes them all.

Your data lives in `~/Library/Application Support/CareerCompanion/`, outside this repository.

| Setting | Environment variable | Default |
|---|---|---|
| AI mode | `COMPANION_AI_MODE` (`mock`, `live`, `off`) | `mock` |
| Port | `COMPANION_PORT` | `8765` |
| Data folder | `COMPANION_DATA_DIR` | see above |
| Time zone for the daily cap | `COMPANION_TIMEZONE` | `America/New_York` |

## Turning on live AI

Live mode has never made a real API call. Its request format is tested against a stand-in server only. Do
this the first time:

1. In the provider Console, create a workspace for this app and set a spend limit of $20 on it. This is the
   backstop behind the app's own $16 stop.
2. `.venv/bin/companion status`. If prices show as stale (older than 45 days), re-check the official pricing
   page and update `PRICES` and `PRICES_VERIFIED_ON` in `src/companion/budget.py`.
3. `.venv/bin/companion set-key` and paste the key at the hidden prompt. It goes to the macOS Keychain.
4. `COMPANION_AI_MODE=live .venv/bin/companion run`
5. Send one chat message, then compare the Budget tab with the Console. If the first call errors, the app
   stays usable and the call is counted at its maximum cost; run in mock mode until it's fixed.

In live mode, chat sends your private planning context and recent conversation to the provider. Drafting and
job comparison send only the evidence you tick, your voice notes, and what you type in the form.

## What it does

First run is a short conversation with the companion (working name: Tempo): four questions, one at a time,
each skippable. The workspace appears afterwards.

- **Today**: one recommended action beside a session ring. Pick 15, 20 or 30 minutes and start; the ring
  counts down. Other options, reminders, and the idea parking lot are tucked into rows below. An empty
  account offers two first steps: add a project, or paste your profile text.
- **People & roles**: who you're talking to and what you're going for, to-dos, one-click outcomes with undo.
- **Evidence**: claims with a status, numbers, approved uses, banned phrases, and a confidential flag.
- **Drafts**: set up, write (yourself or with the companion), check. Every save is checked against evidence.
- **About me**: everything the companion remembers, editable and deletable.
- **Pasted material** and **Settings & data** sit lower in the sidebar: reference text, AI mode, spending,
  export, delete, activity log. AI mode and budget are always visible at the bottom of the sidebar.
- **The companion panel**: shows whether it is ready, thinking, waiting for your OK, or off. Drag its edge
  (or focus the edge and use the arrow keys) to resize; collapse it to a corner pill.

Keyboard: Tab reaches everything, a "Skip to main content" link comes first, Enter sends a chat message
(Shift+Enter for a new line), Escape closes the companion on a narrow window. Motion is removed when macOS
"Reduce motion" is on.

## Test results

`116 passed` on Python 3.13, Linux, 2026-11-10. Not yet run on macOS. Coverage by acceptance criterion:

| Criterion | Tests |
|---|---|
| Data and session progress survive restarts | `test_data_and_session_progress_survive_restart` |
| Preferences corrected conversationally | `test_preferences_can_be_corrected_in_conversation_and_edited_directly` |
| Drafts separate supported claims from gaps | `test_validate_and_ranking.py`, `test_draft_report_separates_supported_claims_from_gaps` |
| Private context excluded from drafting | canary tests in `test_privacy_and_injection.py` |
| Copying a draft does not mark it sent | `test_copying_or_saving_a_draft_never_marks_it_sent` |
| Pasted content cannot act or alter memory | `test_turn_with_pasted_material_cannot_create_proposals`, `test_tainted_turn_is_withheld_from_later_context`, `test_model_cannot_change_action_state_or_evidence` |
| AI failure or spent budget leaves work accessible | `test_everything_manual_works_with_ai_off`, `test_exhausted_budget_blocks_ai_but_not_saved_work` |
| No activity inside LinkedIn | `test_egress_refuses_everything_but_the_provider_api` |
| $16 stop, unknown usage counted conservatively | `test_budget.py`, `test_failed_call_is_charged_conservatively` |
| Local endpoints protected | `test_security.py` (22 tests) |
| Session timer starts only on a chosen action, and ends | `test_session_timer_info_and_end` |

The interface was also driven in headless Chromium at 1470 x 860 (13-inch MacBook Air), 1710 x 1010 and
390 x 844: onboarding, the empty account, sample data, a confirmed suggestion, a full session, a draft and
an edit, outcome recording, every section, a slowed-down load, a forced error and recovery, panel resize by
keyboard, collapse and reopen. No script errors; no control under 44 px; text contrast 5.4:1 or better on the
pairs measured; no sideways scrolling at any size.

## Known limitations

**Not verified**
- No real API call has been made. How `messages.parse` behaves live with `thinking` and `effort` together,
  and real token counts and costs, are unconfirmed.
- Nothing has been run on macOS: Keychain prompts (they may repeat if the Python binary changes), Safari
  (clipboard, cookies on `127.0.0.1`), and whether port 8765 is free are untested.
- Whether failed API requests are billed. The app assumes they might be and counts them at maximum.
- Console usage-page lag, and prepaid-credit behaviour.

**By design**
- Claim checks cover references, permissions, numbers (value and unit), and banned phrases. Strong wording is
  flagged by a word list. A paraphrase that overstates can pass every check. You are the reviewer.
- "Pasted content cannot act" rests on structure: the model has no tools, and a turn with pasted material
  cannot create suggestions. A model can still be influenced in what it *says* in that turn, so read replies
  about pasted material critically.
- The budget uses the app's own price table and a deliberately high token estimate. It is a control, not an
  invoice. The provider's workspace limit is the real backstop.
- Deleting removes the database files. It does not reach Time Machine or other backups, exported files, or
  the provider's copies (deleted within 30 days by default; longer if flagged for a policy violation). It is
  not forensic erasure.
- The database is not encrypted by the app. It relies on FileVault and file permissions. Malware running as
  your macOS user could read it.
- Reminders appear only when the app is open. There are no notifications and no background work.
- Replies are not streamed, so a live reply appears all at once after a pause.
- Light theme only. The earlier automatic dark mode was removed in the redesign and has not been redrawn.
- The session ring is a timer, not an alarm: nothing sounds, and it only updates while the app is open.
- Panel width and collapsed state are stored in the browser (layout only, no personal data).
- The ranking weights are a first guess. Change them in `src/companion/ranking.py` after real sessions.
- One browser session per launch; no multi-tab coordination beyond the shared cookie.
- Dependencies are version-ranged in `pyproject.toml`; `requirements.lock` records the tested versions
  without hashes.

**Out of scope for version one**: LinkedIn integration or automation, URL fetching, background AI calls,
people discovery, accounts, billing, hosting, desktop packaging.
