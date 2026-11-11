"use strict";
// Received packages (D85 S3): the `verified` imports of the books that the person curates and reads, with the
// findings, the diff, who sent it and the sender's policy suggestion. Approve (with the policy to apply) or Reject
// (with a reason), then one passkey act for every chosen package. This page only signs: the owner's timer publishes.
// Every server value is plain text (textContent). Only `packagesPage` is global.

(() => {
const MAX_ITEMS = 50;
const REASONS = ["Not the right content", "Findings are not acceptable", "Duplicate", "Not needed now"];
const state = { selected: new Map(), policies: new Map(), items: new Map() };

function plural(n, one, many) { return `${n} ${n === 1 ? one : many}`; }
function policyOf(item) { return state.policies.get(item.import_id); }

function findingLine(f) {
  const what = f.kind === "personal_data" ? `Personal data (${f.rule})` : f.kind === "agent_instruction" ? "Agent instruction file"
             : f.kind === "instruction_like_text" ? "Text that looks like an instruction" : f.kind;
  return `${what}: ${f.path || ""}${f.note ? " — " + f.note : ""}${f.match ? " — “" + f.match + "”" : ""}`;
}

function section(title, ...nodes) { const s = el("section", "part"); s.append(el("h3", null, title), ...nodes); return s; }

function list(values, cls) { const ul = el("ul", cls); for (const v of values) ul.append(el("li", null, v)); return ul; }

function diff(d) {
  if (!d) return null;
  const rows = [["Added", d.added], ["Changed", d.changed], ["Removed", d.removed]].filter(([, v]) => v.length);
  if (!rows.length) return section("Changes", el("p", "muted", "No change to the files of the current version."));
  const s = section("Changes");
  for (const [name, files] of rows) s.append(el("div", "link-type", `${name} (${files.length})`), list(files.slice(0, 20)));
  return s;
}

// The policy to sign: the sender's suggestion is preselected. cloud_ok is never offered here (the operator's CLI only).
function policyChooser(item) {
  const suggestion = item.policy_suggestion || {};
  const cloud = suggestion.egress === "cloud_ok";
  state.policies.set(item.import_id, { v: 1, sensitivity: suggestion.sensitivity === "restricted" ? "restricted" : "normal",
                                       egress: "local_only", protection: "standard" });
  const box = el("div", "policy");
  const select = el("select");
  select.setAttribute("aria-label", "Sensitivity of the book");
  for (const [value, label] of [["normal", "Normal"], ["restricted", "Restricted"]]) {
    const o = el("option", null, label); o.value = value; select.append(o);
  }
  select.value = policyOf(item).sensitivity;
  select.onchange = () => { policyOf(item).sensitivity = select.value; };
  box.append(el("span", null, "Policy to apply: "), select, el("span", "muted", " · stays on this installation (local only)"));
  if (cloud) box.append(el("p", "risk", "The sender suggested sending passages to cloud models. A passkey cannot approve that: the operator does it on the command line."));
  return box;
}

function details(item) {
  const d = el("details", "details"), dl = el("dl");
  d.append(el("summary", null, "Details"));
  for (const [k, v] of [["Import", `#${item.import_id}`], ["Signing key", item.issuer], ["Sequence", String(item.sequence)],
                        ["Content id", item.content_id], ["Manifest digest", item.manifest_sha256],
                        ["Files", String(item.files)], ["Received", item.received_at]]) dl.append(el("dt", null, k), el("dd", null, v));
  d.append(dl);
  return d;
}

function choose(item, to) {
  const id = item.import_id;
  if (to && state.selected.get(id) === to) to = null;  // a second tap clears the choice
  if (to) state.selected.set(id, to); else state.selected.delete(id);
  const node = document.querySelector(`.pkg[data-id="${id}"]`);
  node.classList.toggle("chose-approved", to === "approve");
  node.classList.toggle("chose-rejected", to === "reject");
  for (const b of node.querySelectorAll(".choices button")) {
    b.classList.toggle("on", b.dataset.to === to); b.setAttribute("aria-pressed", String(b.dataset.to === to));
  }
  bar();
}

function card(item) {
  state.items.set(item.import_id, item);
  const box = el("article", "card pkg");
  box.dataset.id = item.import_id;
  box.append(el("h2", null, `${item.title} (${item.book})`));
  const by = item.submitted_by ? `Sent by ${person(item.submitted_by)}${item.submitted_for ? " for " + person(item.submitted_for) : ""}` : "Received at the console";
  box.append(el("p", "muted", `${by} · ${day(item.received_at)} · ${plural(item.files, "file", "files")}`));
  if (item.accepted_by) {
    box.append(el("p", "kindline", `Accepted by ${person(item.accepted_by.principal)} at the sender (${day(item.accepted_by.at)}): ${item.accepted_by.record}`));
  }
  if (item.findings.length) {
    box.append(section(`Findings (${item.findings.length})`, list(item.findings.map(findingLine), "findings")),
               el("p", "muted", "You may approve with findings; you read them here."));
  } else {
    box.append(el("p", "muted", "No findings."));
  }
  box.append(...[diff(item.diff), policyChooser(item)].filter(Boolean));
  const choices = el("div", "choices");
  for (const [to, label, cls] of [["approve", "Approve", "approve"], ["reject", "Reject", "reject"]]) {
    const b = button(label, cls, () => choose(item, to)); b.dataset.to = to; choices.append(b);
  }
  box.append(choices, details(item));
  return box;
}

function counts() {
  const n = { approve: 0, reject: 0 };
  for (const to of state.selected.values()) n[to]++;
  return n;
}

function bar() {
  const n = counts(), open = !$("decide").hidden;
  $("batchbar").hidden = state.selected.size === 0 || open;
  if (state.selected.size === 0) $("decide").hidden = true;
  $("batch-count").textContent = [n.approve ? `${n.approve} approve` : "", n.reject ? `${n.reject} reject` : ""].filter(Boolean).join(" · ");
  $("bar-open").textContent = `Sign ${plural(state.selected.size, "decision", "decisions")}`;
}

function reasonPanel() {
  const chips = $("batch-chips"), input = $("batch-reason");
  chips.replaceChildren();
  for (const text of REASONS) {
    const chip = button(text, "chip reason-chip", () => { input.value = text; });
    chips.append(chip);
  }
  $("batchbar").hidden = true; $("decide").hidden = false;
}

function openSign() {
  if (state.selected.size > MAX_ITEMS) throw new Error(`Choose at most ${MAX_ITEMS} packages for one signature.`);
  if (counts().reject) return reasonPanel();  // a rejection needs its reason first
  return sign();
}

async function sign() {
  const reason = $("batch-reason").value.trim();
  const rejects = counts().reject;
  if (rejects && !reason) throw new Error("Write a reason for the rejection first.");
  const items = [...state.selected].map(([id, to]) => to === "approve"
    ? { import_id: id, decision: "approve", policy: policyOf(state.items.get(id)) }
    : { import_id: id, decision: "reject", reason });
  const o = await post("/api/act/options", { action: "package", items });
  const n = { approve: 0, reject: 0 };
  const lines = o.statement.items.map((i) => {
    n[i.decision]++;
    const item = state.items.get(i.import_id);
    const name = item ? `${item.title} (${i.book})` : `#${i.import_id} (${i.book})`;
    return i.decision === "approve"
      ? [`Approve: ${name} — ${i.policy.sensitivity}, ${i.policy.egress}`, "approved"]
      : [`Reject: ${name} — “${i.reason}”`, "rejected"];
  });
  lines.push([`Signed as ${person(o.statement.principal)}`, "muted"]);
  const text = `You ${[n.approve ? "approve " + plural(n.approve, "package", "packages") : "",
                        n.reject ? "reject " + plural(n.reject, "package", "packages") : ""].filter(Boolean).join(" and ")}.`;
  const r = await signSheet(o, "Check and sign", text, lines);
  if (!r) return;
  const box = $("receipt"); box.replaceChildren(); box.hidden = false;
  box.append(el("h2", null, "Signed. It is published within a minute."),
             el("p", "muted", "Nothing is published on this page: the server applies your signature, and only while you still hold the right on the book."),
             button("Close", null, () => { box.hidden = true; }));
  state.selected.clear(); $("batch-reason").value = ""; $("decide").hidden = true;
  await packagesPage(true);
}

async function packagesPage(keepReceipt) {
  const r = await fetch("/api/packages", { credentials: "same-origin" });
  if (r.status === 401) return signIn();
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  state.selected.clear(); state.items.clear(); state.policies.clear();
  if (!keepReceipt) $("receipt").hidden = true;
  frame("packages", data.items.length ? `${plural(data.items.length, "package", "packages")} to review` : "");
  const cards = data.items.map(card);
  if (!cards.length) {
    const empty = el("section", "card empty");
    empty.append(el("h2", null, "No packages to review."), el("p", "muted", "Packages that wait for your decision appear here."));
    cards.push(empty);
  }
  $("cards").replaceChildren(...cards);
  $("bar-open").onclick = () => Promise.resolve().then(openSign).catch((e) => msg(e.message, "err"));
  $("decide-back").onclick = () => { $("decide").hidden = true; bar(); };
  $("batch-sign").onclick = () => sign().catch((e) => msg(e.message, "err"));
  bar();
}

window.packagesPage = packagesPage;
})();
