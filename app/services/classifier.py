import re

from app.schemas.enums import CaseType
from app.utils.bn_numerals import normalize_digits

_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"ignore\s+(all\s+)?rules",
        r"you\s+are\s+now",
        r"system\s+prompt",
        r"admin\s+override",
        r"return\s+json\s+with",
        r"disregard\s+safety",
    )
]

_PHISHING_PATTERNS = re.compile(
    r"(otp|pin|password|scam|phishing|fake\s+call|social\s+engineering|"
    r"blocked\s+if\s+i\s+don'?t|share\s+it|"
    r"ওটিপি|পিন|পাসওয়ার্ড|জাল|প্রতারণা|ফিশিং)",
    re.IGNORECASE,
)

_DUPLICATE_PATTERNS = re.compile(
    r"(twice|duplicate|double\s+charg|deducted\s+twice|paid\s+twice|two\s+times|"
    r"দু'?বার|দুই\s*বার)",
    re.IGNORECASE,
)

_FAILED_PAYMENT_PATTERNS = re.compile(
    r"(failed|failure|unsuccessful|did\s+not\s+complete|"
    r"balance\s+was\s+deducted|deducted\s+but|"
    r"ব্যর্থ|কাটা\s+গেছে|ব্যালেন্স\s+কাট)",
    re.IGNORECASE,
)

_REFUND_PATTERNS = re.compile(
    r"(refund|return\s+my\s+money|money\s+back|change\s+my\s+mind|"
    r"don't\s+want\s+it|do\s+not\s+want|"
    r"ফেরত|রিফান্ড|টাকা\s+ফেরত)",
    re.IGNORECASE,
)

_WRONG_TRANSFER_PATTERNS = re.compile(
    r"(wrong\s+(number|person|recipient|account)|sent\s+to\s+wrong|sent\s+\d+.*\bwrong\b|"
    r"mistake\s+transfer|typed\s+wrong|didn'?t\s+get\s+it|not\s+received|"
    r"brother|sister|ভুল\s+নম্বর|ভুল\s+ব্যক্তি|পাই\s+নি)",
    re.IGNORECASE,
)

_SETTLEMENT_PATTERNS = re.compile(
    r"(settlement|settled|not\s+settled|sales\s+have\s+not|merchant|"
    r"সেটেলমেন্ট|মার্চেন্ট)",
    re.IGNORECASE,
)

_CASH_IN_PATTERNS = re.compile(
    r"(cash\s*in|cash-in|agent|balance\s+not|not\s+reflected|"
    r"ক্যাশ\s*ইন|এজেন্ট|ব্যালেন্স\s+আসেনি|টাকা\s+আসেনি)",
    re.IGNORECASE,
)


def sanitize_complaint(complaint: str) -> str:
    """Strip obvious prompt-injection lines from complaint text."""
    lines = complaint.splitlines()
    cleaned: list[str] = []
    for line in lines:
        if any(p.search(line) for p in _INJECTION_PATTERNS):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip() or complaint.strip()


def classify_case_type(complaint: str, user_type: str | None = None) -> CaseType:
    text = normalize_digits(complaint.lower())

    if _PHISHING_PATTERNS.search(text):
        return CaseType.PHISHING_OR_SOCIAL_ENGINEERING

    if user_type == "merchant" and _SETTLEMENT_PATTERNS.search(text):
        return CaseType.MERCHANT_SETTLEMENT_DELAY

    if _DUPLICATE_PATTERNS.search(text):
        return CaseType.DUPLICATE_PAYMENT

    if _FAILED_PAYMENT_PATTERNS.search(text):
        return CaseType.PAYMENT_FAILED

    if _CASH_IN_PATTERNS.search(text) and ("agent" in text or "এজেন্ট" in complaint):
        return CaseType.AGENT_CASH_IN_ISSUE

    if _SETTLEMENT_PATTERNS.search(text) and user_type == "merchant":
        return CaseType.MERCHANT_SETTLEMENT_DELAY

    # Wrong-transfer signals beat generic refund language ("get my money back").
    if _WRONG_TRANSFER_PATTERNS.search(text):
        return CaseType.WRONG_TRANSFER

    if _REFUND_PATTERNS.search(text):
        return CaseType.REFUND_REQUEST

    if _CASH_IN_PATTERNS.search(text):
        return CaseType.AGENT_CASH_IN_ISSUE

    if _SETTLEMENT_PATTERNS.search(text):
        return CaseType.MERCHANT_SETTLEMENT_DELAY

    return CaseType.OTHER
