"use strict";
// D70 R3 "my words" confirmation and R7 withdrawal (docs/25 §7.3). The page shows who asks, the full text (plain
// text, hidden characters as marks) and the canonical fields first; then the two choices in the exact words of the
// design; then one passkey act over the statement. Nothing is stored before the act; leaving the page stores nothing.

async function loginHere() {
  const o = await post("/auth/passkey/options");
  const c = await navigator.credentials.get({ publicKey: requestOptions(o.publicKey) });
  await post("/auth/passkey", { challenge_id: o.challenge_id, credential: credentialJSON(c) });
  location.reload();
}

async function getJSON(path) {
  const r = await fetch(path, { credentials: "same-origin" });
  if (r.status === 401) { start("Sign in with the passkey of this device.", "Sign in with passkey", loginHere); return null; }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

function row(label, value) {
  const d = el("div", "meta");
  d.append(el("b", null, `${label}: `), document.createTextNode(value));
  return d;
}

function noteBlock(item) {
  const box = el("div", "card");
  if (item.integrity) box.classList.add("integrity");
  const pre = el("pre"); textWithMarks(pre, item.text); box.append(pre);
  box.append(row("Kind", `${item.kind} (${item.role}) · ${item.book}`));
  if (item.scope) box.append(row("Scope", `${item.scope.repo}${item.scope.branch ? "@" + item.scope.branch : ""} ${item.scope.paths.join(", ")}`));
  if (item.commit) box.append(row("Commit", item.commit));
  for (const c of item.citations) box.append(row("Cites", c === null ? "a source you may not read" : c));
  for (const l of item.links) box.append(row(l.type, l.target === null ? "a note you may not read" : l.target));
  if (item.decision) box.append(row("Options", item.decision.options.join(" | ")), row("Choice", item.decision.choice));
  box.append(row("Note", item.ref));
  if (item.integrity) box.append(el("div", "err", "The stored parts of this note do not give its id. It cannot be signed."));
  return box;
}

function asker(item) {
  const r = item.request, box = el("div", "card");
  if (!r) { box.append(el("div", "meta", "Nobody asked for a confirmation of this note.")); return box; }
  box.append(el("h2", null, r.open ? "A confirmation is asked" : "This request expired"));
  box.append(row("Entered by", r.entered_by + (r.on_behalf_of ? ` for ${r.on_behalf_of}` : "")));
  if (r.client_id) box.append(row("Client", r.client_id));
  box.append(row("Asked at", r.at), row("It asked for", r.requested), row("Open until", r.expires_at));
  box.append(row("Shown origin now", item.origin + (item.confirmed_by ? ` (confirmed by ${item.confirmed_by})` : "")));
  return box;
}

// The sheet shows the stored statement (docs/25 §5.2), not the choice made on this page: `describe(statement)`.
async function sign(body, describe) {
  const o = await post("/api/act/options", body);
  $("sheet-text").textContent = `${describe(o.statement)} · signed as ${o.statement.principal}`;
  const list = $("sheet-items"); list.replaceChildren();
  list.append(el("li", null, o.statement.item.ref));
  $("sheet").hidden = false;
  return new Promise((resolve, reject) => {
    $("sheet-cancel").onclick = () => { $("sheet").hidden = true; resolve(null); };
    $("sheet-sign").onclick = async () => {
      try {
        const c = await navigator.credentials.get({ publicKey: requestOptions(o.publicKey) });
        const r = await post("/api/act", { challenge_id: o.challenge_id, credential: credentialJSON(c) });
        $("sheet").hidden = true;
        resolve(r);
      } catch (e) { reject(e); }
    };
  });
}

function choices(item) {
  const box = el("div", "card"), name = "claim";
  if (!item.claims.length) return null;
  box.append(el("h2", null, "Whose words are these?"));
  for (const c of item.claims) {
    const label = el("label", "choice"), input = el("input");
    input.type = "radio"; input.name = name; input.value = c.claim; input.id = `claim-${c.claim}`;
    label.append(input, document.createTextNode(" " + c.words));
    box.append(label);
  }
  const b = el("button", "primary", "Sign with passkey"); b.type = "button"; b.id = "confirm-sign";
  b.onclick = async () => {
    try {
      const picked = box.querySelector(`input[name=${name}]:checked`);
      if (!picked) throw new Error("Choose one of the two sentences first.");
      const words = (claim) => (item.claims.find((c) => c.claim === claim) || { words: claim }).words;
      const r = await sign({ action: "confirm", ref: item.ref, claim: picked.value, write: item.request.write },
        (s) => `“${words(s.claim)}” (${s.claim}) · entered by ${s.entered_by}`);
      if (r) { msg(`Confirmed: origin ${r.origin} (entered by ${r.entered_by})`, "ok"); await show(); }
    } catch (e) { msg(e.message, "err"); }
  };
  box.append(el("div", "choices"));
  box.lastChild.append(b);
  return box;
}

function withdrawal(item) {
  if (!item.withdraw) return null;
  const box = el("div", "card");
  box.append(el("div", "meta", `You confirmed this note as ${item.origin}. You can withdraw that confirmation (R7).`));
  const b = el("button", "danger", "Withdraw my confirmation"); b.type = "button"; b.id = "withdraw-sign";
  b.onclick = async () => {
    try {
      const r = await sign({ action: "withdraw", ref: item.ref }, () => "Withdraw my confirmation");
      if (r) { msg(`Withdrawn: origin ${r.origin}`, "ok"); await show(); }
    } catch (e) { msg(e.message, "err"); }
  };
  box.append(b);
  return box;
}

async function show() {
  const [, , book, id] = location.pathname.split("/");
  const item = await getJSON(`/api/requests/${encodeURIComponent(book)}/${encodeURIComponent(id)}`);
  if (!item) return;
  $("start").hidden = true;
  $("progress").textContent = "Confirm whose words a note holds";
  $("cards").replaceChildren(...[asker(item), noteBlock(item), choices(item), withdrawal(item)].filter(Boolean));
}

async function list() {
  const data = await getJSON("/api/requests");
  if (!data) return;
  $("start").hidden = true;
  $("progress").textContent = `${data.items.length} confirmation request(s)`;
  $("cards").replaceChildren(...data.items.map((item) => {
    const box = noteBlock(item);
    const a = el("a", null, "Open"); a.href = `/c/${item.book}/${item.ref.split("@")[1]}`;
    box.prepend(row("Entered by", item.request.entered_by), a);
    return box;
  }));
  if (!data.items.length) $("cards").append(el("section", "meta", "No request is waiting for you."));
}

function confirmPage() {
  return location.pathname === "/requests" ? list() : show();
}
