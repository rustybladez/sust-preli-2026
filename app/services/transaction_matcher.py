from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.schemas.enums import CaseType, TransactionType
from app.schemas.request import Transaction
from app.utils.bn_numerals import extract_amounts
from app.utils.phone import extract_phones, normalize_phone


@dataclass
class MatchResult:
    transaction_id: str | None
    ambiguous: bool = False
    scores: dict[str, float] = field(default_factory=dict)
    duplicate_second_id: str | None = None


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _complaint_time_hints(complaint: str) -> set[str]:
    text = complaint.lower()
    hints: set[str] = set()
    if "today" in text or "আজ" in complaint:
        hints.add("today")
    if "yesterday" in text or "গতকাল" in complaint:
        hints.add("yesterday")
    if "morning" in text or "সকাল" in complaint:
        hints.add("morning")
    if "2pm" in text or "14:" in text or "around 2" in text:
        hints.add("afternoon")
    return hints


def _time_score(txn: Transaction, hints: set[str]) -> float:
    if not hints:
        return 0.0
    ts = _parse_ts(txn.timestamp)
    if ts is None:
        return 0.0
    score = 0.0
    if "today" in hints and ts.hour >= 12:
        score += 1.0
    if "yesterday" in hints:
        score += 1.5
    if "morning" in hints and ts.hour < 12:
        score += 1.5
    if "afternoon" in hints and 12 <= ts.hour < 18:
        score += 1.5
    return score


def _type_score(txn: Transaction, complaint: str, case_type: CaseType) -> float:
    text = complaint.lower()
    mapping = {
        CaseType.WRONG_TRANSFER: TransactionType.TRANSFER,
        CaseType.PAYMENT_FAILED: TransactionType.PAYMENT,
        CaseType.REFUND_REQUEST: TransactionType.PAYMENT,
        CaseType.DUPLICATE_PAYMENT: TransactionType.PAYMENT,
        CaseType.MERCHANT_SETTLEMENT_DELAY: TransactionType.SETTLEMENT,
        CaseType.AGENT_CASH_IN_ISSUE: TransactionType.CASH_IN,
    }
    expected = mapping.get(case_type)
    if expected and txn.type == expected:
        return 2.0
    if "cash in" in text or "cash-in" in text or "ক্যাশ" in complaint:
        if txn.type == TransactionType.CASH_IN:
            return 2.0
    if "transfer" in text or "sent" in text:
        if txn.type == TransactionType.TRANSFER:
            return 1.5
    if "recharge" in text or "bill" in text or "electricity" in text:
        if txn.type == TransactionType.PAYMENT:
            return 2.0
    return 0.0


def find_duplicate_pair(transactions: list[Transaction]) -> tuple[str, str] | None:
    """Return (first_id, second_id) when two near-identical payments exist."""
    completed = [t for t in transactions if t.status.value == "completed"]
    for i, left in enumerate(completed):
        left_ts = _parse_ts(left.timestamp)
        if left_ts is None:
            continue
        for right in completed[i + 1 :]:
            if left.amount != right.amount or left.counterparty != right.counterparty:
                continue
            if left.type != right.type:
                continue
            right_ts = _parse_ts(right.timestamp)
            if right_ts is None:
                continue
            delta = abs((right_ts - left_ts).total_seconds())
            if delta <= 120:
                first, second = (left, right) if left_ts <= right_ts else (right, left)
                return first.transaction_id, second.transaction_id
    return None


def match_transaction(
    complaint: str,
    transactions: list[Transaction],
    case_type: CaseType,
) -> MatchResult:
    if not transactions:
        return MatchResult(transaction_id=None)

    if case_type == CaseType.DUPLICATE_PAYMENT:
        pair = find_duplicate_pair(transactions)
        if pair:
            return MatchResult(
                transaction_id=pair[1],
                duplicate_second_id=pair[1],
                scores={pair[1]: 10.0},
            )

    amounts = extract_amounts(complaint)
    phones = extract_phones(complaint)
    hints = _complaint_time_hints(complaint)

    scores: dict[str, float] = {}
    for txn in transactions:
        score = 0.0
        if amounts:
            if any(abs(txn.amount - amount) < 0.01 for amount in amounts):
                score += 3.0
        else:
            score += 0.5

        score += _time_score(txn, hints)
        score += _type_score(txn, complaint, case_type)

        txn_phone = normalize_phone(txn.counterparty) if txn.counterparty.startswith("+") else ""
        if phones and txn_phone and txn_phone in phones:
            score += 3.0

        if case_type == CaseType.PAYMENT_FAILED and txn.status.value == "failed":
            score += 2.0
        if case_type == CaseType.AGENT_CASH_IN_ISSUE and txn.status.value == "pending":
            score += 2.0
        if case_type == CaseType.MERCHANT_SETTLEMENT_DELAY and txn.status.value == "pending":
            score += 2.0

        scores[txn.transaction_id] = score

    if not scores:
        return MatchResult(transaction_id=None, scores=scores)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_id, best_score = ranked[0]

    if best_score < 2.0:
        return MatchResult(transaction_id=None, ambiguous=True, scores=scores)

    if len(ranked) >= 2:
        second_score = ranked[1][1]
        if second_score > 0 and (best_score - second_score) < 1.0:
            return MatchResult(transaction_id=None, ambiguous=True, scores=scores)

        amount_matches = [
            txn_id
            for txn_id, score in ranked
            if score >= best_score - 0.5 and amounts and score >= 3.0
        ]
        if len(amount_matches) >= 2 and case_type in {
            CaseType.WRONG_TRANSFER,
            CaseType.OTHER,
        }:
            return MatchResult(transaction_id=None, ambiguous=True, scores=scores)

    return MatchResult(transaction_id=best_id, scores=scores)


def count_prior_transfers_to_counterparty(
    transactions: list[Transaction],
    matched_id: str,
) -> int:
    matched = next((t for t in transactions if t.transaction_id == matched_id), None)
    if matched is None or matched.type != TransactionType.TRANSFER:
        return 0

    matched_ts = _parse_ts(matched.timestamp)
    count = 0
    for txn in transactions:
        if txn.transaction_id == matched_id:
            continue
        if txn.type != TransactionType.TRANSFER:
            continue
        if txn.counterparty != matched.counterparty:
            continue
        if txn.status.value != "completed":
            continue
        txn_ts = _parse_ts(txn.timestamp)
        if matched_ts and txn_ts and txn_ts < matched_ts:
            count += 1
    return count
