# Labelling v4 (docs/16)

The tools of the labelling v4 dataset. The dataset itself is local only and git ignores it: `research/labelling-v4/` (`items/*.jsonl`, `files/`, `BUILD.md`).

| File | What it does |
|---|---|
| `propose.py` | The rule proposer (G6). It reads the bytes, the path, the declared item license, the git signals and the record fields. It suggests origin, personal data, license, `ai_use`, acceptance, dates, scope, instruction and activate, with the evidence for each suggestion. It never reads the expected answers of the synthetic stratum. `--eval` scores the suggestions against the facts that each source states. |
| `server.py`, `page.html` | The labelling page: batches of 20 in the order R → S → W → A. It shows the raw text, with hidden characters as `⟦U+…⟧`, and the suggestions. It appends to `labels.jsonl` and records which suggestions the person accepted unchanged (research question Q24). In the synthetic stratum the page hides the case notes, because they are the answers. |

```
python -I propose.py ../../research/labelling-v4 --eval
python -I server.py --data ../../research/labelling-v4 --host <tailnet-ip> --port 8791
# open http://<ip>:8791/?t=<research/labelling-v4/token>
```

The page uses plain HTTP only on loopback or the tailnet. The token is exchanged for an HttpOnly cookie. Fetched files are shown as text and never run.
