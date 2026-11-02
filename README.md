# Local-AI job filter for Telegram (QVAC)

I follow about 60 Telegram channels with job posts. A small script reads every new post, asks an LLM whether it is a vacancy for my role, and forwards the matches to one private channel. So I read one channel instead of 60.

The first version called a cloud model through an API. This project moves the same task to a **local model running on my own server through [QVAC SDK](https://github.com/tetherto/qvac)**. No post text leaves the machine, and there is no per-call API dependency.

## How it works

```
60 Telegram channels
      │  new post
      ▼
keyword pre-filter (regex) ── no match ──► skip
      │
      ▼
QVAC SDK → local LLM on the server ── "YES" / "NO"
      │ YES
      ▼
forward to my private channel  +  one row in decisions.csv
```

- Server: Oracle Cloud Ampere A1 (ARM64), 4 OCPU, 24 GB RAM, Ubuntu 24.04, no GPU (CPU inference)
- Model: `QWEN3_4B_INST_Q4_K_M` from the QVAC model registry (configurable)
- Prompt: the same YES/NO prompt the cloud version uses, so the two are comparable

## Rollout plan

I treated this like a client implementation, not a rewrite.

1. **Keep production running.** The cloud script stays untouched and keeps forwarding to my main channel.
2. **Run side by side.** The QVAC version runs as a separate process with its own Telegram session and forwards to a separate channel, on the same live stream of posts.
3. **Compare after one week.** Posts both versions caught, posts only one caught, and which one was right.
4. **Decide.** Switch, keep both, or roll back. Rolling back means stopping one service.

## Results

### Acceptance test (before go-live)

`eval_prompt.py` runs 12 labelled posts through the local model: 6 real vacancies and 6 traps (Product Manager, an article about PMs, a PM course, a QA job that "works with the PM"). Server: Ampere A1, 4 OCPU, CPU only. Model: Qwen3 4B, Q4_K_M.

| Prompt | Correct | Median time per decision |
|---|---|---|
| Cloud prompt, unchanged | 10 / 12 | 5.5 s |
| Rewritten for the local model | **12 / 12** | 11.1 s |

The cloud prompt was tuned for Claude Haiku. On the 4B model it rejected two plain Project Manager vacancies. The rewritten prompt moves the rules to an English system message, states when to answer YES and when NO, and adds six worked examples. It is twice as slow because the model re-reads the instructions and examples for every post. At 1–5 vacancies a day this does not matter.

The test set is small and written by me, so the one-week live run below is the real check.

### First live run: the YES/NO prompt failed

In six hours on live posts, the rewritten YES/NO prompt forwarded 73 posts. Only 5 were right. The rest were resumes of PMs, sales, backend and affiliate jobs, and a construction PM. On long real posts the 4B model answered YES to almost anything that looked like a job post.

### Fact extraction: the version that works

The model now only fills a JSON schema: post type (vacancy, digest, resume, other), the roles being hired, and whether the job is in IT. Code applies the rule: a vacancy or digest, in IT, with a target role. I extended the synthetic set with the failure types from the live run (rewritten, not copied) and built a private set from the 61 unique posts the failed run forwarded, labelled by hand.

| Test set | Correct | Vacancies caught | Wrong forwards | Median time per post |
|---|---|---|---|---|
| Synthetic, 20 posts | **20 / 20** | 8 / 8 | 0 | 76 s |
| Real posts, 61 | **61 / 61** | 5 / 5 | 0 | 39 s |

Caveats: I labelled the real set myself, and I wrote the worked examples after seeing the failures, so the model may fit this set better than new posts. Timings were taken while the live bot also ran on the same 4 cores. Enforcing the JSON schema at generation time is the main suspect for the slowdown; `STRICT_JSON=false` turns it off for comparison.

### One-week live run

_Filled in after the run._

| Metric | Cloud model | QVAC local |
|---|---|---|
| Posts forwarded | [ ] | [ ] |
| Missed real vacancies | [ ] | [ ] |
| Wrong forwards | [ ] | [ ] |
| Median time per decision | [ ] | [ ] |
| Post text sent to third parties | yes | no |

## What I learned for real implementations

- **A prompt does not transfer between models.** The prompt that worked on a large cloud model failed on a small local one. Moving to local AI needs a prompt rewrite and a test set, not only a new endpoint.
- **Build the acceptance test before go-live.** A dozen labelled cases turned "it seems not to work" into "10/12 vs 12/12" in two minutes, and made each change measurable.
- **A clean test can still mislead.** The rewritten YES/NO prompt scored 12/12 on short synthetic posts. On live posts it forwarded 73 posts in six hours, and only 5 of them were right: resumes, sales and backend jobs, a construction PM. Short, tidy test posts did not look like real ones. The fix was a second test set built from real posts.
- **Let the small model extract facts, and let code decide.** One YES/NO answer asked a 4B model to judge post type, role, industry and exceptions at once. The current version asks it only to fill a JSON schema (post type, roles being hired, IT or not), and plain code applies the business rule. QVAC enforces the schema at generation time.
- **Pin dependencies of young SDKs.** QVAC SDK 0.22 broke with the newest `bare-rpc` release from PyPI. Pinning `bare-rpc==0.0.1` fixed it.
- **CPU-only is enough for low volume.** A 4B model loads in about 8 seconds and answers in 5–11 seconds on a free ARM server with no GPU.

_More after the one-week run._

## Next steps

- Cache the shared part of the prompt (instructions and examples) to bring the time per decision back down.
- Extend the role list to Program, Technical Program, Engagement and Implementation Manager in both versions after the comparison week.
- Try delegated inference: a light device sends posts to this server as a QVAC provider, peer to peer.

## Setup

On Ubuntu 24.04 ARM64:

```bash
sudo apt install -y python3-venv git
git clone <this repo> ~/qvac-job-filter && cd ~/qvac-job-filter
python3 -m venv .venv
# QVAC Python SDK with the bundled worker for linux-arm64 (no Node.js needed)
.venv/bin/pip install tetherto-qvac-sdk -f https://github.com/tetherto/qvac/releases/expanded_assets/sdk-v0.22.0
# If pip installed only the thin wheel (py3-none-any), add the worker separately (needs Node.js 22+):
#   .venv/bin/python -m tetherto.qvac_sdk install-worker
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # fill in your values
cp channels.example.txt channels.txt
.venv/bin/python qvac_filter.py # first run: Telegram login code + model download
```

Then run it as a service:

```bash
sudo cp qvac-job-filter.service /etc/systemd/system/
sudo systemctl enable --now qvac-job-filter
journalctl -u qvac-job-filter -f
```

## Privacy

- Secrets live only in `.env`, which is git-ignored.
- `decisions.csv` stores channel, message id, verdict and latency. It stores no post text and is not published.
- Posts are forwarded with their source, to a private channel for personal use.
