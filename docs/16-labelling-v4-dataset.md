# Labelling v4 — dataset and the origin of program output

**Status:** PLAN 0.2. §2 (the dataset) and the hostile fixtures were accepted on 2026-10-23 (D62). §1 is replaced by `docs/17-program-output-origin.md`.
**Basis:**
- `docs/12-labelling-v4-plan.md` (the 8 fields);
- `docs/research/2026-10-22-tool-origin.md`;
- `docs/research/2026-10-22-labelset-public.md` and `-labelset-public-design.md` (the WG and public sets, the 40 synthetic cases, the 27 questions);
- `docs/research/2026-10-22-labelset-agents.md` and `-labelset-agents-selection.csv` (150 agent documents).

**Language:** ASD-STE100 Simplified Technical English.

## 1. Origin of program output (operator question G7)

**Has anyone studied it?** Yes, but no group gives it a value with defined behaviors.
- The **W3C AI Content Disclosure CG** had this exact question as issue #9 ("deterministic programmatic content": sensor readings, database queries, template-rendered data). It closed the issue on 2026-09-21 with no new value. Its final report (2026-10-09) puts such content out of scope and discloses it as `human-only` when no generative AI was used.
- **IPTC Digital Source Type** has non-AI terms: `dataDrivenMedia` ("digital media representation of data via human programming"; the user guide example is a text weather report made by code from instrument readings), `algorithmicMedia`, `digitalCapture` and `screenCapture`. It has **no term for logs**, and the scheme is written for images.
- **C2PA 2.4** has `softwareAgent` (name, version) and `trainedAlgorithmicData` for data made by AI. It has no matching term for data that a program made without AI.
- **PROV-O** has `SoftwareAgent`, but it does not separate a model from a plain program.
- **DPV** has `ObservedData` and `DerivedData`. `GeneratedData` means data "not derived from other data", so it is the wrong term for typedoc output.
- **EU AI Act:**
  - Recital 12 and the Commission guidelines exclude systems that only run rules that people wrote, and basic data processing. So deterministic output has **no Art. 50 marking duty**.
  - The guidelines count logic- and knowledge-based inference as an AI technique.
- **OpenTelemetry and RFC 5424** record which system made a log (resource, `APP-NAME`, software version) and two times: the event time and the observation time.

**Proposal:** two new origin values. Each value gives a different behavior (D53).

| Value | Meaning | Required | Examples |
|---|---|---|---|
| `programmatic` | A program made the content from recorded inputs by fixed rules, with no AI technique (no trained model, no inference engine) | `inputs` (including the template and config) and `software_agent` (name, version) | typedoc, schemadoc, template briefs, a threshold-rule diagnosis |
| `observed` | A device or program recorded events or states of the world and changed nothing | `observed_at` and `software_agent` (the recorder) | logs, device captures, monitoring snapshots, sensor data |

**Behaviors:**

| | `programmatic` | `observed` |
|---|---|---|
| AI marking on export | none (Disclosure: `human-only`; IPTC `dataDrivenMedia`) | none (IPTC `digitalCapture` / `screenCapture`) |
| Authority | none of its own: it takes the acceptance and rights of its inputs; a withdrawn input withdraws it | primary evidence with a date; **never a mandate** |
| Change | an input change or a new generator version → `pending` until it is regenerated | it cannot change; an edited log is a new `programmatic` item |
| Erasure | erase the input, then regenerate | delete or redact; a redacted copy is `programmatic` |
| Personal data | the strictest value of its inputs | default `unknown` (= `yes`), because logs hold IP addresses and user IDs |
| Trust | can be accepted automatically under a delegation that names the generator and its version; a bad version suspends all its outputs | trust per instrument and per time window |
| Missing required field | counts as `unknown` | counts as `unknown` |

**Precedence rule:**
- If any input of a program is `model` or `unknown`, the output is `model`. For example, a typedoc page whose doc comments an LLM wrote is `model`.
- A template that an LLM fills in is `model`. It is `assisted` only after a substantive review by a named person.
- A formatter or a spell-checker keeps the origin of its input (IPTC `algorithmicallyEnhanced`, as an action).

**The inframedic chain as an example:** a metrics snapshot (`observed`) → a threshold-rule diagnosis (`programmatic`) → an LLM narrative (`model`). Only the narrative gets the AI mark.

**A related term set:** OpenClaw memory entries already carry an origin class: `owner`, `agent`, `untrusted`, `system`. kstd maps them as follows: `owner` → `human`, `agent` → `model`, `system` → `programmatic`/`observed`, `untrusted` → issuer not trusted.

**Contributions for later (on hold, D61):**
- IPTC/C2PA: a non-AI data source type and a log term;
- DPV: a usage note that `GeneratedData` does not cover program output made from inputs.

## 2. The dataset: four strata

The operator's direction:
- start with radar;
- make the set mixed, because our own projects are mostly Claude-made;
- the questions and datasets of the WGs are central;
- use synthetic data for the hard points;
- add public agent documents and the standard documents of popular repos.

| Stratum | Source | Items | What it tests |
|---|---|---|---|
| **R. Radar (initialize)** | `onprem-ai-adoption-radar` snapshot (public, MIT; commit pinned in `research/labelling-v4/sources/radar/.snapshot-sha`) | about 130 docs + 120 of the 2,533 Claude records + 20 Jev labels + 20 template briefs = **about 290** | all four origin kinds in one repo, including `programmatic` (briefs, digests); per-record origin (JSONL); third-party titles and URLs |
| **W. WG and public sets** | DPV examples, odrl-force, AIPREF testbed, Disclosure CG tests, C2PA, VC, in-toto, MCP, TDMRep, nanopub test suite and **live nanopubs** (95k on the registry: 8,013 retractions, 10,382 supersessions; **33 % have no license**), RAID/MAGE/Beemo/HC3/TAB/Nemotron/Common Pile/OKF | **341** | the WG edge cases in their own data; "who may revoke" (91 retractions signed by another key); collection license vs item license |
| **A. Agent documents** | anthropics/skills, agentskills, public AGENTS.md, Copilot, Cursor, awesome-claude-code entries, **OpenClaw + ClawHub, ponytail, rea**, SkillSpector and Skill-Inject hostile fixtures with clean twins | **150** | `activate` (is it an instruction? do the rights allow it? correct scope? hostile? does it run code?); ClawHub forces MIT-0 on every skill (a package license that replaces item licenses); ponytail has 5 byte-identical copies (copies are not independent evidence) |
| **S. Synthetic edge cases** | written by us, invented content | **40** | spelling-only review → `model`; a real record inside a "synthetic" set; a hashed IP is still `yes`; absent vs `n`; an untrusted loosening; an NC item in an MIT collection; a stale status; a superseded decision; injected text in a skill; program output with one model input |

**Total: about 820 items.** The proposer fills in most fields:
- origin comes from model fields, trailers, generator comments, front matter and nanopub provenance;
- license comes from each item;
- dates come from the files.

At about 20 s for each confirmation and 60 s for each correction, the work is **about 6–8 h, done in small batches while you use the library**. The radar owner's lesson: a big gold set made before use was "impossible to label".

**Rules for the set:**
- Copy content only where the item license allows. For other items, keep the source, the commit or blob SHA, the digest and our labels.
- **Never fetch live malicious skills.** Use the published fixtures, and our own replicas with harmless payloads.
- Do not collect third-party `USER.md` or `MEMORY.md` files; they can hold real personal data.
- The set lives in `research/labelling-v4/`, which git ignores, until each item's license is checked. Then a public version can be published as a contribution.

**The label record needs these new fields:**
- `license_item` and `license_collection`;
- `inputs[]`;
- `issuer_trusted`;
- `claim_source`, which records where a label came from: the item says it, a person decided, or the proposer suggested it;
- `needs_split`;
- with §1 accepted: `software_agent` and `observed_at`.

## 3. The deeper questions

The set must let us answer 27 research questions. Each question is tied to a WG issue; the list is in `docs/research/2026-10-22-labelset-public.md` §4. These are the most important:

1. Must a derived label ever be looser than its strictest input? (AIPREF #246/#253)
2. Which evidence separates `assisted` from `model`, and how often is a merge mistaken for a review? (Disclosure #47/#51)
3. How often is `n` written for "not stated", and does that change a gate? (AIPREF #153/#154)
4. Can real personal data hide in a "synthetic" set? Is hashed data still personal data? (DPV)
5. How often is a collection license wrong for its items? (OKF kc#52; ClawHub MIT-0; 33 % of nanopubs have no license)
6. Is a revocation by another signer only a notice? Must superseded and retracted be different states? (in-toto #67; nanopub data)
7. Is a self-declared origin evidence or authority? (Memory CG entry 4; nanopub "no LLM used" claims)
8. Is injected instruction text a content label, or only an activation gate? (MCP SEP-1913)
9. How many labels can come from machine signals, and where do the signals and people disagree? (Web & AI IG #22)
10. Is program output its own origin (§1), and does the precedence rule hold on real chains?

## 4. Order of work

1. **Now:**
   - the radar snapshot is fetched (pinned commit), and the commit history comes from the GitHub API for the trailers;
   - the ingest gaps G1, G3 and G5 are fixed (PR #51);
   - Astra code review #9 is running.
2. **Rule proposer (G6):** read model fields, trailers, generator comments, front matter, PDF metadata and nanopub provenance. Measure it on stratum R first.
3. **Labelling page v4:** the 8 fields + the new record fields; batches of 20; the raw bytes are shown (hidden text, zero-width characters); and `needs_split`.
4. **Batches:** R (radar), then S (synthetic, because it is small and sharp), then W, then A. After each batch, publish the labelled books into Kütüphane and ask the use-case questions.
5. **Local LLM proposer:** Qwen3.8 through LLMDAP (the `chat` route is ready). Compare it with the rule proposer for each field.

## 5. Decisions for the operator

1. **Program output:** replaced by `docs/17` (open).
2. **Dataset:** accepted on 2026-10-23 (D62).
3. **Agent hostile fixtures:** accepted on 2026-10-23 (D62).

## 6. Build state and the first proposer results (2026-10-23)

**Dataset:** 1,063 items in `research/labelling-v4/`, which git ignores. Each item is pinned to a commit or a dataset revision and has a sha256.

| Stratum | Items | Copied | Reference only | Hostile |
|---|---|---|---|---|
| R radar | 290 | 279 | 11 | 0 |
| W WG + public + nanopub | 333 | 221 | 112 | 1 |
| A agent documents | 396 | 303 | 93 | 22 |
| S synthetic | 44 | 44 | 0 | 2 |

- A is larger than 150, because each file of a skill folder is its own item. Rights apply to each file, and `activate` applies to the folder.
- RAID has 11 items, not 20, because the dataset API refused filtered queries. MAGE and Beemo cover the model side.

**Rule proposer v0** (`experiments/labeling_v4/propose.py`), scored against the facts that each source states:

| Stratum | Field | n | Agree | Wrong | Missing |
|---|---|---|---|---|---|
| R | origin | 169 | 160 | 4 | 5 |
| W | origin | 109 | 17 | 0 | 92 |
| W | personal_data | 43 | 0 | 13 | 30 |
| W | acceptance | 58 | 22 | 10 | 26 |
| S | origin | 16 | 6 | 1 | 9 |
| S | personal_data | 11 | 1 | 1 | 9 |
| S | acceptance | 7 | 2 | 1 | 4 |

**Hostile agent files → `activate: deny`:** the proposer caught 9, missed 15 and gave 9 false alarms.

**What this shows:**
1. **Origin is easy only when a record names its model** (radar news, Jev). From plain text, rules find almost nothing (W: 17 of 109). The model text in public sets carries no marker.
2. **Personal data in synthetic sets looks real** (W: 13 wrong). Text alone cannot tell `synthetic` from `yes`; only a trusted statement can (Q7).
3. **Pattern rules cannot find semantic injection.** They missed all of the SkillSpector semantic-injection and narrative-deception fixtures. They also flagged real install instructions (`curl … | sh` in home-assistant), security-audit agents and a guard tool. Q22 is answered for rules: `activate` needs a person or a model review, not a regex gate.
4. So the labelling page shows the evidence for each suggestion, and the person decides. The next proposer is Qwen3.8 through LLMDAP. It is compared with the rules for each field.
