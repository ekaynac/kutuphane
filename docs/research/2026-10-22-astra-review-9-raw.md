1. **High — JSON credentials bypass scanning.** [src/kutuphane/secretscan.py:29](/home/mega/kobra/src/kutuphane/secretscan.py:29)  
   Assignment patterns require the separator immediately after the key, so quoted JSON keys never match. `config.json` containing `{"password": "A9b8C7d6E5f4G3h2"}` passes ingestion and becomes searchable. This also passes inside the unrestricted `.codex/` folder. **Fix:** scan parsed JSON/JSONL key-value pairs, including escaped keys and values, and support quoted keys in fallback scanning.

2. **High — Strong passwords in source-code literals are missed.** [src/kutuphane/secretscan.py:34](/home/mega/kobra/src/kutuphane/secretscan.py:34)  
   `password = "aB3!very.secret-password"` in `config.py` passes. Code files use only `_ALWAYS`, whose quoted-value pattern excludes punctuation such as `!` and `.`. These characters distinguish neither expressions nor secrets when already inside a string literal. **Fix:** extract quoted literals independently of their character set, then assess credential assignments.

3. **High — HTML extraction can introduce secrets after scanning.** [src/kutuphane/source.py:152](/home/mega/kobra/src/kutuphane/source.py:152)  
   `<p>api_key: &#115;k-proj-abcdefghijklmnopqrstuvwx</p>` passes the raw-text scan. HTML extraction subsequently decodes it into a recognizable API key and indexes it. **Fix:** scan both original text and the exact extracted representation before creating chunks.

4. **High — Input restrictions disappear after a second derivation.** [kstd/reference/decide.py:144](/home/mega/kobra/kstd/reference/decide.py:144)  
   For `A → B → C`, with `A.ai_use.ai_input=n` and B/C declaring `y`, inference on C returns `permit`: only C and B are checked. Unknown licenses and training restrictions can likewise be hidden behind an intermediate item. **Fix:** traverse the complete recorded input graph with cycle detection and fail closed on missing ancestors.

5. **High — Input personal-data and handling restrictions are not enforced.** [kstd/reference/decide.py:148](/home/mega/kobra/kstd/reference/decide.py:148)  
   Input checks cover licenses and AI-use flags only. A derivative declaring `personal_data=no` and export `normal` can be forwarded without a legal basis even when its input declares `synthetic` through an untrusted issuer. Restricted/local-only input handling is also ignored. **Fix:** evaluate applicable personal-data requirements and synthetic trust per input, and inherit the strictest handling throughout the lineage.

6. **High — Erasure misses descendants when the source statement is absent.** [kstd/reference/erase.py:17](/home/mega/kobra/kstd/reference/erase.py:17)  
   If local item B records `inputs: [A]`, but A is remote or already removed, erasing A returns B as kept and reports no uncertainty. Intersecting the requested IDs with local items removes A before traversal. **Fix:** seed traversal with every requested ID; intersect with local items only when reporting local deletions, while retaining external-delivery obligations.

7. **Medium — Ordinary configuration values block an entire repository.** [src/kutuphane/secretscan.py:30](/home/mega/kobra/src/kutuphane/secretscan.py:30)  
   `token: refresh_token` produces a credential finding despite being a commonplace protocol identifier. The whole book is rejected, with no reviewed exception mechanism. **Fix:** distinguish semantic constants from credential values and provide narrowly scoped, auditable exceptions for verified fixtures and documentation.

8. **Medium — Empty input lists suppress erasure uncertainty.** [kstd/reference/erase.py:26](/home/mega/kobra/kstd/reference/erase.py:26)  
   A model-origin item with `inputs: []` is omitted from `scope_unknown`; the same item with the field absent is included. Adding an empty list therefore makes missing provenance appear resolved. **Fix:** treat absent and empty lineage alike unless an explicit, validated provenance assertion establishes that no inputs exist.

9. **Medium — Valid JSONL records split at Unicode characters inside strings.** [src/kutuphane/profiles.py:147](/home/mega/kobra/src/kutuphane/profiles.py:147)  
   A JSON string containing literal U+2028 is valid, but `splitlines()` treats it as a record boundary. A short record becomes two incomplete passages carrying the same citation line, separating its content from its provenance fields. **Fix:** split JSONL on physical newline delimiters only and use the same delimiter definition for citation numbering.

10. **Medium — Negative Content-Length bypasses the model server’s body limit.** [deploy/models/server.py:151](/home/mega/kobra/deploy/models/server.py:151)  
    A client able to reach the internal model endpoint can send `Content-Length: -1`. The upper-bound check accepts it, and `read(-1)` reads until EOF without the 8 MiB limit. With no socket timeout and unbounded request threads, clients can retain threads or exhaust memory. **Fix:** require one valid nonnegative bounded length, reject unsupported transfer framing, and bound read time and concurrent requests.