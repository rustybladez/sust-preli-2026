from app.schemas.enums import CaseType, Department, EvidenceVerdict, Severity, UserType


def resolve_department(case_type: CaseType, evidence: EvidenceVerdict) -> Department:
    mapping: dict[CaseType, Department] = {
        CaseType.WRONG_TRANSFER: Department.DISPUTE_RESOLUTION,
        CaseType.PAYMENT_FAILED: Department.PAYMENTS_OPS,
        CaseType.REFUND_REQUEST: Department.CUSTOMER_SUPPORT,
        CaseType.DUPLICATE_PAYMENT: Department.PAYMENTS_OPS,
        CaseType.MERCHANT_SETTLEMENT_DELAY: Department.MERCHANT_OPERATIONS,
        CaseType.AGENT_CASH_IN_ISSUE: Department.AGENT_OPERATIONS,
        CaseType.PHISHING_OR_SOCIAL_ENGINEERING: Department.FRAUD_RISK,
        CaseType.OTHER: Department.CUSTOMER_SUPPORT,
    }
    dept = mapping[case_type]
    if case_type == CaseType.REFUND_REQUEST and evidence == EvidenceVerdict.INCONSISTENT:
        return Department.DISPUTE_RESOLUTION
    return dept


def resolve_severity(
    case_type: CaseType,
    evidence: EvidenceVerdict,
    user_type: UserType | None,
) -> Severity:
    if case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
        return Severity.CRITICAL
    if case_type == CaseType.PAYMENT_FAILED:
        return Severity.HIGH
    if case_type == CaseType.DUPLICATE_PAYMENT:
        return Severity.HIGH
    if case_type == CaseType.AGENT_CASH_IN_ISSUE:
        return Severity.HIGH
    if case_type == CaseType.WRONG_TRANSFER:
        if evidence in {EvidenceVerdict.INCONSISTENT, EvidenceVerdict.INSUFFICIENT_DATA}:
            return Severity.MEDIUM
        return Severity.HIGH
    if case_type == CaseType.MERCHANT_SETTLEMENT_DELAY:
        return Severity.MEDIUM
    if case_type == CaseType.REFUND_REQUEST:
        return Severity.LOW
    if case_type == CaseType.OTHER:
        return Severity.LOW
    return Severity.MEDIUM


def requires_human_review(
    case_type: CaseType,
    evidence: EvidenceVerdict,
    severity: Severity,
    matched_id: str | None,
) -> bool:
    if case_type == CaseType.PHISHING_OR_SOCIAL_ENGINEERING:
        return True
    if case_type == CaseType.WRONG_TRANSFER and matched_id:
        return True
    if case_type == CaseType.DUPLICATE_PAYMENT and matched_id:
        return True
    if case_type == CaseType.AGENT_CASH_IN_ISSUE and matched_id:
        return True
    if evidence == EvidenceVerdict.INCONSISTENT:
        return True
    if severity in {Severity.CRITICAL, Severity.HIGH} and case_type in {
        CaseType.WRONG_TRANSFER,
        CaseType.DUPLICATE_PAYMENT,
    }:
        return True
    return False
