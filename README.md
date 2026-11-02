# Local-AI job filter for Telegram (QVAC)

A personal tool that watches about 60 Telegram job channels and forwards only vacancies for my role (Project / Delivery Manager, Scrum Master, Agile Coach) to one private channel.

The first version sent each candidate post to a cloud LLM through an API. This version runs the model **locally on my own server through [QVAC SDK](https://github.com/tetherto/qvac)**. Post text never leaves the machine, and there is no per-call API dependency.

## How it works

```
60 Telegram channels
      │  new post
      ▼
role pre-filter (regex) ── no target role named ──► skip, no model call
      │  e.g. "Project Manager", "проджект", "Scrum Master", "PM"
      ▼
QVAC SDK → local LLM ── fills a JSON schema:
      │                 post type (vacancy / digest / resume / other),
      │                 roles being hired, IT or not
      ▼
rule in code: vacancy or digest, in IT, with a target role
      │ YES
      ▼
forward to my private channel  +  one row in decisions.csv
```

- **Server:** Oracle Cloud Ampere A1 (ARM64), 4 OCPU, 24 GB RAM, Ubuntu 24.04, no GPU
- **Model:** `QWEN3_4B_INST_Q4_K_M` from the QVAC model registry (configurable)
- **Split of work:** the model reads and describes the post; plain code makes the decision. The rule is visible, testable and changes in one line.

## Results so far

Acceptance tests on the server. "Real posts" are 61 posts from the live stream, labelled by hand and kept only on the server.

| Version | Test set | Correct | Vacancies caught | Wrong forwards |
|---|---|---|---|---|
| Cloud YES/NO prompt, unchanged | synthetic, 12 | 10 / 12 | 4 / 6 | 0 |
| YES/NO prompt rewritten for the 4B model | synthetic, 12 | 12 / 12 | 6 / 6 | 0 |
| ↳ same, on the live stream for 6 hours | live | — | 5 | 68 |
| **Fact extraction + rule in code** | synthetic, 20 | **20 / 20** | 8 / 8 | 0 |
| **Fact extraction + rule in code** | real posts, 61 | **61 / 61** | 5 / 5 | 0 |

Time per post that reaches the model: about 40 s on CPU with the JSON schema enforced. The role pre-filter means most posts never reach it: on the real set, model calls dropped from 61 to 11, with all 5 vacancies kept.

Caveats: I labelled the real set myself, and I wrote the model's worked examples after seeing the live failures, so the model may fit this set better than new posts. The one-week run below is the real check.

## How I got here

1. **Kept production running.** The cloud script stayed untouched. The QVAC version runs as a separate process with its own Telegram session and its own output channel, on the same live stream.
2. **Reused the cloud prompt.** On the 4B model it rejected plain Project Manager vacancies: 10 / 12 on a small test set.
3. **Rewrote the prompt for the small model.** 12 / 12 on the same test set. On the live stream it then forwarded 73 posts in six hours, only 5 of them right: resumes, sales and backend jobs, a construction PM.
4. **Split understanding from decision.** The model now only extracts facts into a JSON schema that QVAC enforces at generation time. A regex on the extracted roles and two plain rules decide. Built a second test set from real posts.
5. **Tightened the pre-filter.** The keyword filter copied from the cloud script matched fragments such as `pm` inside "development", `job` and any `manager`. It now uses the same role pattern as the final rule, so a skipped post could never have passed anyway.

## One-week comparison

_Filled in after the run._

| Metric | Cloud model | QVAC local |
|---|---|---|
| Posts forwarded | [ ] | [ ] |
| Missed real vacancies | [ ] | [ ] |
| Wrong forwards | [ ] | [ ] |
| Post text sent to third parties | yes | no |

## What I learned for real implementations

- **A prompt does not transfer between models.** A prompt tuned for a large cloud model failed on a small local one. Moving to local AI needs prompt work and a test set, not only a new endpoint.
- **A clean test set can mislead.** Short, tidy test posts passed 12 / 12, and real long posts failed. Test on data that looks like production.
- **Let a small model extract facts, and let code decide.** One YES/NO answer asked the model to judge post type, role, industry and exceptions at once. Filling three fields is a task a 4B model does reliably.
- **Keep the expensive step rare.** On a cloud API an extra call costs a second. On your own CPU it costs about 40 seconds. A precise pre-filter matters more locally.
- **Pin dependencies of young SDKs.** QVAC SDK 0.22 broke with the newest `bare-rpc` release on PyPI. Pinning `bare-rpc==0.0.1` fixed it.
- **CPU-only works at this volume.** The 4B model loads in about 8 seconds on a free ARM server with no GPU.

## Next steps

- Measure speed with the schema off (`STRICT_JSON=false`) and with a cached prompt prefix.
- Extend the role list to Program, Technical Program, Engagement and Implementation Manager after the comparison week.
- Try delegated inference: a light device sends posts to this server as a QVAC provider, peer to peer.

## Setup

On Ubuntu 24.04 ARM64:

```bash
sudo apt install -y python3-venv git
git clone https://github.com/lx529162-netizen/qvac-job-filter ~/qvac-job-filter && cd ~/qvac-job-filter
python3 -m venv .venv
# QVAC Python SDK with the bundled worker for linux-arm64 (no Node.js needed)
.venv/bin/pip install tetherto-qvac-sdk -f https://github.com/tetherto/qvac/releases/expanded_assets/sdk-v0.22.0
# If pip installed only the thin wheel (py3-none-any), add the worker separately (needs Node.js 22+):
#   .venv/bin/python -m tetherto.qvac_sdk install-worker
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # fill in your values
cp channels.example.txt channels.txt
.venv/bin/python list_channels.py   # first run: Telegram login; prints channel ids
.venv/bin/python qvac_filter.py     # first run downloads the model
```

Run it as a service:

```bash
sudo cp qvac-job-filter.service /etc/systemd/system/
sudo systemctl enable --now qvac-job-filter
journalctl -u qvac-job-filter -f
```

Test the classifier:

```bash
.venv/bin/python eval_prompt.py extract                          # synthetic set
.venv/bin/python eval_prompt.py extract --real eval_real.jsonl   # private real set
```

## Privacy

- Secrets live only in `.env`, which is git-ignored.
- Posts are forwarded with their source, to a private channel for personal use. If a channel owner has disabled forwarding, the tool sends only a link to the post and never copies its text.
- `decisions.csv` stores channel, message id, verdict and timing, no post text. It is not published.
- The real-post test set is kept only on the server and is not published.
