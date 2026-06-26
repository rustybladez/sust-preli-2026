# QueueStorm Investigator — production image
# Target: Poridhi VM / Render / Railway / Fly.io
# Base image: python:3.12-slim (~120 MB compressed; final layer ~150-180 MB)

FROM python:3.12-slim AS base

# --- System deps -----------------------------------------------------------
# tini = clean PID-1 signal forwarding; ca-certificates = outbound HTTPS if
# an LLM key is provided at deploy time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --- Runtime hygiene -------------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

# --- App layout ------------------------------------------------------------
WORKDIR /app

# Install deps first so this layer caches when only source changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY SUST_Preli_Sample_Cases.json ./
COPY samples/ samples/

# --- Run as non-root -------------------------------------------------------
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Healthcheck: orchestrators (Poridhi LB, Render, Docker, k8s) rely on this
# to confirm the process is serving. Keep it cheap and dependency-free.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys, os; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health', timeout=3).status == 200 else 1)"

# tini reaps zombies and forwards SIGTERM -> uvicorn graceful shutdown.
ENTRYPOINT ["/usr/bin/tini", "--"]

# Single worker is correct for this stateless workload (rules + templates
# are CPU-cheap; concurrency comes from multiple replicas, not workers).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
