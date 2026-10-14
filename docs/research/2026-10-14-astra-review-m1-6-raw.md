Reviewed `34d0465..8e67aba`. No files changed. No network, database, or excluded data access. Checks used synthetic data in memory.

**1. Security**

- **High — Redirect can expose the key.** [deploy/llmdap_contract.py:54](/home/mega/kobra/deploy/llmdap_contract.py:54) uses the default HTTP opener. A 302 redirect to another host carries the `Authorization` header from line 93. An offline check confirmed this behavior. **Fix:** Refuse redirects, as the main LLMDAP client does.

- **Secret input and command execution: no finding.** The key comes from the environment and is not printed or added to command arguments. At line 83, `shlex.split()` produces arguments; `subprocess.run()` does not start a shell. Shell operators and variable references are not expanded. The operator-selected export process inherits the environment, including the key. That process must be trusted.

- **Blind draft before the first document label: no finding.** [server.py:95](/home/mega/kobra/experiments/labeling/server.py:95) requires a saved document label without `skip`. A skip or QA label does not qualify. Line 250 saves the label before line 251 returns the draft. A concurrent `/api/items` request cannot unlock it before a qualifying record exists. However, the unlocked reader can encounter a partial record during a write and fail; this does not expose the draft.

- **XSS: no finding.** Document text, draft reasons, and guide text use `textContent` or text-node insertion. There is no `innerHTML` use.

- **Cookies and tokens: no finding within the stated deployment.** Tokens have private file permissions and constant-time comparison. Cookies use `HttpOnly` and `SameSite=Strict`. Responses prevent caching and referrer disclosure. Logs omit query tokens. The cookie lacks `Secure`, consistent with the documented HTTP service on loopback or the encrypted tailnet.

**2. Correctness**

- **Medium — Failed audit verification can pass.** [deploy/llmdap_contract.py:83](/home/mega/kobra/deploy/llmdap_contract.py:83): export prints matching JSONL, then exits nonzero after a verification error → the script ignores that failure and can report success. **Fix:** Require a zero exit status before using stdout.

- **Medium — Shared-secret test uses a dummy value.** [deploy/llmdap_contract.py:95](/home/mega/kobra/deploy/llmdap_contract.py:95): gateway wrongly accepts its real shared secret but rejects `"s" * 40` → the test passes. **Fix:** Test the configured shared secret through a separate environment variable.

- **Medium — Repeat blind labels have false exposure data.** [server.py:150](/home/mega/kobra/experiments/labeling/server.py:150): save a blind label, view its draft, then change and save the label → `shown_draft` remains false. `latest()` returns this replacement record. **Fix:** Preserve the first blind answer for measurement and record draft exposure on later answers.

**3. Simplicity (D46)**

- **Low — Repeated draft reads.** [server.py:104](/home/mega/kobra/experiments/labeling/server.py:104) calls `shown()` for each document; each call reads all draft files again. **Fix:** Pass the draft already read at line 94 to the visibility helper. No cache or new service is needed.