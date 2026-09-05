"""Converts raw extracted dictionary into a validated Invoice domain model."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from invoice_pipeline.extraction.normalizers import (
    normalize_currency_amount,
    normalize_date,
    normalize_invoice_id,
    normalize_payment_terms,
)
from invoice_pipeline.extraction.vocabulary import get_vocabulary_manager, VocabularyManager
from invoice_pipeline.models import Invoice, LineItem, Vendor


def build_invoice_from_dict(
    data: dict[str, Any],
    vocab_mgr: VocabularyManager | None = None,
) -> Invoice:
    """Build and validate an Invoice model from a normalized dictionary.

    Handles field aliases, vocabulary resolution, type coercion, and defaults.
    """
    vocab = vocab_mgr or get_vocabulary_manager()
    normalized: dict[str, Any] = {}
    for k, v in data.items():
        canonical = vocab.resolve(k)
        if canonical and canonical not in normalized:
            normalized[canonical] = v
        else:
            normalized.setdefault(k, v)
    data = normalized
    # ── Resolve invoice ID ──────────────────────────────────────────────
    raw_id = (
        data.get("invoice_id")
        or data.get("invoice_number")
        or data.get("inv_number")
        or data.get("inv #")
        or data.get("id")
    )
    if not raw_id:
        raise ValueError("Missing critical field: invoice_id")
    invoice_id = normalize_invoice_id(str(raw_id))

    # ── Resolve date ────────────────────────────────────────────────────
    raw_date = data.get("date") or data.get("invoice_date") or data.get("dt")
    if not raw_date:
        raise ValueError("Missing critical field: date")
    dt = normalize_date(str(raw_date))
    if not dt:
        raise ValueError(f"Invalid date: {raw_date}")

    # ── Resolve payment terms ───────────────────────────────────────────
    raw_terms = data.get("payment_terms") or data.get("pymnt_terms") or data.get("terms")
    payment_terms, payment_terms_days = None, None
    if raw_terms:
        payment_terms, payment_terms_days = normalize_payment_terms(str(raw_terms))
    if data.get("payment_terms_days") is not None:
        try:
            payment_terms_days = int(data["payment_terms_days"])
        except (ValueError, TypeError):
            pass

    # ── Resolve due date ────────────────────────────────────────────────
    raw_due = str(data.get("due_date") or data.get("due_dt") or data.get("due") or "").strip()
    due_date = None
    if raw_due:
        if "yesterday" in raw_due.lower():
            due_date = dt - timedelta(days=1)
        else:
            due_date = normalize_date(raw_due)

    if due_date is None:
        if payment_terms_days is not None:
            due_date = dt + timedelta(days=payment_terms_days)
        else:
            due_date = dt

    # ── Resolve vendor ──────────────────────────────────────────────────
    v = data.get("vendor") or data.get("vndr") or data.get("vendor_name")
    if not v:
        vendor = Vendor(name="[MISSING VENDOR NAME]")
    elif isinstance(v, str):
        vendor = Vendor(name=v.strip() or "[MISSING VENDOR NAME]")
    elif isinstance(v, dict):
        name = v.get("name") or v.get("vendor_name") or ""
        name_str = str(name).strip() if name else ""
        vendor = Vendor(name=name_str or "[MISSING VENDOR NAME]", address=v.get("address"))
    else:
        vendor = Vendor(name="[MISSING VENDOR NAME]")

    # ── Resolve line items ──────────────────────────────────────────────
    raw_items = data.get("line_items") or data.get("items") or []
    if not raw_items:
        raise ValueError("Missing critical field: line_items (at least 1 required)")

    line_items: list[LineItem] = []
    for li in raw_items:
        if not isinstance(li, dict):
            continue
        item_name = li.get("item") or li.get("name") or li.get("description") or "Item"
        raw_qty = li.get("quantity") if li.get("quantity") is not None else li.get("qty", 1)
        qty = Decimal(str(raw_qty))

        raw_price = li.get("unit_price") if li.get("unit_price") is not None else li.get("price", 0)
        unit_price = normalize_currency_amount(raw_price) or Decimal("0")

        raw_amt = li.get("amount") if li.get("amount") is not None else li.get("line_total")
        amount = normalize_currency_amount(raw_amt) if raw_amt is not None else (qty * unit_price)

        note = li.get("note") or li.get("notes")

        line_items.append(
            LineItem(
                item=str(item_name),
                quantity=qty,
                unit_price=unit_price,
                amount=amount,
                note=str(note) if note else None,
            )
        )

    if not line_items:
        raise ValueError("No valid line items found")

    # ── Resolve totals ──────────────────────────────────────────────────
    raw_total = (
        data.get("total")
        or data.get("total_amount")
        or data.get("amt")
        or data.get("amount")
    )
    if raw_total is None:
        # Compute total from items
        raw_total = sum(li.amount for li in line_items if li.amount is not None)

    total = normalize_currency_amount(raw_total)
    if total is None:
        raise ValueError(f"Invalid total: {raw_total}")

    subtotal = normalize_currency_amount(data.get("subtotal")) if data.get("subtotal") else None
    tax_rate = normalize_currency_amount(data.get("tax_rate")) if data.get("tax_rate") else None
    tax_amount = normalize_currency_amount(data.get("tax_amount") or data.get("tax")) if (data.get("tax_amount") or data.get("tax")) else None
    shipping = normalize_currency_amount(data.get("shipping")) if data.get("shipping") else None

    # Notes & Revision
    notes = data.get("notes") or data.get("note")
    revision = data.get("revision") or data.get("rev")
    currency = data.get("currency") or "USD"

    return Invoice(
        invoice_id=invoice_id,
        date=dt,
        due_date=due_date,
        vendor=vendor,
        line_items=line_items,
        subtotal=subtotal,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        total=total,
        currency=str(currency),
        payment_terms=payment_terms,
        payment_terms_days=payment_terms_days,
        shipping=shipping,
        notes=str(notes) if notes else None,
        revision=str(revision) if revision else None,
    )
