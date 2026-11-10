// Career Companion interface. All dynamic text is inserted with textContent or text nodes,
// never as HTML, so model output and pasted material cannot inject markup or script.
(function () {
  "use strict";

  const S = {
    csrf: "", ai: {}, budget: {}, onboarding: {}, enums: {}, hasSample: false,
    tab: "today", minutes: 20, attachImport: null, compare: null,
    draft: { action_id: null, purpose: "outreach", audience: "", evidence_ids: new Set(), instruction: "",
             shareable_note: "", include_item_context: false, current: null },
    editEvidence: null,
  };
  const TABS = [["today", "Today"], ["work", "Work"], ["evidence", "Evidence"], ["drafts", "Drafts"],
                ["material", "Pasted material"], ["me", "About me"], ["data", "Budget & data"]];
  const PURPOSES = [["outreach", "First message"], ["follow_up", "Follow-up"], ["profile", "Profile text"],
                    ["application", "Résumé or application text"], ["post", "Post"], ["interview_prep", "Interview answer"]];
  const KIND_TO_PURPOSE = { outreach: "outreach", follow_up: "follow_up", profile_edit: "profile",
                            application: "application", interview_prep: "interview_prep" };
  const OUTCOME_LABELS = { reply: "Got a reply", interview: "Interview", no_response: "No response",
                           rejection: "Rejection", offer: "Offer", other: "Other" };
  const STATE_LABELS = { suggested: "Not started", drafted: "Drafted", reviewed: "Reviewed", done: "Done", dropped: "Dropped" };
  const MEMORY_LABELS = { goal: "Goal", constraint: "Constraint", preference: "Working preference", boundary: "Boundary",
                          voice_note: "Voice note", voice_sample: "Writing sample", drafting_rule: "Drafting rule" };
  const PROPS = new Set(["value", "checked", "disabled", "selected", "open"]);
  const $ = (id) => document.getElementById(id);

  // ---- helpers ------------------------------------------------------------------------
  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (PROPS.has(k)) el[k] = v;
      else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid == null || kid === false) continue;
      el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  const btn = (label, onclick, cls) => h("button", { type: "button", class: cls || "", onclick }, label);
  const badge = (label, cls) => h("span", { class: "badge " + (cls || "") }, label);
  const field = (label, control) => h("label", {}, label, control);
  const select = (options, value, onchange) =>
    h("select", { onchange: (e) => onchange(e.target.value) },
      options.map(([v, l]) => h("option", { value: v, selected: String(v) === String(value) }, l)));
  const money = (n) => "$" + Number(n).toFixed(2);

  async function api(method, path, body) {
    const opts = { method, headers: {} };
    if (method !== "GET") {
      opts.headers["X-CSRF-Token"] = S.csrf;
      if (method !== "DELETE") {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body || {});
      }
    }
    const resp = await fetch(path, opts);
    let data = null;
    try { data = await resp.json(); } catch (e) { /* no body */ }
    if (!resp.ok) {
      let msg = data && data.error;
      if (!msg && data && data.detail) msg = typeof data.detail === "string" ? data.detail : "Please check the form: " +
        data.detail.map((d) => (d.loc || []).slice(-1)[0] + " " + d.msg).join("; ");
      if (resp.status === 401) msg = "This browser session ended. Stop the app and start it again for a new link.";
      const err = new Error(msg || "Request failed (" + resp.status + ")");
      err.status = resp.status; err.data = data;
      throw err;
    }
    return data;
  }

  let toastTimer = null;
  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.add("hidden"), 4500);
  }
  async function act(fn, okMsg) {
    try { const out = await fn(); if (okMsg) toast(okMsg); return out; }
    catch (err) { toast(err.message); return undefined; }
  }

  // ---- status pills -------------------------------------------------------------------
  async function refreshStatus() {
    const b = await api("GET", "/api/bootstrap");
    Object.assign(S, { csrf: b.csrf, ai: b.ai, budget: b.budget, onboarding: b.onboarding, enums: b.enums, hasSample: b.has_sample });
    const ai = $("ai-pill");
    ai.textContent = !b.ai.available ? "AI unavailable" : b.ai.mode === "mock" ? "Mock AI (canned replies)" : "Live AI";
    ai.className = "pill " + (!b.ai.available ? "bad" : b.ai.mode === "mock" ? "warn" : "ok");
    ai.title = b.ai.reason;
    const bp = $("budget-pill");
    bp.textContent = money(b.budget.committed_usd) + " of " + money(b.budget.hard_stop_usd) + " AI limit";
    bp.className = "pill " + (b.budget.level === "hard_stop" ? "bad" : b.budget.level === "warn" ? "warn" : "ok");
    $("dock-note").textContent = b.ai.available ? "" : "AI is unavailable. Everything else still works.";
  }

  // ---- companion dock -----------------------------------------------------------------
  function say(role, text) {
    const el = h("div", { class: "msg " + role, text });
    $("chat-log").append(el);
    el.scrollIntoView({ block: "end" });
    return el;
  }
  function proposalCard(p) {
    const pl = p.payload;
    const what = p.kind === "memory" ? "Remember as " + (MEMORY_LABELS[pl.memory_kind] || pl.memory_kind).toLowerCase() + ": “" + pl.text + "”"
      : p.kind === "reminder" ? "Set a reminder for " + pl.due_on + ": “" + pl.text + "”"
      : "Park this idea (no obligation): “" + pl.text + "”";
    const card = h("div", { class: "proposal" },
      h("div", { class: "eyebrow" }, "Suggestion. Nothing is saved until you choose."),
      h("div", {}, what), h("div", { class: "muted small" }, p.rationale),
      h("div", { class: "row" },
        btn("Save it", async () => { if (await act(() => api("POST", "/api/proposals/" + p.id + "/accept"), "Saved.") !== undefined) { card.remove(); render(); } }, "primary"),
        btn("No thanks", async () => { await act(() => api("POST", "/api/proposals/" + p.id + "/reject")); card.remove(); })));
    $("chat-log").append(card);
    card.scrollIntoView({ block: "end" });
  }
  function renderAttach() {
    const box = $("chat-attach");
    box.replaceChildren();
    if (S.attachImport) {
      box.append(h("div", { class: "notice" }, "Attached to your next message: " + S.attachImport.label + ". ",
        "Suggestions are switched off for that message. ",
        btn("Remove", () => { S.attachImport = null; renderAttach(); }, "link")));
    }
  }
  async function greet() {
    const view = await api("GET", "/api/today?minutes=" + S.minutes);
    say("companion", view.greeting);
    if (view.reminders.length) say("companion", view.reminders.length === 1
      ? "One reminder is due: " + view.reminders[0].text : view.reminders.length + " reminders are due. They're on the Today page.");
  }
  async function startDock() {
    $("chat-skip").addEventListener("click", () => submitChat(""));
    $("chat-form").addEventListener("submit", (e) => { e.preventDefault(); const v = $("chat-input").value.trim(); if (v) submitChat(v); });
    $("chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("chat-form").requestSubmit(); } });
    if (!S.onboarding.done) {
      say("companion", "Hi. I'm your career companion. I keep track of where you are, tell you the one thing I'd do next, " +
        "and push back when a claim isn't backed up. I can't see LinkedIn or your inbox, and I never send anything: you do that. " +
        "Four quick questions first. Skip any of them.");
      say("companion", S.onboarding.question);
      $("chat-skip").classList.remove("hidden");
    } else {
      await greet();
    }
    for (const p of await api("GET", "/api/proposals")) proposalCard(p);
  }
  async function submitChat(text) {
    const input = $("chat-input");
    input.value = "";
    if (!S.onboarding.done) {
      say("user", text || "(skipped)");
      const next = await act(() => api("POST", "/api/onboarding/answer", { text }));
      if (!next) return;
      S.onboarding = next;
      if (next.done) {
        $("chat-skip").classList.add("hidden");
        say("companion", "Thanks. That's saved under About me, where you can change or delete any of it.");
        await greet();
        render();
      } else {
        say("companion", next.question);
      }
      return;
    }
    say("user", text);
    const attached = S.attachImport;
    S.attachImport = null;
    renderAttach();
    const waiting = say("system", "Thinking…");
    const r = await act(() => api("POST", "/api/chat", { message: text, import_id: attached ? attached.id : null }));
    waiting.remove();
    if (!r) return;
    if (r.reply) say("companion", r.reply);
    else say("system", r.unavailable + " Your message was saved.");
    r.proposals.forEach(proposalCard);
    if (attached && r.dropped_proposals) say("system", "The reply tried to suggest saving something. That's blocked for messages with pasted material.");
    refreshStatus();
  }

  // ---- shared pieces ------------------------------------------------------------------
  async function setState(action, state, question) {
    if (question && !window.confirm(question)) return;
    const out = await act(() => api("POST", "/api/actions/" + action.id + "/state", { state }));
    if (!out) return;
    if (state === "done") say("companion", "Marked done: " + action.title + ". When you hear back, record it with one click on the Work page.");
    render();
  }
  async function startWork(action) {
    await act(() => api("POST", "/api/session/start", { minutes: S.minutes, action_id: action.id }));
    if (action.kind === "job_compare") {
      S.tab = "material";
      say("companion", "Okay: " + action.title + ". Paste the job description on this page and I'll line it up against your evidence.");
    } else {
      Object.assign(S.draft, { action_id: action.id, purpose: KIND_TO_PURPOSE[action.kind] || "outreach", current: null });
      S.tab = "drafts";
      say("companion", "Okay: " + action.title + ". Pick the evidence you want to lean on, then draft it yourself or with me. " +
        "I'll save your place as you go.");
    }
    render();
  }
  function actionCard(option, recommended) {
    const a = option.action;
    const note = h("input", { value: a.where_left_off, maxlength: 500, "aria-label": "Where you left it",
      onchange: (e) => act(() => api("POST", "/api/actions/" + a.id + "/note", { where_left_off: e.target.value }), "Saved your place.") });
    return h("section", { class: "card" + (recommended ? " recommended" : "") },
      h("div", { class: "eyebrow" }, recommended ? "Recommended for your " + S.minutes + " minutes" : "Alternative"),
      h("h3", { text: a.title }),
      h("div", { class: "row" },
        badge(STATE_LABELS[a.state], a.state === "reviewed" ? "ok" : ""),
        a.deadline ? badge("Due " + a.deadline, "warn") : null,
        badge("About " + a.effort_min + " min"),
        a.commitment ? badge("Commitment") : null,
        a.is_sample ? badge("Sample data", "warn") : null,
        option.item ? h("span", { class: "muted small" }, option.item.title + (option.item.org ? " · " + option.item.org : "")) : null),
      option.reasons && option.reasons.length ? h("ul", { class: "reasons" }, option.reasons.map((r) => h("li", { text: r }))) : null,
      field("Where you left it", note),
      h("div", { class: "row" },
        btn(a.state === "suggested" ? "Start this" : "Pick this back up", () => startWork(a), recommended ? "primary" : ""),
        a.state === "drafted" ? btn("I've reviewed it", () => setState(a, "reviewed")) : null,
        btn("I did this", () => setState(a, "done", "Mark as done? Only once you've actually sent, applied, or updated it yourself.")),
        btn("Drop it", () => setState(a, "dropped", "Drop this? You can bring it back from the Work page."))));
  }

  // ---- Today --------------------------------------------------------------------------
  async function renderToday(root) {
    const [view, ideas, items] = await Promise.all([api("GET", "/api/today?minutes=" + S.minutes), api("GET", "/api/ideas"), api("GET", "/api/items")]);
    root.append(h("div", { class: "row spread" }, h("h2", { text: "Today" }),
      h("div", { class: "row" }, h("span", { class: "muted small" }, "I have"),
        [15, 20, 30].map((m) => btn(m + " min", () => { S.minutes = m; render(); }, S.minutes === m ? "on" : "")))));
    if (S.hasSample) root.append(h("div", { class: "notice warn" }, "Sample data is loaded. Items marked [SAMPLE] are fictional. ",
      btn("Remove sample data", async () => { await act(() => api("POST", "/api/sample/remove"), "Sample data removed."); await refreshStatus(); render(); }, "link")));

    if (view.recommended) {
      root.append(actionCard(view.recommended, true));
      if (view.alternatives.length) {
        root.append(h("details", {}, h("summary", { text: "Other options (" + view.alternatives.length + ")" }),
          view.alternatives.map((o) => actionCard(o, false))));
      }
    } else {
      root.append(h("section", { class: "card" }, h("h3", { text: "Nothing is waiting on you" }),
        h("p", { class: "muted" }, "Add a to-do below when something real comes up. There's no need to invent work."),
        S.hasSample ? null : btn("Load labelled sample data to look around", async () => { await act(() => api("POST", "/api/sample/load")); await refreshStatus(); await render(); await greet(); })));
    }

    if (view.reminders.length) {
      root.append(h("section", { class: "card" }, h("h3", { text: "Reminders due" }),
        h("ul", { class: "plain" }, view.reminders.map((r) => h("li", { class: "row spread" },
          h("span", {}, r.text, " ", h("span", { class: "muted small" }, "(" + r.due_on + ")")),
          h("span", { class: "row" },
            btn("Done", async () => { await act(() => api("POST", "/api/reminders/" + r.id + "/done")); render(); }),
            btn("In 3 days", async () => { await act(() => api("POST", "/api/reminders/" + r.id + "/snooze", { days: 3 })); render(); })))))));
    }

    const idea = h("input", { placeholder: "Something you're curious about…", maxlength: 300, "aria-label": "Idea" });
    root.append(h("section", { class: "card" }, h("h3", { text: "Park an idea" }),
      h("p", { class: "muted small" }, "Ideas wait here. They never become to-dos unless you say so."),
      h("form", { class: "row", onsubmit: async (e) => { e.preventDefault(); if (!idea.value.trim()) return; await act(() => api("POST", "/api/ideas", { text: idea.value }), "Parked."); render(); } },
        idea, h("button", { type: "submit" }, "Park it")),
      ideas.length ? h("details", {}, h("summary", { text: "Parked ideas (" + ideas.length + ")" }),
        h("ul", { class: "plain" }, ideas.map((i) => h("li", { class: "row spread" }, h("span", { text: i.text }),
          h("span", { class: "row" },
            btn("Make it a to-do", async () => { await act(() => api("POST", "/api/ideas/" + i.id + "/promote")); render(); }),
            btn("Let it go", async () => { await act(() => api("POST", "/api/ideas/" + i.id + "/drop")); render(); })))))) : null));

    root.append(h("details", {}, h("summary", { text: "Add a to-do or a reminder" }), actionForm(items), reminderForm()));
  }
  function actionForm(items) {
    const f = { title: "", kind: "follow_up", item_id: "", commitment: false, importance: 2, effort_min: 15, deadline: "" };
    return h("form", { class: "card stack", onsubmit: async (e) => {
      e.preventDefault();
      const body = { ...f, item_id: f.item_id ? Number(f.item_id) : null, deadline: f.deadline || null, importance: Number(f.importance), effort_min: Number(f.effort_min) };
      if (await act(() => api("POST", "/api/actions", body), "Added.")) render();
    } },
      h("h3", { text: "New to-do" }),
      field("What needs doing", h("input", { required: true, maxlength: 200, oninput: (e) => { f.title = e.target.value; } })),
      h("div", { class: "grid2" },
        field("Type", select(S.enums.action_kinds.map((k) => [k, k.replace("_", " ")]), f.kind, (v) => { f.kind = v; })),
        field("About", select([["", "(nothing specific)"]].concat(items.map((i) => [i.id, i.title])), "", (v) => { f.item_id = v; })),
        field("Importance", select([[3, "High"], [2, "Medium"], [1, "Low"]], 2, (v) => { f.importance = v; })),
        field("Minutes needed", h("input", { type: "number", min: 5, max: 240, value: 15, oninput: (e) => { f.effort_min = e.target.value; } })),
        field("Deadline (optional)", h("input", { type: "date", oninput: (e) => { f.deadline = e.target.value; } }))),
      h("label", { class: "check" }, h("input", { type: "checkbox", onchange: (e) => { f.commitment = e.target.checked; } }), "I've already committed to this (promised it, or someone is waiting)"),
      h("div", {}, h("button", { type: "submit", class: "primary" }, "Add to-do")));
  }
  function reminderForm() {
    const f = { text: "", due_on: "" };
    return h("form", { class: "card stack", onsubmit: async (e) => { e.preventDefault(); if (await act(() => api("POST", "/api/reminders", f), "Reminder set.")) render(); } },
      h("h3", { text: "New reminder" }),
      h("p", { class: "muted small" }, "Reminders show up here when you open the app. They don't send notifications."),
      h("div", { class: "grid2" },
        field("Remind me to", h("input", { required: true, maxlength: 300, oninput: (e) => { f.text = e.target.value; } })),
        field("On", h("input", { type: "date", required: true, oninput: (e) => { f.due_on = e.target.value; } }))),
      h("div", {}, h("button", { type: "submit" }, "Set reminder")));
  }

  // ---- Work: opportunities, relationships, outcomes -----------------------------------
  async function renderWork(root) {
    const [items, actions] = await Promise.all([api("GET", "/api/items"), api("GET", "/api/actions")]);
    root.append(h("h2", { text: "Opportunities and relationships" }),
      h("p", { class: "muted" }, "Record what happened with one click. Outcomes are a record of what you observed, not proof that any wording caused them."));
    for (const it of items) {
      const edit = { ...it };
      root.append(h("section", { class: "card stack" },
        h("div", { class: "row spread" }, h("h3", { text: it.title + (it.org ? " · " + it.org : "") }),
          h("span", { class: "row" }, badge(it.kind), badge(it.status, it.status === "active" ? "ok" : ""), it.is_sample ? badge("Sample data", "warn") : null)),
        h("div", { class: "row" }, h("span", { class: "muted small" }, "What happened?"),
          S.enums.outcome_types.filter((t) => t !== "other").map((t) => btn(OUTCOME_LABELS[t], async () => {
            if (await act(() => api("POST", "/api/outcomes", { item_id: it.id, type: t }), "Recorded: " + OUTCOME_LABELS[t] + ".")) render();
          }))),
        it.outcomes.length ? h("ul", { class: "plain small" }, it.outcomes.map((o) => h("li", { class: "row" },
          badge(OUTCOME_LABELS[o.type], o.type === "interview" || o.type === "offer" || o.type === "reply" ? "ok" : ""), o.occurred_on,
          btn("Undo", async () => { await act(() => api("DELETE", "/api/outcomes/" + o.id)); render(); }, "link")))) : null,
        it.actions.length ? h("ul", { class: "plain" }, it.actions.map((a) => h("li", { class: "row spread" },
          h("span", {}, a.title, " ", badge(STATE_LABELS[a.state])),
          h("span", { class: "row" },
            a.state === "dropped" || a.state === "done" ? btn(a.state === "done" ? "Undo done" : "Bring back", () => setState(a, a.state === "done" ? "reviewed" : "suggested")) : btn("Work on it", () => startWork(a)))))) : null,
        h("details", {}, h("summary", { text: "Notes and details" }), h("div", { class: "stack" },
          field("Private notes (planning only; never sent to drafting)", h("textarea", { rows: 2, maxlength: 8000, value: it.private_notes, oninput: (e) => { edit.private_notes = e.target.value; } })),
          field("Context you're happy to use in a draft", h("textarea", { rows: 2, maxlength: 2000, value: it.shareable_context, oninput: (e) => { edit.shareable_context = e.target.value; } })),
          field("Status", select([["active", "Active"], ["waiting", "Waiting on them"], ["closed", "Closed"]], it.status, (v) => { edit.status = v; })),
          h("div", { class: "row" },
            btn("Save", async () => { const body = { kind: edit.kind, title: edit.title, org: edit.org, private_notes: edit.private_notes, shareable_context: edit.shareable_context, status: edit.status };
              if (await act(() => api("PUT", "/api/items/" + it.id, body), "Saved.")) render(); }, "primary"),
            btn("Delete", async () => { if (window.confirm("Delete this and its outcome history?")) { await act(() => api("DELETE", "/api/items/" + it.id)); render(); } }, "danger"))))));
    }
    const loose = actions.filter((a) => !a.item_id);
    if (loose.length) {
      root.append(h("section", { class: "card" }, h("h3", { text: "Other to-dos" }), h("ul", { class: "plain" }, loose.map((a) => h("li", { class: "row spread" },
        h("span", {}, a.title, " ", badge(STATE_LABELS[a.state])),
        h("span", { class: "row" },
          a.state === "done" || a.state === "dropped" ? btn(a.state === "done" ? "Undo done" : "Bring back", () => setState(a, a.state === "done" ? "reviewed" : "suggested")) : btn("Work on it", () => startWork(a)),
          btn("Delete", async () => { if (window.confirm("Delete this to-do?")) { await act(() => api("DELETE", "/api/actions/" + a.id)); render(); } }, "link")))))));
    }
    const f = { kind: "opportunity", title: "", org: "" };
    root.append(h("form", { class: "card stack", onsubmit: async (e) => { e.preventDefault(); if (await act(() => api("POST", "/api/items", f), "Added.")) render(); } },
      h("h3", { text: "Add an opportunity or a person" }),
      h("div", { class: "grid2" },
        field("Type", select([["opportunity", "Opportunity (role, programme)"], ["relationship", "Relationship (person)"]], f.kind, (v) => { f.kind = v; })),
        field("Name or title", h("input", { required: true, maxlength: 200, oninput: (e) => { f.title = e.target.value; } })),
        field("Organisation", h("input", { maxlength: 200, oninput: (e) => { f.org = e.target.value; } }))),
      h("div", {}, h("button", { type: "submit", class: "primary" }, "Add"))));
  }

  // ---- Evidence -----------------------------------------------------------------------
  const STATUS_LABELS = { unverified_user_claim: "Your claim, not yet verified", user_verified_with_artifact: "Verified with a source", do_not_claim: "Do not claim" };
  function parseMetrics(text) {
    return text.split("\n").map((l) => l.split("|").map((p) => p.trim())).filter((p) => p[0])
      .map((p) => ({ value: p[0], unit: p[1] || "", label: p[2] || "" }));
  }
  async function renderEvidence(root) {
    const list = await api("GET", "/api/evidence");
    root.append(h("h2", { text: "Evidence library" }),
      h("p", { class: "muted" }, "Every factual claim in a draft has to point at an entry here. Numbers are checked against the metrics you record."));
    const e0 = S.editEvidence || { title: "", claim: "", metrics: [], source_ref: "", status: "unverified_user_claim", permitted_uses: [], do_not_claim: "", confidential: false };
    const f = { ...e0, permitted_uses: new Set(e0.permitted_uses), metricsText: e0.metrics.map((m) => [m.value, m.unit, m.label].join(" | ")).join("\n") };
    root.append(h("form", { class: "card stack", onsubmit: async (e) => {
      e.preventDefault();
      const body = { title: f.title, claim: f.claim, metrics: parseMetrics(f.metricsText), source_ref: f.source_ref, status: f.status,
        permitted_uses: [...f.permitted_uses], do_not_claim: f.do_not_claim, confidential: !!f.confidential };
      const ok = await act(() => S.editEvidence ? api("PUT", "/api/evidence/" + S.editEvidence.id, body) : api("POST", "/api/evidence", body), "Saved.");
      if (ok) { S.editEvidence = null; render(); }
    } },
      h("h3", { text: S.editEvidence ? "Edit evidence" : "Add evidence" }),
      field("Short title", h("input", { required: true, maxlength: 200, value: f.title, oninput: (e) => { f.title = e.target.value; } })),
      field("What you can truthfully say", h("textarea", { required: true, rows: 2, maxlength: 2000, value: f.claim, oninput: (e) => { f.claim = e.target.value; } })),
      field("Numbers, one per line: value | unit | what it measures", h("textarea", { rows: 2, placeholder: "4 | segments | customer groups in the dashboard", value: f.metricsText, oninput: (e) => { f.metricsText = e.target.value; } })),
      h("div", { class: "grid2" },
        field("Status", select(S.enums.evidence_statuses.map((s) => [s, STATUS_LABELS[s]]), f.status, (v) => { f.status = v; })),
        field("Where the proof is (needed for “verified”)", h("input", { maxlength: 500, value: f.source_ref, oninput: (e) => { f.source_ref = e.target.value; } }))),
      h("div", { class: "row" }, h("span", { class: "muted small" }, "Approved for:"),
        S.enums.uses.map((u) => h("label", { class: "check" }, h("input", { type: "checkbox", checked: f.permitted_uses.has(u), onchange: (e) => { e.target.checked ? f.permitted_uses.add(u) : f.permitted_uses.delete(u); } }), u))),
      field("Never say (phrases separated by ; )", h("input", { maxlength: 1000, value: f.do_not_claim, oninput: (e) => { f.do_not_claim = e.target.value; } })),
      h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!f.confidential, onchange: (e) => { f.confidential = e.target.checked; } }), "Confidential (employer or school material): never send to AI drafting"),
      h("div", { class: "row" }, h("button", { type: "submit", class: "primary" }, S.editEvidence ? "Save changes" : "Add evidence"),
        S.editEvidence ? btn("Cancel", () => { S.editEvidence = null; render(); }) : null)));
    for (const e of list) {
      root.append(h("section", { class: "card stack" },
        h("div", { class: "row spread" }, h("h3", { text: "#" + e.id + " " + e.title }),
          h("span", { class: "row" },
            badge(STATUS_LABELS[e.status], e.status === "user_verified_with_artifact" ? "ok" : e.status === "do_not_claim" ? "bad" : "warn"),
            e.confidential ? badge("Confidential", "bad") : null, e.is_sample ? badge("Sample data", "warn") : null)),
        h("div", { text: e.claim }),
        e.metrics.length ? h("div", { class: "small" }, "Numbers: " + e.metrics.map((m) => m.value + " " + m.unit + (m.label ? " (" + m.label + ")" : "")).join("; ")) : null,
        h("div", { class: "small muted" }, "Approved for: " + (e.permitted_uses.join(", ") || "nothing yet") + (e.source_ref ? " · Source: " + e.source_ref : "") + (e.do_not_claim ? " · Never say: " + e.do_not_claim : "")),
        h("div", { class: "row" }, btn("Edit", () => { S.editEvidence = e; render(); $("workspace").scrollTop = 0; }),
          btn("Delete", async () => { if (window.confirm("Delete this evidence entry?")) { await act(() => api("DELETE", "/api/evidence/" + e.id)); render(); } }, "danger"))));
    }
  }

  // ---- Drafts -------------------------------------------------------------------------
  function reportView(draft) {
    const r = draft.report || {};
    const box = h("div", { class: "stack" });
    const overall = { passed: ["ok", "The automatic checks passed."], review: ["warn", "Needs your review before you use it."], blocked: ["bad", "Contains claims that aren't supported or aren't allowed."] }[r.overall] || ["", ""];
    box.append(h("div", { class: "notice " + overall[0], text: overall[1] }));
    for (const c of r.claims || []) {
      const worst = c.issues.some((i) => i.severity === "block") ? ["bad", "Problem"] : c.issues.length ? ["warn", "Review"] : ["ok", "Supported"];
      box.append(h("div", { class: "claim" }, h("div", { class: "row" }, badge(worst[1], worst[0]), h("span", { class: "muted small" }, "Evidence #" + c.evidence_id)),
        h("div", { text: "“" + c.text + "”" }), c.issues.map((i) => h("div", { class: "issue " + i.severity, text: i.message }))));
    }
    (r.body_issues || []).forEach((i) => box.append(h("div", { class: "issue " + i.severity, text: i.message })));
    if (draft.gaps && draft.gaps.length) box.append(h("div", {}, h("div", { class: "eyebrow" }, "Left out: no evidence for it"), h("ul", { class: "reasons" }, draft.gaps.map((g) => h("li", { text: g })))));
    if (r.not_checked) box.append(h("p", { class: "muted small", text: r.not_checked }));
    return box;
  }
  async function renderDrafts(root) {
    const D = S.draft;
    const [evidence, actions, drafts] = await Promise.all([api("GET", "/api/evidence"), api("GET", "/api/actions"), api("GET", "/api/drafts")]);
    const action = actions.find((a) => a.id === D.action_id) || null;
    if (!D.current && action) D.current = drafts.find((d) => d.action_id === action.id) || null;
    root.append(h("h2", { text: "Drafts" }),
      h("p", { class: "muted" }, "Drafting only sees what's on this page: the evidence you tick, your voice notes, and what you type here. It never sees your private planning notes or the chat."));
    if (!S.ai.available) root.append(h("div", { class: "notice warn", text: "AI drafting is unavailable (" + S.ai.reason + ") You can still write, save, and check drafts yourself." }));

    const reportBox = h("div", {});
    const stamp = h("span", { class: "muted small" });
    let timer = null;
    const editor = h("textarea", { rows: 9, maxlength: 20000, value: D.current ? D.current.body : "", placeholder: "Write here, or draft with AI.", "aria-label": "Draft text",
      oninput: () => { stamp.textContent = "Saving…"; clearTimeout(timer); timer = setTimeout(save, 900); } });
    async function save() {
      const body = { draft_id: D.current ? D.current.id : null, action_id: D.action_id, purpose: D.purpose, audience: D.audience, body: editor.value };
      const saved = await act(() => api("POST", "/api/drafts/save", body));
      if (!saved) return;
      D.current = saved;
      stamp.textContent = "Saved automatically.";
      reportBox.replaceChildren(reportView(saved));
    }
    if (D.current) reportBox.append(reportView(D.current));

    root.append(h("section", { class: "card stack" },
      h("div", { class: "grid2" },
        field("For which to-do", select([["", "(not linked)"]].concat(actions.filter((a) => a.state !== "dropped").map((a) => [a.id, a.title])), D.action_id || "", (v) => { D.action_id = v ? Number(v) : null; D.current = null; render(); })),
        field("Kind of text", select(PURPOSES, D.purpose, (v) => { D.purpose = v; })),
        field("Audience (matches your voice samples)", h("input", { maxlength: 60, value: D.audience, placeholder: "recruiter, peer, alum…", oninput: (e) => { D.audience = e.target.value; } }))),
      h("div", {}, h("div", { class: "eyebrow" }, "Evidence to use"),
        evidence.length ? h("div", { class: "stack" }, evidence.map((e) => h("label", { class: "check" },
          h("input", { type: "checkbox", checked: D.evidence_ids.has(e.id), onchange: (ev) => { ev.target.checked ? D.evidence_ids.add(e.id) : D.evidence_ids.delete(e.id); } }),
          "#" + e.id + " " + e.title, e.confidential ? badge("Confidential: will be held back", "bad") : null, e.status === "do_not_claim" ? badge("Do not claim: held back", "bad") : null)))
          : h("p", { class: "muted small", text: "No evidence yet. Add some on the Evidence page; without it a draft can't make factual claims." })),
      field("What you want it to say or do", h("textarea", { rows: 2, maxlength: 1500, value: D.instruction, oninput: (e) => { D.instruction = e.target.value; } })),
      field("Extra context you approve for this draft", h("textarea", { rows: 2, maxlength: 1500, value: D.shareable_note, oninput: (e) => { D.shareable_note = e.target.value; } })),
      action && action.item_id ? h("label", { class: "check" }, h("input", { type: "checkbox", checked: D.include_item_context, onchange: (e) => { D.include_item_context = e.target.checked; } }), "Also include the shareable context saved for this person or role") : null,
      h("div", { class: "row" },
        h("button", { type: "button", class: "primary", disabled: !S.ai.available, onclick: async (ev) => {
          ev.target.disabled = true; ev.target.textContent = "Drafting…";
          const body = { action_id: D.action_id, purpose: D.purpose, audience: D.audience, evidence_ids: [...D.evidence_ids], instruction: D.instruction, shareable_note: D.shareable_note, include_item_context: D.include_item_context };
          const out = await act(() => api("POST", "/api/drafts/generate", body));
          if (out) {
            D.current = out.draft;
            if (out.excluded_evidence.length) toast("Held back: " + out.excluded_evidence.map((x) => x.title + " (" + x.reason + ")").join("; "));
            say("companion", out.draft.report.overall === "passed" ? "Draft's ready and the checks passed. Still read it before you use it."
              : "Draft's ready, and I flagged things to look at. The notes are under the text.");
          }
          await refreshStatus(); render();
        } }, S.ai.mode === "mock" ? "Draft with mock AI" : "Draft with AI"),
        h("span", { class: "muted small" }, S.ai.available && S.ai.mode === "live" ? "Sends the ticked evidence, voice notes and this form to the AI provider." : ""))));

    root.append(h("section", { class: "card stack" },
      h("div", { class: "row spread" }, h("h3", { text: "Text" }), stamp), editor,
      h("div", { class: "row" },
        btn("Copy text", async () => {
          try { await navigator.clipboard.writeText(editor.value); } catch (e) { editor.select(); document.execCommand("copy"); }
          if (D.current) api("POST", "/api/drafts/" + D.current.id + "/copied").catch(() => {});
          toast("Copied. Nothing was marked as sent: tick that off yourself once it really is.");
        }),
        action && action.state === "drafted" ? btn("I've reviewed it", () => setState(action, "reviewed")) : null,
        action && action.state !== "done" ? btn("I sent or applied it myself", () => setState(action, "done", "Mark as done? Only once you've actually sent, applied, or updated it yourself.")) : null,
        action ? badge(STATE_LABELS[action.state], action.state === "done" ? "ok" : "") : null),
      reportBox));

    if (drafts.length) {
      root.append(h("details", {}, h("summary", { text: "Saved drafts (" + drafts.length + ")" }), h("ul", { class: "plain" }, drafts.slice(0, 20).map((d) => h("li", { class: "row spread card" },
        h("span", {}, badge(d.purpose.replace("_", " ")), " ", d.body.slice(0, 90) + (d.body.length > 90 ? "…" : "")),
        h("span", { class: "row" }, btn("Open", () => { D.current = d; D.action_id = d.action_id; D.purpose = d.purpose; D.audience = d.audience; render(); }),
          btn("Delete", async () => { if (window.confirm("Delete this draft?")) { await act(() => api("DELETE", "/api/drafts/" + d.id)); if (D.current && D.current.id === d.id) D.current = null; render(); } }, "link")))))));
    }
  }

  // ---- Pasted material ----------------------------------------------------------------
  async function renderMaterial(root) {
    const list = await api("GET", "/api/imports");
    root.append(h("h2", { text: "Pasted material" }),
      h("div", { class: "notice" }, "Paste job descriptions, messages, or your profile text here. It's treated as reference only: nothing in it can change what the companion remembers or does. This app never fetches web pages or opens LinkedIn."));
    const f = { kind: "job_description", label: "", content: "" };
    root.append(h("form", { class: "card stack", onsubmit: async (e) => { e.preventDefault(); if (await act(() => api("POST", "/api/imports", f), "Saved.")) render(); } },
      h("div", { class: "grid2" },
        field("What is it", select(S.enums.import_kinds.map((k) => [k, k.replace("_", " ")]), f.kind, (v) => { f.kind = v; })),
        field("Label", h("input", { required: true, maxlength: 200, oninput: (e) => { f.label = e.target.value; } }))),
      field("Paste the text", h("textarea", { required: true, rows: 5, maxlength: 60000, oninput: (e) => { f.content = e.target.value; } })),
      h("div", {}, h("button", { type: "submit", class: "primary" }, "Save material"))));
    if (S.compare) {
      root.append(h("section", { class: "card stack" }, h("div", { class: "row spread" }, h("h3", { text: "Comparison: " + S.compare.label }), btn("Close", () => { S.compare = null; render(); }, "link")),
        h("p", { text: S.compare.result.summary }),
        h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", { text: "They ask for" }), h("th", { text: "Your evidence" }), h("th", { text: "Gap" }))),
          h("tbody", {}, S.compare.result.requirements.map((r) => h("tr", {}, h("td", { text: r.requirement }),
            h("td", {}, r.evidence.length ? r.evidence.map((e) => h("div", {}, "#" + e.id + " " + e.title + " ", badge(e.status === "user_verified_with_artifact" ? "verified" : "unverified", e.status === "user_verified_with_artifact" ? "ok" : "warn"))) : h("span", { class: "muted", text: "None" })),
            h("td", { text: r.gap })))))),
        h("p", { class: "muted small", text: "A match means an evidence entry relates to the requirement, not that it proves you meet it." })));
    }
    for (const m of list) {
      root.append(h("section", { class: "card stack" },
        h("div", { class: "row spread" }, h("h3", { text: m.label }), h("span", { class: "row" }, badge(m.kind.replace("_", " ")), badge(m.length + " characters"))),
        h("div", { class: "muted small", text: m.content + (m.length > 300 ? "…" : "") }),
        h("div", { class: "row" },
          h("button", { type: "button", disabled: !S.ai.available, onclick: async (ev) => {
            ev.target.disabled = true; ev.target.textContent = "Comparing…";
            const result = await act(() => api("POST", "/api/compare", { import_id: m.id }));
            if (result) S.compare = { label: m.label, result };
            await refreshStatus(); render();
          } }, "Compare with my evidence"),
          btn("Attach to my next chat message", () => { S.attachImport = { id: m.id, label: m.label }; renderAttach(); $("chat-input").focus(); }),
          btn("Delete", async () => { if (window.confirm("Delete this pasted material?")) { await act(() => api("DELETE", "/api/imports/" + m.id)); render(); } }, "danger"))));
    }
  }

  // ---- About me -----------------------------------------------------------------------
  async function renderMe(root) {
    const list = await api("GET", "/api/memory");
    root.append(h("h2", { text: "What the companion knows about you" }),
      h("p", { class: "muted" }, "This is everything it remembers. Edit or delete any of it. The companion can suggest additions in chat, but nothing is saved without your click."));
    const groups = [["Private planning context", "Used to plan with you. Never sent to drafting.", S.enums.memory_private],
                    ["Voice for outward writing", "Sent to drafting, matched by audience.", S.enums.memory_public]];
    for (const [title, sub, kinds] of groups) {
      const sec = h("section", { class: "card stack" }, h("h3", { text: title }), h("p", { class: "muted small", text: sub }));
      const mine = list.filter((m) => kinds.includes(m.kind));
      if (!mine.length) sec.append(h("p", { class: "muted small", text: "Nothing here yet." }));
      for (const m of mine) {
        const ta = h("textarea", { rows: 2, maxlength: 4000, value: m.text, "aria-label": MEMORY_LABELS[m.kind] });
        sec.append(h("div", { class: "stack" },
          h("div", { class: "row" }, badge(MEMORY_LABELS[m.kind]), m.audience ? badge("for: " + m.audience) : null,
            badge(m.provenance === "user_confirmed" ? "suggested by AI, confirmed by you" : m.provenance === "sample" ? "sample data" : "typed by you", m.provenance === "sample" ? "warn" : "")),
          ta,
          h("div", { class: "row" }, btn("Save", () => act(() => api("PUT", "/api/memory/" + m.id, { kind: m.kind, text: ta.value, audience: m.audience }), "Saved.")),
            btn("Delete", async () => { await act(() => api("DELETE", "/api/memory/" + m.id), "Deleted."); render(); }, "danger"))));
      }
      root.append(sec);
    }
    const f = { kind: "voice_sample", text: "", audience: "" };
    root.append(h("form", { class: "card stack", onsubmit: async (e) => { e.preventDefault(); if (await act(() => api("POST", "/api/memory", f), "Added.")) render(); } },
      h("h3", { text: "Add something" }),
      h("div", { class: "grid2" },
        field("Type", select(S.enums.memory_public.concat(S.enums.memory_private).map((k) => [k, MEMORY_LABELS[k]]), f.kind, (v) => { f.kind = v; })),
        field("Audience (voice items only)", h("input", { maxlength: 60, placeholder: "recruiter, peer, alum…", oninput: (e) => { f.audience = e.target.value; } }))),
      field("Text (for a writing sample, paste something you wrote)", h("textarea", { required: true, rows: 3, maxlength: 4000, oninput: (e) => { f.text = e.target.value; } })),
      h("div", {}, h("button", { type: "submit", class: "primary" }, "Add"))));
  }

  // ---- Budget & data ------------------------------------------------------------------
  async function renderData(root) {
    const [b, activity] = await Promise.all([api("GET", "/api/budget"), api("GET", "/api/activity")]);
    const s = b.status;
    root.append(h("h2", { text: "Budget and data" }));
    root.append(h("section", { class: "card stack" }, h("h3", { text: "AI spending this month (" + s.month + ", UTC)" }),
      h("div", { class: "notice " + (s.level === "hard_stop" ? "bad" : s.level === "warn" ? "warn" : "ok") },
        money(s.committed_usd) + " committed. New AI calls stop at " + money(s.hard_stop_usd) + " of your " + money(s.monthly_budget_usd) + " budget. " + money(s.remaining_before_stop_usd) + " left before the stop."),
      h("p", { class: "small" }, "Today: " + money(s.today_usd) + " of " + money(s.day_cap_usd) + ". Per session: " + money(s.session_cap_usd) + ". " +
        (s.unknown_calls ? s.unknown_calls + " call(s) with an unknown outcome are counted at their maximum (" + money(s.unknown_usd) + "). " : "") +
        "Prices verified " + s.prices_verified_on + (s.prices_fresh ? "." : ": out of date, so live AI is switched off.")),
      h("p", { class: "small muted" }, "AI status: " + b.ai.reason + " In live mode, the text you send for chat, drafting, or comparison goes to the AI provider. In mock mode nothing leaves this Mac."),
      (function () {
        const amount = h("input", { type: "number", step: "0.01", min: 0, placeholder: "e.g. 3.42", "aria-label": "Console total" });
        return h("form", { class: "row", onsubmit: async (e) => { e.preventDefault(); if (amount.value === "") return; await act(() => api("POST", "/api/budget/reconcile", { console_total_usd: Number(amount.value) }), "Matched to your Console figure."); await refreshStatus(); render(); } },
          h("span", { class: "small" }, "Match to the provider Console's month-to-date total:"), amount, h("button", { type: "submit" }, "Reconcile"),
          h("span", { class: "muted small" }, "The Console may lag behind recent calls. Do this well after your last AI call."));
      })(),
      b.recent.length ? h("details", {}, h("summary", { text: "Recent AI calls" }), h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, ["When", "Type", "Model", "Status", "Reserved", "Cost", "In", "Out"].map((t) => h("th", { text: t })))),
        h("tbody", {}, b.recent.map((r) => h("tr", {}, [r.ts, r.call_type, r.model, r.status, money(r.reserved_usd), "$" + Number(r.cost_usd).toFixed(4), r.in_tok, r.out_tok].map((t) => h("td", { text: String(t) })))))))) : null));

    const phrase = h("input", { placeholder: "DELETE EVERYTHING", "aria-label": "Type DELETE EVERYTHING to confirm" });
    root.append(h("section", { class: "card stack" }, h("h3", { text: "Your data" }),
      h("p", { class: "small" }, "Everything is stored in one database file on this Mac. Chat transcripts are deleted after 30 days."),
      h("div", { class: "row" }, h("a", { class: "button", href: "/api/export", download: "career-companion-export.json" }, "Export everything (JSON)"),
        S.hasSample ? btn("Remove sample data", async () => { await act(() => api("POST", "/api/sample/remove"), "Removed."); await refreshStatus(); render(); })
          : btn("Load labelled sample data", async () => { await act(() => api("POST", "/api/sample/load"), "Loaded."); await refreshStatus(); await render(); await greet(); })),
      h("p", { class: "small muted" }, "Deleting removes the database files. It can't reach Time Machine or other backups, exports you saved, or the copies the AI provider keeps for up to 30 days. It isn't forensic erasure."),
      h("form", { class: "row", onsubmit: async (e) => { e.preventDefault(); if (await act(() => api("POST", "/api/wipe", { confirm: phrase.value }), "Everything was deleted.")) { $("chat-log").replaceChildren(); await refreshStatus(); S.draft.current = null; S.draft.action_id = null; S.draft.evidence_ids.clear(); await startDockAfterWipe(); render(); } } },
        phrase, h("button", { type: "submit", class: "danger" }, "Delete everything"))));

    root.append(h("section", { class: "card" }, h("h3", { text: "Activity log" }),
      h("p", { class: "muted small" }, "Events, counts and costs only. No message or draft text is logged."),
      h("div", { class: "table-wrap" }, h("table", {}, h("tbody", {}, activity.slice(0, 40).map((a) => h("tr", {}, h("td", { text: a.ts }), h("td", { text: a.event }), h("td", { text: a.detail }))))))));
  }
  async function startDockAfterWipe() {
    say("companion", "Everything's deleted. We can start again whenever you like.");
    if (!S.onboarding.done) { say("companion", S.onboarding.question); $("chat-skip").classList.remove("hidden"); }
  }

  // ---- shell --------------------------------------------------------------------------
  const RENDERERS = { today: renderToday, work: renderWork, evidence: renderEvidence, drafts: renderDrafts, material: renderMaterial, me: renderMe, data: renderData };
  let renderSeq = 0;
  async function render() {
    const seq = ++renderSeq;
    $("tabs").replaceChildren(...TABS.map(([id, label]) => h("button", { type: "button", "aria-current": String(S.tab === id), onclick: () => { S.tab = id; render(); } }, label)));
    const fresh = h("div", {});
    try { await RENDERERS[S.tab](fresh); }
    catch (err) { fresh.replaceChildren(h("div", { class: "notice bad", text: err.message })); }
    if (seq === renderSeq) $("workspace").replaceChildren(fresh);
  }

  (async function init() {
    try {
      await refreshStatus();
      await render();
      await startDock();
    } catch (err) {
      $("workspace").replaceChildren(h("div", { class: "notice bad", text: err.message }));
    }
  })();
})();
