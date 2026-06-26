from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.schemas.request import TicketRequest
from app.schemas.response import AnalyzeTicketResponse
from app.services.analyzer import TicketAnalyzer
from app.services.text_generator import TextGenerator

router = APIRouter()


def get_analyzer(settings: Settings = Depends(get_settings)) -> TicketAnalyzer:
    return TicketAnalyzer(TextGenerator(settings))


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/analyze-ticket", response_model=AnalyzeTicketResponse)
async def analyze_ticket(
    body: TicketRequest,
    analyzer: TicketAnalyzer = Depends(get_analyzer),
) -> AnalyzeTicketResponse:
    if not body.complaint.strip():
        raise HTTPException(status_code=422, detail="complaint must not be empty")
    return await analyzer.analyze(body)
