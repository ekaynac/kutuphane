1. **Canon test (§§0, 2)**

**Role:** `evidence` supports claims; `rule` establishes requirements. No finding on that distinction. `proposal` has distinct presentation and ranking, but its question filter overlaps with `Standing=pending`. Put acceptance restrictions in Standing. Use Role to control how an accepted item supports an answer.

**Agent instruction:** `yes` adds an activation gate; `no` adds none. No finding on that distinction. But `yes` prohibits answer evidence, while `Role=evidence` requires that use. Define this combination as invalid, or specify which restriction takes priority. An automatic `yes` must never activate delivery.

**Time basis:** `durable`, `as_of(t)`, and `window(start,end)` have distinct time behavior: no finding. However, `window` and `Standing=retired` both restrict current use. Define time validity and owner acceptance separately, then require both for current authority.

**Standing:** `pending`, `approved`, and `retired` have distinct behavior: review use, accepted use, and history. No finding beyond the overlap with `proposal`.

**Scope:** `unbounded` and `bounded` differ by context filtering: no finding. Specify behavior when evidence or proposals have bounded scope but the request has no context.

**Sensitivity:** `restricted` changes routing and export. `normal` has no stated behavior. Define it as adding no sensitivity restriction; it must not override book policy.

**Egress:** `local_only` and `cloud_ok` differ by routing: no finding. Sensitivity also controls routing. Make effective egress a calculation from Egress and Sensitivity, with one enforcement rule.

**Recorded fields:** Origin values `human`, `agent`, `model`, and `external` do not each produce distinct behavior. All approvals already require humans in §3.1. Keep authorship as metadata; define approval rights separately. Presentation values `whole` and `chunked` differ: no finding. Protection and access values are not specified here, so this draft cannot support their value-by-value test.

2. **Transitions (§§1.2, 3, 5, 6)**

The transition plan is incomplete:

- Role, Scope, and Time basis lack change tables. Tables also omit initial gate values, removal of a value, parent changes, presets, and imported labels.
- §1.2 keeps every label when an anchor is unchanged. §3.1 removes approval when context changes. An unchanged paragraph under a changed heading satisfies both rules.
- “New or changed → pending” can reopen retired text automatically. Preserve retirement until a human reopens it.
- “Stricter” is undefined for different scopes, time windows, and mixed merge inputs. Do not choose one arbitrarily. Retain all applicable restrictions until review.
- A merge with conflicting labels becomes “open.” This must not remove a restriction. Missing and uncertain values need explicit behavior.
- Automatic supersession can retire a rule before its successor becomes valid. Partial scope overlap can also retire the predecessor outside the successor’s scope. Restrict replacement to the shared scope and effective time.
- Reject self-supersession and cycles such as A supersedes B, B supersedes A. Define restoration when a successor expires, changes, or loses approval.
- §3.1 permits owner approval only by humans; §6 permits future agent approval through `curate`. Select one policy now.

Parent defaults need a source reference and an effective-value rule. A child exception must not automatically remove a gate. A parent change must trigger review where it changes an approved child’s meaning.

Presets must use the same transition checks as individual edits. For example, applying `canon / decision` to approved evidence must not silently establish a rule. Omitted preset fields must preserve existing restrictions.

“Tighten automatically, loosen by a human” needs one exception stated precisely: a human can approve a scheduled change in advance. A window can then start automatically. Approval must cover its dates and scope.

Text changes can consistently remove approval, but they must also preserve retirement and restrictive gates. Effective label or context changes need the same approval check. No listed Standing state is impossible to leave; an inherited or open label lacks a defined confirmation path.

3. **Units and anchors (§§1.1–1.2, 5)**

The block rule does not guarantee one function per block:

- A review can quote a rule and then reject it. Heading defaults must not make the quotation an active rule.
- A table can contain requirements, test results, and exceptions in different cells. Permit stable cell or text-range annotations.
- A list group can mix commands and explanations. A code fence and its explanation can need different labels.
- A long table or code fence can exceed 4,000 characters without paragraph boundaries.
- A PDF page break can divide one requirement or table row.

Define how human split annotations survive source edits and profile changes. Otherwise, block construction is not reproducible.

The anchor also fails in concrete cases. A file move changes `path` and loses continuity. Reordering unchanged blocks preserves anchors but can change meaning. Inserting identical boilerplate changes occurrence numbers and can attach approval to the wrong copy. Normalization can hide meaningful text differences.

Use an immutable block reference within a source version. Record proposed links between versions separately. Confirm continuity when context is uncertain. Ground truth needs the source version, structural profile, and relevant context, not only the text hash. Citation ordinals also need a defined link to these references.

4. **Decisions and permissions (§4)**

A rule block, human enactment, and a drift view are insufficient.

Enactment needs an explicit subject, action, resource, scope, start, expiry, and delegation limit. The human must review this exact grant. Enactment must check the human’s grant rights and the block’s approval, validity, and scope. Repeated enactment must not create duplicate grants.

Store a structured link to the exact source version and approval events. A citation in free-text `purpose` is insufficient for reliable comparison.

Define what happens when the source permission is retired, narrowed, superseded, or loses approval. A drift warning alone leaves access active. Enforce expiry at authorization time. Decide beforehand which other changes suspend the linked grant and which require review. Grant revocation must remain possible independently of document edits.

5. **Recommendations for §7, points 1–6**

1. Keep the record preset. A separate Role adds no stated behavior. Require a supported date; a document date is not always the claim date.
2. Keep optional `review_by`. A warning supports review without inventing an expiry.
3. Keep document-level restriction. It gives one clear enforcement boundary. Measure mixed documents before adding finer gates.
4. Limit `curate` to content review. Keep policy changes and grant enactment under their existing rights, because these actions have different effects.
5. Add direct-grant expiry before temporary enactment. Check it on every authorization request.
6. Measure rule proposals on the blind slice before building the page. Include missed restrictions and false authority assignments, not only agreement and speed.

6. **Overcomplication and missing parts (§§0, 5, 8)**

Remove unused Origin categories from the behavior model. Keep their source facts as metadata. Keep presets as form actions and Sections as views: no finding.

The main missing part is one effective-value specification: explicit labels, parent defaults, retained restrictions, book policy, and approved schedules must produce one predictable result. Add a compact matrix of valid facet combinations and approval dependencies. This is necessary ontology work; more labels will not solve it.