# NVIDIA SkillSpector v2.13.1: dependency evaluation for Kütüphane

Date: 2026-10-27. No change to the kobra repo. The trial venv is deleted.

## 1. Facts

- **Purpose:** [SkillSpector](https://github.com/NVIDIA/SkillSpector) is a static security scanner for agent skills (SKILL.md folders, MCP manifests). It has 71 patterns in 17 categories (prompt injection, exfiltration, supply chain, dangerous code). It gives a 0–100 score and `SAFE` / `CAUTION` / `DO_NOT_INSTALL`. It does not run the skill.
- **Packaging:** It is not on PyPI ([404](https://pypi.org/project/skillspector/); see also the [conda-forge recipe](https://github.com/conda-forge/skillspector-feedstock)). Sources: GitHub tags, `uv tool install git+…`, conda-forge, a Dockerfile. Interfaces: the CLI (terminal, JSON, Markdown, SARIF 2.1.0), an MCP server (`[mcp]` extra), and `skillspector.graph.invoke()`. The README calls only the exit code and the JSON output "a stable contract".
- **Licence:** Apache-2.0, the same as ours. It has no NOTICE file. The YARA rules have NVIDIA Apache-2.0 headers (I checked `agent_skills.yar`). The 66 runtime packages use MIT, BSD, Apache-2.0, ISC or PSF; `certifi` and `orjson` use MPL-2.0. [`THIRD_PARTY_NOTICES.md`](https://github.com/NVIDIA/SkillSpector/blob/v2.13.1/THIRD_PARTY_NOTICES.md) lists only some direct dependencies.
- **Runtime:** No GPU, CUDA or NIM. The LLM stage is **on by default**, with the cloud provider `nv_build`. Ollama and local OpenAI-compatible servers are supported. `--no-llm` keeps file contents local. The SC4 check [sends dependency names to api.osv.dev](https://github.com/NVIDIA/SkillSpector#trust-model-and-data-egress), also with `--no-llm`. There is no switch to stop it. Offline, it uses a bundled list.
- **Versions:** The repo started 2026-03-21. There are [19 releases](https://github.com/NVIDIA/SkillSpector/releases) from v2.5.0 (2026-07-27) to v2.13.1 (2026-10-23), about 1.5 each week. The classifier is "Alpha". It has at least 100 contributors, at least 100 commits in 30 days, and 180 open issues. Minor releases change verdicts: the [2.12.0 notes](https://github.com/NVIDIA/SkillSpector/blob/v2.13.1/docs/release/skillspector-2.12.0.md) say that results can change from `SAFE` to `CAUTION`. Thus semver does not protect verdicts.
- **arm64:** Works (tested on aarch64). yara-python has an aarch64 wheel. Python 3.12–3.14 only.

## 2. Trial (aarch64, Python 3.12.3, v2.13.1 tag tarball)

| Step | Result |
|---|---|
| Runtime install | 28 s, 66 packages, 195 MB |
| Upstream tests (no integration, no provider) | 12,162 passed, 38 skipped, 4 xfailed; 9 min 32 s; peak 755 MB |
| Fixture `malicious_skill` / `safe_skill` | 100 `DO_NOT_INSTALL` (exit 1) / 0 `SAFE` (exit 0) |
| [anthropics/skills](https://github.com/anthropics/skills/tree/dbd4588f9e1033efb41dad4bef2f7947c8993d44/skills) `pdf` | 15 `CAUTION`: coverage partial (missing referenced paths); LP3, TR3 |
| `internal-comms` | 0 `SAFE` |
| `webapp-testing` | 49 `CAUTION`: TM1 HIGH, AST4 ×2, LP3 (subprocess use) |
| One scan | 2.0–3.7 s, 155–158 MB, one CPU. Python API: 2.3 s import, 0.9 s scan |

All scans used `--no-llm`. A dead proxy blocked OSV.dev, so the bundled list was used. The test run had network access; I did not check whether the tests call OSV.dev. Two runs gave the same JSON except `finding_id` (random) and `scanned_at`. JSON keys: `skill`, `risk_assessment`, `components`, `issues` (rule, severity, file, line, fingerprint), `analysis_completeness`, `metadata.skillspector_version`.

## 3. Fit

**Origin:** Static mode runs rules that people wrote (regex, AST, YARA). By D63/D64 the output is `tool` with `software_agent: {name: skillspector, version: "2.13.1"}`. LLM mode gives `model`.

**Record:** One curator proposal for each skill folder: the input content id, the scan mode, the report digest (normalized JSON without `finding_id`/`scanned_at`), the recommendation, the score, the completeness and the findings. It is never an approval, and `SAFE` grants nothing. By docs/09 R1, an unconfirmed gate proposal applies only when it is stricter. Thus `DO_NOT_INSTALL` or partial coverage blocks `activate` at once, and only a curator can remove the block.

**Where:**
- Ingest (`catalog.publish`) and package receive (`packages._scan`): run it. Add the findings next to `agent_instruction` and `instruction_like_text`.
- Activate: do not scan. Show the stored proposal to the person who gives the grant. Refuse a proposal for other bytes or for a suspended version.
- Serve (#80 `skills/get`): do not scan. Serve only activated skills, as now. Optionally, put the proposal reference in `_meta` `kutuphane/handling`.

**agentfiles.py:** Replace nothing. `agentfiles` tells if a file is an instruction (fail closed, many formats). SkillSpector tells if a skill is risky, and it needs a SKILL.md folder. Keep the `SUSPICIOUS` regex for files that are not skills.

**Isolation:** Run it as a subprocess in its own venv. Do not import it. It needs Python 3.12 or later (we allow 3.11), it adds about 66 packages, and its `[mcp]` extra needs `mcp<2` (we need `mcp>=2.3`). Test: kobra + skillspector resolves; kobra + skillspector[mcp] does not.

## 4. Version-binding options

| Option | Advantages | Disadvantages |
|---|---|---|
| A. Exact pin in each release (tag + sha256) | Reproducible proposals | A security fix needs our release; PyPI refuses direct-URL dependencies, so the pin cannot go in our package metadata |
| B. Lockstep releases | Easy to explain | About 1.5 releases each week; minors change verdicts; our version numbers lose meaning. **Reject** |
| C. Extra `kutuphane[skillspector]`, range + contract test | Core and light install stay the same | No PyPI target for the extra; a range lets verdicts change |
| D. Vendoring | No network at install | We own 66 dependencies and all fixes; Apache-2.0 [§4](https://www.apache.org/licenses/LICENSE-2.0#redistribution): keep LICENSE and notices, mark changed files. **Reject** |

For all options:
- **Licence:** Put LICENSE and THIRD_PARTY_NOTICES in each image. Make a full notice for all 66 packages. Keep the MPL-2.0 files unchanged.
- **Security updates:** Monitor the tags and NVIDIA PSIRT. Make a fast path for a fix that does not wait for our release.
- **Supply chain:** Install from the tag tarball with a known sha256 and the upstream `uv.lock`, or from conda-forge. Remove provider keys from the environment. Keep `LANGSMITH_*` unset [INFERENCE: tracing is set by environment].
- **#76:** Keep it out of the core install and the light container.
- **Reproducibility:** Store the version, mode, input digest and report digest. When the version changes, set old proposals to `pending` (docs/17). Keep old versions available to repeat a scan.

## 5. Recommendation

Use A and C together. Do not embed, lockstep or vendor.
1. SkillSpector is an external, optional tool. It is not in our package metadata.
2. Each Kütüphane release names one tested version and its sha256 in a constraints file and in the release notes.
3. The adapter reads `skillspector --version`. It refuses an unknown version unless the operator allows it. It records the real version.
4. A contract test runs the named version on its fixtures and on our harmless copies (D62). It checks the JSON keys, the exit codes and the expected verdicts.
5. Use only `--no-llm` (origin `tool`). A later LLM mode must use a local model through LLMDAP and record origin `model`.

**Risks:**
- Alpha status and fast change: verdicts change between minor versions.
- False positives: 2 of 3 benign skills got `CAUTION`. Curators can get too many alerts.
- False trust: `SAFE` is not proof. It does not read images, binaries or (fully) non-English text.
- OSV.dev egress cannot be switched off. On-prem must block it (smaller SC4 list) or allow it by policy.
- A large dependency tree (LangChain, boto3, cloud SDKs) and no PyPI release increase the supply-chain risk.
- Attack research targets it ([KillSkillSpector](https://github.com/huawei-csl/KillSkillSpector)). Use it as one layer, not as the only gate.
