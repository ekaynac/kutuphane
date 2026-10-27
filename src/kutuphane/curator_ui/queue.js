"use strict";
// The curator queue (docs/25 §6.2, §6.3, §6.5, §6.6): risk-ordered same_as groups at one watermark, the document
// first, Approve / Reject / Skip per pending note, one reason and one passkey act for every selected note. No
// suggestion and no sample mark is ever shown before the act: the server never sends them; the receipt has them.
// Note text and every server value are plain text only (textContent). Only `load` is global (core.js calls it).

(() => {
const CHOICES = [["approved", "Approve", "primary"], ["rejected", "Reject", "danger"], [null, "Skip", ""]];
const REASONS = { approved: ["checked: correct", "useful evidence"],
                  rejected: ["duplicate of …", "wrong", "not useful", "out of scope"] };
const MAX_SHOWN_MS = 3600000;
const state = { w: null, cursor: null, groups: [], selected: new Map(), shownAt: new Map(), items: new Map() };

// --- the visible time of the cards (§6.7: only while the tab is visible) -------------------------------------
let visibleMs = 0, visibleSince = document.visibilityState === "visible" ? performance.now() : null;
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") visibleSince = performance.now();
  else if (visibleSince !== null) { visibleMs += performance.now() - visibleSince; visibleSince = null; }
});
function clock() { return visibleMs + (visibleSince === null ? 0 : performance.now() - visibleSince); }
function shownMs(refs) {
  const starts = refs.map((r) => state.shownAt.get(r)).filter((t) => t !== undefined);
  return starts.length ? Math.min(MAX_SHOWN_MS, Math.round(clock() - Math.min(...starts))) : null;
}
function shortRef(ref) { const [book, id] = ref.split("@"); return `${book}@${id.slice(0, 11)}`; }

// --- one note: every part that its id covers is on the card (review #16 finding 1) ---------------------------
function meta(item) {
  const scope = item.scope ? ` · scope ${item.scope.repo}${item.scope.branch ? "@" + item.scope.branch : ""} ${item.scope.paths.join(", ")}` : " · no scope";
  const box = el("div");
  box.append(el("div", "meta", `${item.kind} (${item.role}) · ${item.book}${scope} · ${shortRef(item.ref)}`));
  if (item.class_key || item.commit) {
    box.append(el("div", "meta", `${item.class_key ? "class " + item.class_key : ""}` +
                                  `${item.class_key && item.commit ? " · " : ""}${item.commit ? "commit " + item.commit : ""}`));
  }
  for (const w of item.writers) {
    box.append(el("div", "meta", `written by ${w.principal}${w.on_behalf_of ? " for " + w.on_behalf_of : ""}` +
                                  `${w.client_id ? " via " + w.client_id : ""} · ${item.written_at}`));
  }
  const origin = `origin ${item.origin}${item.entered_by ? " · entered by " + item.entered_by : ""}` +
                 `${item.confirmed_by ? " · confirmed by " + item.confirmed_by : ""}`;
  const outcomes = Object.entries(item.outcomes).map(([k, n]) => `${k} ${n}`).join(", ");
  box.append(el("div", "meta", origin + (outcomes ? ` · outcomes: ${outcomes}` : "")));
  if (item.decision) {
    const d = el("div", "decision");
    d.append(el("div", "meta", "Decision: the options offered"));
    const list = el("ol");
    for (const o of item.decision.options) { const li = el("li"); textWithMarks(li, o); list.append(li); }
    d.append(list, el("div", "meta", "The choice that an approval accepts:"));
    const choice = el("pre", "choice"); textWithMarks(choice, item.decision.choice); d.append(choice);
    box.append(d);
  }
  return box;
}

function citations(item) {
  const box = el("div", "refs");
  for (const c of item.citations) {
    if (c.hidden) { box.append(el("div", "meta", c.hidden)); continue; }
    const row = el("div", "meta", `${c.kind}: ${c.ref}`);
    if (c.kind === "passage") {
      const open = el("button", "chip", "Open passage"); open.type = "button";
      open.onclick = () => openPassage(item, c.ref, row, open).catch((e) => msg(e.message, "err"));
      row.append(" ", open);
    }
    box.append(row);
  }
  for (const l of item.links) {
    const head = `${l.direction === "out" ? "→" : "←"} ${l.type}${l.creation ? " (creation)" : ""}`;
    if (l.hidden) { box.append(el("div", "meta", `${head}: ${l.hidden}`)); continue; }
    const row = el("div", "link");
    row.append(el("div", "meta", `${head}: ${l.kind ? `${l.kind} ${shortRef(l.ref)} · ${l.standing}` : l.ref}`));
    if (typeof l.text === "string") { const pre = el("pre", "linked"); textWithMarks(pre, l.text); row.append(pre); }
    box.append(row);
  }
  return box;
}

async function openPassage(item, handle, row, button) {
  const [book, id] = item.ref.split("@");
  const r = await fetch(`/api/note/${encodeURIComponent(book)}/${encodeURIComponent(id)}?w=${state.w}`,
                        { credentials: "same-origin" });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  const found = data.passages.find((p) => p.ref === handle);
  const pre = el("pre", "linked"); textWithMarks(pre, found && found.text !== null ? found.text : "(no text)");
  button.remove(); row.append(pre);
}

function member(item) {
  const box = el("div", "member");
  box.dataset.ref = item.ref;
  state.items.set(item.ref, item);
  if (item.integrity) box.classList.add("integrity");
  const pre = el("pre"); textWithMarks(pre, item.text); box.append(pre);
  box.append(meta(item), citations(item));
  if (!item.pending) {
    box.classList.add("decided");
    box.append(el("div", item.standing === "approved" ? "ok" : "meta",
                  item.standing === "approved" ? "already accepted" : `Standing: ${item.standing}`));
    return box;
  }
  if (item.integrity) {
    box.append(el("div", "err", "The stored parts of this note do not give its id. It cannot be signed."));
    return box;
  }
  if (!state.shownAt.has(item.ref)) state.shownAt.set(item.ref, clock());
  box.append(el("div", "meta why", `why here: ${item.why}`));
  const whole = item.hidden_parts === 0;
  if (!whole) box.append(el("div", "err", `${item.hidden_parts} part(s) of this note are in a book you cannot read. ` +
                                          "You can reject it, but not approve it here."));
  const choices = el("div", "choices");
  for (const [to, label, cls] of CHOICES) {
    if (to === "approved" && !whole) continue;  // Approve only when every part of the note is shown
    const b = el("button", cls, label); b.type = "button";
    b.dataset.ref = item.ref; b.dataset.to = to || "skip";
    b.onclick = () => choose(item.ref, to);
    choices.append(b);
  }
  box.append(choices);
  return box;
}

// --- one group (§6.3) ----------------------------------------------------------------------------------------
function group(g) {
  const c = el("div", "card group");
  c.append(el("div", "meta", `tier ${g.tier} · ${g.why} · pending ${g.pending} of ${g.members.length}` +
                             ` · proposed ${g.recurrence} times` +
                             (g.proposed_again_after_rejection ? ` · proposed again after rejection: ${g.proposed_again_after_rejection}` : "")));
  for (const [a, b] of g.pairs) c.append(el("div", "err", `contradicting pair: ${shortRef(a)} ↔ ${shortRef(b)}`));
  if (g.pending > 1) {
    const all = el("button", "chip select-group", "Select group"); all.type = "button";
    all.onclick = () => {
      for (const m of g.members) if (m.pending && !m.integrity && m.hidden_parts === 0) choose(m.ref, "approved");
    };
    c.append(all);
  }
  for (const m of g.members) c.append(member(m));
  return c;
}

// --- the selection and the bottom bar (§6.6 items 4, 5) ------------------------------------------------------
function choose(ref, to) {
  if (to) state.selected.set(ref, to); else state.selected.delete(ref);
  for (const b of document.querySelectorAll(`.choices button[data-ref="${CSS.escape(ref)}"]`)) {
    b.classList.toggle("on", b.dataset.to === (to || "skip"));
  }
  bar();
}

function bar() {
  const counts = { approved: 0, rejected: 0 };
  for (const to of state.selected.values()) counts[to] += 1;
  $("batchbar").hidden = state.selected.size === 0;
  $("batch-count").textContent = `Approve ${counts.approved} · Reject ${counts.rejected}`;
  const chips = $("batch-chips"); chips.replaceChildren();
  const approved = [...state.selected].find(([, to]) => to === "approved");
  for (const to of ["approved", "rejected"]) {
    if (!counts[to]) continue;
    for (const r of REASONS[to]) {
      const text = r === "duplicate of …" ? (approved ? `duplicate of ${shortRef(approved[0])}` : null) : r;
      if (!text) continue;
      const chip = el("button", "chip", text); chip.type = "button";
      chip.onclick = () => { $("batch-reason").value = text; };
      chips.append(chip);
    }
  }
}

async function sign() {
  const reason = $("batch-reason").value.trim();
  if (!reason) throw new Error("Give a reason first.");
  const refs = [...state.selected.keys()];
  const shown = shownMs(refs);
  const o = await post("/api/act/options", { action: "standing", reason,
                                             items: refs.map((ref) => ({ ref, to: state.selected.get(ref) })) });
  const counts = o.statement.items.reduce((n, i) => ({ ...n, [i.to]: (n[i.to] || 0) + 1 }), {});
  $("sheet-text").textContent = `${Object.entries(counts).map(([to, n]) => `${to} ${n}`).join(" · ")} · reason: ` +
    `“${o.statement.reason}” · signed as ${o.statement.principal}`;
  const list = $("sheet-items"); list.replaceChildren();
  for (const i of o.statement.items) {
    const item = state.items.get(i.ref);
    list.append(el("li", null, `${i.to}: ${item ? item.kind : ""} · ${item ? item.text.slice(0, 120) : ""} · ${shortRef(i.ref)}`));
  }
  for (const r of o.statement.retires || []) {  // the approved rules that this approval retires (review #16)
    list.append(el("li", "err", `retired by this approval: ${shortRef(r.ref)}`));
  }
  $("sheet").hidden = false;
  $("sheet-cancel").onclick = () => { $("sheet").hidden = true; };
  $("sheet-sign").onclick = async () => {
    try {
      const c = await navigator.credentials.get({ publicKey: requestOptions(o.publicKey) });
      const r = await post("/api/act", { challenge_id: o.challenge_id, credential: credentialJSON(c), shown_ms: shown });
      $("sheet").hidden = true;
      receipt(r);
      state.selected.clear(); $("batch-reason").value = "";
      await load();
    } catch (e) { msg(e.message, "err"); }
  };
}

// --- after the act (§6.6 item 7): the suggestions, "agrees" or "differs", and the sample ------------------------
function receipt(r) {
  const box = $("receipt"); box.replaceChildren(); box.hidden = false;
  box.append(el("h2", null, `Signed: act ${r.act}`));
  for (const i of r.items) {
    const row = el("div", "member");
    row.append(el("div", "meta", `${shortRef(i.ref)}: ${i.standing}`));
    for (const s of i.suggestions) {
      const verdict = s.agrees === null ? "no answer" : (s.agrees ? "agrees" : "differs");
      row.append(el("div", s.agrees === false ? "err" : "meta",
                    `the model ${s.decider} said: ${s.value}, ${s.confidence} — ${verdict}`));
    }
    if (i.sample) row.append(el("div", "meta sample", `this was a check of delegation ${i.sample}`));
    for (const ref of i.retired || []) row.append(el("div", "meta", `retired: ${shortRef(ref)}`));
    box.append(row);
  }
  msg(`Signed: ${r.items.length} decisions`, "ok");
}

// --- the page ----------------------------------------------------------------------------------------------
async function fetchQueue(cursor) {
  const r = await fetch(cursor ? `/api/queue?cursor=${encodeURIComponent(cursor)}` : "/api/queue",
                        { credentials: "same-origin" });
  if (r.status === 401) return null;
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

function header(data) {
  const need = data.read_needed.length ? ` · grant read to curate: ${data.read_needed.join(", ")}` : "";
  $("progress").textContent = `${data.pending} pending · books: ${data.books.join(", ") || "none"}${need}`;
}

function more() {
  if (!state.cursor) return null;
  const b = el("button", null, "More"); b.type = "button"; b.id = "more";
  b.onclick = async () => {
    try {
      const data = await fetchQueue(state.cursor);
      if (!data) return;
      state.cursor = data.next_cursor; b.remove();
      $("cards").append(...data.groups.map(group));
      const next = more(); if (next) $("cards").append(next);
    } catch (e) { msg(e.message, "err"); }
  };
  return b;
}

async function load() {
  const data = await fetchQueue(null);
  if (!data) return start("Sign in with the passkey of this device.", "Sign in with passkey", login);
  $("start").hidden = true;
  state.w = data.watermark; state.cursor = data.next_cursor; state.items.clear();
  for (const ref of [...state.selected.keys()]) state.selected.delete(ref);
  header(data);
  $("cards").replaceChildren(...data.groups.map(group));
  if (!data.groups.length) $("cards").append(el("section", "meta", "Nothing is pending."));
  const next = more(); if (next) $("cards").append(next);
  $("batch-sign").onclick = () => sign().catch((e) => msg(e.message, "err"));
  bar();
}

window.load = load;
})();
