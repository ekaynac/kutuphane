# Labelling v4 (docs/16)

The tools of the labelling v4 dataset. The dataset itself is local only and git ignores it: `research/labelling-v4/` (`items/*.jsonl`, `files/`, `BUILD.md`).

| File | What it does |
|---|---|
| `propose.py` | The rule proposer (G6). It reads the bytes, the path, the declared item license, the git signals and the record fields. It suggests origin, personal data, license, `ai_use`, acceptance, dates, scope, instruction and activate, with the evidence for each suggestion. It never reads the expected answers of the synthetic stratum. `--eval` scores the suggestions against the facts that each source states. |
| `llm_propose.py` | The local LLM proposer: Qwen3.8 through the LLMDAP `chat` route. Content stays on this machine. It suggests origin, personal data, instruction, hostile intent and acceptance, with evidence, to `proposals_llm.jsonl`. It can resume a run. `--eval` scores it. |
| `server.py`, `page.html` | The labelling page: batches of 20 in the order R → S → W → A. It shows the raw text, with hidden characters as `⟦U+…⟧`, and the rule and Qwen suggestions. It appends to `labels.jsonl`. The server checks each label against the fields that the page shows for the chosen kind, origin, instruction and form mode (a filled field stays visible as `kept` when its condition stops holding). It derives which suggestions the person accepted unchanged (research question Q24) and records the sha256 of both proposal files. About 30 % of each stratum is blind (no suggestions), chosen by family: the item's group, else its source and directory. In the synthetic stratum the page hides the case notes, because they are the answers. |

```
python -I propose.py ../../research/labelling-v4 --eval
python -I server.py --data ../../research/labelling-v4 --host <tailnet-ip> --port 8791
# open http://<ip>:8791/?t=<research/labelling-v4/token>
```

The page uses plain HTTP only on loopback or the tailnet. The token is exchanged for an HttpOnly cookie; the page also keeps it for the tab and sends it as `X-Label-Token`. `/` is a static shell; every `/api/` route needs the cookie or the header, and a label POST must be JSON from the server's own origin. Fetched files are shown as text and never run. Tests: `python -m pytest experiments/labeling_v4/test_server.py`.
