# QueueStorm Investigator — Runbook

Quick copy-paste guide for judges and local reproduction.

## Prerequisites

- Python 3.12+
- pip or uv
- (Optional) Docker
- (Optional) `OPENAI_API_KEY` — service works without it using rule-based fallbacks

## Local setup

```bash
git clone <your-repo-url>
cd sust-preli-2026
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env if using an LLM provider
```

## Run locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify:

```bash
curl http://127.0.0.1:8000/health
# Expected: {"status":"ok"}

curl -X POST http://127.0.0.1:8000/analyze-ticket \
  -H "Content-Type: application/json" \
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

## Run tests

```bash
pytest tests/ -q
python scripts/smoke_test.py --base-url http://127.0.0.1:8000
```

## Docker

Build (keep image < 500MB preferred, 1GB hard limit):

```bash
docker build -t queuestorm-team .
```

Run:

```bash
docker run -p 8000:8000 --env-file .env.example queuestorm-team
```

For judging with secrets:

```bash
docker run -p 8000:8000 --env-file judging.env queuestorm-team
```

`judging.env` is **not** committed — submit values via the form's private field if needed.

## Deploy — Render (recommended, free tier)

1. Push repo to GitHub
2. Render → New Web Service → connect repo
3. Settings:
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health check path:** `/health`
4. Environment variables: `OPENAI_API_KEY`, `OPENAI_MODEL`, `PORT` (auto on Render)
5. Submit base URL: `https://<service>.onrender.com`

## Deploy — Railway / Fly.io

Same start command. Bind `0.0.0.0`, expose `$PORT`.

## Deploy — Poridhi VM / EC2

```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv
git clone <repo> && cd sust-preli-2026
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=... PORT=8000
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 &
```

Open security group port 8000 (or use nginx reverse proxy on 443).

Test from **outside** the VM:

```bash
curl https://<public-ip-or-domain>/health
```

## Troubleshooting

| Issue | Fix |
|---|---|
| 404 on routes | Confirm exact paths `/health` and `/analyze-ticket` (no prefix unless documented) |
| Connection refused | Bind `--host 0.0.0.0`, check firewall |
| Timeout | Disable LLM or reduce to one fast call; use templates |
| Invalid enum in response | Print response JSON; compare to `SUST_Preli_Sample_Cases.json` `_meta.allowed_enums` |
| Schema validation error on input | Return 400/422, never crash |

## Submission checklist

- Public HTTPS base URL **or** Docker pull command + run command
- GitHub repo accessible to `bipulhf`
- README with MODELS section, safety logic, limitations
- Sample output file from public case pack
