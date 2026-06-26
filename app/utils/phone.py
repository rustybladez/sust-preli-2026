import re

from app.utils.bn_numerals import normalize_digits

_PHONE_PATTERN = re.compile(
    r"(?:\+?880|0)?1[3-9]\d{8}|\+880\d{10}"
)


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", normalize_digits(raw))
    if digits.startswith("880"):
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 11:
        return f"+880{digits[1:]}"
    if len(digits) == 10 and digits.startswith("1"):
        return f"+880{digits}"
    return raw.strip()


def extract_phones(text: str) -> list[str]:
    normalized = normalize_digits(text)
    phones: list[str] = []
    for match in _PHONE_PATTERN.finditer(normalized):
        phones.append(normalize_phone(match.group(0)))
    return list(dict.fromkeys(phones))
