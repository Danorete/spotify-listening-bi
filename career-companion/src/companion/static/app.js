// Career Companion interface ("Daylight" design).
// All dynamic text is inserted as text nodes, never as HTML, so model output and pasted
// material cannot inject markup or script. No inline style attributes: the page's
// Content-Security-Policy forbids them, so styling is by class and dimensions by CSSOM.
(function () {
  "use strict";

  const store = {
    get(k, d) { try { const v = window.localStorage.getItem("cc." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { window.localStorage.setItem("cc." + k, JSON.stringify(v)); } catch (e) { /* layout preference only */ } },
  };
  const S = {
    csrf: "", ai: {}, budget: {}, onboarding: {}, enums: {}, hasSample: false,
    tab: "today", minutes: store.get("minutes", 20), skipped: new Set(), session: null, timeUpSaid: null,
    busy: 0, attachImport: null, compare: null, open: new Set(), editEvidence: null, evidenceForm: false, pasteKind: "job_description",
    draft: { action_id: null, purpose: "outreach", audience: "", evidence_ids: new Set(), instruction: "",
             shareable_note: "", include_item_context: false, current: null },
  };
  const NAV = [["today", "Today", "today"], ["people", "People & roles", "people"], ["evidence", "Evidence", "evidence"],
               ["drafts", "Drafts", "drafts"], ["me", "About me", "me"]];
  const NAV_MINOR = [["pasted", "Pasted material", "pasted"], ["settings", "Settings & data", "settings"]];
  const PURPOSES = [["outreach", "First message"], ["follow_up", "Follow-up"], ["profile", "Profile text"],
                    ["application", "Résumé or application text"], ["post", "Post"], ["interview_prep", "Interview answer"]];
  const KIND_TO_PURPOSE = { outreach: "outreach", follow_up: "follow_up", profile_edit: "profile",
                            application: "application", interview_prep: "interview_prep" };
  const OUTCOME = { reply: "Got a reply", interview: "Interview", no_response: "No response", rejection: "Rejection", offer: "Offer", other: "Other" };
  const STATE = { suggested: "Not started", drafted: "Drafted", reviewed: "Reviewed", done: "Done", dropped: "Dropped" };
  const MEMORY = { goal: "Goal", constraint: "Constraint", preference: "Working preference", boundary: "Boundary",
                   voice_note: "Voice note", voice_sample: "Writing sample", drafting_rule: "Drafting rule" };
  const EV_STATUS = { unverified_user_claim: "Your claim, not yet verified", user_verified_with_artifact: "Verified with a source", do_not_claim: "Do not claim" };
  const PROPS = new Set(["value", "checked", "disabled", "selected", "open"]);
  const $ = (id) => document.getElementById(id);

  // ---- DOM helpers ----------------------------------------------------------------------
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
  const NS = "http://www.w3.org/2000/svg";
  function sv(tag, attrs, ...kids) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
    el.append(...kids);
    return el;
  }
  const PATHS = {
    today: ["M12 8a4 4 0 1 0 0 8a4 4 0 0 0 0-8z", "M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4"],
    people: ["M5 7h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z", "M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"],
    evidence: ["M6 3h9l4 4v14H6z", "M9 14l2 2 4-4"],
    drafts: ["M4 20h4L19 9l-4-4L4 16z"],
    me: ["M12 4a4 4 0 1 0 0 8a4 4 0 0 0 0-8z", "M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"],
    pasted: ["M3 13l3-8h12l3 8v6H3z", "M3 13h5l1 3h6l1-3h5"],
    settings: ["M4 7h10M18 7h2M4 17h2M10 17h10", "M16 5a2 2 0 1 0 0 4a2 2 0 0 0 0-4z", "M8 15a2 2 0 1 0 0 4a2 2 0 0 0 0-4z"],
    chev: ["M9 6l6 6-6 6"], down: ["M6 9l6 6 6-6"], plus: ["M12 5v14M5 12h14"],
    collapse: ["M13 6l6 6-6 6M5 6l6 6-6 6"], send: ["M12 19V5M6 11l6-6 6 6"], bookmark: ["M7 3h10v18l-5-4-5 4z"],
    warn: ["M12 3l10 17H2z", "M12 10v4M12 17v.5"], info: ["M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18z", "M12 8v5M12 16v.5"],
    help: ["M12 3a9 9 0 1 0 0 18a9 9 0 0 0 0-18z", "M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17v.5"],
    docplus: ["M6 3h9l4 4v14H6z", "M12 11v6M9 14h6"], clip: ["M7 4h10a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z", "M9 4V3h6v1M9 10h6M9 14h4"],
  };
  function icon(name, size) {
    return sv("svg", { width: size || 18, height: size || 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2",
      "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" }, ...PATHS[name].map((d) => sv("path", { d })));
  }
  function playIcon() { return sv("svg", { width: 16, height: 16, viewBox: "0 0 24 24", fill: "currentColor", "aria-hidden": "true" }, sv("path", { d: "M7 4l13 8-13 8z" })); }
  function orbSvg(size) {
    return sv("svg", { width: size, height: size, viewBox: "0 0 40 40", "aria-hidden": "true" },
      sv("circle", { class: "bg", cx: 20, cy: 20, r: 18.5 }), sv("circle", { class: "ring-a", cx: 20, cy: 20, r: 12 }), sv("circle", { class: "core", cx: 20, cy: 20, r: 5 }));
  }
  // Session ring: `fraction` of the circle is drawn; the label sits in the middle.
  function ring(size, fraction, num, unit, cls) {
    const stroke = size > 80 ? 10 : 5, r = (size - stroke) / 2, c = 2 * Math.PI * r;
    const f = Math.max(0, Math.min(1, fraction));
    return h("div", { class: "ring " + (cls || ""), role: "img", "aria-label": num + " " + unit },
      sv("svg", { width: size, height: size, viewBox: "0 0 " + size + " " + size, "aria-hidden": "true" },
        sv("circle", { class: "track", cx: size / 2, cy: size / 2, r, "stroke-width": stroke }),
        sv("circle", { class: "arc", cx: size / 2, cy: size / 2, r, "stroke-width": stroke, "stroke-dasharray": (c * f).toFixed(1) + " " + c.toFixed(1) })),
      h("div", { class: "ring-label" }, h("span", { class: "num", text: String(num) }), h("span", { class: "unit", text: unit })));
  }
  function fill(el, ...kids) { el.replaceChildren(...kids.flat(Infinity).filter((k) => k != null && k !== false)); return el; }
  const btn = (label, onclick, cls) => h("button", { type: "button", class: "btn " + (cls || ""), onclick }, label);
  const chip = (label, cls) => h("span", { class: "chip " + (cls || "") }, label);
  const field = (label, control) => h("label", { class: "field" }, label, control);
  const select = (options, value, onchange) => h("select", { onchange: (e) => onchange(e.target.value) },
    options.map(([v, l]) => h("option", { value: v, selected: String(v) === String(value) }, l)));
  const money = (n) => "$" + Number(n).toFixed(2);
  const plural = (n, one, many) => n + " " + (n === 1 ? one : many);
  function help(label, ...body) {
    return h("details", { class: "help" }, h("summary", {}, icon("help", 16), label), h("div", {}, body.map((b) => (typeof b === "string" ? h("p", { text: b }) : b))));
  }
  // A collapsible row. Open/closed survives re-rendering.
  function disc(key, title, hint, ...body) {
    const d = h("details", { class: "disc", open: S.open.has(key), ontoggle: (e) => { e.target.open ? S.open.add(key) : S.open.delete(key); } },
      h("summary", {}, h("span", {}, h("span", { class: "t", text: title }), hint ? h("span", { class: "hint", text: " · " + hint }) : null), icon("chev", 16)),
      h("div", { class: "disc-body" }, body));
    return d;
  }
  function pageHead(title, lead, ...extra) {
    return h("header", { class: "page-head" }, h("h2", { text: title }), lead ? h("p", { class: "lead", text: lead }) : null, extra);
  }

  async function api(method, path, body) {
    const opts = { method, headers: {} };
    if (method !== "GET") {
      opts.headers["X-CSRF-Token"] = S.csrf;
      if (method !== "DELETE") { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body || {}); }
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
      err.status = resp.status;
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
    try { const out = await fn(); if (okMsg) toast(okMsg); return out === undefined ? true : out; }
    catch (err) { toast(err.message); return undefined; }
  }
  async function thinking(fn) {
    S.busy += 1; syncCompanion();
    try { return await fn(); } finally { S.busy -= 1; syncCompanion(); }
  }

  // ---- status, sidebar, session timer ---------------------------------------------------
  async function refreshStatus() {
    const b = await api("GET", "/api/bootstrap");
    Object.assign(S, { csrf: b.csrf, ai: b.ai, budget: b.budget, onboarding: b.onboarding, enums: b.enums, hasSample: b.has_sample });
    renderSide(); syncCompanion();
  }
  async function loadToday() {
    const view = await api("GET", "/api/today?minutes=" + S.minutes);
    S.session = view.session;
    renderSide();
    return view;
  }
  function secondsLeft() {
    if (!S.session) return 0;
    return S.session.minutes * 60 - (Date.now() - Date.parse(S.session.started_at)) / 1000;
  }
  function renderSide() {
    const b = S.budget, level = b.level === "hard_stop" ? "bad" : b.level === "warn" ? "warn" : "";
    const mode = !S.ai.available ? ["AI is off", "bad"] : S.ai.mode === "mock" ? ["Mock AI", "warn"] : ["Live AI", ""];
    const link = ([id, label, ic], minor) => h("a", { class: "nav-link" + (minor ? " minor" : ""), href: "#" + id, "aria-current": S.tab === id ? "page" : null }, icon(ic, minor ? 16 : 18), label);
    let session = null;
    if (S.session) {
      const left = secondsLeft(), mins = Math.max(0, Math.ceil(left / 60));
      session = h("div", { class: "side-session" }, ring(32, left / (S.session.minutes * 60), mins, "minutes left", "mini" + (left <= 0 ? " done" : "")),
        h("div", { class: "grow" }, h("strong", { text: left > 0 ? mins + " min left" : "Time's up" }), h("span", { class: "muted", text: "Session" })),
        btn("End", endSession, "quiet"));
    }
    fill($("side"),
      h("div", { class: "brand" }, sv("svg", { width: 26, height: 26, viewBox: "0 0 26 26", "aria-hidden": "true" }, sv("circle", { cx: 13, cy: 13, r: 12, fill: "#4338CA" }), sv("circle", { cx: 13, cy: 13, r: 5, fill: "#F1F2F7" })), h("span", { text: "Career Companion" })),
      NAV.map((n) => link(n, false)), h("div", { class: "side-spacer" }), NAV_MINOR.map((n) => link(n, true)), session,
      h("a", { class: "side-status", href: "#settings", title: S.ai.reason || "" },
        h("span", { class: "mode" }, h("span", { class: "dot " + mode[1] }), mode[0]),
        h("span", { class: "detail muted", text: !S.ai.available ? "Everything else still works." : S.ai.mode === "mock" ? "Canned replies. Nothing leaves this Mac." : "Text you send goes to the AI provider." }),
        h("span", { class: "detail split" }, h("span", { text: "AI budget" }), h("span", { text: money(b.committed_usd || 0) + " / $" + Math.round(b.hard_stop_usd || 16) })),
        (function () { const m = h("span", { class: "detail meter " + level }, h("span", {})); m.firstChild.style.width = Math.min(100, 100 * (b.committed_usd || 0) / (b.hard_stop_usd || 16)) + "%"; return m; })()));
  }
  async function endSession() {
    await act(() => api("POST", "/api/session/end"));
    S.session = null;
    say("companion", "Session ended. Your place is saved.");
    renderSide();
    if (S.tab === "today") render();
  }
  function tick() {
    if (!S.session) return;
    renderSide();
    if (secondsLeft() <= 0 && S.timeUpSaid !== S.session.id) {
      S.timeUpSaid = S.session.id;
      say("companion", "That's your " + S.session.minutes + " minutes. Good place to stop: note where you left it and I'll have it ready next time.");
    }
    const live = $("live-ring");
    if (live) live.replaceWith(liveRing());
  }

  // ---- companion ------------------------------------------------------------------------
  function syncCompanion() {
    const pending = document.querySelectorAll("#chat-log .proposal").length;
    let state = "ready", text = S.ai.mode === "mock" ? "Ready · mock replies" : "Ready";
    if (!S.ai.available) { state = "off"; text = "AI is off. I still keep your place."; }
    else if (S.busy > 0) { state = "thinking"; text = "Thinking…"; }
    else if (pending) { state = "waiting"; text = "Waiting for your OK"; }
    for (const el of document.querySelectorAll(".orb")) el.className = "orb is-" + state;
    $("dock-status").textContent = text;
    fill($("dock-pill"), h("span", { class: "orb is-" + state }, orbSvg(36)), "Tempo", pending ? h("span", { class: "count", text: String(pending) }) : null);
    $("dock-pill").setAttribute("aria-label", "Open Tempo, your companion" + (pending ? ", " + plural(pending, "suggestion", "suggestions") + " waiting" : ""));
  }
  function say(role, text) {
    const el = h("div", { class: "msg " + role, text });
    $("chat-log").append(el);
    el.scrollIntoView({ block: "end" });
    return el;
  }
  function proposalCard(p) {
    const pl = p.payload;
    const what = p.kind === "memory" ? "“" + pl.text + "” as a " + (MEMORY[pl.memory_kind] || pl.memory_kind).toLowerCase() + "."
      : p.kind === "reminder" ? "A reminder on " + pl.due_on + ": “" + pl.text + "”" : "Park this idea: “" + pl.text + "”";
    const decide = async (accept) => {
      const ok = await act(() => api("POST", "/api/proposals/" + p.id + (accept ? "/accept" : "/reject")), accept ? "Saved." : null);
      if (ok === undefined) return;
      card.remove(); syncCompanion();
      if (accept) render();
    };
    const card = h("div", { class: "proposal", role: "group", "aria-label": "Suggestion waiting for your decision" },
      h("div", { class: "eyebrow", text: p.kind === "memory" ? "Remember this?" : p.kind === "reminder" ? "Set this reminder?" : "Park this?" }),
      h("div", { text: what + " Nothing is saved until you say so." }),
      h("div", { class: "row" }, btn("Save it", () => decide(true), "dark"), btn("No thanks", () => decide(false))));
    $("chat-log").append(card);
    card.scrollIntoView({ block: "end" });
    syncCompanion();
  }
  function renderAttach() {
    fill($("chat-attach"), S.attachImport ? h("div", { class: "notice" }, h("span", { class: "grow" },
      "Attached to your next message: " + S.attachImport.label + ". Suggestions are off for that message."),
      btn("Remove", () => { S.attachImport = null; renderAttach(); }, "quiet")) : null);
  }
  async function greet() {
    const view = await loadToday();
    say("companion", view.greeting);
    if (view.reminders.length) say("companion", view.reminders.length === 1 ? "One reminder is due: " + view.reminders[0].text : view.reminders.length + " reminders are due. They're on Today.");
  }
  function setDock(open) {
    document.body.classList.toggle("dock-closed", !open);
    store.set("dockOpen", open);
    if (open) $("chat-input").focus(); else $("dock-pill").focus();
  }
  function setDockWidth(w) {
    const max = Math.max(320, Math.min(640, window.innerWidth - 760));
    const width = Math.round(Math.max(320, Math.min(max, w)));
    document.documentElement.style.setProperty("--dock-w", width + "px");
    const r = $("resize");
    r.setAttribute("aria-valuenow", width); r.setAttribute("aria-valuemin", 320); r.setAttribute("aria-valuemax", max);
    store.set("dockW", width);
    return width;
  }
  function startDock() {
    $("orb").append(orbSvg(40));
    $("dock-collapse").append(icon("collapse", 18));
    $("chat-send").append(icon("send", 18));
    $("dock-collapse").addEventListener("click", () => setDock(false));
    $("dock-pill").addEventListener("click", () => setDock(true));
    const narrow = window.matchMedia("(max-width: 1000px)").matches;
    document.body.classList.toggle("dock-closed", !store.get("dockOpen", !narrow) || narrow);
    let width = setDockWidth(store.get("dockW", 400));
    const r = $("resize");
    r.addEventListener("pointerdown", (e) => {
      r.setPointerCapture(e.pointerId);
      const move = (ev) => { width = setDockWidth(window.innerWidth - ev.clientX - 18); };
      const up = () => { r.removeEventListener("pointermove", move); r.removeEventListener("pointerup", up); };
      r.addEventListener("pointermove", move); r.addEventListener("pointerup", up);
    });
    r.addEventListener("keydown", (e) => {
      const step = { ArrowLeft: 24, ArrowRight: -24, Home: 1000, End: -1000 }[e.key];
      if (step) { e.preventDefault(); width = setDockWidth(width + step); }
    });
    const input = $("chat-input");
    input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(140, input.scrollHeight) + "px"; });
    input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("chat-form").requestSubmit(); } });
    $("chat-form").addEventListener("submit", (e) => { e.preventDefault(); const v = input.value.trim(); if (v) submitChat(v); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && window.matchMedia("(max-width: 1000px)").matches && !document.body.classList.contains("dock-closed")) setDock(false); });
  }
  async function submitChat(text) {
    const input = $("chat-input");
    input.value = ""; input.style.height = "auto";
    say("user", text);
    const attached = S.attachImport;
    S.attachImport = null; renderAttach();
    const r = await thinking(() => act(() => api("POST", "/api/chat", { message: text, import_id: attached ? attached.id : null })));
    if (!r) return;
    if (r.reply) say("companion", r.reply); else say("system", r.unavailable + " Your message was saved.");
    r.proposals.forEach(proposalCard);
    if (attached && r.dropped_proposals) say("system", "That reply tried to save something. That's blocked for messages with pasted material.");
    refreshStatus();
  }

  // ---- shared actions -------------------------------------------------------------------
  async function setState(action, state, question) {
    if (question && !window.confirm(question)) return;
    const out = await act(() => api("POST", "/api/actions/" + action.id + "/state", { state }));
    if (!out) return;
    if (state === "done") say("companion", "Marked done: " + action.title + ". When you hear back, record it under People & roles.");
    render();
  }
  function openFor(action) {
    if (action.kind === "job_compare") { S.pasteKind = "job_description"; go("pasted"); return; }
    Object.assign(S.draft, { action_id: action.id, purpose: KIND_TO_PURPOSE[action.kind] || "outreach", current: null });
    go("drafts");
  }
  async function startSession(action) {
    const session = await act(() => api("POST", "/api/session/start", { minutes: S.minutes, action_id: action.id }));
    if (!session) return;
    S.session = session;
    say("companion", action.kind === "job_compare"
      ? S.minutes + " minutes on: " + action.title + ". Paste the job description and I'll line it up against your evidence."
      : S.minutes + " minutes on: " + action.title + ". Pick the evidence to lean on, then write it yourself or with me. I'll keep your place.");
    renderSide();
    openFor(action);
  }
  function go(tab) { if (window.location.hash === "#" + tab) { S.tab = tab; render(); } else window.location.hash = tab; }
  function dueText(deadline, today) {
    const days = Math.round((Date.parse(deadline) - Date.parse(today)) / 86400000);
    if (days < 0) return "Overdue by " + plural(-days, "day", "days");
    if (days === 0) return "Due today";
    if (days === 1) return "Due tomorrow";
    const d = new Date(deadline + "T12:00:00");
    return "Due " + (days < 7 ? d.toLocaleDateString(undefined, { weekday: "long" }) : d.toLocaleDateString(undefined, { day: "numeric", month: "short" }));
  }
  function sampleNotice() {
    return S.hasSample ? h("div", { class: "notice warn center" }, icon("info", 18), h("span", { class: "grow", text: "Sample data is loaded. Anything marked [SAMPLE] is fictional." }),
      btn("Remove it", async () => { await act(() => api("POST", "/api/sample/remove"), "Sample data removed."); await refreshStatus(); render(); }, "quiet")) : null;
  }

  // ---- onboarding: the companion, one question at a time ---------------------------------
  function renderOnboarding(root) {
    const o = S.onboarding;
    const answer = h("textarea", { id: "onb-answer", rows: 3, maxlength: 4000, "aria-describedby": "onb-hint" });
    const submit = async (text) => {
      const next = await act(() => api("POST", "/api/onboarding/answer", { text }));
      if (!next) return;
      S.onboarding = next;
      if (next.done) {
        document.body.classList.remove("onboarding");
        await render();
        say("companion", "Thanks. That's saved under About me, where you can change or delete any of it.");
        await greet();
      } else { await render(); }
    };
    answer.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(answer.value.trim()); } });
    root.append(h("section", { class: "onb", "aria-labelledby": "onb-q" },
      h("div", { class: "onb-who" }, h("span", { class: "orb is-ready" }, orbSvg(56)), h("div", {}, h("div", { class: "name", text: "Tempo" }), h("div", { class: "muted small", text: "Your career companion" }))),
      o.step === 0 ? h("p", { text: "I keep your place, tell you the one thing I'd do next, and push back when a claim isn't backed up. I can't see LinkedIn or your inbox, and I never send anything. You do that." }) : null,
      h("div", { class: "onb-progress" }, h("span", { text: "Question " + (o.step + 1) + " of " + o.total }),
        h("div", { class: "onb-bar", "aria-hidden": "true" }, Array.from({ length: o.total }, (_, i) => h("span", { class: i <= o.step ? "done" : "" })))),
      h("h1", { id: "onb-q" }, h("label", { for: "onb-answer", text: o.question })),
      answer, h("p", { id: "onb-hint", class: "muted small", text: o.hint || "" }),
      h("div", { class: "row" }, btn("Continue", () => submit(answer.value.trim()), "primary big"), btn("Skip", () => submit(""), "quiet")),
      help("Where do my answers go?", "They're saved on this Mac under About me. You can edit or delete any of them later, and skipping is fine.",
        "They help with planning only. They are never passed to drafting.")));
    setTimeout(() => answer.focus(), 0);
  }

  // ---- Today ----------------------------------------------------------------------------
  function timePicker(disabled) {
    return h("div", { class: "seg", role: "group", "aria-label": "Minutes I have" }, [15, 20, 30].map((m) =>
      h("button", { type: "button", "aria-pressed": String(S.minutes === m), disabled, "aria-label": m + " minutes", onclick: () => { S.minutes = m; store.set("minutes", m); render(); } }, String(m))));
  }
  function liveRing() {
    const left = secondsLeft(), mins = Math.max(0, Math.ceil(left / 60));
    const el = ring(168, left / (S.session.minutes * 60), mins, left > 0 ? "min left" : "time's up", left <= 0 ? "done" : "");
    el.id = "live-ring";
    return el;
  }
  function hero(option, today) {
    const a = option.action, running = S.session && S.session.focus_action_id === a.id;
    const note = h("input", { value: a.where_left_off, maxlength: 500, "aria-label": "Where you left it",
      onchange: (e) => act(() => api("POST", "/api/actions/" + a.id + "/note", { where_left_off: e.target.value }), "Saved your place.") });
    const reasons = h("ul", { class: "reasons hidden", id: "why" }, option.reasons.map((r) => h("li", { text: r })));
    const clean = (t) => (a.is_sample ? t.replace(/^\[SAMPLE\]\s*/, "") : t);  // the "Sample data" chip carries the label here
    const toggle = (label, target) => h("button", { type: "button", class: "btn quiet", "aria-expanded": "false", "aria-controls": target.id,
      onclick: (e) => { const open = target.classList.toggle("hidden") === false; e.currentTarget.setAttribute("aria-expanded", String(open)); } }, label, icon("down", 14));
    const dealt = h("div", { class: "row hidden", id: "dealt" },
      a.state === "drafted" ? btn("I've reviewed it", () => setState(a, "reviewed")) : null,
      btn("I did this", () => setState(a, "done", "Mark as done? Only once you've actually sent, applied, or updated it yourself.")),
      btn("Drop it", () => setState(a, "dropped", "Drop this? You can bring it back from People & roles.")));
    const meta = [option.item ? clean(option.item.title) + (option.item.org ? " at " + option.item.org : "") : null,
      a.deadline ? dueText(a.deadline, today) : null, "About " + a.effort_min + " minutes"].filter(Boolean).join(". ") + ".";
    return h("section", { class: "hero", "aria-labelledby": "hero-title" },
      h("div", { class: "hero-time" },
        running ? liveRing() : ring(168, 1, S.minutes, "minutes"),
        timePicker(running)),
      h("div", { class: "hero-body" },
        h("div", { class: "row" }, h("span", { class: "eyebrow accent", text: a.state === "suggested" ? "Start here" : "Pick up where you left off" }),
          a.is_sample ? chip("Sample data", "warn") : null, a.commitment ? chip("You committed to this") : null),
        h("h1", { id: "hero-title", text: clean(a.title) }),
        h("p", { class: "hero-meta", text: meta }),
        h("div", { class: "well" }, icon("bookmark", 18), h("div", { class: "grow" }, h("div", { class: "muted small", text: "You left it at" }), note)),
        h("div", { class: "row" },
          running ? [h("button", { type: "button", class: "btn primary big", onclick: () => openFor(a) }, playIcon(), "Continue"), btn("End session", endSession, "big")]
            : [h("button", { type: "button", class: "btn primary big", onclick: () => startSession(a) }, playIcon(), "Start " + S.minutes + "-minute session"),
               btn("Not today", () => { S.skipped.add(a.id); render(); }, "big")]),
        h("div", { class: "row" }, toggle("Why this one?", reasons), toggle("Already dealt with it?", dealt)),
        reasons, dealt));
  }
  function firstSteps() {
    const step = (primary, ic, title, sub, onclick) => h("button", { type: "button", class: "first-step" + (primary ? " primary" : ""), onclick }, icon(ic, 22), h("span", {}, h("b", { text: title }), h("span", { text: sub })));
    return h("section", { class: "state" },
      h("h1", { text: "Nothing's waiting on you." }),
      h("p", { class: "hero-meta", text: "Give me one real thing to work with and I'll take it from there." }),
      step(true, "docplus", "Add a project", "About 10 minutes. Gives drafts evidence to use.", () => { S.evidenceForm = true; go("evidence"); }),
      step(false, "clip", "Paste your profile text", "About 5 minutes. Shows me where you're starting.", () => { S.pasteKind = "profile_text"; go("pasted"); }),
      S.hasSample ? null : h("div", {}, btn("Or look around with labelled sample data", async () => { await act(() => api("POST", "/api/sample/load")); await refreshStatus(); await render(); await greet(); }, "quiet")));
  }
  async function renderToday(root) {
    const [view, ideas, items] = await Promise.all([loadToday(), api("GET", "/api/ideas"), api("GET", "/api/items")]);
    const all = [view.recommended].concat(view.alternatives).filter(Boolean);
    const options = all.filter((o) => !S.skipped.has(o.action.id));
    const date = new Date(view.today + "T12:00:00").toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
    const page = h("div", { class: "page" }, h("div", { class: "muted", text: date }), sampleNotice());
    root.append(page);
    if (options.length) page.append(hero(options[0], view.today));
    else if (all.length) page.append(h("section", { class: "state" }, h("h1", { text: "That's everything set aside for today." }),
      h("p", { class: "hero-meta", text: "Nothing was changed. Your to-dos are still there." }), h("div", {}, btn("Show them again", () => { S.skipped.clear(); render(); }))));
    else page.append(firstSteps());

    const rest = options.slice(1);
    const tucked = h("section", { class: "section", "aria-label": "Everything else" }, h("div", { class: "eyebrow", text: "Tucked away" }));
    const list = h("div", {});
    if (rest.length) list.append(disc("others", plural(rest.length, "other thing", "other things") + " you could do", rest.map((o) => o.action.title.replace("[SAMPLE] ", "")).join("; "),
      h("ul", { class: "rows" }, rest.map((o) => h("li", {}, h("div", { class: "grow" }, h("div", { text: o.action.title }), h("div", { class: "muted small", text: o.reasons.slice(0, 2).join(" ") })),
        btn("Do this instead", () => startSession(o.action)))))));
    if (view.reminders.length) list.append(disc("reminders", plural(view.reminders.length, "reminder", "reminders") + " due", view.reminders[0].text,
      h("ul", { class: "rows" }, view.reminders.map((r) => h("li", {}, h("span", { class: "grow" }, r.text, " ", h("span", { class: "muted small", text: r.due_on })),
        h("span", { class: "row" }, btn("Done", async () => { await act(() => api("POST", "/api/reminders/" + r.id + "/done")); render(); }),
          btn("In 3 days", async () => { await act(() => api("POST", "/api/reminders/" + r.id + "/snooze", { days: 3 })); render(); })))))));
    const idea = h("input", { placeholder: "Something you're curious about…", maxlength: 300, "aria-label": "Idea to park" });
    list.append(disc("idea", "Park an idea", ideas.length ? plural(ideas.length, "idea", "ideas") + " parked" : "it waits here and never becomes a to-do on its own",
      h("form", { class: "row", onsubmit: async (e) => { e.preventDefault(); if (!idea.value.trim()) return; await act(() => api("POST", "/api/ideas", { text: idea.value }), "Parked."); render(); } },
        h("div", { class: "grow" }, idea), h("button", { type: "submit", class: "btn" }, "Park it")),
      ideas.length ? h("ul", { class: "rows" }, ideas.map((i) => h("li", {}, h("span", { class: "grow", text: i.text }), h("span", { class: "row" },
        btn("Make it a to-do", async () => { await act(() => api("POST", "/api/ideas/" + i.id + "/promote")); render(); }),
        btn("Let it go", async () => { await act(() => api("POST", "/api/ideas/" + i.id + "/drop")); render(); }, "quiet"))))) : null));
    list.append(disc("add", "Add a to-do or reminder", "", actionForm(items), reminderForm()));
    tucked.append(list);
    page.append(tucked);
  }
  function actionForm(items) {
    const f = { title: "", kind: "follow_up", item_id: "", commitment: false, importance: 2, effort_min: 15, deadline: "" };
    return h("form", { class: "panel", onsubmit: async (e) => {
      e.preventDefault();
      const body = { ...f, item_id: f.item_id ? Number(f.item_id) : null, deadline: f.deadline || null, importance: Number(f.importance), effort_min: Number(f.effort_min) };
      if (await act(() => api("POST", "/api/actions", body), "Added.")) render();
    } },
      h("h3", { text: "New to-do" }),
      field("What needs doing", h("input", { required: true, maxlength: 200, oninput: (e) => { f.title = e.target.value; } })),
      h("div", { class: "grid2" },
        field("Type", select(S.enums.action_kinds.map((k) => [k, k.replace("_", " ")]), f.kind, (v) => { f.kind = v; })),
        field("About", select([["", "Nothing specific"]].concat(items.map((i) => [i.id, i.title])), "", (v) => { f.item_id = v; })),
        field("Importance", select([[3, "High"], [2, "Medium"], [1, "Low"]], 2, (v) => { f.importance = v; })),
        field("Minutes needed", h("input", { type: "number", min: 5, max: 240, value: 15, oninput: (e) => { f.effort_min = e.target.value; } })),
        field("Deadline (optional)", h("input", { type: "date", oninput: (e) => { f.deadline = e.target.value; } }))),
      h("label", { class: "check" }, h("input", { type: "checkbox", onchange: (e) => { f.commitment = e.target.checked; } }), "I've already committed to this"),
      h("div", {}, h("button", { type: "submit", class: "btn primary" }, "Add to-do")));
  }
  function reminderForm() {
    const f = { text: "", due_on: "" };
    return h("form", { class: "panel", onsubmit: async (e) => { e.preventDefault(); if (await act(() => api("POST", "/api/reminders", f), "Reminder set.")) render(); } },
      h("h3", { text: "New reminder" }),
      h("div", { class: "grid2" }, field("Remind me to", h("input", { required: true, maxlength: 300, oninput: (e) => { f.text = e.target.value; } })),
        field("On", h("input", { type: "date", required: true, oninput: (e) => { f.due_on = e.target.value; } }))),
      h("div", { class: "row" }, h("button", { type: "submit", class: "btn" }, "Set reminder"), h("span", { class: "muted small", text: "Shows up when you open the app. No notifications." })));
  }

  // ---- People & roles -------------------------------------------------------------------
  function todoRow(a, deletable) {
    const closed = a.state === "done" || a.state === "dropped";
    return h("li", {}, h("span", { class: "grow" }, a.title, " ", chip(STATE[a.state], a.state === "done" ? "ok" : "")),
      h("span", { class: "row" },
        closed ? btn(a.state === "done" ? "Undo done" : "Bring back", () => setState(a, a.state === "done" ? "reviewed" : "suggested")) : btn("Work on it", () => startSession(a)),
        deletable ? btn("Delete", async () => { if (window.confirm("Delete this to-do?")) { await act(() => api("DELETE", "/api/actions/" + a.id)); render(); } }, "quiet") : null));
  }
  async function renderPeople(root) {
    const [items, actions] = await Promise.all([api("GET", "/api/items"), api("GET", "/api/actions")]);
    const page = h("div", { class: "page" }, pageHead("People & roles", "Who you're talking to, what you're going for, and what happened.",
      help("What do outcomes mean?", "One click records what you observed: a reply, an interview, silence.", "It's a record, not proof that any particular wording caused it.")), sampleNotice());
    root.append(page);
    const f = { kind: "opportunity", title: "", org: "" };
    const addForm = h("form", { class: "panel", onsubmit: async (e) => { e.preventDefault(); if (await act(() => api("POST", "/api/items", f), "Added.")) render(); } },
      h("div", { class: "grid2" },
        field("Type", select([["opportunity", "Role or programme"], ["relationship", "Person"]], f.kind, (v) => { f.kind = v; })),
        field("Name or title", h("input", { required: true, maxlength: 200, oninput: (e) => { f.title = e.target.value; } })),
        field("Organisation", h("input", { maxlength: 200, oninput: (e) => { f.org = e.target.value; } }))),
      h("div", {}, h("button", { type: "submit", class: "btn primary" }, "Add")));
    if (!items.length) page.append(h("section", { class: "section" }, h("h3", { text: "No one here yet" }), h("p", { class: "muted", text: "Add the first person or role you're actually pursuing." }), addForm));
    const listing = h("div", {});
    for (const it of items) {
      const edit = { ...it };
      listing.append(h("section", { class: "entry" },
        h("div", { class: "row spread" }, h("h3", { text: it.title + (it.org ? " · " + it.org : "") }),
          h("span", { class: "row" }, chip(it.kind === "relationship" ? "Person" : "Role"), chip(it.status, it.status === "active" ? "ok" : ""), it.is_sample ? chip("Sample data", "warn") : null)),
        h("div", { class: "row" }, h("span", { class: "muted small", text: "What happened?" }),
          S.enums.outcome_types.filter((t) => t !== "other").map((t) => btn(OUTCOME[t], async () => {
            if (await act(() => api("POST", "/api/outcomes", { item_id: it.id, type: t }), "Recorded: " + OUTCOME[t] + ".")) render();
          }))),
        it.outcomes.length ? h("div", { class: "row small" }, it.outcomes.map((o) => h("span", { class: "row" },
          chip(OUTCOME[o.type] + " · " + o.occurred_on, ["interview", "offer", "reply"].includes(o.type) ? "ok" : ""),
          btn("Undo", async () => { await act(() => api("DELETE", "/api/outcomes/" + o.id)); render(); }, "quiet")))) : null,
        it.actions.length ? h("ul", { class: "rows" }, it.actions.map((a) => todoRow(a, false))) : null,
        help("Notes and details", h("div", { class: "stack" },
          field("Private notes (planning only, never sent to drafting)", h("textarea", { rows: 2, maxlength: 8000, value: it.private_notes, oninput: (e) => { edit.private_notes = e.target.value; } })),
          field("Context you're happy to use in a draft", h("textarea", { rows: 2, maxlength: 2000, value: it.shareable_context, oninput: (e) => { edit.shareable_context = e.target.value; } })),
          field("Status", select([["active", "Active"], ["waiting", "Waiting on them"], ["closed", "Closed"]], it.status, (v) => { edit.status = v; })),
          h("div", { class: "row" },
            btn("Save", async () => { const body = { kind: edit.kind, title: edit.title, org: edit.org, private_notes: edit.private_notes, shareable_context: edit.shareable_context, status: edit.status };
              if (await act(() => api("PUT", "/api/items/" + it.id, body), "Saved.")) render(); }, "primary"),
            btn("Delete", async () => { if (window.confirm("Delete this and its outcome history?")) { await act(() => api("DELETE", "/api/items/" + it.id)); render(); } }, "danger"))))));
    }
    page.append(listing);
    const loose = actions.filter((a) => !a.item_id);
    if (loose.length) page.append(h("section", { class: "section" }, h("div", { class: "eyebrow", text: "Other to-dos" }), h("ul", { class: "rows" }, loose.map((a) => todoRow(a, true)))));
    if (items.length) page.append(h("div", {}, disc("additem", "Add a person or role", "", addForm)));
  }

  // ---- Evidence -------------------------------------------------------------------------
  function parseMetrics(text) {
    return text.split("\n").map((l) => l.split("|").map((p) => p.trim())).filter((p) => p[0]).map((p) => ({ value: p[0], unit: p[1] || "", label: p[2] || "" }));
  }
  async function renderEvidence(root) {
    const list = await api("GET", "/api/evidence");
    const page = h("div", { class: "page" }, pageHead("Evidence", "What you can truthfully say about your work. Every claim in a draft points here.",
      help("How is this used?", "A draft can only state facts that link to an entry here. Numbers are checked against the value and unit you record.",
        "“Verified” means you've noted where the proof is. “Do not claim” entries are never sent to drafting. Confidential entries aren't either.")), sampleNotice());
    root.append(page);
    const showForm = S.evidenceForm || S.editEvidence || !list.length;
    const e0 = S.editEvidence || { title: "", claim: "", metrics: [], source_ref: "", status: "unverified_user_claim", permitted_uses: [], do_not_claim: "", confidential: false };
    const f = { ...e0, permitted_uses: new Set(e0.permitted_uses), metricsText: e0.metrics.map((m) => [m.value, m.unit, m.label].join(" | ")).join("\n") };
    const form = h("form", { class: "panel", onsubmit: async (e) => {
      e.preventDefault();
      const body = { title: f.title, claim: f.claim, metrics: parseMetrics(f.metricsText), source_ref: f.source_ref, status: f.status,
        permitted_uses: [...f.permitted_uses], do_not_claim: f.do_not_claim, confidential: !!f.confidential };
      const ok = await act(() => (S.editEvidence ? api("PUT", "/api/evidence/" + S.editEvidence.id, body) : api("POST", "/api/evidence", body)), "Saved.");
      if (ok) { S.editEvidence = null; S.evidenceForm = false; render(); }
    } },
      h("h3", { text: S.editEvidence ? "Edit evidence" : list.length ? "Add evidence" : "Add your first project" }),
      field("Short title", h("input", { required: true, maxlength: 200, value: f.title, oninput: (e) => { f.title = e.target.value; } })),
      field("What you can truthfully say", h("textarea", { required: true, rows: 2, maxlength: 2000, value: f.claim, oninput: (e) => { f.claim = e.target.value; } })),
      field("Numbers, one per line: value | unit | what it measures", h("textarea", { rows: 2, placeholder: "4 | segments | customer groups in the dashboard", value: f.metricsText, oninput: (e) => { f.metricsText = e.target.value; } })),
      h("div", { class: "grid2" },
        field("Status", select(S.enums.evidence_statuses.map((s) => [s, EV_STATUS[s]]), f.status, (v) => { f.status = v; })),
        field("Where the proof is (needed for “verified”)", h("input", { maxlength: 500, value: f.source_ref, oninput: (e) => { f.source_ref = e.target.value; } }))),
      h("fieldset", { class: "row" }, h("legend", { class: "small muted", text: "Approved for" }),
        S.enums.uses.map((u) => h("label", { class: "check" }, h("input", { type: "checkbox", checked: f.permitted_uses.has(u), onchange: (e) => { e.target.checked ? f.permitted_uses.add(u) : f.permitted_uses.delete(u); } }), u))),
      field("Never say (phrases separated by ; )", h("input", { maxlength: 1000, value: f.do_not_claim, oninput: (e) => { f.do_not_claim = e.target.value; } })),
      h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!f.confidential, onchange: (e) => { f.confidential = e.target.checked; } }), "Confidential (employer or school material)"),
      h("div", { class: "row" }, h("button", { type: "submit", class: "btn primary" }, S.editEvidence ? "Save changes" : "Add evidence"),
        list.length ? btn("Cancel", () => { S.editEvidence = null; S.evidenceForm = false; render(); }) : null));
    if (showForm) page.append(form); else page.append(h("div", {}, btn("Add evidence", () => { S.evidenceForm = true; render(); }, "primary")));
    const listing = h("div", {});
    for (const e of list) {
      listing.append(h("section", { class: "entry" },
        h("div", { class: "row spread" }, h("h3", { text: e.title }),
          h("span", { class: "row" }, chip(EV_STATUS[e.status], e.status === "user_verified_with_artifact" ? "ok" : e.status === "do_not_claim" ? "bad" : "warn"),
            e.confidential ? chip("Confidential", "bad") : null, e.is_sample ? chip("Sample data", "warn") : null)),
        h("p", { text: e.claim }),
        e.metrics.length ? h("p", { class: "small", text: "Numbers: " + e.metrics.map((m) => m.value + " " + m.unit + (m.label ? " (" + m.label + ")" : "")).join("; ") }) : null,
        h("p", { class: "small muted", text: "Approved for: " + (e.permitted_uses.join(", ") || "nothing yet") + (e.source_ref ? ". Source: " + e.source_ref : "") + (e.do_not_claim ? ". Never say: " + e.do_not_claim : "") }),
        h("div", { class: "row" }, btn("Edit", () => { S.editEvidence = e; render(); $("main").scrollTop = 0; }),
          btn("Delete", async () => { if (window.confirm("Delete this evidence entry?")) { await act(() => api("DELETE", "/api/evidence/" + e.id)); render(); } }, "quiet"))));
    }
    page.append(listing);
  }

  // ---- Drafts ---------------------------------------------------------------------------
  function reportView(draft) {
    const r = draft.report || {};
    const box = h("div", { class: "stack" });
    const overall = { passed: ["ok", "The automatic checks passed. Still read it before you use it."], review: ["warn", "Needs your review before you use it."],
      blocked: ["bad", "Contains claims that aren't supported or aren't allowed."] }[r.overall] || ["", ""];
    box.append(h("div", { class: "notice " + overall[0] }, icon(r.overall === "passed" ? "info" : "warn", 18), overall[1]));
    for (const c of r.claims || []) {
      const worst = c.issues.some((i) => i.severity === "block") ? ["bad", "Problem"] : c.issues.length ? ["warn", "Review"] : ["ok", "Supported"];
      box.append(h("div", { class: "claim" }, h("div", { class: "row" }, chip(worst[1], worst[0]), h("span", { class: "muted small", text: "Evidence #" + c.evidence_id })),
        h("div", { text: "“" + c.text + "”" }), c.issues.map((i) => h("div", { class: "issue " + i.severity, text: i.message }))));
    }
    (r.body_issues || []).forEach((i) => box.append(h("div", { class: "issue " + i.severity, text: i.message })));
    if (draft.gaps && draft.gaps.length) box.append(h("div", {}, h("div", { class: "eyebrow", text: "Left out: no evidence for it" }), h("ul", { class: "reasons" }, draft.gaps.map((g) => h("li", { text: g })))));
    if (r.not_checked) box.append(help("What isn't checked?", r.not_checked));
    return box;
  }
  async function renderDrafts(root) {
    const D = S.draft;
    const [evidence, actions, drafts] = await Promise.all([api("GET", "/api/evidence"), api("GET", "/api/actions"), api("GET", "/api/drafts")]);
    const action = actions.find((a) => a.id === D.action_id) || null;
    if (!D.current && action) D.current = drafts.find((d) => d.action_id === action.id) || null;
    const page = h("div", { class: "page" }, pageHead("Drafts", "Write it yourself or with Tempo. Either way, every save is checked against your evidence.",
      help("What can drafting see?", "Only this page: the evidence you tick, your voice notes for the audience, and what you type here.",
        "It never sees your private planning notes, your goals, or the chat.",
        S.ai.available && S.ai.mode === "live" ? "In live mode, those three things are sent to the AI provider." : "In mock mode nothing leaves this Mac.")));
    root.append(page);
    if (!S.ai.available) page.append(h("div", { class: "notice warn" }, icon("info", 18), "AI drafting is off right now. You can still write, save, and check drafts yourself."));

    const reportBox = h("div", {});
    const stamp = h("span", { class: "muted small", role: "status" });
    let timer = null;
    const editor = h("textarea", { rows: 9, maxlength: 20000, value: D.current ? D.current.body : "", placeholder: "Write here, or draft with Tempo.", "aria-label": "Draft text",
      oninput: () => { stamp.textContent = "Saving…"; clearTimeout(timer); timer = setTimeout(save, 900); } });
    async function save() {
      const saved = await act(() => api("POST", "/api/drafts/save", { draft_id: D.current ? D.current.id : null, action_id: D.action_id, purpose: D.purpose, audience: D.audience, body: editor.value }));
      if (!saved) return;
      D.current = saved;
      stamp.textContent = "Saved automatically.";
      reportBox.replaceChildren(reportView(saved));
    }
    reportBox.append(D.current ? reportView(D.current) : h("p", { class: "muted", text: "Checks appear here once there's a draft." }));

    page.append(h("section", { class: "section" }, h("div", { class: "eyebrow", text: "1 · Set it up" }), h("div", { class: "panel" },
      h("div", { class: "grid2" },
        field("For which to-do", select([["", "Not linked"]].concat(actions.filter((a) => a.state !== "dropped").map((a) => [a.id, a.title])), D.action_id || "", (v) => { D.action_id = v ? Number(v) : null; D.current = null; render(); })),
        field("Kind of text", select(PURPOSES, D.purpose, (v) => { D.purpose = v; })),
        field("Audience", h("input", { maxlength: 60, value: D.audience, placeholder: "recruiter, peer, alum…", oninput: (e) => { D.audience = e.target.value; } }))),
      h("fieldset", { class: "stack" }, h("legend", { class: "small muted", text: "Evidence to use" }),
        evidence.length ? evidence.map((e) => h("label", { class: "check" },
          h("input", { type: "checkbox", checked: D.evidence_ids.has(e.id), onchange: (ev) => { ev.target.checked ? D.evidence_ids.add(e.id) : D.evidence_ids.delete(e.id); } }),
          h("span", {}, e.title, " ", e.confidential ? chip("Confidential: held back", "bad") : null, e.status === "do_not_claim" ? chip("Do not claim: held back", "bad") : null)))
          : h("p", { class: "muted small" }, "No evidence yet, so a draft can't make factual claims. ", h("a", { href: "#evidence", text: "Add some" }), ".")),
      field("What you want it to say or do", h("textarea", { rows: 2, maxlength: 1500, value: D.instruction, oninput: (e) => { D.instruction = e.target.value; } })),
      field("Extra context you approve for this draft", h("textarea", { rows: 2, maxlength: 1500, value: D.shareable_note, oninput: (e) => { D.shareable_note = e.target.value; } })),
      action && action.item_id ? h("label", { class: "check" }, h("input", { type: "checkbox", checked: D.include_item_context, onchange: (e) => { D.include_item_context = e.target.checked; } }), "Also use the shareable context saved for this person or role") : null,
      h("div", {}, h("button", { type: "button", class: "btn primary", disabled: !S.ai.available, onclick: async (ev) => {
        ev.currentTarget.disabled = true;
        const body = { action_id: D.action_id, purpose: D.purpose, audience: D.audience, evidence_ids: [...D.evidence_ids], instruction: D.instruction, shareable_note: D.shareable_note, include_item_context: D.include_item_context };
        const out = await thinking(() => act(() => api("POST", "/api/drafts/generate", body)));
        if (out) {
          D.current = out.draft;
          if (out.excluded_evidence.length) toast("Held back: " + out.excluded_evidence.map((x) => x.title + " (" + x.reason + ")").join("; "));
          say("companion", out.draft.report.overall === "passed" ? "Draft's ready and the checks passed. Still read it before you use it." : "Draft's ready, and I flagged things to look at. The notes are under the text.");
        }
        await refreshStatus(); render();
      } }, S.ai.mode === "mock" ? "Draft with Tempo (mock)" : "Draft with Tempo")))));

    page.append(h("section", { class: "section" }, h("div", { class: "row spread" }, h("div", { class: "eyebrow", text: "2 · Write" }), stamp), editor,
      h("div", { class: "row" },
        btn("Copy text", async () => {
          try { await navigator.clipboard.writeText(editor.value); } catch (e) { editor.select(); document.execCommand("copy"); }
          if (D.current) api("POST", "/api/drafts/" + D.current.id + "/copied").catch(() => {});
          toast("Copied. Nothing was marked as sent: do that yourself once it really is.");
        }),
        action && action.state === "drafted" ? btn("I've reviewed it", () => setState(action, "reviewed")) : null,
        action && action.state !== "done" ? btn("I sent or applied it myself", () => setState(action, "done", "Mark as done? Only once you've actually sent, applied, or updated it yourself.")) : null,
        action ? chip(STATE[action.state], action.state === "done" ? "ok" : "") : null)));
    page.append(h("section", { class: "section" }, h("div", { class: "eyebrow", text: "3 · Check" }),
      reportBox));

    if (drafts.length) page.append(h("div", {}, disc("saved", plural(drafts.length, "saved draft", "saved drafts"), "",
      h("ul", { class: "rows" }, drafts.slice(0, 20).map((d) => h("li", {}, h("span", { class: "grow" }, chip(d.purpose.replace("_", " ")), " ", d.body.slice(0, 80) + (d.body.length > 80 ? "…" : "")),
        h("span", { class: "row" }, btn("Open", () => { D.current = d; D.action_id = d.action_id; D.purpose = d.purpose; D.audience = d.audience; render(); }),
          btn("Delete", async () => { if (window.confirm("Delete this draft?")) { await act(() => api("DELETE", "/api/drafts/" + d.id)); if (D.current && D.current.id === d.id) D.current = null; render(); } }, "quiet"))))))));
  }

  // ---- Pasted material ------------------------------------------------------------------
  async function renderPasted(root) {
    const list = await api("GET", "/api/imports");
    const page = h("div", { class: "page" }, pageHead("Pasted material", "Job descriptions, messages, or your profile text, kept as reference.",
      help("Is pasting safe?", "Pasted text is treated as reference only. Nothing in it can change what Tempo remembers or does, and a chat message with pasted text attached can't save anything.",
        "This app never fetches web pages and never opens LinkedIn. You paste; it reads.")));
    root.append(page);
    const f = { kind: S.pasteKind, label: "", content: "" };
    page.append(h("form", { class: "panel", onsubmit: async (e) => { e.preventDefault(); if (await act(() => api("POST", "/api/imports", f), "Saved.")) render(); } },
      h("div", { class: "grid2" },
        field("What is it", select(S.enums.import_kinds.map((k) => [k, k.replace("_", " ")]), f.kind, (v) => { f.kind = v; S.pasteKind = v; })),
        field("Label", h("input", { required: true, maxlength: 200, placeholder: f.kind === "profile_text" ? "My LinkedIn profile, November" : "", oninput: (e) => { f.label = e.target.value; } }))),
      field("Paste the text", h("textarea", { required: true, rows: 5, maxlength: 60000, oninput: (e) => { f.content = e.target.value; } })),
      h("div", {}, h("button", { type: "submit", class: "btn primary" }, "Save"))));
    if (S.compare) {
      page.append(h("section", { class: "section" }, h("div", { class: "row spread" }, h("h3", { text: "Compared: " + S.compare.label }), btn("Close", () => { S.compare = null; render(); }, "quiet")),
        h("p", { text: S.compare.result.summary }),
        h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["They ask for", "Your evidence", "Gap"].map((t) => h("th", { scope: "col", text: t })))),
          h("tbody", {}, S.compare.result.requirements.map((r) => h("tr", {}, h("td", { text: r.requirement }),
            h("td", {}, r.evidence.length ? r.evidence.map((e) => h("div", {}, e.title + " ", chip(e.status === "user_verified_with_artifact" ? "verified" : "unverified", e.status === "user_verified_with_artifact" ? "ok" : "warn"))) : h("span", { class: "muted", text: "None" })),
            h("td", { text: r.gap })))))),
        h("p", { class: "muted small", text: "A match means an entry relates to the requirement, not that it proves you meet it." })));
    }
    const listing = h("div", {});
    for (const m of list) {
      listing.append(h("section", { class: "entry" },
        h("div", { class: "row spread" }, h("h3", { text: m.label }), h("span", { class: "row" }, chip(m.kind.replace("_", " ")), chip(m.length + " characters"))),
        h("p", { class: "muted small", text: m.content + (m.length > 300 ? "…" : "") }),
        h("div", { class: "row" },
          h("button", { type: "button", class: "btn", disabled: !S.ai.available, onclick: async (ev) => {
            ev.currentTarget.disabled = true;
            const result = await thinking(() => act(() => api("POST", "/api/compare", { import_id: m.id })));
            if (result) S.compare = { label: m.label, result };
            await refreshStatus(); render();
          } }, "Compare with my evidence"),
          btn("Attach to my next message", () => { S.attachImport = { id: m.id, label: m.label }; renderAttach(); if (document.body.classList.contains("dock-closed")) setDock(true); else $("chat-input").focus(); }),
          btn("Delete", async () => { if (window.confirm("Delete this pasted material?")) { await act(() => api("DELETE", "/api/imports/" + m.id)); render(); } }, "quiet"))));
    }
    page.append(listing);
  }

  // ---- About me -------------------------------------------------------------------------
  async function renderMe(root) {
    const list = await api("GET", "/api/memory");
    const page = h("div", { class: "page" }, pageHead("About me", "Everything Tempo remembers about you. Change or delete any of it.",
      help("How does Tempo learn things?", "From what you type here, your onboarding answers, and suggestions it makes in chat.", "A suggestion is never saved until you click Save it.")));
    root.append(page);
    const groups = [["Private planning context", "Used to plan with you. Never sent to drafting.", S.enums.memory_private],
                    ["Your voice for outward writing", "Sent to drafting, matched by audience.", S.enums.memory_public]];
    for (const [title, sub, kinds] of groups) {
      const mine = list.filter((m) => kinds.includes(m.kind));
      const sec = h("section", { class: "section" }, h("div", {}, h("div", { class: "eyebrow", text: title }), h("p", { class: "muted small", text: sub })));
      if (!mine.length) sec.append(h("p", { class: "muted", text: "Nothing here yet." }));
      for (const m of mine) {
        const ta = h("textarea", { rows: 2, maxlength: 4000, value: m.text, "aria-label": MEMORY[m.kind] });
        sec.append(h("div", { class: "stack" },
          h("div", { class: "row" }, chip(MEMORY[m.kind], "accent"), m.audience ? chip("for " + m.audience) : null,
            chip(m.provenance === "user_confirmed" ? "Suggested by Tempo, confirmed by you" : m.provenance === "sample" ? "Sample data" : "Typed by you", m.provenance === "sample" ? "warn" : "")),
          ta, h("div", { class: "row" }, btn("Save", () => act(() => api("PUT", "/api/memory/" + m.id, { kind: m.kind, text: ta.value, audience: m.audience }), "Saved.")),
            btn("Delete", async () => { await act(() => api("DELETE", "/api/memory/" + m.id), "Deleted."); render(); }, "quiet"))));
      }
      page.append(sec);
    }
    const f = { kind: "voice_sample", text: "", audience: "" };
    page.append(h("div", {}, disc("addme", "Add something", "a writing sample, a preference, a boundary",
      h("form", { class: "panel", onsubmit: async (e) => { e.preventDefault(); if (await act(() => api("POST", "/api/memory", f), "Added.")) render(); } },
        h("div", { class: "grid2" },
          field("Type", select(S.enums.memory_public.concat(S.enums.memory_private).map((k) => [k, MEMORY[k]]), f.kind, (v) => { f.kind = v; })),
          field("Audience (voice items only)", h("input", { maxlength: 60, placeholder: "recruiter, peer, alum…", oninput: (e) => { f.audience = e.target.value; } }))),
        field("Text", h("textarea", { required: true, rows: 3, maxlength: 4000, placeholder: "For a writing sample, paste something you wrote.", oninput: (e) => { f.text = e.target.value; } })),
        h("div", {}, h("button", { type: "submit", class: "btn primary" }, "Add"))))));
  }

  // ---- Settings & data ------------------------------------------------------------------
  async function renderSettings(root) {
    const [b, activity] = await Promise.all([api("GET", "/api/budget"), api("GET", "/api/activity")]);
    const s = b.status, level = s.level === "hard_stop" ? "bad" : s.level === "warn" ? "warn" : "";
    const page = h("div", { class: "page" }, pageHead("Settings & data", "AI mode, spending, and everything stored on this Mac."));
    root.append(page);
    const meter = h("div", { class: "meter " + level }, h("span", {}));
    meter.firstChild.style.width = Math.min(100, 100 * s.committed_usd / s.hard_stop_usd) + "%";
    page.append(h("section", { class: "section" }, h("div", { class: "eyebrow", text: "AI" }),
      h("div", { class: "row" }, h("h3", { text: !b.ai.available ? "AI is off" : b.ai.mode === "mock" ? "Mock AI" : "Live AI" }), chip(b.ai.mode === "mock" ? "Canned replies" : b.ai.available ? "Real replies" : "Unavailable", b.ai.available ? (b.ai.mode === "mock" ? "warn" : "ok") : "bad")),
      h("p", { text: b.ai.reason }),
      help("What leaves this Mac?", "In mock mode, nothing.", "In live mode, chat sends your planning context and recent conversation to the AI provider. Drafting and comparison send only the evidence you tick, your voice notes, and what you type in the form.",
        "To switch modes, set COMPANION_AI_MODE when starting the app. The README has the steps for a first live call.")));
    const amount = h("input", { type: "number", step: "0.01", min: 0, placeholder: "e.g. 3.42", "aria-label": "Month-to-date total from the provider Console" });
    page.append(h("section", { class: "section" }, h("div", { class: "eyebrow", text: "Spending this month" }),
      h("h3", { text: money(s.committed_usd) + " of " + money(s.hard_stop_usd) }), meter,
      h("p", { class: level ? "notice " + level : "", text: s.level === "hard_stop" ? "The limit is reached. New AI calls are paused until next month. Your saved work is unaffected."
        : money(s.remaining_before_stop_usd) + " left before new AI calls pause. Your monthly budget is " + money(s.monthly_budget_usd) + "." }),
      help("How is this counted?", "Each AI call sets aside its maximum possible cost first, then settles to the actual cost.",
        "Limits: " + money(s.session_cap_usd) + " a session, " + money(s.day_cap_usd) + " a day (today: " + money(s.today_usd) + "). The month follows UTC, like the provider's billing.",
        s.unknown_calls ? plural(s.unknown_calls, "call", "calls") + " with an unknown outcome are counted at their maximum (" + money(s.unknown_usd) + ")." : "A call that fails midway is counted at its maximum, in case it was billed.",
        "Prices were last verified on " + s.prices_verified_on + (s.prices_fresh ? "." : ". That's out of date, so live AI is switched off until they're re-checked."),
        h("form", { class: "row", onsubmit: async (e) => { e.preventDefault(); if (amount.value === "") return; await act(() => api("POST", "/api/budget/reconcile", { console_total_usd: Number(amount.value) }), "Matched to your Console figure."); await refreshStatus(); render(); } },
          h("div", { class: "grow" }, field("Match to the provider Console's month-to-date total", amount)), h("button", { type: "submit", class: "btn" }, "Reconcile")),
        h("p", { class: "small muted", text: "The Console may lag behind recent calls, so do this well after your last one." })),
      b.recent.length ? h("div", {}, disc("calls", "Recent AI calls", String(b.recent.length), h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, ["When", "Type", "Model", "Status", "Cost"].map((t) => h("th", { scope: "col", text: t })))),
        h("tbody", {}, b.recent.map((r) => h("tr", {}, [r.ts.replace("T", " ").slice(0, 16), r.call_type, r.model, r.status, "$" + Number(r.status === "settled" || r.status === "adjustment" ? r.cost_usd : r.reserved_usd).toFixed(4)].map((t) => h("td", { text: String(t) })))))))))
        : null));

    const phrase = h("input", { placeholder: "DELETE EVERYTHING", "aria-label": "Type DELETE EVERYTHING to confirm" });
    page.append(h("section", { class: "section" }, h("div", { class: "eyebrow", text: "Your data" }),
      h("p", { text: "Everything is in one file on this Mac. Chat transcripts are removed after 30 days." }),
      h("div", { class: "row" }, h("a", { class: "btn", href: "/api/export", download: "career-companion-export.json" }, "Export everything"),
        S.hasSample ? btn("Remove sample data", async () => { await act(() => api("POST", "/api/sample/remove"), "Removed."); await refreshStatus(); render(); })
          : btn("Load labelled sample data", async () => { await act(() => api("POST", "/api/sample/load"), "Loaded."); await refreshStatus(); render(); })),
      help("Delete everything", "This removes the database files. It can't reach Time Machine or other backups, exports you saved, or copies the AI provider keeps for up to 30 days. It isn't forensic erasure.",
        h("form", { class: "row", onsubmit: async (e) => {
          e.preventDefault();
          if (!(await act(() => api("POST", "/api/wipe", { confirm: phrase.value }), "Everything was deleted."))) return;
          $("chat-log").replaceChildren();
          Object.assign(S.draft, { current: null, action_id: null }); S.draft.evidence_ids.clear(); S.session = null; S.skipped.clear();
          await refreshStatus(); go("today");
        } }, h("div", { class: "grow" }, phrase), h("button", { type: "submit", class: "btn danger" }, "Delete everything")))));
    page.append(h("div", {}, disc("activity", "Activity log", "events and costs only, never your text",
      h("div", { class: "table-wrap" }, h("table", {}, h("tbody", {}, activity.slice(0, 40).map((a) => h("tr", {}, h("td", { text: a.ts.replace("T", " ").slice(0, 16) }), h("td", { text: a.event }), h("td", { text: a.detail })))))))));
  }

  // ---- shell: routing, loading and error states -----------------------------------------
  const RENDERERS = { today: renderToday, people: renderPeople, evidence: renderEvidence, drafts: renderDrafts, me: renderMe, pasted: renderPasted, settings: renderSettings };
  function skeleton() {
    const bar = (w, ht) => { const s = h("span", {}); s.style.width = w; s.style.height = ht + "px"; return s; };
    return h("div", { class: "skeleton", "aria-busy": "true" }, h("span", { class: "sr", text: "Loading" }), bar("30%", 12), bar("85%", 40), bar("60%", 40), bar("70%", 16), bar("100%", 56), bar("45%", 56));
  }
  function errorView(err) {
    return h("section", { class: "state", role: "alert" }, h("span", { class: "notice bad" }, icon("warn", 20), "Something went wrong"),
      h("h1", { text: "Couldn't load this." }), h("p", { class: "hero-meta", text: "Your saved work is fine. This usually means the app stopped running." }),
      h("div", { class: "row" }, btn("Try again", () => render(), "dark")),
      help("What to check", "Is the terminal window that started the app still open and running?", "If you restarted the app, use the new link it printed. The old page can't reconnect.", "Details: " + err.message));
  }
  let renderSeq = 0;
  async function render() {
    const seq = ++renderSeq, main = $("main");
    if (!S.onboarding.done) {
      document.body.classList.add("onboarding");
      const fresh = h("div", {});
      renderOnboarding(fresh);
      main.replaceChildren(...fresh.childNodes);
      return;
    }
    renderSide();
    const wait = setTimeout(() => { if (seq === renderSeq) main.replaceChildren(skeleton()); }, 220);
    const fresh = h("div", {});
    try { await RENDERERS[S.tab](fresh); }
    catch (err) { fresh.replaceChildren(errorView(err)); }
    clearTimeout(wait);
    if (seq === renderSeq) main.replaceChildren(...fresh.childNodes);
  }
  function route() {
    const tab = window.location.hash.replace("#", "");
    S.tab = RENDERERS[tab] ? tab : "today";
    document.title = "Career Companion";
    // Moving focus to the new page lets keyboard and screen-reader users land in it directly.
    render().then(() => { if (S.onboarding.done) { $("main").scrollTop = 0; $("main").focus({ preventScroll: true }); } });
  }

  (async function init() {
    startDock();
    try {
      await refreshStatus();
      window.addEventListener("hashchange", route);
      const tab = window.location.hash.replace("#", "");
      S.tab = RENDERERS[tab] ? tab : "today";
      await render();
      if (S.onboarding.done) {
        await greet();
        for (const p of await api("GET", "/api/proposals")) proposalCard(p);
      }
      setInterval(tick, 15000);
    } catch (err) {
      $("main").replaceChildren(errorView(err));
    }
  })();
})();
