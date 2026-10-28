"use strict";
// Curator web, D73 delegations (docs/25 §8), shown as "Auto-approval". Uses the helpers of core.js. The page shows the
// shadow agreement in plain words before a person signs a `delegate` act, the live agreement of each delegation, an
// `end_delegation` act, and the review list of an ended delegation with one batch Retire act.

const STATE_WORDS = { live: "Running", expired: "Ended: its time ran out", "ended:revoked": "Ended by a person",
                      "ended:disagreement": "Ended: a person said no to a check" };

function kindNotes(kind) { return `${kindName(kind).toLowerCase()} notes`; }
function pct(x) { return `${Math.round(x * 100)} %`; }
function stateBadge(state) { return el("span", `badge state-${state.split(":")[0]}`, STATE_WORDS[state] || state); }

async function getDelegationJSON(path) {
  const r = await fetch(path, { credentials: "same-origin" });
  if (r.status === 401) { signIn(); return null; }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

function agreementTable(rows, minShadow) {
  const t = el("table", "agreement");
  const head = el("tr");
  for (const h of ["Model at least", "Your decisions", "You agreed", "Share", "Lower bound (95 %)"]) head.append(el("th", null, h));
  t.append(head);
  for (const r of rows) {
    const tr = el("tr", r.n < minShadow ? "short" : null);
    for (const v of [pct(r.threshold), r.n, r.agreed, r.share === null ? "–" : pct(r.share),
                     r.wilson_lower === null ? "–" : pct(r.wilson_lower)]) tr.append(el("td", null, String(v)));
    t.append(tr);
  }
  return t;
}

function numberField(label, value, min, max, step, unit) {
  const wrap = el("label", "field");
  const input = el("input"); input.type = "number"; input.inputMode = "numeric";
  input.min = min; input.max = max; input.step = step; input.value = value;
  wrap.append(el("span", null, label), input);
  if (unit) wrap.append(el("span", "muted", unit));
  return [wrap, input];
}

function agreementWords(s, threshold) {
  const r = s.agreement.reduce((best, row) => (row.threshold <= threshold + 1e-6 ? row : best), s.agreement[0]);
  const base = `When the model was at least ${pct(r.threshold)} sure, you agreed with it on ${r.agreed} of ${r.n} notes.`;
  return r.n < s.min_shadow ? `${base} It needs at least ${s.min_shadow} of your decisions at this level first.` : base;
}

function shadowCard(s, data) {
  const c = el("article", "card");
  c.append(el("h3", null, `${s.decider} on ${kindNotes(s.kind)} in ${s.book}`));
  const words = el("p");
  c.append(words);
  const more = el("details", "details");
  more.append(el("summary", null, "Agreement at each level"), agreementTable(s.agreement, s.min_shadow),
              el("p", "muted", `Model spec ${s.spec_sha256.slice(0, 16)}…`));
  c.append(more);
  const [f1, threshold] = numberField("Approve only when the model is at least", Math.round(data.defaults.min_confidence * 100), 50, 100, 5, "% sure");
  const [f2, every] = numberField("You check 1 in", data.defaults.sample_every, 2, 100, 1, "of its approvals");
  const [f3, days] = numberField("For", data.defaults.days, 1, data.max_days, 1, `days (at most ${data.max_days})`);
  const preview = el("p", "plain");
  const update = () => {
    words.textContent = agreementWords(s, Number(threshold.value) / 100);
    preview.textContent = `A local model may approve ${kindNotes(s.kind)} in ${s.book} for ${days.value} days. ` +
                          `You check 1 in ${every.value}.`;
  };
  for (const i of [threshold, every, days]) i.oninput = update;
  update();
  const go = button("Allow auto-approval", "primary big", async () => {
    const o = await post("/api/act/options", { action: "delegate", book: s.book, kind: s.kind, decider: s.decider,
      spec_sha256: s.spec_sha256, min_confidence: Number(threshold.value) / 100, sample_every: Number(every.value),
      days: Number(days.value) });
    const d = o.statement.delegation;
    const n = Math.round((new Date(d.expires_at) - Date.now()) / 86400000);
    const r = await signSheet(o, "Check and sign",
      `A local model may approve ${kindNotes(d.kind)} in ${d.book} for ${n} days (until ${day(d.expires_at)}). ` +
      `You check 1 in ${d.sample_every}.`, [
        [`The model: ${d.decider}. It approves only when it is at least ${pct(d.min_confidence)} sure.`],
        [`You check 1 in ${d.sample_every} of its approvals, and always one after ${2 * d.sample_every} unchecked ones.`],
        ["If you say no to one check, auto-approval stops at once."],
        [`Signed as ${person(o.statement.principal)}`, "muted"]]);
    if (r) { msg("Auto-approval started.", "ok"); await showDelegations(); }
  });
  const form = el("div", "form"); form.append(f1, f2, f3, preview, go);
  c.append(form);
  return c;
}

function delegationCard(d) {
  const c = el("article", "card");
  c.append(stateBadge(d.state));
  c.append(el("h3", null, d.state === "live"
    ? `A local model may approve ${kindNotes(d.kind)} in ${d.book} until ${day(d.expires_at)}. You check 1 in ${d.sample_every}.`
    : `Auto-approval of ${kindNotes(d.kind)} in ${d.book}`));
  c.append(el("p", null, `${d.approved} approved by the model so far · ${d.samples} checks` +
                         (d.open_samples ? ` (${d.open_samples} waiting for you in To review)` : "")));
  c.append(el("p", "muted", `Model ${d.decider} · at least ${pct(d.min_confidence)} sure · started by ${person(d.created_by)}`));
  c.append(button("Details", null, () => showDelegation(d.id)));
  return c;
}

async function showDelegations() {
  const data = await getDelegationJSON("/api/delegations");
  if (!data) return;
  frame("auto");
  const live = data.delegations.filter((d) => d.state === "live"), ended = data.delegations.filter((d) => d.state !== "live");
  const cards = [el("h2", "section-title", "Running now"), ...live.map(delegationCard)];
  if (!live.length) cards.push(el("p", "muted", "No auto-approval is running. A person approves every note."));
  cards.push(el("h2", "section-title", "Start auto-approval"));
  cards.push(...data.shadow.map((s) => shadowCard(s, data)));
  if (!data.shadow.length) cards.push(el("p", "muted", "No local model has given advice on your notes yet."));
  if (ended.length) cards.push(el("h2", "section-title", "Ended"), ...ended.map(delegationCard));
  $("cards").replaceChildren(...cards);
}

async function showDelegation(id) {
  const rep = await getDelegationJSON(`/api/delegations/${encodeURIComponent(id)}`);
  if (!rep) return;
  const d = rep.delegation, live = rep.live_agreement;
  const head = el("article", "card");
  head.append(stateBadge(d.state), el("h3", null, `Auto-approval of ${kindNotes(d.kind)} in ${d.book}`));
  head.append(el("p", null, `Your checks: ${live.agreed} agreed, ${live.disagreed} said no, ${live.open} waiting` +
                            (live.closed ? `, ${live.closed} closed with no answer` : "") + "."));
  head.append(el("p", null, `It approved ${rep.coverage.approved} of the ${rep.coverage.class_notes} ${kindNotes(d.kind)} in ${d.book}.`));
  if (rep.end) head.append(el("p", "muted", `Ended ${day(rep.end.at)} by ${person(rep.end.ended_by)} (${rep.end.cause}).`));
  head.append(el("p", "muted", `Model ${d.decider} · until ${day(d.expires_at)} · id ${d.id}`));
  const reason = el("input"); reason.type = "text"; reason.placeholder = "Reason (required)"; reason.maxLength = 500;
  const row = el("div", "choices");
  if (d.state === "live") {
    row.append(button("End auto-approval", "reject", async () => {
      if (!reason.value.trim()) throw new Error("Give a reason first.");
      const o = await post("/api/act/options", { action: "end_delegation", delegation: d.id, reason: reason.value.trim() });
      const done = await signSheet(o, "Check and sign", `You end auto-approval of ${kindNotes(d.kind)} in ${d.book}.`,
        [[`Reason: “${o.statement.reason}”`], ["An end is final."], [`Signed as ${person(o.statement.principal)}`, "muted"]]);
      if (done) { msg("Auto-approval ended.", "ok"); await showDelegation(d.id); }
    }));
  }
  const retirable = rep.review.filter((i) => i.retirable).slice(0, 50);
  if (d.state !== "live" && retirable.length) {
    row.append(button(`Retire the ${retirable.length} it approved`, "reject", async () => {
      if (!reason.value.trim()) throw new Error("Give a reason first.");
      const o = await post("/api/act/options", { action: "standing", reason: reason.value.trim(),
                                                 items: retirable.map((i) => ({ ref: i.ref, to: "retired" })) });
      const heads = new Map(rep.review.map((i) => [i.ref, i]));
      const done = await signSheet(o, "Check and sign",
        `You retire ${o.statement.items.length} notes. Reason: “${o.statement.reason}”.`,
        [...o.statement.items.map((i) => [`Retire: ${heads.has(i.ref) ? kindName(heads.get(i.ref).kind) + " — " + firstLine(heads.get(i.ref).head) : i.ref}`]),
         [`Signed as ${person(o.statement.principal)}`, "muted"]]);
      if (done) { msg("Retired.", "ok"); await showDelegation(d.id); }
    }));
  }
  if (row.children.length) head.append(reason);
  row.append(button("Back", null, () => showDelegations()));
  head.append(row);
  const list = rep.review.map((i) => {
    const c = el("article", "card");
    c.append(textWithMarks(el("div", "text"), i.head));
    c.append(el("div", "kindline", `${kindName(i.kind)} · approved by the model ${day(i.approved_at)} · now ${i.standing}`));
    return c;
  });
  $("cards").replaceChildren(head, el("h2", "section-title", "Notes it approved (newest first)"), ...list);
  if (!list.length) $("cards").append(el("p", "muted", "It has not approved any note."));
  scrollTo(0, 0);
}
