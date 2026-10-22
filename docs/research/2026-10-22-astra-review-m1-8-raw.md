Reviewed `c49a62d..369d427` on `main`. No files changed. No network, database, or excluded directories used. All 20 reference cases passed in memory; additional checks exposed failures.

1. **High — MCP bypasses `ai_input`.** [server.py:322](/home/mega/kobra/src/kutuphane/server.py:322)  
   A file with `search: y, ai_input: n` reaches a calling model through `search_library` or `open_citation`. `read_document` also returns its text without a kstd check, even when search is disabled. The internal answer filter does not protect these tool results. **Fix:** check `ai_input` before MCP delivers text. Keep human reading separate. Add tests for all three tools.

2. **High — Hosted shadow calls use obsolete labels.** [shadow_v2.py:82](/home/mega/kobra/experiments/labeling/shadow_v2.py:82)  
   Start a Jev run with a document labelled `normal + cloud_ok`. Change its label to `restricted + local_only` while earlier documents run. The runner still sends that document and its sections because `allowed` was calculated once. LLMDAP checks the purpose, not these labels. **Fix:** check the latest label before each outbound request; coordinate label changes and dispatch.

3. **Medium — Duplicate YAML keys replace restrictions.** [kstd.py:55](/home/mega/kobra/src/kutuphane/kstd.py:55)  
   Confirmed: `ai_input: n` followed by `ai_input: y` passes validation and permits model input. `personal_data: yes` followed by `personal_data: no` also passes; export then needs no legal basis. Alias rejection does not reject duplicate keys. **Fix:** reject duplicate mapping keys at every depth, including YAML merge overrides.

4. **High — Trust does not enforce the action boundary.** [decide.py:18](/home/mega/kobra/kstd/reference/decide.py:18), [decide.py:72](/home/mega/kobra/kstd/reference/decide.py:72)  
   All callers omit `action`. Confirmed: an external issuer trusted for handling only on `read` can set `cloud_ok` and permit cloud `infer`. Trust also accepts a missing expiry. This conflicts with §4 rule 4. **Fix:** pass the requested action and require explicit action coverage and expiry for external loosening statements.

5. **High — Pending, withdrawn, and held items can return `permit`.** [decide.py:87](/home/mega/kobra/kstd/reference/decide.py:87)  
   Remove acceptance from the first test case: the result is `permit`, authority `none`. A hold likewise changes authority without stopping ordinary use. The hold test explicitly expects this wrong result. Section 5 permits ordinary use only for accepted items. **Fix:** add an availability decision; reject ordinary use when acceptance is absent or suspended. Correct the hold case and add pending/withdrawn cases.

6. **Medium — A required rule outside its scope still gets `permit`.** [decide.py:112](/home/mega/kobra/kstd/reference/decide.py:112)  
   Confirmed: `want: rule` with an expired validity period returns `permit/evidence`. The wrong-plant case also expects `permit`. Section 5 requires `escalate` outside conditions or valid time when authority is required. **Fix:** add escalation in both branches and correct the expected cases.

7. **Medium — Permit version binding is incomplete.** [decide.py:151](/home/mega/kobra/kstd/reference/decide.py:151)  
   An unexpired prior permit with the same item ID passes after the policy version changes. Only item ID and expiry are compared. Section 4 rule 7 also binds artifact, statement, and policy versions. **Fix:** represent and compare all required versions. Add separate mismatch cases.

8. **Medium — Reopening an answer loses item information.** [server.py:94](/home/mega/kobra/src/kutuphane/server.py:94), [answers.py:129](/home/mega/kobra/src/kutuphane/answers.py:129)  
   A new HTTP answer shows origin, license, validity, and notices. Reopen it: the evidence contains only citation and text. CLI answers also omit the added information. This leaves D58 incomplete. **Fix:** attach item information in the shared answer functions. This also follows D46 and removes duplicated presentation work.

9. **Low — Validation accepts invalid license syntax and leaks parser errors.** [kstd.py:74](/home/mega/kobra/src/kutuphane/kstd.py:74), [kstd.py:56](/home/mega/kobra/src/kutuphane/kstd.py:56)  
   Confirmed: `(MIT` passes license validation. A roughly 3 KB nested YAML value raises uncaught `RecursionError`. Neither proves a content leak, but both break clean validation. **Fix:** validate expression grammar, bound nesting, and convert parser failures to `KstdError`.

No further finding in digest checks, normalized duplicate-path publication checks, passage embedding, rerank filtering, or internal answer filtering. Query embedding sends the supplied query; reopen and explain make no model call. Static compose review found Laya on the internal network and outbound access added only to LLMDAP. Runtime deployment was not tested.