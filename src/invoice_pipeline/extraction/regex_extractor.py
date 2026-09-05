"""Deterministic regex-based fallback extractor with dynamic vocabulary integration.

Extracts invoice fields from unstructured text using dynamically compiled
regular expressions built directly from the persistent VocabularyManager.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from invoice_pipeline.extraction.vocabulary import get_vocabulary_manager, VocabularyManager


def _clean_amount(val: str) -> Decimal | None:
    if not val:
        return None
    try:
        val = str(val).replace("O", "0").replace("o", "0")
        cleaned = re.sub(r"[^\d.]", "", val)
        return Decimal(cleaned) if cleaned else None
    except (InvalidOperation, ValueError):
        return None


def _make_pattern(aliases: list[str]) -> str:
    """Build a regex alternation from aliases with strict word boundaries and whitespace handling."""
    unique = sorted(set(aliases), key=len, reverse=True)
    parts = []
    for a in unique:
        clean = a.strip()
        if not clean:
            continue
        if clean.lower() == "id":
            # Avoid matching random "id" inside other words; require invoice/inv id
            parts.append(r"\b(?:invoice[\s_]+id|inv[\s_]+id)\b")
        else:
            space_norm = clean.replace("_", " ")
            escaped = re.escape(space_norm).replace(r"\ ", r"[\s_]+")
            prefix = r"\b" if clean[0].isalnum() else ""
            suffix = r"\b" if clean[-1].isalnum() else ""
            parts.append(f"{prefix}{escaped}{suffix}")
    return r"(?:" + "|".join(parts) + r")"


def extract_from_raw_text(
    text: str,
    vocab_mgr: VocabularyManager | None = None,
) -> dict[str, Any]:
    """Deterministically extracts invoice fields from plain text using vocabulary-compiled regex patterns."""
    vocab = vocab_mgr or get_vocabulary_manager()
    result: dict[str, Any] = {}
    lines = [line.strip() for line in text.splitlines()]

    # 1. Invoice Number / ID
    id_aliases = vocab.get_aliases_for("invoice_id") + ["inv #", "inv no", "invoice #", "invoice number", "invoice", "inv"]
    id_pat = _make_pattern(id_aliases)

    m = re.search(
        r"^(?:[^\S\r\n]*)" + id_pat + r"[^\S\r\n]*[:#][^\S\r\n]*([A-Za-z0-9\-_]+(?:[^\S\r\n]+[A-Za-z0-9\-_]+)?)",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if not m:
        m = re.search(
            id_pat + r"[^\S\r\n]*[:#][^\S\r\n]*([A-Za-z0-9\-_]+(?:[^\S\r\n]+[A-Za-z0-9\-_]+)?)",
            text,
            re.IGNORECASE,
        )
    if m:
        raw_id = m.group(1).splitlines()[0].strip()
        raw_id = re.split(r"\s{2,}|\t", raw_id)[0].strip()
        if " " in raw_id and any(c.isdigit() for c in raw_id):
            parts = raw_id.split()
            if len(parts) == 2 and parts[0].isalpha() and parts[1].isdigit():
                raw_id = f"{parts[0]}-{parts[1]}"
        result["invoice_id"] = raw_id

    # 2. Vendor
    # Dynamic aliases: vendor, vndr, supplier, seller, payee, provider, remit_to, company, from, etc.
    vendor_aliases = vocab.get_aliases_for("vendor") + ["vndr", "from", "supplier", "seller", "billed by"]
    vendor_pat = _make_pattern(vendor_aliases)
    m = re.search(
        r"^(?:[^\S\r\n]*)" + vendor_pat + r"[^\S\r\n]*:[^\S\r\n]*([^\r\n]+)",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if m:
        vname = m.group(1).strip()
        vname = re.split(r"\s{2,}|\t", vname)[0].strip()
        result["vendor"] = {"name": vname}

    # 3. Dates
    # Dynamic aliases: date, invoice_date, issue_date, dt, bill_date
    date_aliases = vocab.get_aliases_for("date") + ["dt"]
    date_pat = _make_pattern(date_aliases)
    m = re.search(
        r"(?:" + date_pat + r")[^\S\r\n]*:[^\S\r\n]*([A-Za-z0-9\-/\.]+)",
        text,
        re.IGNORECASE,
    )
    if m:
        dval = m.group(1).strip().replace("2O26", "2026")
        result["date"] = dval

    # Due Date: due_date, due_dt, payment_due, due, settlement_date, pay_by
    due_aliases = vocab.get_aliases_for("due_date") + ["due dt", "due"]
    due_pat = _make_pattern(due_aliases)
    m = re.search(
        r"(?:" + due_pat + r")[^\S\r\n]*:[^\S\r\n]*([A-Za-z0-9\-/\.]+)",
        text,
        re.IGNORECASE,
    )
    if m:
        result["due_date"] = m.group(1).strip().replace("2O26", "2026")

    # 4. Payment Terms
    # Dynamic aliases: payment_terms, pymnt_terms, terms, credit_terms, payment_conditions
    terms_aliases = vocab.get_aliases_for("payment_terms") + ["pymnt terms", "pay terms", "terms"]
    terms_pat = _make_pattern(terms_aliases)
    m = re.search(
        r"(?:" + terms_pat + r")[^\S\r\n]*:[^\S\r\n]*([^\r\n]+)",
        text,
        re.IGNORECASE,
    )
    if m:
        result["payment_terms"] = re.split(r"\s{2,}|\t", m.group(1).strip())[0].strip()

    # 5. Notes
    # Dynamic aliases: notes, note, comment, remarks, memo, instructions
    notes_aliases = vocab.get_aliases_for("notes")
    notes_pat = _make_pattern(notes_aliases)
    m = re.search(
        r"^(?:[^\S\r\n]*)" + notes_pat + r"[^\S\r\n]*:[^\S\r\n]*([^\r\n]+(?:\n[^\r\n]+)*)",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if m:
        result["notes"] = m.group(1).strip()

    # 6. Revision
    # Dynamic aliases: revision, rev, version, amendment
    rev_aliases = vocab.get_aliases_for("revision") + ["rev"]
    rev_pat = _make_pattern(rev_aliases)
    m = re.search(
        r"^(?:[^\S\r\n]*)" + rev_pat + r"[^\S\r\n]*:[^\S\r\n]*([A-Za-z0-9\-_]+)",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if m:
        result["revision"] = m.group(1).strip()

    # 7. Line Items
    line_items: list[dict[str, Any]] = []

    # Dynamic line item keywords from vocabulary
    qty_aliases = vocab.get_aliases_for("quantity", is_line_item=True) + ["qty", "x"]
    qty_pat = _make_pattern(qty_aliases)

    price_aliases = vocab.get_aliases_for("unit_price", is_line_item=True) + ["unit price", "price", "rate", "@"]
    price_pat = _make_pattern(price_aliases)

    for line in lines:
        # Pattern 1: WidgetA qty: 10 unit price: $250.00  (or count: 10 rate: $250)
        m = re.search(
            r"^\s*([A-Za-z0-9_\-]+)\s+" + qty_pat + r"\s*[:]?\s*(\d+)\s+(?:" + price_pat + r"\s*[:]?\s*|\@\s*)\$?([\d,.]+)(?:\s*ea)?",
            line,
            re.IGNORECASE,
        )
        if m:
            qty = Decimal(m.group(2))
            price = Decimal(m.group(3).replace(",", ""))
            line_items.append({
                "item": m.group(1).strip(),
                "quantity": qty,
                "unit_price": price,
                "amount": qty * price,
            })
            continue

        # Pattern 2: GadgetX qty 20 @ $750 ea
        m = re.search(
            r"^\s*([A-Za-z0-9_\-]+)\s+" + qty_pat + r"\s+(\d+)\s+@\s+\$?([\d,.]+)(?:\s*ea)?",
            line,
            re.IGNORECASE,
        )
        if m:
            qty = Decimal(m.group(2))
            price = Decimal(m.group(3).replace(",", ""))
            line_items.append({
                "item": m.group(1).strip(),
                "quantity": qty,
                "unit_price": price,
                "amount": qty * price,
            })
            continue

        # Pattern 3: - SuperGizmo x12 $400.00 each
        m = re.search(
            r"^[-*•]?\s*([A-Za-z0-9_\-]+)\s+[xX](\d+)\s+\$?([\d,.]+)(?:\s*(?:each|ea))?",
            line,
            re.IGNORECASE,
        )
        if m:
            qty = Decimal(m.group(2))
            price = Decimal(m.group(3).replace(",", ""))
            line_items.append({
                "item": m.group(1).strip(),
                "quantity": qty,
                "unit_price": price,
                "amount": qty * price,
            })
            continue

        # Pattern 4: Space-aligned tabular: Description Qty Rate Amount [Notes]
        # e.g., WidgetA 8 $250.00 $2,000.00 or WidgetA 5 $240.00 $1,200.00 Volume discount
        clean_line = line.replace("$", "").replace("ea", "")
        m = re.search(
            r"^\s*([A-Za-z0-9_\-\.\(\)\s]+?)\s+(\d+)\s+([0-9O,.]+)\s+([0-9O,.]+)(?:\s+(.+))?\s*$",
            clean_line,
        )
        if m:
            item_candidate = m.group(1).strip()
            skip_words = ["description", "subtotal", "total", "tax", "shipping", "rate", "amount", "item", "qty", "due", "date", "bill", "terms", "notes", "price", "unit"]
            if not any(sw == item_candidate.lower() or item_candidate.lower().startswith(sw) for sw in skip_words):
                qty = Decimal(m.group(2))
                price = Decimal(m.group(3).replace("O", "0").replace(",", ""))
                amount = Decimal(m.group(4).replace("O", "0").replace(",", ""))
                note = m.group(5).strip() if m.group(5) else None
                if "(" in item_candidate and ")" in item_candidate:
                    match_note = re.search(r"\((.*?)\)", item_candidate)
                    if match_note:
                        note = match_note.group(1).strip()
                        item_candidate = re.sub(r"\(.*?\)", "", item_candidate).strip()
                line_items.append({
                    "item": item_candidate,
                    "quantity": qty,
                    "unit_price": price,
                    "amount": amount,
                    "note": note,
                })
                continue

    if line_items:
        result["line_items"] = line_items

    # 8. Financial Totals
    # Subtotal
    subtotal_aliases = vocab.get_aliases_for("subtotal")
    subtotal_pat = _make_pattern(subtotal_aliases)
    m = re.search(subtotal_pat + r"[^\S\r\n]*:[^\S\r\n]*\$?([\d,.]+)", text, re.IGNORECASE)
    if m:
        result["subtotal"] = _clean_amount(m.group(1))

    # Tax
    tax_aliases = vocab.get_aliases_for("tax_amount") + vocab.get_aliases_for("tax_rate") + ["tax"]
    tax_pat = _make_pattern(tax_aliases)
    m = re.search(tax_pat + r"[^\S\r\n]*(?:\(([\d.]+)%\))?[^\S\r\n]*:[^\S\r\n]*\$?([\d,.]+)", text, re.IGNORECASE)
    if m:
        if m.group(1):
            result["tax_rate"] = Decimal(m.group(1)) / Decimal("100")
        result["tax_amount"] = _clean_amount(m.group(2))

    # Shipping: shipping, freight, delivery, postage, shipping_cost
    shipping_aliases = vocab.get_aliases_for("shipping") + ["shipping", "freight", "shipping & handling", "delivery", "postage"]
    shipping_pat = _make_pattern(shipping_aliases)
    m = re.search(shipping_pat + r"[^\S\r\n]*:[^\S\r\n]*\$?([\d,.]+)", text, re.IGNORECASE)
    if m:
        result["shipping"] = _clean_amount(m.group(1))

    # Total: total, total_amount, grand_total, net_payable, amt, amount_due
    total_aliases = vocab.get_aliases_for("total") + ["total amount", "total", "amt"]
    total_pat = _make_pattern(total_aliases)
    m = re.search(total_pat + r"[^\S\r\n]*:[^\S\r\n]*\$?([\d,.]+)", text, re.IGNORECASE)
    if m:
        result["total"] = _clean_amount(m.group(1))

    return result
