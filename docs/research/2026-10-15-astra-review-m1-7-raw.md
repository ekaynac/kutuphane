Reviewed `aae9bc4..b627a83`. I used synthetic input for the parser checks. I did not change files, use the network or database, or read excluded paths.

**1. Security**

- **Access, egress policy, and pool logging: no finding.** Search checks `read` and, where required, `activate` before reranking. It logs citation handles for the full pool (`src/kutuphane/search.py:118–144`). The reranker only changes the order of these passages. All pool books pass through `_check_egress` before transmission (`src/kutuphane/llmdap.py:119`). Passage text is not added to the application log.

- **Medium — AT-10 claims exceed the network controls.** Core and ingress share `web` (`compose.yaml:55,66`). Thus Core can connect to `ingress:8080`, although AT-10 permits only Postgres and LLMDAP. The probe does not test ingress, yet reports “only allowed peers reachable” (`deploy/egress_probe.py:50–56`). **Fix:** block new connections from Core to ingress while permitting replies, or explicitly revise AT-10. Add ingress to the probe. This finding does not establish an Internet escape path.

- **Secrets, mounts, and model-stub exposure: no finding in the declared configuration.** LLMDAP mounts only its configuration directory and audit volume (`compose.yaml:78–80`). It does not mount `core.key` or receive Core’s environment. It does receive the bearer token during authentication. Secret paths are ignored by Git. LLMDAP and the stub have read-only root filesystems; the audit volume remains writable. Core and ingress do not have read-only root filesystems. The stub has no published port and joins only `models`. Actual secret contents and runtime controls were not checked.

**2. Correctness**

- **Medium — one threshold has two score meanings.** Reranking replaces positive RRF scores with arbitrary finite relevance scores (`src/kutuphane/retrieval.py:45`). `answers.py:70` still requires `score > 0`. Input: two useful passages receive scores `-0.1` and `-0.2`. Result: `not_in_library`, without an answer-model call. The LLMDAP contract permits negative scores. **Fix:** keep ranking scores separate from answer eligibility, or use a threshold calibrated for the configured reranker.

- **Medium — code fences lose their preceding paragraph.** `experiments/ontology/propose.py:94–103` checks for a previously flushed paragraph before it flushes the current paragraph. Input: `Explain.`, a blank line, then a fence. Result: separate paragraph and code blocks. §1.1 requires one combined block. **Fix:** take the immediately preceding paragraph from the buffer and attach it to the fence.

- **Medium — table processing drops content and misses long-table splits.** At `propose.py:111–115`, two unique numeric-style IDs trigger row output, but only matching rows survive. Input: rows `D1`, `D2`, and `appendix`. Result: the last row disappears. A 5,649-character ordinary table also remains whole because `_split_long` only splits at blank lines (`:138–147`). **Fix:** validate all data rows, preserve their content, and split long tables at row boundaries.

- **Medium — paragraphs without headings merge.** Input: `First.\n\nSecond.` produces one block (`propose.py:123–127`). §1.1 requires separate paragraph blocks for documents without headings. **Fix:** flush these paragraphs at blank lines.

- **Medium — parent heading words defeat child proposals.** Input: `# Decisions` followed by `## Proposal`. The combined heading path returns `decision` (`propose.py:170–176`). This defeats the child’s proposal signal. **Fix:** evaluate the nearest heading first, then inherit.

**3. Simplicity (D46)**

No finding. The shared retrieval function and `Routed` type keep the implementation small. The proposer remains local and prints counts only.