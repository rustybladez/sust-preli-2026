# QueueStorm Investigator

FastAPI service for the **SUST CSE Carnival 2026 · Codex Community Hackathon · Online Preliminary** challenge.

## What it does

`POST /analyze-ticket` reads a customer complaint plus recent transaction history and returns a structured investigation result: matched transaction, evidence verdict, routing, escalation flag, and safe customer reply.

Design: **rules-first reasoning** with **template-based text**. Optional Gemini/OpenAI can polish prose when enabled — decisions never depend on an LLM.

## Quick start (venv)

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/macOS

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Optional LLM (Gemini free tier)

Rules + templates work without any API key. To optionally enhance text fields:

```env
USE_LLM=true
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.0-flash
```

Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY` to use OpenAI instead.

## Tests

```bash
pytest tests/ -q
python scripts/smoke_test.py --base-url http://127.0.0.1:8000
```

## Docker

```bash
docker build -t queuestorm-team .
docker run -p 8000:8000 --env-file .env.example queuestorm-team
```

See `RUNBOOK.md` for deployment options (Render, Railway, VM).

## MODELS

| Component | Where it runs | Why |
|---|---|---|
| Case classification | In-process rules | Fast, deterministic, no API cost |
| Transaction matching | In-process scoring | Core 35% evidence score — must not be LLM-driven |
| Evidence verdict & routing | In-process rules | Policy-aligned, auditable |
| Text fields | Templates (default) | Zero-cost, safe baseline |
| Gemini / OpenAI (optional) | External API | Polishes `agent_summary`, `recommended_next_action`, `customer_reply` only when `USE_LLM=true` |

## Safety logic

- Post-processes all customer-facing text
- Blocks credential requests and unauthorized refund/reversal promises
- Adds PIN/OTP warning when missing
- Ignores prompt-injection lines in complaints
- Bangla replies when `language=bn` or Bangla detected

## Known limitations

- Time parsing uses simple hints (`today`, `yesterday`, `2pm`) — not full NLP
- Ambiguous multi-transaction cases ask for clarification instead of guessing
- LLM enhancement is best-effort; templates used on failure or when disabled

## Docs

- `PUKU_DEV_GUIDELINES.md` — developer execution guide
- `RUNBOOK.md` — judge reproduction & deployment
- `SUST_Preli_Sample_Cases.json` — 10 public reference cases
