import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.safety import is_safe_reply

SAMPLE_FILE = Path(__file__).resolve().parents[1] / "SUST_Preli_Sample_Cases.json"


def _load_cases() -> list[dict]:
    data = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    return data["cases"]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["id"])
async def test_public_sample_functional_equivalence(case: dict) -> None:
    expected = case["expected_output"]
    payload = case["input"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/analyze-ticket", json=payload)

    assert response.status_code == 200, case["id"]
    body = response.json()

    assert body["relevant_transaction_id"] == expected["relevant_transaction_id"], case["id"]
    assert body["evidence_verdict"] == expected["evidence_verdict"], case["id"]
    assert body["case_type"] == expected["case_type"], case["id"]
    assert body["department"] == expected["department"], case["id"]
    assert body["severity"] == expected["severity"], case["id"]
    assert body["human_review_required"] == expected["human_review_required"], case["id"]
    assert is_safe_reply(body["customer_reply"]), case["id"]
