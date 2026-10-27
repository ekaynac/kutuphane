"use strict";
// Curator web, D73 delegations (docs/25 §8). Uses the helpers of core.js ($, el, post, msg, requestOptions,
// credentialJSON). The page shows the shadow agreement before a person signs a `delegate` act, the live agreement of
// each delegation, an `end_delegation` act, and the review list of an ended delegation with one batch Retire act.

const DELEGATION_WORDS = { live: "live", expired: "expired", "ended:revoked": "ended by a curator",
                           "ended:disagreement": "ended: a person disagreed with a sample" };

async function signAct(options, words, lines) {
  $("sheet-text").textContent = `${words} · signed as ${options.statement.principal}`;
  const list = $("sheet-items"); list.replaceChildren(...lines.map((l) => el("li", null, l)));
  $("sheet").hidden = false;
  return new Promise((resolve, reject) => {
    $("sheet-cancel").onclick = () => { $("sheet").hidden = true; resolve(null); };
    $("sheet-sign").onclick = async () => {
      try {
        const c = await navigator.credentials.get({ publicKey: requestOptions(options.publicKey) });
        const r = await post("/api/act", { challenge_id: options.challenge_id, credential: credentialJSON(c) });
        $("sheet").hidden = true;
        resolve(r);
      } catch (e) { reject(e); }
    };
  });
}

function agreementTable(rows, minShadow) {
  const t = el("table", "agreement");
  const head = el("tr");
  for (const h of ["threshold", "n", "agreed", "share", "Wilson low"]) head.append(el("th", null, h));
  t.append(head);
  for (const r of rows) {
    const tr = el("tr", r.n < minShadow ? "short" : null);
    for (const v of [r.threshold, r.n, r.agreed, r.share ?? "–", r.wilson_lower ?? "–"]) tr.append(el("td", null, String(v)));
    t.append(tr);
  }
  return t;
}

function numberField(label, value, min, max, step) {
  const wrap = el("label", "field", label + " ");
  const input = el("input"); input.type = "number"; input.min = min; input.max = max; input.step = step; input.value = value;
  wrap.append(input);
  return [wrap, input];
}

function shadowCard(s, data) {
  const c = el("div", "card");
  c.append(el("div", null, `${s.decider} · ${s.book} / ${s.kind}`));
  c.append(el("div", "meta", `spec ${s.spec_sha256.slice(0, 16)}… · a delegation needs ${s.min_shadow} shadow decisions at its threshold`));
  c.append(agreementTable(s.agreement, s.min_shadow));
  const [f1, threshold] = numberField("threshold", data.defaults.min_confidence, 0.5, 1, 0.05);
  const [f2, every] = numberField("sample 1 in", data.defaults.sample_every, 2, 100, 1);
  const [f3, days] = numberField("days", data.defaults.days, 1, data.max_days, 1);
  const go = el("button", "primary", "Delegate"); go.type = "button";
  go.onclick = async () => {
    try {
      const o = await post("/api/act/options", { action: "delegate", book: s.book, kind: s.kind, decider: s.decider,
        spec_sha256: s.spec_sha256, min_confidence: Number(threshold.value), sample_every: Number(every.value),
        days: Number(days.value) });
      const d = o.statement.delegation;
      const r = await signAct(o, `Delegate: ${d.decider} may approve ${d.kind} notes of ${d.book}`, [
        `approver of record: model:${d.decider}`, `only suggestions "approved" at confidence ≥ ${d.min_confidence}`,
        `the database checks 1 in ${d.sample_every} (and one after ${2 * d.sample_every} unchecked); a "no" on a check ends it`,
        `until ${d.expires_at}`]);
      if (r) { msg(`Delegation ${r.delegation} signed.`, "ok"); await showDelegations(); }
    } catch (e) { msg(e.message, "err"); }
  };
  const row = el("div", "choices"); row.append(f1, f2, f3, go);
  c.append(row);
  return c;
}

function delegationCard(d) {
  const c = el("div", "card");
  c.append(el("div", null, `${d.decider} · ${d.book} / ${d.kind} · ${DELEGATION_WORDS[d.state] || d.state}`));
  c.append(el("div", "meta", `threshold ${d.min_confidence} · 1 in ${d.sample_every} · by ${d.created_by} · until ${d.expires_at}`));
  c.append(el("div", "meta", `${d.approved} approved by the model · ${d.samples} checks (${d.open_samples} open)`));
  const open = el("button", null, "Details"); open.type = "button";
  open.onclick = () => showDelegation(d.id).catch((e) => msg(e.message, "err"));
  c.append(open);
  return c;
}

async function showDelegations() {
  const r = await fetch("/api/delegations", { credentials: "same-origin" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const data = await r.json();
  $("start").hidden = true;
  $("progress").textContent = `delegations · books: ${data.books.join(", ") || "none"}`;
  const cards = [el("h2", null, "Delegations"), ...data.delegations.map(delegationCard)];
  if (!data.delegations.length) cards.push(el("section", "meta", "No delegation yet."));
  cards.push(el("h2", null, "Shadow agreement (suggestions before your decisions)"), ...data.shadow.map((s) => shadowCard(s, data)));
  if (!data.shadow.length) cards.push(el("section", "meta", "No decider has written suggestions in an evidence class of your books."));
  $("cards").replaceChildren(...cards);
}

async function showDelegation(id) {
  const r = await fetch(`/api/delegations/${encodeURIComponent(id)}`, { credentials: "same-origin" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const rep = await r.json(), d = rep.delegation, live = rep.live_agreement;
  const head = el("div", "card");
  head.append(el("div", null, `${d.decider} · ${d.book} / ${d.kind} · ${DELEGATION_WORDS[d.state] || d.state}`));
  head.append(el("div", "meta", `checks: ${live.agreed} agreed, ${live.disagreed} disagreed, ${live.open} open, ${live.closed} closed with no verdict`));
  head.append(el("div", "meta", `coverage: ${rep.coverage.approved} of ${rep.coverage.class_notes} notes of the class`));
  if (rep.end) head.append(el("div", "meta", `ended ${rep.end.at} by ${rep.end.ended_by} (${rep.end.cause})`));
  const reason = el("input"); reason.type = "text"; reason.placeholder = "Reason (required)"; reason.maxLength = 500;
  head.append(reason);
  const row = el("div", "choices");
  if (d.state === "live") {
    const stop = el("button", "danger", "End delegation"); stop.type = "button";
    stop.onclick = async () => {
      try {
        if (!reason.value.trim()) throw new Error("Give a reason first.");
        const o = await post("/api/act/options", { action: "end_delegation", delegation: d.id, reason: reason.value.trim() });
        const done = await signAct(o, `End delegation ${d.id}`, [`reason: “${o.statement.reason}”`, "an end is final"]);
        if (done) { msg("Delegation ended.", "ok"); await showDelegation(d.id); }
      } catch (e) { msg(e.message, "err"); }
    };
    row.append(stop);
  }
  const retirable = rep.review.filter((i) => i.retirable).slice(0, 50);
  if (d.state !== "live" && retirable.length) {
    const retire = el("button", "danger", `Retire ${retirable.length}`); retire.type = "button";
    retire.onclick = async () => {
      try {
        if (!reason.value.trim()) throw new Error("Give a reason first.");
        const o = await post("/api/act/options", { action: "standing", reason: reason.value.trim(),
                                                   items: retirable.map((i) => ({ ref: i.ref, to: "retired" })) });
        const done = await signAct(o, `Retire ${o.statement.items.length} notes · reason: “${o.statement.reason}”`,
                                   o.statement.items.map((i) => `${i.to}: ${i.ref.slice(0, 40)}…`));
        if (done) { msg("Retired.", "ok"); await showDelegation(d.id); }
      } catch (e) { msg(e.message, "err"); }
    };
    row.append(retire);
  }
  const back = el("button", null, "Back"); back.type = "button";
  back.onclick = () => showDelegations().catch((e) => msg(e.message, "err"));
  row.append(back);
  head.append(row);
  const list = rep.review.map((i) => {
    const c = el("div", "card");
    c.append(el("div", "meta", `${i.kind} · ${i.standing} · approved ${i.approved_at}`));
    const pre = el("pre"); textWithMarks(pre, i.head); c.append(pre);
    return c;
  });
  $("cards").replaceChildren(head, el("h2", null, "Notes this delegation approved (newest first)"), ...list);
}

(function addDelegationsButton() {
  const b = el("button", "chip", "Delegations"); b.type = "button"; b.id = "nav-delegations";
  b.onclick = () => showDelegations().catch((e) => msg(e.message, "err"));
  $("progress").after(b);
})();
