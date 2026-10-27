# Required fields, conditional fields, custom tags, and a simpler labelling page

**Status:** 0.2, 2026-10-26.
- §2–§4 and §6 are revised after Astra's review (`docs/research/2026-10-26-astra-review-docs19-raw.md`).
- §5 follows the operator's answers (D65).
- The first simplification of the labelling page is live (PR #63).

**Trigger:** on 2026-10-26 the operator said:
- the labelling page is too complex;
- not every field should be required;
- documents differ;
- the standard can have a baseline of truly required fields;
- some fields must open or close by flags;
- he asked earlier for custom tags in Kütüphane.

**Language:** ASD-STE100 Simplified Technical English.

## 1. The problem

- The v4 page showed **22 inputs for every item**. Most did not apply: a news record has no mandate, a log has no reviewer, and a README is not an agent instruction.
- Some inputs were not item labels:
  - `issuer_trusted` belongs to the node's trust policy;
  - `export`/`route` are usually one value for the whole folder.
- **No study of required fields existed.** kstd L0 requires only the identity fields; every other field has a fail-closed default.
- **No study of custom tags existed.** Draft 0.2 removed "labels" from the core.

## 2. Principle: requirements belong to operations, not to items

Astra (point 1) showed that "required" is the wrong question for an item. A missing value still gives a correct decision: `deny` or `escalate`. So the question is: **which evidence must exist before an item can be used for a given operation?**

| Operation | Needed evidence | Without it |
|---|---|---|
| store and list (L0) | issuer, path, digest (machine-filled) | format error |
| search (index) | `ai_use.search = y` | not indexed |
| send to a model | `ai_use.ai_input = y`; handling allows the route | text withheld |
| derive / forward / train | item license, plus the rights of every recorded input | deny |
| forward with personal data | personal data ≠ yes/unknown, or a DPV legal basis | deny |
| ordinary use as knowledge | acceptance = accepted (for **every** item, not only policies) | evidence only |
| impose a requirement | accepted + mandate + applicability in scope | evidence only, `escalate` if needed |
| run as an instruction | an `activate` permission, given by an authorized person | read only |

**Origin may stay `unknown`.** It then counts as `model`. Nobody must guess it.

**A label is not an authorization (Astra point 5).** When a person confirms a label on the page, that does not accept the item, give a mandate or allow activation. Those need an authorized issuer. The page records *annotations*. The decision rule (docs/11 §4) uses the signed statements.

## 3. Folder defaults and conditional fields

### 3.1 Folder defaults are assertions

A folder default is an explicit claim **by the issuer that it covers the listed files**. It is not a guess from a collection license (Astra point 2; docs/11 §5: a package license does not replace an item license).

The page shows the inherited values and their source in one line, so a person can see an exception. It keeps `unknown` apart from `model`, and an absent `ai_use` term apart from `n`.

**Fixed (D74, draft 0.3):** `kstd-init` writes every `ai_use` term as **not stated**, so a new manifest starts fully fail-closed. In 0.2 it wrote `search: y`.

### 3.2 Conditions follow behavior, not genre (Astra points 3–4)

| Field | Shown when |
|---|---|
| `reviewed_by` | origin = `assisted` |
| `software_agent` (name + version) | origin = `tool` |
| observation time | a recording (`tool` with no transform). This is an explicit choice: an empty input list is not proof (docs/11). |
| `inputs` | the item is derived, whatever its origin |
| `activate` | the item is an agent instruction; a negative detection does not prove "not an instruction" |
| acceptance | always available; preset open for decisions and procedures |
| mandate | someone proposes requirement authority |
| validity, applicability | always available; preset open for decisions and procedures. An unknown scope never becomes a universal scope. |
| license, `ai_use`, personal data, handling | as an exception to the folder value |
| `needs_split` | always available |

**Dates are different facts (Astra point 7).** The statement issue time, the source publication date, the git commit date, the observation time and the validity window are five separate dates. Git can only *suggest* a source date.

## 4. No document kind (D66, 2026-10-26)

- **Removed.** The operator found the document-kind question confusing, and it is: D54 already removed the document categories K1–K8 as labels. A kind changes no decision (D53), so the labelling form must not ask it, and certainly not as a required field.
- **Replaced by one optional question,** "Kural / karar mı?" (does the document state a rule, decision or procedure that people or agents must follow?). It opens acceptance, mandate, validity and scope. These fields do change behavior: authority and applicability.
- An agent instruction opens activate and scope.
- "All fields" is always available. A field with a value stays visible when its condition stops holding.
- **The label form now has 3 required questions:** origin, agent instruction, personal data.

## 5. Custom tags (operator answers, D65)

| Question | Operator answer |
|---|---|
| Purpose | Search and organization; **some tags also control access** |
| Who adds them | people and agents; **an agent's tag waits for a person's approval** |
| Vocabulary | **a controlled list only** |

### 5.1 Model

- **One tag model, two representations (Astra point 9):**
  - tags in `kstd.yaml`, for portable declarations;
  - **tag annotations** in Kütüphane, for later changes.
- **A tag annotation records:**
  - the target: the exact item version or digest;
  - the tag concept;
  - the issuer and the time;
  - the action: add or remove;
  - the prior statement;
  - the state: proposed, confirmed, retracted or superseded.
- **Format:** it follows the W3C Web Annotation model (body = the tag concept, target = the item) and uses the kstd DSSE envelope when a signature is needed. A signature proves who made the annotation. It does not give authority.
- **Registry:** the library keeps a SKOS concept scheme. Each tag concept has:
  - a stable id;
  - an owner of its namespace;
  - Turkish and English labels;
  - aliases;
  - a deprecation date.

  A name alone is not identity across libraries.
- **Inheritance:**
  - folder tags are inherited, and an item can add or exclude a tag;
  - the provenance of each tag is visible;
  - **a derived item does not inherit tags automatically.**
- **Visibility:** search results, tag counts and suggestions respect item access. A tag never shows that a hidden item exists.
- **Mappings** (they lose signatures, approval state and policy meaning):
  - controlled concepts → `dcat:theme`;
  - strings → `dcat:keyword`;
  - schema.org `keywords` / `DefinedTerm`;
  - OKF `tags`, with the version pinned.

### 5.2 Access tags (operator: yes). The rules come before the code.

Astra (point 8) recommended discovery-only tags for version one. The operator wants some tags to control access. Then **an access tag is a governed facet**, the same as handling. The plan:

1. **Only registry concepts that are marked as access attributes can control access.** Each one has a defined meaning, for example `customer:acme` → "readable only by the members of team Acme".
2. **Who may change an access tag:**
   - only an issuer that is trusted for that namespace and scope (docs/11 §4 rule 4);
   - an agent can only *propose* it.
3. **Adding a restrictive tag is a tightening:** it applies at once.
4. **Removing a restrictive tag is a loosening:** it needs a trusted issuer and is audited.
5. **Moving an item from one customer to another is both** a tightening and a loosening. It needs the trusted path.
6. **A missing access tag** on a folder that requires one gives the most restrictive result (`deny` for the readers who would need it).
7. **Conflicts:**
   - two access tags of the same namespace on one item → the intersection of the readers;
   - a trusted conflict without a precedence rule → `escalate`.
8. **Registry changes:** a change of the meaning of a concept is a policy change, with a version and an audit. Old decisions keep their policy version (rule 7).
9. **Needed in Kütüphane:** access for each item (gap G10). Today, grants exist only for a whole book.

**Proposed order:**
1. discovery tags: registry, annotations, search filters, agent proposals with approval;
2. access tags, after rules 1–8 have conformance cases in `kstd/tests/decision/cases.yaml` and G10 exists.

## 6. The labelling page

**Live now (PR #63):**
- 4 required choices: kind, origin, instruction, personal data;
- the other fields open only by the conditions in §3.2;
- rights are inherited, with an exception button;
- "all fields" on request;
- Ctrl+Enter saves;
- a record stores only the shown fields.

**Production and measurement are kept apart (Astra point 12):**
- the server withholds the suggestions for a fixed **~30 % blind sample**, chosen by a hash of the item id;
- the record stores `blind`, `shown` and the accepted suggestions.

**Next:**
1. **Folder form:** confirm the folder defaults once.
2. **Field-level bulk actions,** with a preview of the affected items, kept exceptions, and undo. There is no "accept all" and no "same as previous" for reviewer, inputs or authorization (Astra point 13).
3. **Review contradictions and missing provenance first.**
4. **For the blind measurement:**
   - freeze the proposer versions;
   - compare them on the same items;
   - split the items by source family to avoid leakage;
   - report accuracy, abstention and dangerous errors separately.
5. Record the exposure and the proposal version for each field.

## 7. Questions still open for the operator (Astra point 14)

1. **First operation:** for which operation must the radar books be ready first: search, model answers or export?
2. **Folder-wide rights:** who may assert them and approve a loosening? Only you, or also a team lead?
3. **Tag visibility:** are tags shared by the team only, or exported with packages too?
4. **Tag level:** do tags attach to books, files or blocks? Must a tag follow an item to its new version?
5. **Error budget:** how many dangerous errors may the proposers make? How many items may the blind sample cost?
