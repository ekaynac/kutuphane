"use strict";
// Curator web (docs/25 §3.3, §3.4, §5, §6.6): the shared helpers, the plain words of the page, enrollment, passkey
// login and the three tabs. The queue is in queue.js (`load`), "my words" in confirm.js (`confirmPage`), auto-approval
// in delegation.js (`showDelegations`). Note text is plain text only (textContent); hidden characters become marks.

const $ = (id) => document.getElementById(id);
const HIDDEN = /[\u200b\u200c\u200d\u2060\ufeff\u202a-\u202e\u2066-\u2069\u00ad]/g;

// The kinds of note in plain words: [short name, what it is].
const KINDS = {
  finding: ["Finding", "something an agent observed"],
  convention: ["Convention", "a rule the team should follow"],
  decision_proposal: ["Decision proposal", "a choice between options"],
  lesson: ["Lesson", "something learned from experience"],
  dead_end: ["Dead end", "an approach that did not work"],
  test_result: ["Test result", "what a test run showed"],
};
const TABS = {
  review: "Agents proposed these notes. Approve what is true and useful; reject the rest. Your fingerprint signs each decision.",
  words: "An agent typed text for you. Confirm only if these are your words (or you checked them).",
  auto: "A local model may approve findings and other evidence notes for a short time. You check some of its approvals.",
};

function kindName(kind) { return (KINDS[kind] || [kind])[0]; }
function kindLine(kind) { const k = KINDS[kind]; return k ? `${k[0]}: ${k[1]}` : kind; }
function person(principal) { return principal ? principal.replace(/^(user|agent|model):/, "") : ""; }
function day(iso) {
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
function firstLine(text, n = 120) {
  const line = text.split("\n").find((l) => l.trim()) || "";
  return line.length > n ? line.slice(0, n - 1) + "…" : line;
}
function fileName(path) { return path.split("/").pop(); }
// Where a note applies (its scope) and the commit it saw: parts of the note id, so always on the card (not in Details).
function where(item) {
  const parts = [];
  if (item.scope) {
    const s = item.scope;
    parts.push(`Applies to ${s.repo}${s.branch ? ` (branch ${s.branch})` : ""}${s.paths.length ? ": " + s.paths.join(", ") : ""}`);
  } else if (item.role === "rule") parts.push("Applies everywhere (no scope)");
  if (item.commit) parts.push(`seen at commit ${item.commit.slice(0, 12)}`);
  if (!parts.length) return null;
  const text = parts.join(" · ");
  return el("div", "where", `${text[0].toUpperCase()}${text.slice(1)}.`);
}

function b64u(buf) {
  let s = "";
  for (const b of new Uint8Array(buf)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function unb64u(text) {
  const s = atob(text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4));
  return Uint8Array.from(s, (c) => c.charCodeAt(0)).buffer;
}
let msgTimer = null;
function msg(text, cls) {
  const m = $("msg"); m.textContent = text || ""; m.className = cls || "";
  clearTimeout(msgTimer);
  if (cls === "ok") msgTimer = setTimeout(() => { if (m.textContent === text) msg(""); }, 6000);
}

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

// --- the page frame: the active tab and its one-line explanation ------------------------------------------------
function frame(tab, progress) {
  $("tabs").hidden = false;
  for (const [name, id] of [["review", "tab-review"], ["words", "tab-words"], ["auto", "tab-auto"]]) {
    $(id).classList.toggle("on", name === tab);
    if (name === tab) $(id).setAttribute("aria-current", "page"); else $(id).removeAttribute("aria-current");
  }
  $("intro").hidden = false; $("intro").textContent = TABS[tab];
  $("progress").textContent = progress || "";
  $("start").hidden = true;
}

// The sign sheet: the stored statement in words (`text`, `lines`), then one passkey act. Resolves with the act
// result, or null when the person goes back.
function signSheet(options, title, text, lines, body = {}) {
  $("sheet-title").textContent = title;
  $("sheet-text").textContent = text;
  $("sheet-items").replaceChildren(...lines.map(([line, cls]) => el("li", cls || null, line)));
  $("sheet").hidden = false;
  $("sheet-sign").focus();
  return new Promise((resolve, reject) => {
    $("sheet-cancel").onclick = () => { $("sheet").hidden = true; resolve(null); };
    $("sheet-sign").onclick = async () => {
      try {
        const c = await navigator.credentials.get({ publicKey: requestOptions(options.publicKey) });
        const r = await post("/api/act", { challenge_id: options.challenge_id, credential: credentialJSON(c), ...body });
        $("sheet").hidden = true;
        resolve(r);
      } catch (e) { reject(e); }
    };
  });
}

// --- enrollment and login ----------------------------------------------------------------------------------------
async function enroll() {
  const code = location.hash.slice(1);
  history.replaceState(null, "", "/enroll");  // the code leaves the address bar at once
  if (!code) return start("This sign-up link has no code. Ask the operator for a new one.", "Back", async () => { location.href = "/"; });
  const s = await post("/api/enroll/session", { code });
  start(`Create the passkey of ${person(s.principal)} on this phone. It asks for your fingerprint, face or PIN.`, "Create passkey", async () => {
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
  if (location.pathname === "/enroll") location.href = "/"; else location.reload();
}

function signIn() { start("Sign in with the passkey of this phone (fingerprint, face or PIN).", "Sign in with passkey", login); }

// --- plain text with visible marks for hidden characters -------------------------------------------------------
function textWithMarks(node, text) {
  let last = 0;
  for (const m of text.matchAll(HIDDEN)) {
    node.append(text.slice(last, m.index));
    const span = document.createElement("span");
    span.className = "mark";
    span.title = "A hidden character";
    span.textContent = `⟦U+${m[0].codePointAt(0).toString(16).toUpperCase().padStart(4, "0")}⟧`;
    node.append(span);
    last = m.index + m[0].length;
  }
  node.append(text.slice(last));
  return node;
}

function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
function button(label, cls, fn) {
  const b = el("button", cls || null, label); b.type = "button";
  if (fn) b.onclick = () => Promise.resolve(fn()).catch((e) => msg(e.message, "err"));
  return b;
}

async function main() {
  if (!window.PublicKeyCredential) return start("This browser cannot use passkeys. Open the page in Chrome.", "Reload", async () => location.reload());
  if (location.pathname === "/enroll") return enroll();
  const me = await fetch("/api/me", { credentials: "same-origin" });
  if (!me.ok) return signIn();
  $("who").textContent = person((await me.json()).principal);
  if (location.pathname.startsWith("/c/") || location.pathname === "/requests") return confirmPage();
  if (location.pathname === "/delegations") return showDelegations();
  return load();
}

// Every deferred script (queue.js, …) has run when the document is parsed.
document.addEventListener("DOMContentLoaded", () => main().catch((e) => msg(e.message, "err")));
