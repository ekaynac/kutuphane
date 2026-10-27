"use strict";
// Curator web (docs/25 §3.3, §3.4, §5, §6.6): the shared helpers, enrollment and passkey login. The queue and its
// acts are in queue.js (`load`). Note text is plain text only.

const $ = (id) => document.getElementById(id);
const HIDDEN = /[\u200b\u200c\u200d\u2060\ufeff\u202a-\u202e\u2066-\u2069\u00ad]/g;

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

async function main() {
  if (!window.PublicKeyCredential) return start("This browser has no passkey support.", "Reload", async () => location.reload());
  if (location.pathname === "/enroll") return enroll();
  const me = await fetch("/api/me", { credentials: "same-origin" });
  if (me.ok) $("who").textContent = `Kütüphane curator · ${(await me.json()).principal}`;
  return load();
}

// Every deferred script (queue.js, …) has run when the document is parsed.
document.addEventListener("DOMContentLoaded", () => main().catch((e) => msg(e.message, "err")));
