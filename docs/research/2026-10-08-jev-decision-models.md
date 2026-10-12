# Brief: "Jev gibi decision tabanlı modeller" in an on-prem knowledge platform

Web research by a delegated agent (2026-10-08); model output, reviewed by the session. Operator-supplied source:
https://typesafe.ai/blog/introducing-system-one-models-and-jev

**What "jev" means (confidence high).** Jev is TypeSafe AI's "System One model": a non-autoregressive model that takes
unstructured state plus typed questions and returns typed decisions with calibrated probabilities, never prose. Early
access opened 2026-09-15; the official post is dated 2026-10-08. The operator's phrasing "jev gibi" = "models like
Jev" asks about the *class*, not just the vendor.

## 1. What Jev / System One models are

- **Interface.** One `state` (text/JSON, 32k-token context) + N typed questions, all answered in parallel in one pass.
  Three primitives: **Choice** (pick from a supplied option list, ≤255), **Score** (rubric/ordinal), **Noul** (yes/no
  probability). Output is a probability distribution + confidence per question; it cannot emit a value outside the
  schema. Endpoint `POST https://api.typesafe.ai/v1/systemone`, model id `jev-latest`, Python/JS SDKs, LangChain
  `TypeSafeClassifier`. Sources: typesafe.ai launch post (2026-10-08); DataCamp (2026-09-16)
  https://www.datacamp.com/blog/system-one-models-jev ; InfoQ (2026-10-01)
  https://www.infoq.com/news/2026/10/typesafe-ai-jev-released/
- **Training.** "Reinforcement Learning for Calibrated Decisions" (RLCD): reward for probabilities matching real
  outcomes rather than human preference (RLHF) or verifiable correctness (RLVR). No paper, reward function, dataset or
  reproducible eval published. https://systemonemodels.org/guides/rlcd-explained/ (2026-10-02)
- **Claims.** 70–500 ms end-to-end; "40–200x faster", "444.6x cheaper" vs frontier LLMs; $0.042/M input tokens, output
  free; 0% type/tool-call errors. On TypeSafe's own 4-workflow eval Jev scores ~67.8% vs 74.1% GPT-5.6 Sol / 73.1%
  Opus 5, with reference labels derived from averaged frontier-model answers, not human ground truth.
  https://evals.typesafe.ai/ ; https://www.marktechpost.com/2026/09/19/typesafe-ai-releases-jev/
- **Known weaknesses.** Confidently wrong *valid* values; arithmetic, counting, date comparison; literal reading of
  negations; multi-document reconciliation (17-point drop on invoice eval); complementary yes/no questions need not sum
  to 1. HN pushback on "can't hallucinate" and the latency comparison.
  https://www.width.ai/post/what-is-jev-ai-typesafe ; https://www.eesel.ai/blog/typesafe-jev-review
- **Deployment.** Hosted API only, early-access waitlist. No open weights, parameter count, self-hosting, VPC or
  data-residency statements found. **For an air-gapped platform Jev itself is not usable.**
  https://www.getmaxim.ai/articles/what-is-jev-system-one-model/

## 2. The broader class and on-prem equivalents

Jev is a productised version of a known pattern: a small, fast, schema-constrained classifier/scorer with calibrated
confidence placed *between* reasoning steps. Open-weight building blocks that run air-gapped:

| Role | Open-weight options (2026) | Notes |
|---|---|---|
| Jev-shaped decision model | **Laya** (Convai, ModernBERT-large 421M + mmBERT-base 322M multilingual 100+ langs, Apache-2.0, HF 2026-09-18, ~33–40 ms on a T4, same choice/score/noul primitives); Kev (Qwen3.5 LoRA, 0.8–9B); SemIf, NanoJev (MIT) | Need fine-tuning: base checkpoints near random; zero-shot out-of-domain quality is where Jev leads (0.704 vs 0.966 macro acc. on one independent benchmark). https://pinggy.io/blog/best_open_source_jev_alternatives_self_hosted_decision_models/ ; https://huggingface.co/convaiinnovations/laya |
| Fine-tuned encoders | ModernBERT / mmBERT / DeBERTa heads + temperature scaling or MCGrad post-hoc calibration | Calibration must be measured per task (temperature scaling can improve Brier but worsen ECE). CalArena https://arxiv.org/pdf/2605.30188 |
| Guardrail / policy classifiers | Llama Guard 4 (12B), Prompt Guard 2, Qwen3Guard (0.6B/4B/8B, 119 langs incl. Turkish), gpt-oss-safeguard (20B/120B, bring-your-own-policy), Granite Guardian 4.1, Shieldstral; NeMo Guardrails as orchestration | https://arxiv.org/html/2605.28830v1 ; https://vdf.ai/blog/open-weight-guard-models-on-premises-ai/ |
| Reward / process models | Skywork-Reward-V2 (0.6B–8B, ICLR 2026); AgentPRM (step-wise "promise and progress"); ToolPRMBench, CUARewardBench | https://arxiv.org/abs/2507.01352 ; https://arxiv.org/abs/2511.08325 ; https://aclanthology.org/2026.findings-acl.602.pdf |
| Routers | RouteLLM (Apache-2.0, unmaintained since 2024-08); Not Diamond hosted/proprietary | https://nomadx.ae/blog/llm-model-routing-routellm-openrouter-notdiamond-2026/ |

## 3. Roles inside the knowledge platform, and how to evaluate them as library products

Candidate decision points (each a Choice/Score/Noul question over a small, relevant slice of state):

1. **Query routing** – category / collection / parse profile / "hybrid vs lexical only" (Choice).
2. **Ingestion classification** – document type, sensitivity tier, runbook vs skill vs reference, duplicate/version-of
   (Choice + Noul).
3. **Relevance and citation verification** – "does passage P support claim C?" (Noul), reranking score (Score).
4. **Access-policy risk scoring** – should this agent read/export this doc under this task? (Score + Noul gate).
5. **Runbook outcome prediction** – probability the next step succeeds / needs human (Noul); PRM-style value signal.
6. **Agent-read guardrailing** – prompt-injection / policy screening of retrieved content (guard models).

Evaluating such a model as a versioned library product (feasibility-ranked):

1. **Golden sets + calibration report per question type**: ≥500 labelled items per decision; accuracy, macro-F1,
   Brier, ECE, reliability diagram, per-question thresholds (thresholds do not transfer between question types). The
   report is a versioned document next to the model card.
2. **Shadow mode**: run the decision model alongside the current rule/LLM path, log disagreements, review; promote
   only when disagreement-resolved accuracy beats baseline.
3. **Decision ledger**: every decision (question id, state hash, answer, probability, downstream outcome, cost,
   latency) is a library record — the training/eval corpus for fine-tuning and for calibration-drift tracking.
4. **Trajectory replay harness**: replay logged agent trajectories with the decision model at the gate points; score
   with an AgentPRM-style step reward and task success. Requires deterministic replay of retrieval.
5. **Model registry entries** with eval-report lineage, so a decision model is a library item with provenance like any
   runbook.

## 4. The API-only risk and the on-prem substitute

Jev cannot run air-gapped today. Realistic substitute: **Laya (mmBERT variant for Turkish) fine-tuned on our decision
ledger**, temperature-scaled calibration, served in-process; a **Qwen3Guard-0.6B / Llama Guard 4** pre-filter; optionally
a **Skywork-Reward/AgentPRM-style** scorer. Expect zero-shot quality well below Jev until a few thousand labelled
decisions exist; the ledger is the prerequisite. Whether RLCD-style training can be reproduced in-house is unknown
(method unpublished).

## Clarifying questions for the operator

1. Which decision point hurts most today: routing, ingestion classification, citation checks, access gating, or
   runbook step prediction?
2. Is a hosted API ever acceptable for *non-sensitive* decisions, or is everything air-gapped without exception?
3. Do we already have labelled outcomes (tickets, runbook results, reviewer verdicts) for golden sets, roughly how many?
4. Is Turkish-language state required? (Jev and Laya-English are English-only; mmBERT-Laya/Qwen3Guard cover Turkish.)
5. Latency/cost budget per decision, and on what GPU/CPU?
