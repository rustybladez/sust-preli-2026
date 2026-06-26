from app.schemas.enums import CaseType, EvidenceVerdict, Language
from app.schemas.request import TicketRequest, Transaction
from app.schemas.response import AnalyzeTicketResponse
from app.services.classifier import classify_case_type, sanitize_complaint
from app.services.evidence import determine_evidence_verdict
from app.services.router import requires_human_review, resolve_department, resolve_severity
from app.services.safety import apply_safety
from app.services.text_generator import TextGenerator
from app.services.transaction_matcher import match_transaction


def _reply_language(request: TicketRequest, complaint: str) -> str:
    if request.language == Language.BN:
        return "bn"
    if request.language == Language.EN:
        return "en"
    if request.language == Language.MIXED:
        return "bn" if any("\u0980" <= ch <= "\u09FF" for ch in complaint) else "en"
    return "bn" if any("\u0980" <= ch <= "\u09FF" for ch in complaint) else "en"


def _txn_summary(txn: Transaction | None) -> str | None:
    if txn is None:
        return None
    return (
        f"Transaction {txn.transaction_id}: {txn.amount} BDT {txn.type.value} "
        f"to {txn.counterparty} ({txn.status.value})."
    )


def _confidence(
    case_type: CaseType,
    evidence: EvidenceVerdict,
    matched_id: str | None,
    ambiguous: bool,
) -> float:
    if case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
        return 0.95
    if ambiguous or matched_id is None:
        return 0.6 if case_type == CaseType.OTHER else 0.65
    if evidence == EvidenceVerdict.INCONSISTENT:
        return 0.75
    if evidence == EvidenceVerdict.CONSISTENT:
        return 0.9 if case_type != CaseType.REFUND_REQUEST else 0.85
    return 0.7


def _reason_codes(
    case_type: CaseType,
    evidence: EvidenceVerdict,
    matched_id: str | None,
    ambiguous: bool,
) -> list[str]:
    codes = [case_type.value]
    if matched_id:
        codes.append("transaction_match")
    if ambiguous:
        codes.append("ambiguous_match")
    if evidence == EvidenceVerdict.INSUFFICIENT_DATA:
        codes.append("needs_clarification")
    if evidence == EvidenceVerdict.INCONSISTENT:
        codes.append("evidence_inconsistent")
    if case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
        codes.extend(["phishing", "credential_protection", "critical_escalation"])
    if case_type == CaseType.DUPLICATE_PAYMENT:
        codes.append("duplicate_payment")
    return list(dict.fromkeys(codes))


class TicketAnalyzer:
    def __init__(self, text_generator: TextGenerator) -> None:
        self._text_generator = text_generator

    async def analyze(self, request: TicketRequest) -> AnalyzeTicketResponse:
        complaint = sanitize_complaint(request.complaint)
        user_type = request.user_type.value if request.user_type else None

        case_type = classify_case_type(complaint, user_type=user_type)

        matched_id: str | None = None
        ambiguous = False

        if case_type != CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
            match = match_transaction(
                complaint,
                request.transaction_history,
                case_type,
            )
            matched_id = match.transaction_id
            ambiguous = match.ambiguous

        evidence = determine_evidence_verdict(
            case_type=case_type,
            complaint=complaint,
            matched_id=matched_id,
            ambiguous=ambiguous,
            transactions=request.transaction_history,
        )

        department = resolve_department(case_type, evidence)
        severity = resolve_severity(case_type, evidence, request.user_type)
        human_review = requires_human_review(
            case_type, evidence, severity, matched_id
        )

        matched_txn = next(
            (t for t in request.transaction_history if t.transaction_id == matched_id),
            None,
        )
        reply_lang = _reply_language(request, complaint)

        summary, action, reply = await self._text_generator.generate(
            complaint=complaint,
            case_type=case_type,
            department=department,
            evidence=evidence,
            matched_id=matched_id,
            reply_language=reply_lang,
            txn_summary=_txn_summary(matched_txn),
        )

        reply, action = apply_safety(reply, action, reply_language=reply_lang)

        return AnalyzeTicketResponse(
            ticket_id=request.ticket_id,
            relevant_transaction_id=matched_id,
            evidence_verdict=evidence,
            case_type=case_type,
            severity=severity,
            department=department,
            agent_summary=summary,
            recommended_next_action=action,
            customer_reply=reply,
            human_review_required=human_review,
            confidence=_confidence(case_type, evidence, matched_id, ambiguous),
            reason_codes=_reason_codes(
                case_type, evidence, matched_id, ambiguous
            ),
        )
