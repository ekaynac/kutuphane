"use strict";
// Curator web (docs/25 §3.3, §3.4, §5, §6.6). Enrollment, passkey login, and one act per decision: the server builds
// the statement, the page shows it in words, the passkey signs its digest. Note text is plain text only.

const $ = (id) => document.getElementById(id);
const HIDDEN = /[\u200b\u200c\u200d\u2060\ufeff\u202a-\u202e\u2066-\u2069\u00ad]/g;
const REASONS = { approved: ["checked: correct", "useful evidence"], rejected: ["wrong", "duplicate", "not useful", "out of scope"] };

function b64u(buf) {
  let s = "";
  for (const b of new Uint8Array(buf)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function unb64u(text) {
  const s = atob(text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4));
  return Uint8Array.from(s, (c) => c.charCodeAt(0)).buffer;
}
function msg(text, cls) { const m = $("msg"); m.textContent = text || ""; m.className = cls || ""; }

async function post(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "content-type": "application/json" },
                                body: JSON.stringify(body || {}), credentials: "same-origin" });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

function creationOptions(o) {
  return { ...o, challenge: unb64u(o.challenge), user: { ...o.user, id: unb64u(o.user.id) },
           excludeCredentials: (o.excludeCredentials || []).map((c) => ({ ...c, id: unb64u(c.id) })) };
}
function requestOptions(o) {
  return { ...o, challenge: unb64u(o.challenge),
           allowCredentials: (o.allowCredentials || []).map((c) => ({ ...c, id: unb64u(c.id) })) };
}
function credentialJSON(c) {
  const r = c.response, out = { id: c.id, rawId: b64u(c.rawId), type: c.type, clientExtensionResults: {},
                                authenticatorAttachment: c.authenticatorAttachment || null,
                                response: { clientDataJSON: b64u(r.clientDataJSON) } };
  if (r.attestationObject) {
    out.response.attestationObject = b64u(r.attestationObject);
    out.response.transports = r.getTransports ? r.getTransports() : [];
  } else {
    out.response.authenticatorData = b64u(r.authenticatorData);
    out.response.signature = b64u(r.signature);
    if (r.userHandle) out.response.userHandle = b64u(r.userHandle);
  }
  return out;
}

function start(text, label, fn) {
  $("start").hidden = false; $("start-text").textContent = text;
  const b = $("start-button"); b.textContent = label;
  b.onclick = () => fn().catch((e) => msg(e.message, "err"));
}

// --- enrollment and login ----------------------------------------------------------------------------------------
async function enroll() {
  const code = location.hash.slice(1);
  history.replaceState(null, "", "/enroll");  // the code leaves the address bar at once
  if (!code) return start("This enrollment link has no code. Ask the operator for a new one.", "Back", async () => { location.href = "/"; });
  const s = await post("/api/enroll/session", { code });
  start(`Create the passkey of ${s.principal} on this device. It asks for your face, fingerprint or PIN.`, "Create passkey", async () => {
    const o = await post("/api/enroll/options");
    const c = await navigator.credentials.create({ publicKey: creationOptions(o.publicKey) });
    await post("/api/enroll", { challenge_id: o.challenge_id, credential: credentialJSON(c) });
    msg("Passkey saved. Sign in now.", "ok");
    start("Your passkey is saved.", "Sign in with passkey", login);
  });
}

async function login() {
  const o = await post("/auth/passkey/options");
  const c = await navigator.credentials.get({ publicKey: requestOptions(o.publicKey) });
  await post("/auth/passkey", { challenge_id: o.challenge_id, credential: credentialJSON(c) });
  location.href = "/";
}

// --- pending notes and the act ---------------------------------------------------------------------------------
function textWithMarks(pre, text) {
  let last = 0;
  for (const m of text.matchAll(HIDDEN)) {
    pre.append(text.slice(last, m.index));
    const span = document.createElement("span");
    span.className = "mark";
    span.textContent = `⟦U+${m[0].codePointAt(0).toString(16).toUpperCase().padStart(4, "0")}⟧`;
    pre.append(span);
    last = m.index + m[0].length;
  }
  pre.append(text.slice(last));
}

function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }

function card(item) {
  const c = el("div", "card"), shown = performance.now();
  if (item.integrity) c.classList.add("integrity");
  const pre = el("pre"); textWithMarks(pre, item.text); c.append(pre);
  const scope = item.scope ? ` · ${item.scope.repo}${item.scope.branch ? "@" + item.scope.branch : ""} ${item.scope.paths.join(", ")}` : "";
  c.append(el("div", "meta", `${item.kind} (${item.role}) · ${item.book}${scope}`));
  const w = item.writers[0] || {};
  c.append(el("div", "meta", `written by ${w.principal}${w.on_behalf_of ? " for " + w.on_behalf_of : ""}` +
                              `${w.client_id ? " via " + w.client_id : ""} · origin ${w.origin} · ${item.written_at}`));
  if (item.integrity) { c.append(el("div", "err", "The stored parts of this note do not give its id. It cannot be signed.")); return c; }
  const reason = el("input"); reason.type = "text"; reason.placeholder = "Reason (required)"; reason.maxLength = 500;
  const chips = el("div", "chips"), choices = el("div", "choices");
  for (const [to, label, cls] of [["approved", "Approve", "primary"], ["rejected", "Reject", "danger"]]) {
    const b = el("button", cls, label); b.type = "button";
    b.onclick = () => decide(item, to, reason.value.trim(), Math.round(performance.now() - shown)).catch((e) => msg(e.message, "err"));
    choices.append(b);
    for (const r of REASONS[to]) {
      const chip = el("button", "chip", r); chip.type = "button";
      chip.onclick = () => { reason.value = r; };
      chips.append(chip);
    }
  }
  c.append(chips, reason, choices);
  return c;
}

async function decide(item, to, reason, shownMs) {
  if (!reason) throw new Error("Give a reason first.");
  const o = await post("/api/act/options", { action: "standing", items: [{ ref: item.ref, to }], reason });
  $("sheet-text").textContent = `${o.statement.items.length === 1 ? "" : o.statement.items.length + " notes: "}` +
    `${to === "approved" ? "Approve" : "Reject"} · reason: “${o.statement.reason}” · signed as ${o.statement.principal}`;
  const list = $("sheet-items"); list.replaceChildren();
  for (const i of o.statement.items) list.append(el("li", null, `${i.to}: ${i.ref.slice(0, 40)}…`));
  $("sheet").hidden = false;
  $("sheet-cancel").onclick = () => { $("sheet").hidden = true; };
  $("sheet-sign").onclick = async () => {
    try {
      const c = await navigator.credentials.get({ publicKey: requestOptions(o.publicKey) });
      const r = await post("/api/act", { challenge_id: o.challenge_id, credential: credentialJSON(c), shown_ms: shownMs });
      $("sheet").hidden = true;
      msg(`Signed: ${r.items.map((i) => i.standing).join(", ")}`, "ok");
      await load();
    } catch (e) { msg(e.message, "err"); }
  };
}

async function load() {
  const r = await fetch("/api/pending", { credentials: "same-origin" });
  if (r.status === 401) return start("Sign in with the passkey of this device.", "Sign in with passkey", login);
  const data = await r.json();
  $("start").hidden = true;
  $("progress").textContent = `${data.items.length} pending · books: ${data.books.join(", ") || "none"}`;
  $("cards").replaceChildren(...data.items.map(card));
  if (!data.items.length) $("cards").append(el("section", "meta", "Nothing is pending."));
}

async function main() {
  if (!window.PublicKeyCredential) return start("This browser has no passkey support.", "Reload", async () => location.reload());
  if (location.pathname === "/enroll") return enroll();
  const me = await fetch("/api/me", { credentials: "same-origin" });
  if (me.ok) $("who").textContent = `Kütüphane curator · ${(await me.json()).principal}`;
  return load();
}

main().catch((e) => msg(e.message, "err"));
