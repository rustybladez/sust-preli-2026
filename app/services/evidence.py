from app.schemas.enums import CaseType, EvidenceVerdict
from app.schemas.request import Transaction
from app.services.transaction_matcher import count_prior_transfers_to_counterparty


def determine_evidence_verdict(
    case_type: CaseType,
    complaint: str,
    matched_id: str | None,
    ambiguous: bool,
    transactions: list[Transaction],
) -> EvidenceVerdict:
    if case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
        return EvidenceVerdict.INSUFFICIENT_DATA

    if case_type == CaseType.OTHER and _is_vague_complaint(complaint):
        return EvidenceVerdict.INSUFFICIENT_DATA

    if ambiguous or matched_id is None:
        if case_type == CaseType.OTHER:
            return EvidenceVerdict.INSUFFICIENT_DATA
        if matched_id is None and case_type in {
            CaseType.WRONG_TRANSFER,
            CaseType.PAYMENT_FAILED,
            CaseType.DUPLICATE_PAYMENT,
        }:
            return EvidenceVerdict.INSUFFICIENT_DATA
        return EvidenceVerdict.INSUFFICIENT_DATA

    if case_type == CaseType.WRONG_TRANSFER:
        prior = count_prior_transfers_to_counterparty(transactions, matched_id)
        if prior >= 2:
            return EvidenceVerdict.INCONSISTENT
        return EvidenceVerdict.CONSISTENT

    if case_type == CaseType.PAYMENT_FAILED:
        matched = _get_txn(transactions, matched_id)
        if matched and matched.status.value == "failed":
            return EvidenceVerdict.CONSISTENT
        return EvidenceVerdict.INSUFFICIENT_DATA

    if case_type in {
        CaseType.REFUND_REQUEST,
        CaseType.DUPLICATE_PAYMENT,
        CaseType.MERCHANT_SETTLEMENT_DELAY,
        CaseType.AGENT_CASH_IN_ISSUE,
    }:
        return EvidenceVerdict.CONSISTENT

    return EvidenceVerdict.INSUFFICIENT_DATA


def _get_txn(transactions: list[Transaction], txn_id: str) -> Transaction | None:
    return next((t for t in transactions if t.transaction_id == txn_id), None)


def _is_vague_complaint(complaint: str) -> bool:
    text = complaint.lower().strip()
    vague_markers = (
        "something is wrong",
        "please check",
        "help me",
        "wrong with my money",
        "কিছু ভুল",
    )
    if len(text) < 40 and any(marker in text for marker in vague_markers):
        return True
    return False
