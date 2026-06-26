#!/usr/bin/env python3
"""Smoke-test deployed or local QueueStorm Investigator endpoints."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FILE = ROOT / "SUST_Preli_Sample_Cases.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test QueueStorm API")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="API base URL (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--case-id",
        default="SAMPLE-01",
        help="Sample case id from SUST_Preli_Sample_Cases.json",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    with httpx.Client(timeout=30.0) as client:
        health = client.get(f"{base}/health")
        print("GET /health", health.status_code, health.text)
        health.raise_for_status()

        cases = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))["cases"]
        case = next(c for c in cases if c["id"] == args.case_id)
        response = client.post(f"{base}/analyze-ticket", json=case["input"])
        print("POST /analyze-ticket", response.status_code)
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        response.raise_for_status()

    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
