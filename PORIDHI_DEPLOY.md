# Deploying QueueStorm Investigator to Poridhi

Poridhi provides VMs/containers for hackathon teams. QueueStorm Investigator
is a stateless FastAPI service that runs anywhere Python 3.12 and an HTTP
port are available. This guide covers the path that needs no Docker
locally and no proprietary knowledge of Poridhi internals — just SSH,
Python, and uvicorn.

> If Poridhi exposes a Docker option you also want to use, see `Dockerfile`
> in the repo root. The image is hardened (non-root, tini, healthcheck,
> single-worker) and < 200 MB.

## 0. Prerequisites

- SSH access to your Poridhi VM (IP + key given by the organizers)
- Outbound HTTPS (only needed if you opt in to LLM via env vars)
- Inbound TCP on port 8000 *or* a reverse proxy in front (recommended: nginx + Let's Encrypt)

## 1. Get the code onto the VM

```bash
ssh user@<poridhi-ip>
sudo apt update && sudo apt install -y python3.12 python3.12-venv git
git clone <your-repo-url> sust-preli-2026
cd sust-preli-2026
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure environment

Copy the example and edit only what you need. **The service works with
defaults** — no LLM key is required; templates cover all 10 sample cases.

```bash
cp .env.example .env
nano .env
```

Keys you may want to set:

| Var | Default | Why |
|---|---|---|
| `PORT` | `8000` | Change if Poridhi maps a different public port |
| `LOG_LEVEL` | `info` | `warning` in prod is quieter |
| `USE_LLM` | `false` | Set `true` only if you have a working key and want richer text |
| `LLM_PROVIDER` | `gemini` | or `openai` |
| `LLM_TIMEOUT_SECONDS` | `8` | Hard cap per LLM call; template fallback after timeout |
| `GEMINI_API_KEY` | _empty_ | Required if `USE_LLM=true` and `LLM_PROVIDER=gemini` |
| `OPENAI_API_KEY` | _empty_ | Required if `USE_LLM=true` and `LLM_PROVIDER=openai` |

## 3. Smoke-test locally on the VM

```bash
source .venv/bin/activate
python scripts/verify_local.py
```

Expected last line:

```
All sample cases verified locally.
```

If this fails, fix it before exposing the service publicly. Typical issues:
- Wrong `PORT` in `.env`
- Outbound HTTPS blocked (only matters if `USE_LLM=true`)

## 4. Run as a background service

Two options, pick one.

### 4a. systemd unit (preferred)

```bash
sudo tee /etc/systemd/system/queuestorm.service > /dev/null <<'EOF'
[Unit]
Description=QueueStorm Investigator
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/sust-preli-2026
EnvironmentFile=/home/ubuntu/sust-preli-2026/.env
ExecStart=/home/ubuntu/sust-preli-2026/.venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 --port ${PORT} --workers 1
Restart=on-failure
RestartSec=2
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now queuestorm
sudo systemctl status queuestorm
curl http://127.0.0.1:8000/health
```

### 4b. nohup fallback (no systemd)

```bash
source .venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 \
    > server.log 2>&1 &
echo $! > server.pid
```

Logs: `tail -f server.log`. Stop: `kill $(cat server.pid)`.

## 5. Public exposure

### Option A: open port 8000 directly (fastest)

Add Poridhi security-group / firewall rule for inbound TCP 8000.
Submit `http://<poridhi-ip>:8000` as your public URL.

### Option B: nginx + TLS (recommended)

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo tee /etc/nginx/sites-available/queuestorm > /dev/null <<'EOF'
server {
    listen 80;
    server_name <your-domain>;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }
}
EOF
sudo ln -s /etc/nginx/sites-available/queuestorm /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d <your-domain>
```

Submit `https://<your-domain>` as your public URL.

## 6. Verify from outside

From your laptop or any external machine:

```bash
curl https://<your-public-url>/health
# {"status":"ok"}

python scripts/smoke_test.py --base-url https://<your-public-url>
# Smoke test passed.
```

## 7. Hand-off checklist

- [ ] `GET /health` returns `{"status":"ok"}` from outside
- [ ] `POST /analyze-ticket` works with one sample case from outside
- [ ] Logs show no tracebacks in the first 5 minutes
- [ ] Service survives `sudo systemctl restart queuestorm`
- [ ] Repo link shared with the judges
- [ ] Public URL submitted via the hackathon form
- [ ] (If using LLM) key stored in `.env`, not committed to git

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Connection refused` from outside | Port not open / wrong host binding | Bind `0.0.0.0`; open firewall for `8000` (or 443 behind nginx) |
| `502 Bad Gateway` from nginx | Uvicorn not running | `sudo systemctl status queuestorm`; check `server.log` |
| `/analyze-ticket` returns 500 | Schema mismatch or LLM timeout | Check logs; set `USE_LLM=false` to use templates |
| Slow first response | App startup | `--workers 1` is correct for this workload; first hit warms routes |
| Healthcheck flapping | OOM or LLM hang | Lower `LLM_TIMEOUT_SECONDS`; check Poridhi VM RAM |

## Local sanity (no SSH, no Docker)

If you want to confirm everything is wired up before SSHing into Poridhi:

```powershell
# Windows
.\.venv\Scripts\python.exe scripts\verify_local.py
```

This boots uvicorn in-process, hits `/health`, and runs all 10 sample cases.
Expected: `All sample cases verified locally.` and p95 < 50 ms.