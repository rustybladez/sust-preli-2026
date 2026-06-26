#!/usr/bin/env python3
"""Rewrite RUNBOOK.md with em-dashes and other UTF-8 intact.

This exists because PowerShell's console layer strips U+2014 (em-dash)
out of here-string literals before they reach the script engine,
even with a UTF-8 encoding hint. Writing via Python guarantees the
file on disk contains the intended bytes.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "RUNBOOK.md"

CONTENT = """\
# QueueStorm Investigator \u2014 Runbook

Quick copy-paste guide for judges and local reproduction.

> **Hackathon primary target:** Poridhi VM. See [PORIDHI_DEPLOY.md](PORIDHI_DEPLOY.md).
> Render / Railway / Fly.io / a plain Docker image all work the same way; pick the
> one your infrastructure team has provisioned.

## Prerequisites

- Python 3.12+
- `pip` (or `uv`)
- (Optional) Docker \u2014 only needed if you choose the container path
- (Optional) `GEMINI_API_KEY` / `OPENAI_API_KEY` \u2014 service works without either
  using rule-based templates; LLM only enriches `customer_reply` text

## Local setup

```bash
git clone <your-repo-url>
cd sust-preli-2026
python -m venv .venv

# Windows (PowerShell)
.venv\\Scripts\\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env only if you want to enable the optional LLM path
```

## Run locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify:

```bash
curl http://127.0.0.1:8000/health
# Expected: {"status":"ok"}

curl -X POST http://127.0.0.1:8000/analyze-ticket \\
  -H "Content-Type: application/json" \\
  -d @- <<'EOF'
{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5000 taka to a wrong number around 2pm today.",
  "language": "en",
  "transaction_history": [
    {
      "transaction_id": "TXN-9101",
      "timestamp": "2026-04-14T14:08:22Z",
      "type": "transfer",
      "amount": 5000,
      "counterparty": "+8801719876543",
      "status": "completed"
    }
  ]
}
EOF
```

## Tests & verification

```bash
# Full test suite (26 cases: 16 original + 10 synthetic edge cases)
pytest tests/ -q

# No-Docker end-to-end gate \u2014 boots uvicorn in-process and runs all 10
# SAMPLE cases against /analyze-ticket. Works on Windows without Docker.
python scripts/verify_local.py
# Expected: "All sample cases verified locally." with per-case p95 < 50 ms

# Smoke test against an already-running server (e.g. local uvicorn, deployed URL)
python scripts/smoke_test.py --base-url http://127.0.0.1:8000
```

If you change anything in `app/services/text_generator.py` or
`app/services/analyzer.py`, regenerate the committed sample output so it stays
in sync with real responses:

```bash
python scripts/regenerate_sample.py
# Writes samples/sample_output_tkt001.json
```

## Docker (optional \u2014 only if your host has Docker)

Build (image is < 200 MB; guideline prefers < 500 MB, hard limit 1 GB):

```bash
docker build -t queuestorm-team .
```

Run with no LLM (rules + templates only):

```bash
docker run --rm -p 8000:8000 queuestorm-team
```

Run with the example env file (no real keys, just for shape):

```bash
docker run --rm -p 8000:8000 --env-file .env.example queuestorm-team
```

Run with a real key for judging:

```bash
# Create judging.env locally (NEVER commit):
#   GEMINI_API_KEY=...
#   USE_LLM=true
#   LLM_PROVIDER=gemini
docker run --rm -p 8000:8000 --env-file judging.env queuestorm-team
```

The image is hardened: non-root user, `tini` PID-1 for graceful shutdown,
in-image healthcheck against `/health`, single-worker uvicorn, and a
`.dockerignore` that keeps tests / docs / secrets out of the build context.

## Deploy \u2014 Poridhi VM (primary)

Full step-by-step: **[PORIDHI_DEPLOY.md](PORIDHI_DEPLOY.md)**.

TL;DR:

```bash
ssh user@<poridhi-ip>
sudo apt update && sudo apt install -y python3.12 python3.12-venv
git clone <repo> && cd sust-preli-2026
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # edit only if you want LLM
python scripts/verify_local.py
```

Then either:

```bash
# systemd (preferred)
sudo tee /etc/systemd/system/queuestorm.service > /dev/null <<'EOF'
[Unit]
Description=QueueStorm Investigator
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/sust-preli-2026
EnvironmentFile=/home/ubuntu/sust-preli-2026/.env
ExecStart=/home/ubuntu/sust-preli-2026/.venv/bin/uvicorn app.main:app \\
    --host 0.0.0.0 --port ${PORT} --workers 1
Restart=on-failure
RestartSec=2
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable --now queuestorm
```

or:

```bash
# nohup fallback (no systemd)
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 \\
    > server.log 2>&1 &
echo $! > server.pid
```

Open firewall for port 8000, or front it with nginx + Let's Encrypt for HTTPS.

Verify from outside the VM:

```bash
curl http://<poridhi-ip>:8000/health
python scripts/smoke_test.py --base-url http://<poridhi-ip>:8000
```

## Deploy \u2014 Render / Railway / Fly.io

Same start command. Bind `0.0.0.0`, expose `$PORT`.

- **Build:** `pip install -r requirements.txt`
- **Start:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Health check path:** `/health`
- **Env vars (optional):** `GEMINI_API_KEY`, `GEMINI_MODEL`, `OPENAI_API_KEY`, `OPENAI_MODEL`

Submit base URL: `https://<service>.onrender.com` (or whichever platform).

## Troubleshooting

| Issue | Fix |
|---|---|
| `404` on routes | Confirm exact paths `/health` and `/analyze-ticket` (no prefix) |
| `Connection refused` | Bind `--host 0.0.0.0`; open firewall / security group for the port |
| Timeout on `/analyze-ticket` | Disable LLM (`USE_LLM=false`) or lower `LLM_TIMEOUT_SECONDS` |
| Invalid enum in response | Compare response JSON to `SUST_Preli_Sample_Cases.json` `_meta.allowed_enums` |
| Schema validation error on input | FastAPI returns 400/422 with details \u2014 never crashes the process |
| `verify_local.py` says `ModuleNotFoundError: app` | Run from the repo root, or activate the venv first |
| Windows path: `python` not found | Use `.\\.venv\\Scripts\\python.exe ...` instead of `python ...` |

## Submission checklist

- [ ] Public HTTPS base URL **or** Docker pull command + run command
- [ ] `GET /health` reachable from outside, returns `{"status":"ok"}`
- [ ] `POST /analyze-ticket` returns 200 on SAMPLE-01 input
- [ ] GitHub repo accessible to the judges
- [ ] `samples/sample_output_tkt001.json` matches live output (regenerate if not)
- [ ] `judging.env` / API keys are NOT in the repo \u2014 submitted via the form's private field only
"""


def main() -> int:
    OUT.write_text(CONTENT, encoding="utf-8")
    size = OUT.stat().st_size
    # Sanity: count em-dashes via UTF-8 byte sequence.
    raw = OUT.read_bytes()
    em = raw.count(b"\xe2\x80\x94")
    print(f"Wrote {OUT} ({size} bytes, {em} em-dashes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())