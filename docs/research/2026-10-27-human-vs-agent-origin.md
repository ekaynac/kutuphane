# Agent-entered knowledge and the `human` origin: design for kstd / Kütüphane

## 1. Answer

- **No system can prove that a human wrote a text.** A system can prove two things: which credential wrote the bytes, and which verified person confirmed those exact bytes. Everything else is a claim. That claim has a named owner, but it is not a fact.
- **The rule:** the server sets the origin from the authenticated write path. The writer does not declare it. An agent path always gives `model`. Only a confirmation can change this. The human must give it in the human's own session, bound to the digest of the exact bytes, with user verification.
- **Dictation and "save exactly this text":** these are `human` + `entered_by: agent:…` when the person confirms the bytes as "my own words, verbatim". If the person only reviewed the text, the result is `assisted`. With no confirmation, the result is `model`.

## 2. What exists, and what it proves

| Mechanism | It proves | It does not prove |
|---|---|---|
| [RFC 8693](https://www.rfc-editor.org/rfc/rfc8693.html) `act` claim | The token has a delegation: `sub` = user, `act.sub` = agent. Only the current actor counts for policy. | That anything was confirmed. An *impersonation* token has no `act`, so the server sees only the user. |
| [draft-oauth-ai-agents-on-behalf-of-user](https://datatracker.ietf.org/doc/draft-oauth-ai-agents-on-behalf-of-user/) (`requested_actor`, `actor_token`) | The user gave consent to one named agent. | Who wrote a given text. (Individual draft. Rev 02 expired 2026-02.) |
| [draft-ietf-wimse-aims-00](https://datatracker.ietf.org/doc/draft-ietf-wimse-aims/) (adopted from draft-klrc-aiagent-auth), §10.7 | "the agent MUST NOT treat local UI confirmation alone as sufficient authorization". It recommends step-up through CIBA. | — |
| [MCP elicitation](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation) | In **form mode**, "data is exposed to the client", so the agent host can answer the form. In **URL mode**, the client "MUST NOT … enable the client or LLM to inspect the content or user inputs", and the server "MUST verify the identity of the user who opens the URL". | A form answer is not proof that a human answered. |
| [OpenID CIBA](https://openid.net/specs/openid-client-initiated-backchannel-authentication-core-1_0.html) `binding_message` | An out-of-band approval on the user's own device. | That the user read the text. |
| [WebAuthn](https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API/Authenticator_data) UV flag | The authenticator verified the user (PIN or biometric), and the challenge can commit to a digest. | That the user saw the text. The authenticator does not show it, because `txAuthSimple` was removed ([w3c/webauthn#1386](https://github.com/w3c/webauthn/issues/1386)). The relying-party page must show the text. |
| [C2PA 2.4](https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html) `c2pa.ai-disclosure` | A signed declaration of `humanOversightLevel` (`fully_autonomous` / `prompt_guided` / `human_validated`). | The claim generator only *declares* it. |
| [CAWG identity 1.2](https://cawg.io/identity/1.2/) | The named actor's signature is "construed as … authorization of or active participation". Roles include `cawg.creator` and `cawg.editor`. | Authorship. |
| [W3C AI Content Disclosure](https://www.w3.org/community/reports/ai-content-disclosure/CG-FINAL-ai-content-disclosure-20261009) (Final, 2026-10-09) | "A human dictates ideas; AI structures and expands them" → `ai-assisted`. | It is "self-declared". "cryptographic validation alone does not establish that a human actually authored or reviewed the text." Verbatim speech-to-text: no guidance found. |
| Git signing / [GitHub](https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification) | A signature covers the committer. GitHub says that when the author is someone else, "the commit signature doesn't guarantee the consent of the author". | The `Co-authored-by` trailer is plain text. |
| [Kernel policy](https://docs.kernel.org/process/coding-assistants.html) | "AI agents MUST NOT add Signed-off-by tags." | This is a social rule, and the kernel does not enforce it technically. The Maintainers Summit agreed to deprecate `Assisted-by` ([The Register, 2026-10-14](https://www.theregister.com/ai-and-ml/2026/10/14/linux-kernel-devs-drop-obligatory-confession-of-ai-tool-usage/5303140)). The final doc state is not verified. |
| LangGraph [`interrupt`](https://docs.langchain.com/oss/python/langgraph/interrupts) / Claude Code [permission modes](https://code.claude.com/docs/en/permission-modes) | A pause, then a resume value. | Who resumed it. `bypassPermissions` and hooks auto-approve. |
| [USCO AI report, Part 2](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-2-Copyrightability-Report.pdf) | "prompts alone do not provide sufficient human control". This supports: directing an agent ≠ human authorship. | — |
| Process attestation (keystrokes, e.g. [arXiv 2603.00179](https://arxiv.org/abs/2603.00179)) | Behaviour during typing. | Nothing for agent-entered text. It is also privacy-heavy. |
| Approval fatigue: [OpenID agentic paper](https://arxiv.org/abs/2510.25819) §4.1, [CISA on push bombing](https://www.cisa.gov/sites/default/files/publications/fact-sheet-implement-number-matching-in-mfa-applications-508c.pdf) | People approve prompts without reading them. | — |

**Our own finding** (docs/16 §): Qwen could not identify model text by its style. So detection cannot replace provenance.

## 3. Design

### Facts in the current code

- `identity.actor_from_claims` makes `act` → `agent:<act.sub>` with `on_behalf_of=user:<sub>`.
- **When the type claim is missing, the default is `user`.** This is safe for access, but it is not proof that a person is present.
- `server._for_model` already treats every MCP call as model context. Writes must use the same mirror rule.
- Today the origin comes only from `kstd.yaml` (self-declared by the issuer). There is no write API (G9). This design is for that future API.

### Rules (Kütüphane profile)

- **R1. Origin is computed.**
  - The server computes it from (principal, on_behalf_of, channel, client_id, token auth evidence, confirmation).
  - A requested origin is a request only. A lower trust level is always allowed (`model`/`unknown`). A higher one needs R3.
- **R2. Agent paths give `model`.**
  - Agent paths are: an `agent:` principal (by `act` or type claim), or any MCP call, whatever the principal is.
  - These paths never give `human`, `assisted` or `tool`.
  - If the agent requests a higher origin, the node does three things: it stores the item as `model`, it records the claim with the notice `origin-claim-refused`, and it opens a confirmation request.
- **R3. Upgrade proof.** An upgrade needs all of these:
  - (a) A `user:` principal confirms. For `human`, this must be the agent's `on_behalf_of`. For `assisted`, it can be any person with review rights in the scope.
  - (b) The confirmation happens in the person's own session on Kütüphane's own page, which the agent opens through **MCP URL-mode elicitation**. CIBA is the fallback. **Form-mode answers are refused.**
  - (c) The page shows the full stored text, or a diff against the last confirmed version.
  - (d) The person does a **WebAuthn assertion with UV=1**. Its challenge commits to `sha256(item path ‖ digest ‖ claim ‖ nonce)`.
  - (e) The person chooses one claim:
    - "these are my words, verbatim (written or dictated)" → `human`
    - "a model wrote or reworded this; I reviewed it in substance" → `assisted`
  - (f) The confirmation expires (proposal: 24 h). A changed byte gives a new digest, and the item is `model` again.
- **R4. Direct human writes.**
  - A `user:` token with no `act` gets `human` only on three conditions: the client is a registered first-party human client (the UI), the token has `amr`/`acr` showing user verification, and `auth_time` is fresh.
  - Otherwise the origin is `unknown`, because a script or agent can hold a user token.
- **R5. Manifests (`kstd.yaml`).** A declared non-model origin counts only when the issuer is trusted for `item` statements in the scope (docs/21 §6.8). Otherwise it is `unknown` with the notice `origin-claim-untrusted`.
- **R6. Missing proof.**
  - The node knows that an agent wrote the bytes → `model`. This is the true value.
  - The write path is not known (legacy import, untrusted issuer) → `unknown`.
  - Both behave the same.
- **R7. Withdrawal.** The confirming person can withdraw a confirmation, and the origin then falls back to the R6 value. Other people use `contest`.

### Export mapping

| Our origin | C2PA / IPTC | CAWG role | W3C |
|---|---|---|---|
| `human` via agent | no `ai-disclosure` | `cawg.creator` = the confirmer | `human-only` |
| `assisted` | `compositeWithTrainedAlgorithmicMedia` + `human_validated` | `cawg.editor` | — |
| agent `model` with a human prompt | `prompt_guided` | — | — |

PROV-O: `prov:wasAttributedTo` = the human, `prov:wasAssociatedWith` = the agent, linked by `prov:actedOnBehalfOf`.

### The dictation question

- Today, docs/11 §5 says neural speech-to-text is a learned model, so a raw transcript is `model`.
- The verbatim confirmation in R3 moves the responsibility for every byte to the person. The agent is then a channel only, which is close to the existing "change of form only" rule.
- Choose `human` + `entered_by` here, not `assisted`. Two behaviours depend on it: human-only corpora (training profiles), and the W3C mapping.

## 4. Honest limits

1. **It proves who confirmed, not who wrote.** A person can paste chatbot text and click "verbatim". Our record then has a named, user-verified owner for a false claim. That is accountability, not truth.
2. **Rubber-stamping.** UV proves a PIN or a touch. It does not prove that the person read the text.
   - Mitigations: show the full text, add a rate limit per person, and use per-confirmer suspension.
   - Residual risk remains.
3. **Collusion.** "Record it as mine" from a person who then confirms is not detectable. The system only makes sure that the person, and not the agent, signs it.
4. **Impersonation tokens.** An agent with a raw user token (no `act`, browser automation) looks like the user to the server.
   - The IdP policy must forbid this. Token binding ([DPoP, RFC 9449](https://www.rfc-editor.org/rfc/rfc9449)) and short token lifetimes reduce the risk.
   - The code cannot fully exclude it.
5. **A compromised endpoint.** An agent with desktop control and a known PIN can satisfy a platform authenticator. A hardware key with touch is stronger.
6. **Across nodes,** a receiver sees only the issuer's signature. Trust in the remote write path is trust in the issuer, the same as C2PA trust lists.
7. **Partial human contribution** is not measured. Any model edit gives `assisted` or `model`.

## 5. Fields: core or not?

| Field | Where | Required? |
|---|---|---|
| `origin` (exists; default `unknown` = `model`) | core | yes, as today |
| Rule R5: issuer trust for non-model origins | core rule, no new field | normative |
| `entered_by`: the agent or software that wrote the bytes when it is not the author | core, optional | no. Behaviour: suspend all items from a compromised agent (the same argument as `software_agent`). |
| `reviewed_by` widened to mean "the person who confirmed the final bytes" (`assisted`: review; `human` with `entered_by`: own words) | core, conditional | only with `assisted`, or with `human` + `entered_by` |
| Write record: principal, on_behalf_of, channel, client_id, acr/amr/auth_time | Kütüphane profile (`access_event`) | node-local |
| Confirmation: `by`, `digest`, `claim`, `method` (`webauthn-uv`/`ciba`), `at`, `expires` | Kütüphane profile; signed by the node | node-local |

**Recommendation:** do not add a new required core field. The core needs one rule and two optional, conditional fields. Put the proof method in a profile. This answers the operator's point about minimality: the core cannot check another node's authentication, so the method does not belong there.

## 6. Test cases

Base for T1–T6: `ayse` = `user:ayse`, `claude` = `agent:claude`; the token has `sub=ayse`, `act.sub=claude`; the channel is MCP; the bytes have digest D.

| # | Case | Proof | Recorded origin |
|---|---|---|---|
| T1 | base; claude requests `human` | none | `model` + `origin-claim-refused`; a confirmation request is opened |
| T2 | as T1 | ayse, URL elicitation → own page, WebAuthn UV=1, challenge ⊇ D, "verbatim" | `human`, `entered_by: agent:claude`, `reviewed_by: ayse` |
| T3 | as T1 | MCP **form** elicitation `accept` | `model` (the client can answer the form) |
| T4 | as T2, then claude changes 1 byte (D′) | the old confirmation for D | `model` (the confirmation is not reused) |
| T5 | as T2, but the confirmer is `user:mehmet` | mehmet chooses "verbatim" | refused. If mehmet has review rights and chooses "reviewed": `assisted`, `reviewed_by: mehmet` |
| T6 | as T2, but the WebAuthn assertion has UV=0 (presence only) | — | `model` + `user-verification-missing` |
| T7 | `user:ayse`, no `act`, REST | registered UI client, `amr` has UV, `auth_time` 2 min old | `human`. With an unknown client_id, or `auth_time` older than the limit: `unknown` |
| T8 | `kstd.yaml` declares `human` | issuer trusted for `item` in the scope | `human`. Untrusted issuer: `unknown` + `origin-claim-untrusted` |

**Checks for Main:** none ran. These are proposals only. No repo files were changed.