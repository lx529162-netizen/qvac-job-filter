# Decision log

Each entry records a decision, the options I considered, and why I chose one. Newest first. Status: **active**, **superseded** or **revisit**.

| # | Date | Decision | Status |
|---|---|---|---|
| D9 | 2026-11-02 | Send only a link when a channel disables forwarding | active |
| D8 | 2026-11-02 | Pre-filter on the target-role pattern, not on broad keywords | active |
| D7 | 2026-11-02 | Keep the JSON schema enforced, accept slower answers | revisit |
| D6 | 2026-11-02 | Model extracts facts, code makes the decision | active |
| D5 | 2026-11-02 | Add a test set built from real posts | active |
| D4 | 2026-11-02 | Rewrite the prompt for the small model | superseded by D6 |
| D3 | 2026-11-02 | Pin `bare-rpc==0.0.1` | active |
| D2 | 2026-11-01 | Run side by side with the cloud version for a week | active |
| D1 | 2026-11-01 | Qwen3 4B, 4-bit, on the existing ARM server | active |

---

### D9. Send only a link when a channel disables forwarding

- **Context.** The cloud script copied the full text of a post when its channel disallowed forwarding.
- **Options.** Copy the text. Skip the post. Send a link to the post.
- **Decision.** Send a link, never the text.
- **Why.** The channel owner chose to restrict copying. A link still lets me find the vacancy, and respects that choice.

### D8. Pre-filter on the target-role pattern, not on broad keywords

- **Context.** The keyword filter from the cloud script matched fragments without word boundaries: `pm` inside "development", `job`, `ищем`, any `manager`. Most chat and unrelated jobs reached the model, at about 40 s each on CPU.
- **Options.** Keep the broad filter and buy speed elsewhere. Use the same role pattern as the final rule.
- **Decision.** Use the role pattern with word boundaries.
- **Why.** The final rule needs a target role in the hired roles, so a post that names none can only be NO. Skipping it loses nothing. On the real test set, model calls fell from 61 to 11, with all 5 vacancies kept.

### D7. Keep the JSON schema enforced, accept slower answers

- **Context.** With the schema enforced at generation time, an answer takes about 40 s on real posts.
- **Options.** Keep it. Turn it off (`STRICT_JSON=false`) and rely on the worked examples.
- **Decision.** Keep it for the comparison week.
- **Why.** It scored 61 / 61 and 20 / 20. After D8 the model runs rarely, so speed matters less than a proven result. To revisit after the week: measure with the schema off.

### D6. Model extracts facts, code makes the decision

- **Context.** On the live stream, the YES/NO prompt from D4 forwarded 73 posts in six hours. Only 5 were right.
- **Options.** A bigger model with the same YES/NO task. Fine-tuning. Split the task: the model fills three fields, code applies the rule.
- **Decision.** Split the task. The model fills a JSON schema: post type, roles being hired, IT or not. A regex on the roles and two rules decide.
- **Why.** One YES/NO answer asked a 4B model to judge type, role, industry and exceptions at once. Extraction is easier for it, and the rule is visible and changes in one line. A bigger model stays as plan B. Fine-tuning needs more labelled data.

### D5. Add a test set built from real posts

- **Context.** D4 passed 12 / 12 on short synthetic posts and then failed on live ones.
- **Decision.** Label the 61 unique posts from the failed run and test every change on them. Keep the set private on the server.
- **Why.** Tidy test posts did not look like real ones. The set holds people's resumes, so it is not published.

### D4. Rewrite the prompt for the small model (superseded by D6)

- **Context.** The cloud prompt, tuned for Claude Haiku, rejected plain Project Manager vacancies on the 4B model: 10 / 12.
- **Decision.** English system message, explicit YES and NO rules, six worked examples. Result: 12 / 12.
- **Outcome.** Failed on the live stream. See D6.

### D3. Pin `bare-rpc==0.0.1`

- **Context.** QVAC Python SDK 0.22 calls `bare_rpc.RPC(send=...)`. The newest `bare-rpc` on PyPI, 0.1.0, changed that signature, and the worker failed to start.
- **Decision.** Pin the version that matches the SDK.
- **Why.** The SDK declares `bare-rpc>=0.0.1`, so pip picks the newest. Re-check the pin when the SDK updates.

### D2. Run side by side with the cloud version for a week

- **Context.** The cloud script is how I find vacancies today. It must not lose posts while I experiment.
- **Options.** Replace it. Run both on the same stream.
- **Decision.** Run both. The QVAC version has its own Telegram session and its own output channel. Both read the same channel list.
- **Why.** Production keeps working, and the comparison is on the same live posts. A separate session avoids two processes sharing one session file. Rollback means stopping one service.

### D1. Qwen3 4B, 4-bit, on the existing ARM server

- **Context.** Oracle Ampere A1, 4 OCPU, 24 GB RAM, no GPU. The Mac at hand runs macOS 13, below QVAC's minimum of macOS 14.
- **Options.** Llama 3.2 1B (the QVAC quickstart model). Qwen3 4B. Qwen3 8B.
- **Decision.** Qwen3 4B, `Q4_K_M`, about 2.5 GB.
- **Why.** Posts are in Russian and English, and the rule "Product Manager is not Project Manager" needs some language skill, so 1B looked too small. 8B would be about twice as slow on CPU. It loads in about 8 s.
