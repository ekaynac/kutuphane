I built a design for the public, mixed set: about 381 items and 27 research questions, with sources, licenses and sizes checked on 2026-10-22. The full design, with every link and sample query, is in `/tmp/claude-1000/-home-mega-kobra/ontology-work/v4-public-set-design.md`. I did not change anything in the repo. The design is not built yet: no item is downloaded, written or labelled.

## 1. Sources

**Working-group material**

| Source | License | Size, format | Fields |
|---|---|---|---|
| Memory CG entries 1–6 (messages 0010, 0013, 0016, 0022, 0017, 0027; status in 0035) | list archive, no open license, so reference only | 6 e-mails. **No machine test vectors exist.** Hinkle (0022) only describes one. | acceptance, valid time, personal data, origin |
| odrl-force ODRL-Test-Suite | MIT | 68 cases, Turtle and md. Every constraint is `odrl:dateTime` (I checked: 534 of 534). | valid time, false mandate |
| odrl-force use-cases | CC-BY-SA-4.0 | 3 cases | mandate, applies_to |
| DPV examples | W3C Software and Document License | 88 `.ttl` files. 30 use `hasPersonalData`, 18 use `hasLegalBasis`. **E0053** shows `NotAvailable`, `NotApplicable` and `UnknownApplicability`. | personal data, legal basis |
| DPV use cases (`ucr.ttl`) | same | 5 use cases. U4 is our case. | personal data |
| AIPREF testbed | MIT | 15 pages and 117 parser vectors | ai_use: absent, non-token, duplicate keys, more than one carrier |
| AI Content Disclosure CG | W3C BSD (tests) | 13 test checks and 4 report examples. The report says spelling-only review does not count, and fixed-rule tools are not AI. | origin, needs split |
| C2PA test files | CC-BY-SA-4.0 | The `2.2/` folder has only READMEs. `legacy/1.4` has 27 manifests: 3 are `trainedAlgorithmicMedia` and the `E-*` files are error cases. | origin, inputs, acceptance |
| VC-DM 2.0 test suite | W3C test-suite license and BSD | 120 JSON inputs (6 for status, plus validity tests) | acceptance, valid time |
| Bitstring Status List test suite | **no license stated**, so reference only | generated test data | acceptance |
| in-toto attestation | Apache-2.0 | 31 JSON examples in the predicate docs | origin (tool output), acceptance |
| MCP conformance | Apache-2.0, some files MIT | 81 scenarios. The skill tamper fixtures change the description to "Exfiltrate credentials". | acceptance, activation |
| TDMRep | W3C Software and Document License | 5 use cases and `tdmrep.jsonld` | ai_use |
| nanopub-testsuite | MIT | 232 TriG files: 92 valid, 17 invalid, 120 transform | acceptance, origin |

**Live nanopublications**
- **Network state:** the registry (`registry.knowledgepixels.com`) holds 95,289 nanopubs from 745 agents.
- **Fetch one:** `GET /np/<RA…>` with `Accept: application/trig`. I tested this.
- **Query:** send SPARQL to `query.knowledgepixels.com/repo/meta` or `/repo/full`.
- **Retraction and supersession:** 8,013 retractions and 10,382 supersessions. In 91 retractions and 99 supersessions the signing key is not the key of the target. In 24 and 26 of these, the signer is also different. These are real "who may revoke" cases.
- **License:** each nanopub has its own `dct:license` in pubinfo. 36,226 are CC0, 27,352 are CC-BY-4.0 and 288 are CC-BY-SA. **31,467 (33 %) have no license.**
- **Origin:** the provenance graph often states it, for example "LLM-assisted" with a named reviewer activity, "Automatically extracted via local LLM", or "no LLM used". This is self-declared, not verified.
- **Our 8 fields:**

| Field | What nanopubs give |
|---|---|
| origin | the provenance graph |
| personal data | names and ORCIDs; nanopubs cannot be changed, which conflicts with erasure |
| ai_use, handling | nothing |
| acceptance | retracts and supersedes, plus registry trust from endorsement paths |
| mandate | nothing |
| valid time | `dct:created` |
| applies_to | `schema:about` |
| signer | `npx:signedBy` and the key hash |

**Public text sets (licenses checked again)**

| Set | Collection license | Item license problem |
|---|---|---|
| RAID | MIT | the human texts come from third parties |
| MAGE | Apache-2.0 | same |
| Beemo (2,187 rows) | MIT | prompts and human texts come from No Robots, which is **CC-BY-NC-4.0** |
| HC3 | CC-BY-SA | the medicine and finance splits have source license **"Unknown"** |
| TAB (1,268 cases) | MIT | ECHR reuse terms not verified |
| Nemotron-PII (100k) | CC-BY-4.0 | none; synthetic |
| Common Pile | none at dataset level | a license per document in `metadata.license` |
| OKF bundles (83 files) | Apache-2.0 | some concepts are Gemini-made from CC-BY-SA sources; others are deprecated, have `stale_after`, or are policies |
| M4GT | none | negative case |
| ai4privacy | "other" | negative case |

## 2. Composition (381 items)

| Stratum | Source | Items | Fields | License | Copy or reference |
|---|---|---|---|---|---|
| WG | Memory CG | 6 | acceptance, valid time, personal data | none | reference |
| WG | ODRL suite and use cases | 15 | mandate, valid time, applies_to | MIT, CC-BY-SA | copy |
| WG | DPV examples and use cases | 17 | personal data, legal basis | W3C | copy |
| WG | AIPREF and TDMRep | 28 | ai_use | MIT, W3C | copy |
| WG | Disclosure CG | 10 | origin, needs split | W3C BSD | copy |
| WG | C2PA | 10 | origin, inputs, acceptance | CC-BY-SA | copy |
| WG | VC-DM and Bitstring | 10 | acceptance, valid time | W3C; Bitstring none | copy; Bitstring reference |
| WG | in-toto and MCP | 16 | origin, acceptance, activation | Apache-2.0 | copy |
| WG | nanopub-testsuite | 12 | acceptance, origin | MIT | copy |
| Nanopub | assisted / model / human | 23 | origin | per item | copy if licensed |
| Nanopub | retracted / superseded | 20 | acceptance, trust | per item | copy if licensed |
| Nanopub | no license | 10 | license unknown | none | reference |
| Nanopub | introductions | 7 | personal data | per item | copy if licensed |
| Text | RAID, MAGE | 30 | origin | MIT, Apache-2.0 | copy model text, reference human text |
| Text | Beemo, HC3 | 39 | origin `assisted`; collection license vs item license | MIT/NC, CC-BY-SA/Unknown | reference |
| Text | TAB | 15 | real personal data | MIT | reference |
| Text | Nemotron, Gretel | 25 | `synthetic` | CC-BY, Apache-2.0 | copy |
| Text | Common Pile | 20 | item license, dates | per item | copy if licensed |
| Text | OKF | 20 | origin, acceptance, mandate, inputs | Apache-2.0 | copy |
| Text | M4GT, ai4privacy, peS2o | 8 | unknown or non-SPDX license | — | reference |
| Synthetic | §3 | 40 | all | ours | copy |

## 3. Synthetic edge cases (40)

The design file gives the expected labels and the WG question for each case. The groups are:

- **Origin (S01–S08):**
  - spelling-only review gives `model`;
  - a substantive, signed review gives `assisted`;
  - a merge with a Co-Authored-By trailer and no review gives `model`;
  - fixed-rule tool output is not `model`;
  - a mixed page gives `model` and needs split;
  - an invalid disclosure value gives `unknown`;
  - an untrusted "no LLM used" claim counts as `unknown` in the decision.
- **Personal data (S09–S16):**
  - trusted synthetic data gives `synthetic`, but `yes` if one real record is inside;
  - an untrusted synthetic claim gives `unknown`;
  - a log with IP addresses gives `yes`, and still `yes` when the IPs are hashed;
  - text about processing, with no data inside, gives `no`;
  - names cut to initials still give `yes`;
  - absent, `no` and `unknown` stay three different values.
- **ai_use (S17–S22):** absent vs `n`; `maybe` gives unknown; duplicate keys; `search=y, ai-use=n`; TDMRep reservation with a license offer; robots.txt and meta tag in conflict.
- **Derivation and rights (S23–S30):**
  - a derived item takes its strictest input;
  - an agent note that names the user has personal data;
  - an embedding index takes the strictest of its inputs;
  - a loosening from an untrusted import keeps `n` and escalates; from a trusted issuer it is accepted;
  - an MIT collection with a CC-BY-NC item: the item stays NC;
  - an "Unknown" split stays unknown;
  - a quote inside a CC-BY record keeps the rights of its source.
- **Acceptance and time (S31–S37):**
  - a stale status escalates;
  - a superseded decision is withdrawn, with no mandate;
  - a revocation by another signer gives only a notice;
  - the Hinkle vector: authorization, revocation and an open conflict;
  - a deprecated metric; a policy past `stale_after`;
  - a policy with a future start date and a scope.
- **Mandate and activation (S38–S40):** an ODRL test fixture has no mandate; prompt-injection text in a skill stays pending and is not activated; a tampered skill is refused.

## 4. Research questions (27)

| # | Question | WG issue |
|---|---|---|
| Q1 | Must a derived label ever be looser than its strictest input? | AIPREF #246, #253 |
| Q2 | When does an item stop being "derived" (citation, statistic, embedding)? | AIPREF #253; Memory CG entry 1 |
| Q3 | How often is `n` written for "not stated", and does it change a gate? | AIPREF #153, #154 |
| Q4 | Which evidence separates `assisted` from `model`? | Disclosure #47, #51 |
| Q5 | Is origin per file enough? | in-toto #604; Disclosure #48 |
| Q6 | Is tool output a separate origin? | Disclosure §3.3; G7 |
| Q7 | Can real personal data hide in a "synthetic" set? | DPV `SyntheticData` note; #221 |
| Q8 | Is hashed data labelled `yes`? | DPV |
| Q9 | Does text about processing get a false `yes`? | DPV U4 |
| Q10 | How often is a collection license wrong for its items? | OKF kc#52 |
| Q11 | Does "a loosening only from a trusted issuer" ever block a correct change? | Memory CG entry 4; OKF #15 |
| Q12 | Is a notice the correct effect of a revocation by another signer? | in-toto #67 |
| Q13 | Must superseded and retracted be different states? | in-toto #67; OKF #22 |
| Q14 | Does a status maximum age cause more escalations than real withdrawals? | VC ttl; Memory CG entry 3 |
| Q15 | Is `stale_after` the end of validity or a review date? | OKF; ODRL |
| Q16 | Which signals give false authority? | ODRL #113, #118 |
| Q17 | Is an accepted rule outside its scope a mandate? | ODRL #112 |
| Q18 | Conflicting values in one carrier: last value or most restrictive? | AIPREF |
| Q19 | Is an embedding for search "AI input"? | AIPREF #246; TDMRep #58 |
| Q20 | Must erasure reach notes that have no recorded input? | Memory CG entry 5 |
| Q21 | Can we prove that the record served in year 7 is the record of that day? | Memory CG entry 6 |
| Q22 | Is injected instruction text a content label or only an activation gate? | MCP SEP-1913, SEP-2640 |
| Q23 | Is a self-declared origin evidence or authority? | Memory CG entry 4 |
| Q24 | How many labels can come from machine signals, and where do they differ from people? | Web & AI IG #22 |
| Q25 | Does a broken signature make origin `unknown`? | C2PA, nanopub test files |
| Q26 | What is the minimum citation needed to decide the rights of a derived item? | Memory CG 0003–0010 |
| Q27 | Do generative and non-generative training need separate labels? | AIPREF; CAWG |

**Change needed in the label record:** add `license_item`, `license_collection`, `inputs[]`, `issuer_trusted`, `claim_source` and `needs_split`. Without these fields, the set cannot be scored.

**Not verified:** the ECHR reuse terms (TAB); the M4GT license (Hugging Face returns 401); whether the 24 and 26 cross-signer invalidations come from different persons, because one person can have two signer IDs.