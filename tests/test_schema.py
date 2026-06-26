import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_analyze_ticket_minimal_shape() -> None:
    payload = {
        "ticket_id": "TKT-TEST",
        "complaint": "Something is wrong with my money. Please check.",
        "transaction_history": [],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/analyze-ticket", json=payload)

    assert response.status_code == 200
    body = response.json()
    required = {
        "ticket_id",
        "relevant_transaction_id",
        "evidence_verdict",
        "case_type",
        "severity",
        "department",
        "agent_summary",
        "recommended_next_action",
        "customer_reply",
        "human_review_required",
    }
    assert required.issubset(body.keys())
    assert body["ticket_id"] == "TKT-TEST"


@pytest.mark.asyncio
async def test_empty_complaint_returns_422() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/analyze-ticket",
            json={"ticket_id": "TKT-EMPTY", "complaint": "   "},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_malformed_json_returns_400() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/analyze-ticket",
            content=b"{not-json",
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 400
