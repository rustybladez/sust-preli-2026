import re

_CREDENTIAL_REQUEST = re.compile(
    r"\b("
    r"share\s+(your\s+)?(pin|otp|password|cvv|card\s*number)|"
    r"send\s+(your\s+)?(pin|otp|password)|"
    r"provide\s+(your\s+)?(pin|otp|password)|"
    r"verify\s+by\s+sharing"
    r")\b",
    re.IGNORECASE,
)

_UNAUTHORIZED_PROMISE = re.compile(
    r"\b("
    r"we\s+will\s+refund|will\s+be\s+refunded|money\s+will\s+be\s+returned\s+to\s+you|"
    r"we\s+have\s+reversed|has\s+been\s+reversed|account\s+unblocked|"
    r"we\s+will\s+recover|guaranteed\s+refund"
    r")\b",
    re.IGNORECASE,
)

_THIRD_PARTY = re.compile(
    r"\b(contact|call|whatsapp|message)\s+(this|the following)\s+(number|person|agent)\b",
    re.IGNORECASE,
)

_SAFE_REFUND_LINE = (
    "any eligible amount will be returned through official channels"
)
_SAFE_REVIEW_LINE = (
    "Our team will review the case and contact you through official support channels."
)


def apply_safety(
    customer_reply: str,
    recommended_next_action: str,
    *,
    reply_language: str = "en",
) -> tuple[str, str]:
    reply = _sanitize_text(customer_reply)
    action = _sanitize_text(recommended_next_action)

    reply = _UNAUTHORIZED_PROMISE.sub(_SAFE_REFUND_LINE, reply)
    action = _UNAUTHORIZED_PROMISE.sub(
        "initiate the standard review workflow per policy", action
    )

    if _CREDENTIAL_REQUEST.search(reply):
        reply = _strip_credential_requests(reply)
    if _CREDENTIAL_REQUEST.search(action):
        action = _strip_credential_requests(action)

    if _THIRD_PARTY.search(reply):
        reply = re.sub(
            _THIRD_PARTY,
            "please contact us through official support channels only",
            reply,
            flags=re.IGNORECASE,
        )

    reply = _ensure_safety_footer(reply, reply_language)
    return reply.strip(), action.strip()


def _sanitize_text(text: str) -> str:
    cleaned = text
    cleaned = re.sub(
        r"(?i)ignore (all )?(previous )?instructions.*",
        "",
        cleaned,
    )
    return cleaned.strip()


def _strip_credential_requests(text: str) -> str:
    return _CREDENTIAL_REQUEST.sub(
        "please do not share your PIN or OTP with anyone",
        text,
    )


def _ensure_safety_footer(text: str, language: str) -> str:
    en_footer = "Please do not share your PIN or OTP with anyone."
    bn_footer = "অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না."

    if language == "bn":
        if "পিন" not in text and "ওটিপি" not in text:
            return f"{text.rstrip('.')}। {bn_footer}"
        return text

    if "pin" not in text.lower() and "otp" not in text.lower():
        return f"{text.rstrip('.')}. {en_footer}"
    return text


def _safety_check_text(text: str) -> str:
    """Normalize text so safety warnings ('do not share PIN') are not flagged."""
    return re.sub(
        r"(?i)\b(?:do\s+not|don't|never|please\s+do\s+not)\s+share\b[^.!?]*[.!?]?",
        " ",
        text,
    )


def is_safe_reply(text: str) -> bool:
    check_text = _safety_check_text(text)
    return not (
        _CREDENTIAL_REQUEST.search(check_text)
        or _UNAUTHORIZED_PROMISE.search(check_text)
        or _THIRD_PARTY.search(check_text)
    )
