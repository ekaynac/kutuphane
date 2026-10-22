# Brief: W3C ODRL CG and the proposed Digital Policy WG (ODRL 3.0)

All sources were checked on 2026-10-22. Turtle was parsed with rdflib: case A has 54 triples and case B has 38. I posted nothing and I changed no repo files.

## 1. What the group wants

- **Charter.** The [draft charter](https://w3c.github.io/odrl/w3c-wg-draft-charter-2026/dpwg-draft-charter.html) runs from 2027-01-01 to 2028-12-31. The CG approved it on 2026-10-05 ([minutes](https://github.com/w3c/odrl/blob/master/meetings/2026/meeting-2026-10-05.md)). It is not in AC review yet: `w3.org/groups/wg/dp` returns 404.
  - Deliverables: Semantic Model (Q4 2027), Vocabulary and Registry (Q4 2027), Profile Declaration (Q1 2028), **Conformance Evaluation (Q2 2028)**, and Architecture and Protocols (Q3 2028).
  - Conformance "will test the behaviour of policy-processing software". The draft state is "No draft". The adopted input is the CG Formal Semantics.
  - Tentative profiles: DPV, AI/Data Governance, Data Spaces, Market Data, PLUS.
  - Out of scope: "Building or mandating specific enforcement infrastructure".
- **Where comments go.** The charter says: "Feel free to raise [issues](https://github.com/w3c/odrl/issues)". Charter issues get the label `W3C Charter` (see [#167](https://github.com/w3c/odrl/issues/167)).
  - **Deadline:** the TPAC breakout ["Proposed Digital Policy WG Charter"](https://www.w3.org/events/meetings/7cbcb701-7df3-4fbc-ada4-5321a51fb7ea/) is on **2026-10-28, 11:45–12:45 GMT**, in Dublin. Its goal: "Confirm the draft charter".
- **Workshop report** ([July 2026](https://www.w3.org/2026/ODRLWS/report.html)):
  - "given a policy and a defined state of the world, different implementations should be able to reach compatible conclusions";
  - "test cases with inputs and expected outputs";
  - multi-level conformance;
  - requirements must come from use cases.
- **[odrl-force/ODRL-Test-Suite](https://github.com/odrl-force/ODRL-Test-Suite)** (MIT, 68 cases).
  - A case is an `ex:TestCase` with `ex:policy`, `ex:request`, `ex:sotw` and `ex:expectedReport`.
  - Files go in `data/{policies,requests,sotw,test_cases,documentation}` and `data/index.ttl`.
  - The report ([FORCE model](https://github.com/odrl-force/ODRL-Compliance-Report-Model)) gives `activationState` Active/Inactive for each rule and `satisfactionState` Satisfied/Unsatisfied for each premise.
  - `report:Unknown` exists only for the performance state of duties.
  - **There is no result at request level.** All constraints in the suite use `odrl:dateTime`.
- **[#112](https://github.com/w3c/odrl/issues/112)** (agent delegation): assigner → agent, with a `dateTime lt` expiry and a count. The expiry is optional.
- **[#113](https://github.com/w3c/odrl/issues/113)** (AuthZEN call and response): the response has `"decision": false|true`. If "a variable in the state of the world hasn't been set", the response only sends a message to the client. Its parent issue is #118, which is open. [AuthZEN 1.0](https://openid.net/specs/authorization-api-1_0.html) also uses a boolean `decision` and an optional `context`.
- **Gap in ODRL 2.2.** §3.2 says that an unknown profile means the processor "MUST stop processing". No result is defined. The Formal Semantics draft has no "unknown" case: I searched for unknown, undefined, missing and indeterminate, and found nothing.

## 2. What we bring

- `docs/11-standard-draft.md` §4: the decision rule. It gives `deny` > `escalate` > `permit`. Unknown rights mean deny. Unknown applicability means escalate. It has "same result and same reason".
- §7 of the same file: conformance levels L0–L3.
- `kstd/tests/decision/cases.yaml`: 33 cases. `kstd/reference/decide.py`: the reference rule.
- `docs/13-landscape.md` §3.2(7): the fail-closed difference from ODRL and EDC.
- Kütüphane implements only L0 (`src/kutuphane/kstd.py`). It has no ODRL processor and no `escalate`.

## 3. Comparison

| Their requirement | Our element | Fit | Note |
|---|---|---|---|
| Deterministic evaluation (workshop) | §4: same result and reason | match | — |
| Test cases with inputs and expected output | `cases.yaml`, `decide.py` | partial | Ours are YAML; theirs are Turtle |
| policy + request + SotW → report | policy + trust + statements + request + `now` → result/authority/reasons/notices | partial | `authority` and `notices` have no slot in the report |
| Active/Inactive for each rule | permit/deny/escalate for each request | we differ | No result at request level |
| Unknown profile: "MUST stop processing" | Rule 3: unknown required term → deny | partial | They stop; we return a result |
| Multi-level conformance | L0–L3 | match | — |
| Delegation with expiry (#112) | Rule 4: trust per kind × scope × action, expiry mandatory | partial | We make the expiry mandatory |
| Boolean decision (#113, AuthZEN) | result + reasons | we differ | A boolean has no third value |
| An ODRL processor that passes the tests | — | we lack | Kütüphane is L0 only |

## 4. Reason

- **For them:** they need use cases with testable requirements, and their report model has no result at request level. Our cases have a fixed expected result and reason, so they fit their conformance method directly. Also, `report:Unknown` already exists for duties. The same idea can apply to premises.
- **For us:** kstd becomes a profile (D60). If the third result and fail-closed behavior become part of ODRL 3.0, we can cite ODRL for kstd rules 1–3, and we do not need to own them.

## 5. Consequences

**IPR and licensing**
- **W3C CLA** (issues and the list of the ODRL CG and the Agent Conformance CG):
  - a "worldwide, non-exclusive, no-charge, royalty-free, copyright license" on each contribution;
  - royalty-free licensing of Essential Claims in the CG Specification, "for the life of the patents";
  - a written withdrawal is possible within 45 days.
- **odrl-force PR:** MIT, under the GitHub inbound = outbound terms [INFERENCE]. MIT has no patent grant. We own the cases, so we can also give them under MIT.
- **WG (2027 and later):** the W3C Patent Policy applies. A non-participant can contribute "provided they agree to the terms of the W3C Patent Policy". To take part, you must work for a W3C Member or be an Invited Expert. Company Membership: not verified.

**Effect on kstd**
- **If they accept:** rename `escalate` in the crosswalk to their term. Align the reason codes with their registry. Add an ODRL Turtle export of `cases.yaml`. Section 4 of docs/11 then cites ODRL 3.0 Conformance.
- **If they reject:** rules 1–3 stay as kstd profile semantics, and we publish a crosswalk:
  - escalate ↔ `Inactive` + a profile result;
  - escalate ↔ AuthZEN `decision:false` + `context`;
  - escalate ↔ XACML `Indeterminate`.
- Kütüphane does not change in either case.

**Effort**
- Charter issue: about 2 h. Breakout: 1 h. CG call: 1 h per month.
- Converting the two cases and running them on ODRL-Evaluator (tested with Node 18): 1–2 days.
- In the WG: a 1-hour call every two weeks. A Test Lead role takes half a day per week.

**Risks**
- The CG already approved the charter, so a change in scope late in the process can get resistance.
- They can read `escalate` as enforcement, which is out of scope. Our answer: it is an evaluation result, not enforcement.
- Case A needs a way to put the request context into the SotW, and #118 does not define one yet.
- The `prop:` terms are ours. Expect the group to choose different names.
- The repo must be public before you link to it.
- Agent Conformance CG: at launch it had no chair. Its activity now: not verified.

## 6. Steps for the operator

1. Sign in to the W3C account and join the ODRL CG. Make sure that the account shows the company affiliation, so the company CLA applies (not verified how).
2. **Before 2026-10-26:** open the charter issue on `w3c/odrl` (draft A). Ask the chairs to add the `W3C Charter` label.
3. **On 2026-10-28:** attend the breakout, or ask Víctor Rodríguez-Doncel (chair, present at TPAC) to mention the issue. Remote access needs a W3C login. Whether it also needs TPAC registration: not verified.
4. Send an email to `public-odrl@w3.org` and ask for an agenda item at the CG call on **2026-11-02, 12:00 UTC**.
5. Make kstd public. Then open an issue on odrl-force: ask if they accept non-`dateTime` constraints and a result at request level. After that, send the PR (draft B).
6. Comment on #113 (the third value in the response) and on #112 (expiry is mandatory). Link the cases.
7. Agent Conformance CG: join, and send one list post that offers `cases.yaml` as a versioned fixture set. Their scope asks for "runnable conformance suites with adversarial reference fixtures", and results must name the engine, the corpus version and the date. Low priority.
8. **Follow-up:** watch for the AC review. The WG starts on 2027-01-01, and the conformance spec is due in Q2 2028.

## 7. Draft text

**A. Charter issue, `w3c/odrl`**

> **Title:** Charter: Conformance Evaluation should define the evaluation result, a not-determined result, and fail-closed behaviour
>
> The draft says Conformance Evaluation "will test the behaviour of policy-processing software". The workshop asks for "test cases with inputs and expected outputs". Today the Formal Semantics and the FORCE report give Active/Inactive per rule and Satisfied/Unsatisfied per premise, but no result per evaluation request. So two evaluators can agree on every premise and still answer the request differently.
>
> We propose that the charter scope names:
> 1. **A result set per evaluation request:** permitted, not permitted, and **not determined** (as XACML `Indeterminate`). Not determined means that a person or another process must decide.
> 2. **Fail closed:** when a premise cannot be evaluated (no value in the state of the world, an unknown action, operand or profile), the result is never "permitted". ODRL 2.2 §3.2 says "MUST stop processing"; conformance should define what the processor then returns.
> 3. **Reason codes** with each result, so tests compare result and reason.
>
> Text to add after "Define a new conformance model…": *"including a defined result set for evaluation requests with a not-determined result, fail-closed behaviour for premises that cannot be evaluated, and reason codes."*
>
> Related: #113 (boolean `decision`), #118, #112. We offer test cases in the odrl-force format (below).

**B. Two cases in the odrl-force format** (the `prop:` terms are proposals)

Case A comes from "a rule request outside the conditions escalates". Expected kstd result: `escalate`, `[outside-conditions]`.

```turtle
@prefix odrl: <http://www.w3.org/ns/odrl/2/>. @prefix ex: <http://example.org/>.
@prefix temp: <http://example.com/request/>. @prefix dct: <http://purl.org/dc/terms/>.
@prefix xsd: <http://www.w3.org/2001/XMLSchema#>. @prefix report: <https://w3id.org/force/compliance-report#>.
@prefix prop: <https://example.org/kstd-proposal#>.
ex:policyA a odrl:Set; odrl:uid ex:policyA; odrl:permission ex:permA.
ex:permA a odrl:Permission; odrl:assignee ex:alice; odrl:action prop:applyAsRule;
    odrl:target ex:procedureP; odrl:constraint ex:cA.
ex:cA odrl:leftOperand odrl:spatial; odrl:operator odrl:eq; odrl:rightOperand ex:site3.
ex:requestA a odrl:Request; odrl:uid ex:requestA; odrl:permission ex:reqA.
ex:reqA a odrl:Permission; odrl:assignee ex:alice; odrl:action prop:applyAsRule; odrl:target ex:procedureP.
ex:sotwA a ex:Sotw; ex:includes temp:currentTime, temp:currentLocation.
temp:currentTime dct:issued "2026-11-01T00:00:00Z"^^xsd:dateTime.
temp:currentLocation dct:spatial ex:site7.   # context encoding: our assumption (#118)
ex:tcA a ex:TestCase; dct:title "Rule request outside the declared conditions escalates.";
    ex:policy ex:policyA; ex:request ex:requestA; ex:sotw ex:sotwA; ex:expectedReport ex:repA.
ex:repA a report:PolicyReport; report:policy ex:policyA; report:policyRequest ex:requestA;
    report:ruleReport ex:rrA; prop:result prop:Escalate; prop:reason "outside-conditions".
ex:rrA a report:PermissionReport; report:attemptState report:Attempted; report:rule ex:permA;
    report:ruleRequest ex:reqA; report:activationState report:Inactive;
    report:premiseReport ex:pA1, ex:pA2, ex:pA3, ex:pA4.
ex:pA1 a report:ConstraintReport; report:constraint ex:cA; report:constraintLeftOperand ex:site7;
    report:satisfactionState report:Unsatisfied.
ex:pA2 a report:TargetReport; report:satisfactionState report:Satisfied.
ex:pA3 a report:PartyReport; report:satisfactionState report:Satisfied.
ex:pA4 a report:ActionReport; report:satisfactionState report:Satisfied.
```

Case B comes from "trust without an expiry is not trust". The kstd case reads the item later and gets `deny`, `[not-accepted:pending]`. This test checks the delegation step that causes that result.

```turtle
# same prefixes as case A
ex:policyB a odrl:Set; odrl:uid ex:policyB; odrl:profile prop:delegationProfile; odrl:permission ex:permB.
ex:permB a odrl:Permission; odrl:assigner ex:nodeA; odrl:assignee ex:nodeB;
    odrl:action prop:accept; odrl:target ex:bookOps.          # no dateTime constraint
ex:requestB a odrl:Request; odrl:uid ex:requestB; odrl:permission ex:reqB.
ex:reqB a odrl:Permission; odrl:assignee ex:nodeB; odrl:action prop:accept; odrl:target ex:itemI.
ex:sotwB a ex:Sotw; ex:includes temp:currentTime, ex:itemI.
temp:currentTime dct:issued "2026-11-01T00:00:00Z"^^xsd:dateTime.
ex:itemI odrl:partOf ex:bookOps.
ex:tcB a ex:TestCase; dct:title "Delegation without an expiry is not delegation.";
    ex:policy ex:policyB; ex:request ex:requestB; ex:sotw ex:sotwB; ex:expectedReport ex:repB.
ex:repB a report:PolicyReport; report:policy ex:policyB; report:policyRequest ex:requestB;
    report:ruleReport ex:rrB; prop:result prop:Deny; prop:reason "delegation-without-expiry".
ex:rrB a report:PermissionReport; report:attemptState report:Attempted; report:rule ex:permB;
    report:ruleRequest ex:reqB; report:activationState report:Inactive.
```

Notes for case B:
- Plain ODRL 2.2 gives `Active` here. Only the profile rule changes the result to Deny.
- An evaluator that does not know the profile must stop (§3.2). The expected output is still Deny, not Permit.
- Matching positive case: add `ex:permB odrl:constraint [odrl:leftOperand odrl:dateTime; odrl:operator odrl:lt; odrl:rightOperand "2027-06-01T00:00:00Z"^^xsd:dateTime]`. The expected result is then `Active` and permit.

Before you submit, change the `ex:` names to `urn:uuid:` and add the `index.ttl` entries.

**Not verified:** how the company affiliation is set on the W3C account; whether the breakout needs TPAC registration; company W3C Membership; whether the Agent Conformance CG is active now.