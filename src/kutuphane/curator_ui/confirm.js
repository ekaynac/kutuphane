"use strict";
// D70 R3 "my words" confirmation and R7 withdrawal (docs/25 §7.3). The page shows the full text first (plain text,
// hidden characters as marks), who typed it and every canonical field; then the two choices in the exact words of
// the design; then one passkey act over the statement. Nothing is stored before the act; leaving the page stores
// nothing. The sign sheet shows the stored statement, not the choice made on this page.

const ASKED = { human: "your own words", assisted: "a model's text that you checked" };

async function getJSON(path) {
  const r = await fetch(path, { credentials: "same-origin" });
  if (r.status === 401) { signIn(); return null; }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

function when(iso) {
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function typedBy(item) {
  const r = item.request, line = el("div", "kindline");
  const by = r ? `Typed by ${person(r.entered_by)}${r.on_behalf_of ? " for " + person(r.on_behalf_of) : ""} · ${day(r.at)}` : "";
  line.append(el("strong", null, kindLine(item.kind)), el("span", null, by));
  return line;
}

// Every canonical field that the note holds besides its text (§6.6 items 1–2), in plain words.
function parts(item) {
  const out = [];
  if (item.citations.length) {
    const s = el("section", "part evidence"); s.append(el("h3", null, "Evidence"));
    for (const c of item.citations) {
      if (c === null) { s.append(el("div", "muted", "A source in a book you cannot read")); continue; }
      const m = c.match(/^[^@]+@[^/]+\/[^/]+\/(.+)#\d+$/) || c.match(/^[^@]+@[^:]+:(.+):\d+-\d+(#.*)?$/);
      const row = el("div", "src"); row.append(el("strong", null, m ? fileName(m[1]) : c));
      if (m) row.append(el("span", "muted", ` ${m[1]}`));
      s.append(row);
    }
    out.push(s);
  }
  if (item.decision) {
    const s = el("section", "part decision"); s.append(el("h3", null, "Options"));
    const list = el("ol");
    for (const o of item.decision.options) {
      const li = el("li", o === item.decision.choice ? "chosen" : null);
      if (o === item.decision.choice) li.append(el("span", "badge", "Proposed choice"));
      li.append(textWithMarks(el("span"), o)); list.append(li);
    }
    s.append(list);
    if (!item.decision.options.includes(item.decision.choice)) {
      const chosen = el("div", "chosen solo");
      chosen.append(el("span", "badge", "Proposed choice (not one of the options)"), textWithMarks(el("span"), item.decision.choice));
      s.append(chosen);
    }
    out.push(s);
  }
  if (item.links.length) {
    const s = el("section", "part links"); s.append(el("h3", null, "Linked"));
    for (const l of item.links) s.append(el("div", "src", `${l.type}: ${l.target === null ? "a note in a book you cannot read" : l.target}`));
    out.push(s);
  }
  return out;
}

function details(item) {
  const d = el("details", "details");
  d.append(el("summary", null, "Details"));
  const dl = el("dl"), add = (k, v) => { if (v) dl.append(el("dt", null, k), el("dd", null, v)); };
  add("Note id", item.ref);
  add("Kind", `${item.kind} (${item.role === "rule" ? "a rule" : "evidence"}) in ${item.book}`);
  add("Scope", item.scope ? `${item.scope.repo}${item.scope.branch ? "@" + item.scope.branch : ""} ${item.scope.paths.join(", ")}` :
               item.applies_to ? "No repository scope" : "Everywhere (no scope)");
  add("Applies to", appliesTo(item.applies_to));  // #164: the kstd Scope bound, part of the note id
  add("Class key", item.class_key || "none");
  add("Commit", item.commit);
  const r = item.request;
  if (r) {
    add("Typed by", r.entered_by + (r.on_behalf_of ? ` for ${r.on_behalf_of}` : ""));
    add("Client", r.client_id);
    add("Asked", `${r.at}; it asked for ${r.requested}; open until ${r.expires_at}`);
  }
  add("Origin now", item.origin + (item.confirmed_by ? ` (confirmed by ${item.confirmed_by})` : ""));
  d.append(dl);
  return d;
}

function noteCard(item) {
  const box = el("article", "card");
  if (item.integrity) box.classList.add("integrity");
  box.append(textWithMarks(el("div", "text"), item.text), ...[typedBy(item), where(item)].filter(Boolean), ...parts(item));
  const r = item.request;
  if (!r) box.append(el("p", "muted", "Nobody asked you to confirm this note."));
  else if (!r.open) box.append(el("p", "err", `This request expired on ${when(r.expires_at)}. Ask the agent to send it again.`));
  else box.append(el("p", "muted", `${person(r.entered_by)} says these are ${ASKED[r.requested] || r.requested}. ` +
                                   `Open until ${when(r.expires_at)}.`));
  if (item.integrity) box.append(el("div", "err", "The stored parts of this note do not match its id: it may have been changed. It cannot be signed."));
  box.append(details(item));
  return box;
}

async function signHere(body, title, text, lines) {
  const o = await post("/api/act/options", body);
  return signSheet(o, title, text(o.statement), [...lines(o.statement), [`Signed as ${person(o.statement.principal)}`, "muted"]]);
}

function choices(item) {
  if (!item.claims.length) return null;
  const box = el("article", "card"), name = "claim";
  box.append(el("h2", null, "Whose words are these?"));
  for (const c of item.claims) {
    const label = el("label", "choice"), input = el("input");
    input.type = "radio"; input.name = name; input.value = c.claim; input.id = `claim-${c.claim}`;
    label.append(input, el("span", null, c.words));
    box.append(label);
  }
  const words = (claim) => (item.claims.find((c) => c.claim === claim) || { words: claim }).words;
  const b = button("Sign with fingerprint", "primary big", async () => {
    const picked = box.querySelector(`input[name=${name}]:checked`);
    if (!picked) throw new Error("Choose one of the two sentences first.");
    const r = await signHere({ action: "confirm", ref: item.ref, claim: picked.value, write: item.request.write },
      "Check and sign",
      (s) => `You confirm: “${words(s.claim)}” Typed by ${person(s.entered_by)}.`,
      () => [[`Note: ${firstLine(item.text)}`]]);
    if (r) { msg(`Confirmed. The note now shows ${r.origin === "human" ? "your words" : "text you checked"}.`, "ok"); await show(); }
  });
  b.id = "confirm-sign";
  const row = el("div", "choices"); row.append(b);
  box.append(row);
  return box;
}

function withdrawal(item) {
  if (!item.withdraw) return null;
  const box = el("article", "card");
  box.append(el("p", null, item.origin === "human" ? "You confirmed these as your words. You can take that back."
                                                   : "You confirmed that you checked this text. You can take that back."));
  const b = button("Withdraw my confirmation", "reject big", async () => {
    const r = await signHere({ action: "withdraw", ref: item.ref }, "Check and sign",
      () => "You withdraw your confirmation.", () => [[`Note: ${firstLine(item.text)}`]]);
    if (r) { msg("Withdrawn.", "ok"); await show(); }
  });
  b.id = "withdraw-sign";
  box.append(b);
  return box;
}

async function show() {
  const [, , book, id] = location.pathname.split("/");
  const item = await getJSON(`/api/requests/${encodeURIComponent(book)}/${encodeURIComponent(id)}`);
  if (!item) return;
  frame("words");
  $("cards").replaceChildren(...[noteCard(item), choices(item), withdrawal(item)].filter(Boolean));
}

async function list() {
  const data = await getJSON("/api/requests");
  if (!data) return;
  frame("words", data.items.length ? `${data.items.length} ${data.items.length === 1 ? "text waits" : "texts wait"} for you` : "");
  $("cards").replaceChildren(...data.items.map((item) => {
    const box = el("article", "card");
    box.append(textWithMarks(el("div", "text"), item.text), typedBy(item));
    const a = el("a", "open button primary", "Check and confirm");
    a.href = `/c/${encodeURIComponent(item.book)}/${encodeURIComponent(item.ref.split("@")[1])}`;
    box.append(a);
    return box;
  }));
  if (!data.items.length) {
    const empty = el("section", "card empty");
    empty.append(el("h2", null, "Nothing to confirm."), el("p", "muted", "When an agent types text for you, it appears here."));
    $("cards").append(empty);
  }
}

function confirmPage() {
  return location.pathname === "/requests" ? list() : show();
}
