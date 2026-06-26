import re

_BN_TO_ASCII = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def normalize_digits(text: str) -> str:
    """Convert Bangla numerals to ASCII digits."""
    return text.translate(_BN_TO_ASCII)


def extract_amounts(text: str) -> list[float]:
    """Extract monetary amounts from English or Bangla complaint text."""
    normalized = normalize_digits(text.lower())
    amounts: list[float] = []
    for match in re.finditer(r"\b(\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?\b", normalized):
        raw = match.group(1).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        if value > 0:
            amounts.append(value)
    return amounts
