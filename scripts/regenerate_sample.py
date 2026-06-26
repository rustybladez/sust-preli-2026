#!/usr/bin/env python3
"""Regenerate samples/sample_output_tkt001.json from the live analyzer.

Boots uvicorn in a background thread, posts the TKT-001 input from
SUST_Preli_Sample_Cases.json to /analyze-ticket, and writes the response
JSON to samples/sample_output_tkt001.json (pretty-printed, UTF-8).

Use this whenever analyzer.py / text_generator.py change shape so the
committed sample mirrors real output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from threading import Event, Thread

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SAMPLE_FILE = ROOT / "SUST_Preli_Sample_Cases.json"
OUT_FILE = ROOT / "samples" / "sample_output_tkt001.json"
PORT = 8766


class _Server(uvicorn.Server):
    def run(self) -> None:  # type: ignore[override]
        self.run_in_thread = True  # type: ignore[attr-defined]
        super().run()


def _wait_ready(base: str, timeout: float = 15.0) -> None:
    import time

    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=2.0) as client:
        while time.monotonic() < deadline:
            try:
                r = client.get(f"{base}/health")
                if r.status_code == 200:
                    return
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.1)
    raise RuntimeError("Server did not become ready in time")


def main() -> int:
    cases = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))["cases"]
    case = next((c for c in cases if c.get("id") == "SAMPLE-01"), None)
    if case is None:
        print("SAMPLE-01 not found in SUST_Preli_Sample_Cases.json", file=sys.stderr)
        return 2

    payload = case["input"]

    server = _Server(
        config=uvicorn.Config(
            "app.main:app",
            host="127.0.0.1",
            port=PORT,
            log_level="warning",
            access_log=False,
        )
    )
    Thread(target=server.run, daemon=True).start()
    base = f"http://127.0.0.1:{PORT}"

    try:
        _wait_ready(base)
        with httpx.Client(timeout=30.0) as client:
            r = client.post(f"{base}/analyze-ticket", json=payload)
        if r.status_code != 200:
            print(f"HTTP {r.status_code}: {r.text[:400]}", file=sys.stderr)
            return 1
        body = r.json()

        # Strip the echoed ticket_id from text fields is unnecessary; keep the
        # full response so the sample mirrors what clients receive.
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUT_FILE.write_text(
            json.dumps(body, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {OUT_FILE.relative_to(ROOT)}")
        print(f"  verdict={body.get('evidence_verdict')} "
              f"case={body.get('case_type')} txn={body.get('relevant_transaction_id')}")
        return 0
    finally:
        server.should_exit = True
        Event().wait(0.2)


if __name__ == "__main__":
    raise SystemExit(main())