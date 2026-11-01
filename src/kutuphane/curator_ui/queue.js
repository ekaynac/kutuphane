"use strict";
// The curator queue (docs/25 §6.2, §6.3, §6.5, §6.6): risk-ordered same_as groups at one watermark, the note text
// first, then every part that the note id covers in plain words (evidence, options and the proposed choice, the
// replaced rule, every creation link with its target text), Approve / Reject / Skip, one reason and one passkey act
// for every chosen note. No suggestion and no sample mark is ever shown before the act: the server never sends them;
// the receipt has them. Note text and every server value are plain text only (textContent). Only `load` is global.

(() => {
const REASONS = ["Correct and useful", "Wrong", "Duplicate", "Not useful now"];
const SKIP_REASON = "Not sure — skip";
const LINK_WORDS = { derived_from: "Based on", same_as: "Same as", about: "About", fixed_by: "Fixed by",
                     violates: "Breaks the rule", decided_by: "Decided by", supersedes: "Replaces",
                     contradicts: "Contradicts" };
const LINK_WORDS_IN = { contradicts: "Contradicted by", supersedes: "Replaced by", same_as: "Same as" };
const STANDING_WORDS = { approved: "approved", pending: "waiting for review", rejected: "rejected", retired: "retired" };
const MAX_SHOWN_MS = 3600000;
const state = { w: null, cursor: null, selected: new Map(), shownAt: new Map(), items: new Map() };

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
function plural(n, one, many) { return `${n} ${n === 1 ? one : many}`; }

// --- the parts of one note: every part that its id covers is on the card (review #16 finding 1) ----------------
function section(cls, title) { const s = el("section", `part ${cls}`); s.append(el("h3", null, title)); return s; }

function noteText(text, cls) { return textWithMarks(el("div", cls || "quote"), text); }

function proposedBy(item) {
  const w = item.writers[0];
  const by = w ? `Proposed by ${person(w.principal)}${w.on_behalf_of ? " for " + person(w.on_behalf_of) : ""}` : "Written";
  const line = el("div", "kindline");
  line.append(el("strong", null, kindLine(item.kind)), el("span", null, `${by} · ${day(item.written_at)}`));
  return line;
}

function codeLines(ref) {
  const m = ref.match(/:(\d+)-(\d+)(#.*)?$/);
  return m ? (m[1] === m[2] ? `line ${m[1]}` : `lines ${m[1]}–${m[2]}`) : "";
}

function source(path, extra) {
  const d = el("div", "src");
  const dir = path.includes("/") ? path.slice(0, path.lastIndexOf("/") + 1) : "";
  d.append(el("strong", null, fileName(path)));
  if (dir || extra) d.append(el("span", "muted", ` ${dir}${extra ? (dir ? " · " : "") + extra : ""}`));
  return d;
}

// #140: a passage of an earlier version: where it is now (the excerpt stays the cited text)
function passageState(c) {
  if (c.status === "moved") return `re-indexed: ${c.match === "exact" ? "the same text" : "most of the text"} is now passage ${c.moved_to.split("#").pop()} of the current version`;
  if (c.status === "stale") return "not in the current version";
  return null;
}

function evidence(item) {
  if (!item.citations.length) return null;
  const s = section("evidence", "Evidence");
  for (const c of item.citations) {
    const row = el("div", "cite");
    if (c.hidden) { row.append(el("div", "muted", "A passage in a book you cannot read")); s.append(row); continue; }
    if (c.kind === "code") { row.append(source(c.path, `code in ${c.ref.split("@")[0]}, ${codeLines(c.ref)}`)); s.append(row); continue; }
    row.append(source(c.path, passageState(c)));
    const excerpt = noteText(c.excerpt === null ? "(the passage has no text)" : c.excerpt, "excerpt");
    const open = button("Show passage", "chip", () => openPassage(item, c.ref, excerpt, open));
    row.append(excerpt, open);
    s.append(row);
  }
  return s;
}

async function openPassage(item, handle, excerpt, open) {
  const [book, id] = item.ref.split("@");
  const r = await fetch(`/api/note/${encodeURIComponent(book)}/${encodeURIComponent(id)}?w=${state.w}`,
                        { credentials: "same-origin" });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  const found = data.passages.find((p) => p.ref === handle);
  excerpt.replaceWith(noteText(found && found.text !== null ? found.text : "(the passage has no text)", "quote passage"));
  open.remove();
}

function decision(item) {
  if (!item.decision) return null;
  const s = section("decision", "Options");
  const list = el("ol");
  const { options, choice } = item.decision;
  for (const o of options) {
    const li = el("li", o === choice ? "chosen" : null);
    if (o === choice) li.append(el("span", "badge", "Proposed choice"));
    li.append(textWithMarks(el("span"), o));
    list.append(li);
  }
  s.append(list);
  if (!options.includes(choice)) {
    const chosen = el("div", "chosen solo");
    chosen.append(el("span", "badge", "Proposed choice (not one of the options)"), textWithMarks(el("span"), choice));
    s.append(chosen);
  }
  s.append(el("p", "muted", "Approving accepts the proposed choice."));
  return s;
}

function target(l) {
  const box = el("div", "target");
  if (l.hidden) { box.append(el("div", "muted", l.hidden.replace(/^a /, "A "))); return box; }
  if (!l.kind) {  // a passage
    box.append(source(l.path, passageState(l)), noteText(l.text === null ? "(the passage has no text)" : l.text, "quote"));
    return box;
  }
  box.append(noteText(l.text), el("div", "muted", `${kindName(l.kind)} · ${STANDING_WORDS[l.standing] || l.standing}`));
  return box;
}

function replaces(item) {
  const found = item.links.filter((l) => l.direction === "out" && l.type === "supersedes");
  if (!found.length) return null;
  const s = section("replaces", "Replaces");
  for (const l of found) s.append(target(l));
  return s;
}

function otherLinks(item, groupRefs) {
  const shown = item.links.filter((l) => l.type !== "supersedes" && (l.direction === "out" || l.type === "contradicts")
                                         && !(l.type === "same_as" && groupRefs.has(l.ref)));
  if (!shown.length) return null;
  const s = section("links", "Linked");
  for (const l of shown) {
    const words = l.direction === "out" ? LINK_WORDS[l.type] || l.type : LINK_WORDS_IN[l.type] || l.type;
    s.append(el("div", "link-type", words), target(l));
  }
  return s;
}

function risks(item, g) {
  const lines = [];
  const approvedOther = (type) => item.links.some((l) => l.type === type && l.standing === "approved" &&
                                                        (type !== "supersedes" || (l.direction === "out" && l.creation)));
  if (approvedOther("supersedes")) lines.push("Approving this replaces an approved rule.");
  if (approvedOther("contradicts")) lines.push("Contradicts an approved note. Check which one is true.");
  else if (item.links.some((l) => l.type === "contradicts")) lines.push("Contradicts another note.");
  if (!lines.length && g.tier === 1) lines.push("Approving this changes what is current now.");
  if (!lines.length) return null;
  const box = el("div", "risks");
  for (const line of lines) box.append(el("div", "risk", line));
  return box;
}

function row(dl, label, value) { if (value) dl.append(el("dt", null, label), el("dd", null, value)); }

function details(item, g) {
  const d = el("details", "details");
  d.append(el("summary", null, "Details"));
  const dl = el("dl");
  row(dl, "Note id", item.ref);
  row(dl, "Kind", `${item.kind} (${item.role === "rule" ? "a rule" : "evidence"}) in ${item.book}`);
  row(dl, "Scope", item.scope ? `${item.scope.repo}${item.scope.branch ? "@" + item.scope.branch : ""} ` +
                                `${item.scope.paths.join(", ") || "(whole repository)"}` :
               item.applies_to ? "No repository scope" : "Everywhere (no scope)");
  row(dl, "Applies to", appliesTo(item.applies_to));
  row(dl, "Class key", item.class_key || "none");
  row(dl, "Commit", item.commit);
  row(dl, "Written", item.written_at);
  row(dl, "Written by", item.writers.map((w) => `${w.principal}${w.on_behalf_of ? " for " + w.on_behalf_of : ""}` +
                                                 `${w.client_id ? " via " + w.client_id : ""}`).join("; "));
  row(dl, "Origin", `${item.origin}${item.entered_by ? ", typed by " + item.entered_by : ""}` +
                    `${item.confirmed_by ? ", confirmed by " + item.confirmed_by : ""}`);
  const outcomes = Object.entries(item.outcomes).map(([k, n]) => `${k} ${n}`).join(", ");
  row(dl, "Outcomes", outcomes);
  row(dl, "Why here", item.why);
  row(dl, "Proposed", g.members.length === 1 ? plural(g.recurrence, "time", "times") : null);
  row(dl, "Sources", item.citations.filter((c) => c.ref).map((c) => c.ref).join("\n"));
  row(dl, "All links", item.links.map((l) => `${l.direction === "out" ? "→" : "←"} ${l.type}` +
                                            `${l.creation ? " (written with the note)" : ""}: ${l.ref || l.hidden}`).join("\n"));
  d.append(dl);
  return d;
}

function choices(item) {
  const box = el("div", "choices");
  const whole = item.hidden_parts === 0;
  for (const [to, label, cls] of [["approved", "Approve", "approve"], ["rejected", "Reject", "reject"], ["skip", "Skip", "skip"]]) {
    if (to === "approved" && !whole) continue;  // Approve only when every part of the note is shown
    const b = button(label, cls, () => choose(item.ref, to === "skip" ? null : to, true));
    b.dataset.ref = item.ref; b.dataset.to = to;
    box.append(b);
  }
  return box;
}

function note(item, g, groupRefs) {
  const box = el("div", "note");
  box.dataset.ref = item.ref;
  state.items.set(item.ref, item);
  if (item.integrity) box.classList.add("integrity");
  box.append(...[noteText(item.text, "text"), proposedBy(item), where(item)].filter(Boolean));
  box.append(...[evidence(item), decision(item), replaces(item), otherLinks(item, groupRefs)].filter(Boolean));
  if (!item.pending) {
    box.classList.add("decided");
    box.append(el("div", "status", item.standing === "approved" ? "Already approved" : `Already ${STANDING_WORDS[item.standing] || item.standing}`));
    box.append(details(item, g));
    return box;
  }
  const risk = risks(item, g); if (risk) box.append(risk);
  if (item.integrity) {
    box.append(el("div", "err", "The stored parts of this note do not match its id: it may have been changed. It cannot be signed."));
    box.append(details(item, g));
    return box;
  }
  if (!state.shownAt.has(item.ref)) state.shownAt.set(item.ref, clock());
  if (item.hidden_parts) box.append(el("div", "err", `${item.hidden_parts === 1 ? "A part" : item.hidden_parts + " parts"} of this note ` +
                                                     "is in a book you cannot read. You can reject it, but not approve it here."));
  box.append(choices(item), details(item, g));
  return box;
}

// --- one card: one note, or a same_as group (§6.3) -------------------------------------------------------------
function card(g) {
  const refs = new Set(g.members.map((m) => m.ref));
  const c = el("article", "card");
  if (g.members.length === 1) { c.append(note(g.members[0], g, refs)); return c; }
  c.classList.add("group");
  c.append(el("h2", null, `${g.members.length} notes say the same thing`));
  const pending = g.members.filter((m) => m.pending && !m.integrity);
  const lines = [];
  const decided = g.members.length - g.pending;
  if (decided) lines.push(`${decided} of them ${decided === 1 ? "is" : "are"} already decided.`);
  if (g.recurrence > g.members.length) lines.push(`Agents proposed it ${g.recurrence} times.`);
  if (g.proposed_again_after_rejection) lines.push(`Proposed again after a rejection (${plural(g.proposed_again_after_rejection, "time", "times")}).`);
  c.append(el("p", "muted", pending.length > 1 ? "Decide once for all of them, or one by one below." : "Decide the one that waits."));
  for (const l of lines) c.append(el("p", "muted", l));
  for (const [a, b] of g.pairs) {
    c.append(el("div", "risk", `Two of these notes contradict each other (${shortRef(a)}, ${shortRef(b)}): approve at most one.`));
  }
  if (pending.length > 1) {
    const all = el("div", "group-all");
    const rules = pending.filter((m) => m.role === "rule").length;
    if (!g.pairs.length && rules <= 1 && pending.every((m) => m.hidden_parts === 0)) {
      all.append(button("Approve all", "approve", () => { for (const m of pending) choose(m.ref, "approved", false); }));
    }
    all.append(button("Reject all", "reject", () => { for (const m of pending) choose(m.ref, "rejected", false); }));
    c.append(all);
  }
  for (const m of g.members) c.append(note(m, g, refs));
  return c;
}

// --- the choice, the bottom bar, the reason (§6.6 items 4, 5) ---------------------------------------------------
function choose(ref, to, toggle) {
  if (toggle && to && state.selected.get(ref) === to) to = null;  // a second tap clears the choice
  if (to) state.selected.set(ref, to); else state.selected.delete(ref);
  const node = document.querySelector(`.note[data-ref="${CSS.escape(ref)}"]`);
  if (node) {
    node.classList.toggle("chose-approved", to === "approved");
    node.classList.toggle("chose-rejected", to === "rejected");
    node.classList.toggle("chose-skip", !to);
  }
  for (const b of document.querySelectorAll(`.choices button[data-ref="${CSS.escape(ref)}"]`)) {
    b.classList.toggle("on", b.dataset.to === (to || "skip"));
    b.setAttribute("aria-pressed", String(b.dataset.to === (to || "skip")));
  }
  bar();
}

function counts(values) {
  const n = { approved: 0, rejected: 0 };
  for (const to of values) n[to] = (n[to] || 0) + 1;
  return n;
}

function bar() {
  const n = counts(state.selected.values());
  const open = !$("decide").hidden;
  $("batchbar").hidden = state.selected.size === 0 || open;
  if (state.selected.size === 0) $("decide").hidden = true;
  $("batch-count").textContent = [n.approved ? `${n.approved} approve` : "", n.rejected ? `${n.rejected} reject` : ""]
    .filter(Boolean).join(" · ");
  $("bar-open").textContent = `Sign ${plural(state.selected.size, "decision", "decisions")}`;
}

function reasonPanel() {
  const chips = $("batch-chips"); chips.replaceChildren();
  const input = $("batch-reason");
  for (const text of REASONS) {
    const chip = button(text, "chip reason-chip", () => {
      input.value = text;
      for (const other of chips.children) other.classList.toggle("on", other === chip);
    });
    chips.append(chip);
  }
  chips.append(button(SKIP_REASON, "chip", () => {
    for (const ref of [...state.selected.keys()]) choose(ref, null, false);
    input.value = ""; $("decide").hidden = true; bar();
    msg("Skipped. Nothing was signed.", "ok");
  }));
  input.oninput = () => { for (const chip of chips.children) chip.classList.toggle("on", chip.textContent === input.value); };
  $("batchbar").hidden = true; $("decide").hidden = false;
}

function retiredText(ref) {
  for (const item of state.items.values()) {
    const l = item.links.find((x) => x.ref === ref && typeof x.text === "string");
    if (l) return firstLine(l.text);
  }
  return shortRef(ref);
}

async function sign() {
  const reason = $("batch-reason").value.trim();
  if (!reason) throw new Error("Pick a reason first.");
  const refs = [...state.selected.keys()];
  const shown = shownMs(refs);
  const o = await post("/api/act/options", { action: "standing", reason,
                                             items: refs.map((ref) => ({ ref, to: state.selected.get(ref) })) });
  const s = o.statement, n = counts(s.items.map((i) => i.to));
  const what = [n.approved ? `approve ${plural(n.approved, "note", "notes")}` : "",
                n.rejected ? `reject ${n.approved ? n.rejected : plural(n.rejected, "note", "notes")}` : ""];
  const text = `You ${what.filter(Boolean).join(" and ")}. Reason: “${s.reason}”.`;
  const lines = s.items.map((i) => {
    const item = state.items.get(i.ref);
    return [`${i.to === "approved" ? "Approve" : i.to === "rejected" ? "Reject" : i.to}: ` +
            `${item ? kindName(item.kind) + " — " + firstLine(item.text) : shortRef(i.ref)}`, i.to];
  });
  for (const r of s.retires || []) lines.push([`Also retires the approved rule: ${retiredText(r.ref)}`, "retires"]);
  lines.push([`Signed as ${person(s.principal)}`, "muted"]);
  const r = await signSheet(o, "Check and sign", text, lines, { shown_ms: shown });
  if (!r) return;
  receipt(r);
  state.selected.clear(); $("batch-reason").value = ""; $("decide").hidden = true;
  await load();
}

// --- after the act (§6.6 item 7): the suggestions, "agrees" or "differs", and the check --------------------------
function receipt(r) {
  const box = $("receipt"); box.replaceChildren(); box.hidden = false;
  const n = counts(r.items.map((i) => i.standing));
  const parts = [n.approved ? `${n.approved} approved` : "", n.rejected ? `${n.rejected} rejected` : ""].filter(Boolean);
  box.append(el("h2", null, `Done. ${parts.join(", ")}.`));
  const list = el("ul", "receipt-items");
  for (const i of r.items) {
    const item = state.items.get(i.ref);
    const li = el("li", i.standing);
    li.append(el("div", null, `${i.standing === "approved" ? "Approved" : i.standing === "rejected" ? "Rejected" : i.standing}: ` +
                              `${item ? firstLine(item.text) : shortRef(i.ref)}`));
    for (const s of i.suggestions) {
      const verdict = s.agrees === null ? "it gave no answer" : (s.agrees ? "agrees with you" : "differs from you");
      li.append(el("div", s.agrees === false ? "err" : "muted",
                   `The local model ${s.decider} said: ${s.value} (${Math.round(s.confidence * 100)} % sure), ${verdict}.`));
    }
    if (i.sample) li.append(el("div", "muted", `This was a check of auto-approval ${i.sample}.`));
    for (const ref of i.retired || []) li.append(el("div", "muted", `Also retired: ${retiredText(ref)}`));
    list.append(li);
  }
  box.append(list, button("Close", null, () => { box.hidden = true; }));
  msg("");
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

function more() {
  if (!state.cursor) return null;
  const b = button("Show more", "more", async () => {
    const data = await fetchQueue(state.cursor);
    if (!data) return;
    state.cursor = data.next_cursor; b.remove();
    $("cards").append(...data.groups.map(card));
    const next = more(); if (next) $("cards").append(next);
  });
  b.id = "more";
  return b;
}

async function load() {
  const data = await fetchQueue(null);
  if (!data) return signIn();
  state.w = data.watermark; state.cursor = data.next_cursor; state.items.clear(); state.selected.clear();
  frame("review", data.pending ? `${plural(data.pending, "note", "notes")} to review` : "");
  $("tab-count").textContent = data.pending ? String(data.pending) : "";
  const cards = data.groups.map(card);
  if (data.read_needed.length) {
    cards.unshift(el("p", "notice", `You may review ${data.read_needed.join(", ")}, but you cannot read it. ` +
                                    "Ask the operator for read access to see its notes."));
  }
  if (!data.groups.length) {
    const empty = el("section", "card empty");
    empty.append(el("h2", null, "Nothing to review."), el("p", "muted", "Agents' new notes appear here."));
    cards.push(empty);
  }
  const next = more(); if (next) cards.push(next);
  $("cards").replaceChildren(...cards);
  $("bar-open").onclick = reasonPanel;
  $("decide-back").onclick = () => { $("decide").hidden = true; bar(); };
  $("batch-sign").onclick = () => sign().catch((e) => msg(e.message, "err"));
  bar();
}

window.load = load;
})();
