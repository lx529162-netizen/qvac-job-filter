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

_Filled in after the one-week run._

| Metric | Cloud model | QVAC local |
|---|---|---|
| Posts forwarded | [ ] | [ ] |
| Missed real vacancies | [ ] | [ ] |
| Wrong forwards | [ ] | [ ] |
| Median time per decision | [ ] | [ ] |
| Post text sent to third parties | yes | no |

## What I learned for real implementations

_Filled in after the run._

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
