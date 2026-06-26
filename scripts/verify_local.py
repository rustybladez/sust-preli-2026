#!/usr/bin/env python3
"""Local, no-Docker verification for QueueStorm Investigator.

Boots the FastAPI app via uvicorn in a background thread, hits /health,
and runs every case from SUST_Preli_Sample_Cases.json through
/analyze-ticket. For each case it asserts that the produced decision
fields match the case's _expected keys.

Designed for the user's Windows dev box (no Docker required) and as a
fast pre-deploy gate on any host with Python 3.12.

Usage:
    python scripts/verify_local.py
    python scripts/verify_local.py --port 8765 --quiet
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from threading import Event, Thread

import httpx
import uvicorn

# Make `app` importable when this script is launched from any cwd.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SAMPLE_FILE = ROOT / "SUST_Preli_Sample_Cases.json"
DECISION_KEYS = (
    "relevant_transaction_id",
    "evidence_verdict",
    "case_type",
    "human_review_required",
)


# ---------------------------------------------------------------------------
# Uvicorn lifecycle
# ---------------------------------------------------------------------------


class _Server(uvicorn.Server):
    """Uvicorn server whose install/serve loop returns control to the caller."""

    def run(self) -> None:  # type: ignore[override]
        self.run_in_thread = True  # type: ignore[attr-defined]
        super().run()


def _start_server(port: int, stopped: Event) -> uvicorn.Server:
    config = uvicorn.Config(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )
    server = _Server(config=config)

    def _serve() -> None:
        try:
            server.run()
        finally:
            stopped.set()

    Thread(target=_serve, daemon=True).start()
    return server


def _wait_ready(base: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    with httpx.Client(timeout=2.0) as client:
        while time.monotonic() < deadline:
            try:
                r = client.get(f"{base}/health")
                if r.status_code == 200 and r.json().get("status") == "ok":
                    return
            except Exception as e:  # noqa: BLE001
                last_err = e
            time.sleep(0.1)
    raise RuntimeError(f"Server did not become ready in {timeout:.1f}s: {last_err}")


# ---------------------------------------------------------------------------
# Case runner
# ---------------------------------------------------------------------------


def _check_decision(case_id: str, expected: dict, got: dict) -> list[str]:
    failures: list[str] = []
    for key in DECISION_KEYS:
        if key not in expected:
            continue
        want = expected[key]
        got_val = got.get(key)
        if got_val != want:
            failures.append(
                f"{case_id}: {key} expected={want!r} got={got_val!r}"
            )
    return failures


def _run_cases(base: str, cases: list[dict], quiet: bool) -> tuple[list[float], list[str]]:
    durations: list[float] = []
    failures: list[str] = []
    with httpx.Client(timeout=30.0) as client:
        for case in cases:
            case_id = case["id"]
            payload = case["input"]
            # SUST_Sample_Cases uses 'expected_output' as the canonical
            # expected-response key; older drafts used '_expected'.
            expected = case.get("expected_output") or case.get("_expected") or {}
            t0 = time.perf_counter()
            r = client.post(f"{base}/analyze-ticket", json=payload)
            dt = time.perf_counter() - t0
            durations.append(dt)

            if r.status_code != 200:
                failures.append(f"{case_id}: HTTP {r.status_code} {r.text[:120]}")
                continue

            body = r.json()
            failures.extend(_check_decision(case_id, expected, body))

            if not quiet:
                verdict = body.get("evidence_verdict")
                case_type = body.get("case_type")
                txn = body.get("relevant_transaction_id")
                print(
                    f"  {case_id:10s} {dt*1000:6.1f} ms  "
                    f"verdict={verdict:<22s} case={case_type:<22s} txn={txn}"
                )
    return durations, failures


# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Local no-Docker verification")
    parser.add_argument("--port", type=int, default=8765, help="Ephemeral port for in-process uvicorn")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-case output")
    parser.add_argument(
        "--timeout", type=float, default=15.0, help="Seconds to wait for server readiness"
    )
    args = parser.parse_args()

    base = f"http://127.0.0.1:{args.port}"

    cases = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))["cases"]
    if not cases:
        print("No sample cases found.", file=sys.stderr)
        return 2

    server = _start_server(args.port, Event())  # noqa: F841

    overall_start = time.perf_counter()
    try:
        _wait_ready(base, args.timeout)
        if not args.quiet:
            print(f"Server ready on {base}")
            print(f"Running {len(cases)} sample cases ...")

        durations, failures = _run_cases(base, cases, args.quiet)

        total = time.perf_counter() - overall_start
        p50 = statistics.median(durations) * 1000
        p95 = sorted(durations)[max(0, int(len(durations) * 0.95) - 1)] * 1000
        mx = max(durations) * 1000
        ok = len(cases) - len({f.split(":")[0] for f in failures})

        print()
        print(f"Cases:        {ok}/{len(cases)} matched expected decision fields")
        print(f"Total time:   {total*1000:.1f} ms")
        print(f"Per-case p50: {p50:.1f} ms   p95: {p95:.1f} ms   max: {mx:.1f} ms")

        if failures:
            print("\nFailures:")
            for f in failures:
                print(f"  - {f}")
            return 1

        print("\nAll sample cases verified locally.")
        return 0
    finally:
        server.should_exit = True


if __name__ == "__main__":
    raise SystemExit(main())