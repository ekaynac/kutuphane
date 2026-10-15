Round 2 of the Kütüphane ontology brainstorm. You are a co-author. Your round-1 proposal was merged with two others into `docs/09-ontology-v2.md` in /home/mega/kobra. Read that file first; it is the subject. Repository is read-only. Do not change files. Do not use the network or database. Do NOT read `experiments/labeling/data/`.

Operator canon:
- "Knowledge facets must have meaningful behavioral distinctions."
- "Facet state changes should be planned carefully beforehand."
- "The ontology is the core; implementation stays simple."

Critique the draft as a co-author. Write in ASD-STE100 Simplified Technical English, at most ~1200 words:

1. **Canon test.** For each facet and each value:
   - Does the value change a real system behavior that differs from every other value?
   - Name any value that fails, and any behavior that two facets both claim (non-orthogonal).
2. **Transitions.**
   - Find missing transitions, two automatic rules that conflict, loops, and states that nobody can leave.
   - Are "tighten automatically, loosen by a human" and "approved → pending on text change" consistent in every case? Check also: inheritance, parent defaults, and preset application.
3. **Units and anchors.** Find failure cases of the block rule and of the anchor `(book, path, block_hash, occurrence)`. Examples: a moved file, reordered blocks, duplicated boilerplate, a quoted rule inside a review, a table that holds both rules and evidence.
4. **Decisions and permissions.** Is "a rule block + human enactment + a drift view" enough? What is missing?
5. **Open points 1–6 in §7.** Give your recommendation for each, with one reason.
6. **Overcomplication.** What can be removed while the canon still holds? What important thing is missing?

Be concrete, cite section numbers of the draft, and do not repeat praise. If a part is correct, say "no finding".
