#!/usr/bin/env bash
# ============================================================================
# QueueStorm Investigator — one-shot VM setup for Poridhi Ubuntu 20.04
# ----------------------------------------------------------------------------
# What it does, in order (every step is idempotent — safe to re-run):
#   1. Sanity checks (Ubuntu 20.04, root/sudo, network, cwd)
#   2. Installs Python 3.12 via deadsnakes PPA (Ubuntu 20.04 ships 3.8 — too old)
#   3. Installs git (in case it's a stripped image)
#   4. Creates .venv with Python 3.12 and installs requirements.txt
#   5. Seeds .env from .env.example if missing (NEVER overwrites)
#   6. Runs scripts/verify_local.py — must show "All sample cases verified locally."
#   7. Writes /etc/systemd/system/queuestorm.service (only if missing)
#   8. Reloads systemd, enables + (re)starts the service
#   9. Waits for /health, prints the final verification commands
#
# Usage (from the repo root on the VM):
#     bash scripts/vm_setup.sh
#
# Exit codes:
#     0   everything green
#     1   precondition failed (wrong OS, no sudo, no network, no repo)
#     2   pip install failed
#     3   verify_local.py failed (do NOT start the service)
#     4   service didn't come up healthy
# ============================================================================

set -euo pipefail

# ---------- pretty logging ----------------------------------------------------
RED=$'\033[0;31m'; GRN=$'\033[0;32m'; YLW=$'\033[0;33m'; CYN=$'\033[0;36m'; RST=$'\033[0m'
log()  { printf '%s[vm-setup]%s %s\n' "$CYN" "$RST" "$*"; }
ok()   { printf '%s[ vm-ok ]%s %s\n' "$GRN" "$RST" "$*"; }
warn() { printf '%s[vm-warn]%s %s\n' "$YLW" "$RST" "$*"; }
die()  { printf '%s[vm-die ]%s %s\n' "$RED" "$RST" "$*" >&2; exit "${2:-1}"; }

# ---------- 1. preconditions --------------------------------------------------
log "Checking preconditions ..."

# We're on the VM — Ubuntu 20.04 expected, but anything 20.04+ works.
. /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
    die "This script targets Ubuntu. Detected: ${ID:-unknown} ${VERSION_ID:-?}" 1
fi
case "${VERSION_ID:-}" in
    20.04|22.04|24.04) ok "Ubuntu ${VERSION_ID} supported";;
    *) warn "Ubuntu ${VERSION_ID} is untested but proceeding";;
esac

# Must be root OR passwordless sudo. We need root to install apt packages
# and write the systemd unit file.
SUDO=""
if [[ "$EUID" -eq 0 ]]; then
    ok "Running as root"
elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    SUDO="sudo"
    ok "Passwordless sudo available"
else
    die "Need root or passwordless sudo to install apt packages." 1
fi

# Network sanity — one DNS lookup, fail fast if we can't reach PyPI or GitHub.
if ! curl -fsS --max-time 5 -o /dev/null https://pypi.org/simple/ 2>/dev/null \
   && ! curl -fsS --max-time 5 -o /dev/null https://github.com 2>/dev/null; then
    die "No outbound HTTPS to pypi.org / github.com. Check the VM firewall." 1
fi
ok "Network reachable"

# Repo layout — must run from the cloned repo root.
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
[[ -f requirements.txt ]] || die "requirements.txt not found at $REPO_ROOT — are you in the repo root?" 1
[[ -f app/main.py       ]] || die "app/main.py not found — repo looks incomplete." 1
ok "Repo root: $REPO_ROOT"

# ---------- 2. install Python 3.12 + git --------------------------------------
log "Installing Python 3.12 + git via apt ..."

$SUDO apt-get update -y
$SUDO apt-get install -y --no-install-recommends \
    software-properties-common \
    ca-certificates \
    curl \
    git

# deadsnakes PPA is the cleanest path to a maintained 3.12 on 20.04.
if ! command -v python3.12 >/dev/null 2>&1; then
    log "Adding deadsnakes PPA and installing python3.12 ..."
    $SUDO add-apt-repository -y ppa:deadsnakes/ppa
    $SUDO apt-get update -y
    $SUDO apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-venv \
        python3.12-dev
fi
ok "Python: $(python3.12 --version)"

# ---------- 3. venv + pip install ---------------------------------------------
VENV="$REPO_ROOT/.venv"
if [[ ! -d "$VENV" ]]; then
    log "Creating venv at $VENV ..."
    python3.12 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
ok "venv: $VENV (Python $(python -c 'import sys;print(sys.version.split()[0])'))"

log "Installing requirements ..."
python -m pip install --upgrade pip wheel >/dev/null
python -m pip install -r requirements.txt || die "pip install failed" 2
ok "requirements installed"

# ---------- 4. seed .env ------------------------------------------------------
if [[ ! -f "$REPO_ROOT/.env" && -f "$REPO_ROOT/.env.example" ]]; then
    log "Seeding .env from .env.example ..."
    cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
    ok ".env created — edit only if you want to enable LLM"
elif [[ -f "$REPO_ROOT/.env" ]]; then
    ok ".env already exists — leaving it untouched"
else
    warn "No .env.example found — proceeding with defaults baked into config.py"
fi

# ---------- 5. verify BEFORE going public ------------------------------------
log "Running scripts/verify_local.py (must show 10/10 cases green) ..."
# verify_local.py exits non-zero if any case fails. Capture and report.
if python scripts/verify_local.py; then
    ok "verify_local.py passed"
else
    die "verify_local.py FAILED — do NOT start the service. Fix and rerun." 3
fi

# ---------- 6. systemd unit ---------------------------------------------------
SERVICE_FILE=/etc/systemd/system/queuestorm.service
SERVICE_USER="$(stat -c '%U' "$REPO_ROOT")"   # run as the repo owner
log "Systemd unit will run service as user: $SERVICE_USER"

if [[ ! -f "$SERVICE_FILE" ]]; then
    log "Writing $SERVICE_FILE ..."
    $SUDO tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=QueueStorm Investigator (FastAPI)
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${REPO_ROOT}
EnvironmentFile=${REPO_ROOT}/.env
ExecStart=${VENV}/bin/uvicorn app.main:app \\
    --host 0.0.0.0 --port \${PORT} --workers 1 \\
    --no-server-header --proxy-headers
Restart=on-failure
RestartSec=2
KillSignal=SIGTERM
TimeoutStopSec=15
# Hardening (does not block the app)
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF
    $SUDO systemctl daemon-reload
    ok "systemd unit installed"
else
    ok "systemd unit already exists — leaving it"
fi

# ---------- 7. enable + (re)start ---------------------------------------------
log "Enabling + (re)starting queuestorm.service ..."
$SUDO systemctl enable queuestorm >/dev/null 2>&1 || true
$SUDO systemctl restart queuestorm

# ---------- 8. wait for /health ----------------------------------------------
log "Waiting for http://127.0.0.1:8000/health ..."
PORT_VAL=$("$VENV/bin/python" -c "import os,re,sys; \
p=os.environ.get('PORT','8000'); \
m=re.fullmatch(r'\d+',p); \
print(p if m else '8000', file=sys.stderr)" 2>/dev/null \
    || awk -F= '/^PORT=/{print $2; exit}' "$REPO_ROOT/.env" 2>/dev/null \
    || echo 8000)
PORT_VAL=${PORT_VAL:-8000}

for i in {1..30}; do
    if curl -fsS --max-time 2 "http://127.0.0.1:${PORT_VAL}/health" >/dev/null; then
        ok "Service is healthy on :${PORT_VAL}"
        break
    fi
    sleep 1
done

if ! curl -fsS --max-time 2 "http://127.0.0.1:${PORT_VAL}/health" >/dev/null; then
    warn "Service did not become healthy in 30 s. Dumping last 50 log lines:"
    $SUDO journalctl -u queuestorm -n 50 --no-pager || true
    die "Service unhealthy — investigate logs above." 4
fi

# ---------- 9. final report ---------------------------------------------------
PUBLIC_IP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo '<vm-public-ip>')"
cat <<EOF

${GRN}============================================================${RST}
${GRN} QueueStorm Investigator — deployed${RST}
${GRN}============================================================${RST}
  Repo:        ${REPO_ROOT}
  Service:     queuestorm.service (systemd, auto-restart on failure)
  Bind:        0.0.0.0:${PORT_VAL}  (uvicorn, 1 worker)
  Health:      http://127.0.0.1:${PORT_VAL}/health
  Public IP:   ${PUBLIC_IP}
  Public URL:  http://${PUBLIC_IP}:${PORT_VAL}

  Configure the Poridhi load balancer to forward to:
      ${PUBLIC_IP}:${PORT_VAL}

  Smoke check from the VM:
      curl http://127.0.0.1:${PORT_VAL}/health
      python scripts/smoke_test.py --base-url http://127.0.0.1:${PORT_VAL}

  From your laptop (after LB is up):
      python scripts/smoke_test.py --base-url http://${PUBLIC_IP}:${PORT_VAL}

  Useful commands:
      sudo systemctl status queuestorm
      sudo systemctl restart queuestorm
      sudo journalctl -u queuestorm -f
      tail -f ${REPO_ROOT}/server.log    # if you ever switch to nohup

${GRN}Done.${RST}
EOF