from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from dateutil import parser


def normalize_date(raw: str) -> date | None:
    if not raw:
        return None
    raw_str = str(raw).strip()
    if raw_str.lower() in ("yesterday", "today", "tomorrow", "immediate", "immediately", "none", "null"):
        return None
    try:
        dt = parser.parse(raw_str, dayfirst=False)
        return dt.date()
    except (ValueError, TypeError):
        return None


def normalize_currency_amount(raw: Any) -> Decimal | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, Decimal):
        return raw
    # Extract the first valid numeric amount (handling commas, negatives, decimals)
    m = re.search(r"[-+]?\d+(?:,\d+)*(?:\.\d+)?", str(raw))
    if m:
        cleaned = m.group(0).replace(",", "")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def normalize_payment_terms(raw: str) -> tuple[str, int | None]:
    if not isinstance(raw, str):
        return str(raw), None
    raw = raw.strip()
    raw_lower = raw.lower()

    match = re.search(r"net\s*(\d+)", raw_lower)
    if match:
        days = int(match.group(1))
        return (f"Net {days}", days)

    if any(term in raw_lower for term in ("immediate", "immediately")):
        return ("Immediate", 0)

    if "due on receipt" in raw_lower:
        return ("Due on receipt", 0)

    return (raw, None)


def normalize_invoice_id(raw: str) -> str:
    return str(raw).strip()
