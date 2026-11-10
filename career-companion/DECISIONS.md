# Career Companion: decision record

Status: accepted 2026-11-10. Personal, single-user, local tool. Version one.

## Verified platform facts (official docs, checked 2026-11-10)

| Fact | Value | Source |
|---|---|---|
| Model IDs | `claude-sonnet-5-5`, `claude-haiku-5-5` (also `claude-opus-5-5`, `claude-fable-5-2`) | platform.claude.com/docs/en/about-claude/models/overview |
| Sonnet 5.5 price per MTok | $2 input, $10 output, $2.50 5-minute cache write, $4 1-hour cache write, $0.10 cache read | .../about-claude/pricing |
| Haiku 5.5 price per MTok | $0.10 input, $0.50 output, $0.125 / $0.20 cache write, $0.01 cache read; 5x higher when the prompt exceeds 100,000 tokens | same |
| Thinking | Billed as output tokens and counted inside `max_tokens`. Sonnet 5.5 rejects `disabled`; `between_tools` turns off up-front thinking at low/medium/high effort. Haiku 5.5 accepts `disabled` at high effort or below | .../build-with-claude/thinking, .../effort |
| Effort | `output_config.effort`; default `high` on Sonnet 5.5, `medium` on Haiku 5.5 | .../build-with-claude/effort |
| Structured output | `client.messages.parse(output_format=PydanticModel)`, generally available; refusals and `max_tokens` stops can break the schema | .../build-with-claude/structured-outputs |
| Prompt caching | Minimum 512 tokens on both models, 5-minute default TTL, usage fields `cache_creation_input_tokens` and `cache_read_input_tokens` | .../build-with-claude/prompt-caching |
| Token counting | `client.messages.count_tokens`, free, an estimate | .../build-with-claude/token-counting |
| Spend limits | Organization and per-workspace limits set in Console (not on the default workspace). At a user-set limit the API returns HTTP 400. Billing month resets 00:00 UTC on the 1st | .../api/rate-limits |
| Data handling | API inputs and outputs deleted within 30 days by default; up to 2 years if flagged for a usage-policy violation. No training on API data under commercial terms | privacy.claude.com article 7996866; code.claude.com/docs/en/data-usage |
| Python SDK | `anthropic` 2.7.0 installed; `messages.parse` accepts `thinking`, `output_config`, `output_format`; `Usage` has the cache fields | installed package, inspected |

Not verified: prepaid credits and auto-reload behaviour, Console usage-page lag, the exact live behaviour of `messages.parse` combined with `thinking` and `effort` (no API key was used; the live client has never made a real call), and every macOS-specific item in the limitations section of the README.

## Decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Stack | Python 3.11+, FastAPI, SQLite (stdlib `sqlite3`), vanilla JS front end served from the same process. No Streamlit, no CDN, no build step. |
| D2 | Local endpoint protection | Bind `127.0.0.1` only (startup refuses anything else), port 8765. Every request: `Host` allowlist. Every state-changing request: matching `Origin`, JSON content type, session cookie (`HttpOnly`, `SameSite=Strict`), and a per-session CSRF header. No CORS, `OPTIONS` refused. Single-use launch token delivered in the URL fragment. Strict CSP; all model and imported text rendered with `textContent`. |
| D3 | Model capability boundary | The model has no tools. It returns schema-validated JSON. It can only produce *proposals* (memory, reminder, idea), which become pending rows that only a click commits. It has no way to change an action's state, evidence, or settings. |
| D4 | Untrusted material | Pasted job descriptions and conversation text go through Import and are wrapped as untrusted in prompts. A chat turn with imported material attached cannot create any proposal (they are dropped in code), and that turn is replaced by a placeholder in later conversation history. |
| D5 | Planning versus drafting | Two separate code paths. Drafting input is built from an allowlist: voice items for the audience, eligible evidence, and text typed into the draft form. It never receives goals, constraints, boundaries, private notes, or chat history. Canary tests enforce this. |
| D6 | Evidence and claim checks | Evidence has a status (`unverified_user_claim`, `user_verified_with_artifact`, `do_not_claim`), permitted uses, structured metrics (value, unit, label), banned phrases, and a confidential flag. Code checks every draft: evidence ID exists and is permitted, numbers match a metric's value and unit, banned phrases are absent, numbers in the body are traceable. Strong wording not found in the evidence is flagged for human review. Semantic overclaims are not machine-verified. |
| D7 | Budget | $20 monthly budget, hard stop at $16 of committed spend for every new AI call. Each call reserves worst-case cost (conservative input estimate plus full `max_tokens`) before dispatch and settles to actual usage. A call whose outcome is unknown stays charged at its reservation. Caps: $1 per session, $2 per day. Month boundary is UTC, matching the provider. Unknown models are refused. No SDK retries. |
| D8 | Models | Conversation, drafting, comparison: `claude-sonnet-5-5`, effort `medium`, thinking `between_tools`. All configurable; Opus and Fable are priced in the table but never selected by default. |
| D9 | Live-call gate | Default mode is `mock`. Live mode needs `COMPANION_AI_MODE=live`, a key in Keychain, and a price table verified within the last 45 days; otherwise the app stays usable with AI off. |
| D10 | Recommendation | Code ranks actions (deadline, importance, existing commitment, in progress, fits the time available). The app opens on one recommended action with up to two alternatives collapsed. Exploratory actions never outrank an open commitment. The model does not rank. |
| D11 | Proactive colleague | The docked companion greets with a code-generated briefing (zero cost), runs the short onboarding as a scripted conversation, and converses through the model when AI is available. No background model calls. |
| D12 | Confirmation rule | Model-proposed memory changes and reminders need a click. Marking an action done needs a click. Autosaving drafts, session progress, and the resume note does not. Copying a draft never changes state. |
| D13 | Storage | `~/Library/Application Support/CareerCompanion/` on macOS, outside the repo, files mode 600. Chat transcripts kept 30 days. `secure_delete` on; "delete everything" removes the database files. Backups, exports, and the provider's 30-day retention are outside the app's control. No forensic-erasure promise. |
| D14 | Credentials | macOS Keychain through `keyring`, set with a hidden prompt. No environment-variable or file fallback. The key never reaches the browser or logs. |
| D15 | Egress and logs | The live client uses an HTTP transport that only allows `https://api.anthropic.com`. Logs and the activity table hold metadata only (event, IDs, token counts, cost). |
| D16 | Without AI | Every workspace feature (evidence, opportunities, actions, drafts, outcomes, reminders, memory, export) works with AI off, over budget, or failing. |
| D17 | Resume card, reminder, outcomes | Interpreted as: a card showing where you left off on the recommended action; date-based reminders that surface when the app is open (no notifications); one-click outcome buttons (reply, interview, no response, rejection, offer). |
| D18 | Out of scope for version one | LinkedIn integration or automation, URL fetching, background AI calls, people discovery, accounts, billing, hosting, desktop packaging, streaming responses. |

## Implementation plan

1. Foundation: config, database, schema, progress file.
2. Local endpoint security and its tests.
3. Budget ledger and its tests.
4. AI layer: schemas, mock client, gated live client, egress allowlist, gateway.
5. Domain: memory, evidence, items, actions, outcomes, reminders, ideas, proposals, ranking, resume note.
6. Context assembly, claim validation, drafting and comparison pipelines; canary and injection tests.
7. HTTP API and browser interface; end-to-end tests; browser check.
8. Export, delete, sample data, setup instructions, limitations.
