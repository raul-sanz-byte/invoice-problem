"""Deterministic and agentic self-correction engine for invoices.

Attempts to automatically repair validation and arithmetic errors using:
1. Rule-based deterministic correction (math recomputation, date deduction, catalog name alignment).
2. LLM-powered self-correction loop (crystallizing validation feedback back to the LLM).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any

from invoice_pipeline.models import Invoice, LineItem, ValidationResult, ValidationSeverity

logger = logging.getLogger(__name__)


def deterministic_self_correct(
    invoice: Invoice,
    validation: ValidationResult,
    database: Any = None,
    repair_stated_totals: bool = False,
) -> tuple[Invoice, list[str]]:
    """Attempts to deterministically correct arithmetic and inventory discrepancies.

    Args:
        invoice: The invoice to inspect and repair.
        validation: The validation result containing issues.
        database: Optional product database for catalog alignment.
        repair_stated_totals: If True, recalibrates stated subtotal/total to match
                              line item sums. If False, preserves stated document totals
                              so that vendor billing errors remain visible.

    Returns:
        Tuple of (possibly_corrected_invoice, list_of_applied_corrections).
    """
    corrections: list[str] = []
    new_items: list[LineItem] = []
    has_item_changes = False

    # 1. Line item math recomputation
    for idx, it in enumerate(invoice.line_items):
        expected_amt = (it.quantity * it.unit_price).quantize(Decimal("0.01"))
        if it.amount is None or (repair_stated_totals and abs(it.amount - expected_amt) > Decimal("0.01")):
            has_discount = bool(
                it.note
                and any(w in it.note.lower() for w in ["discount", "volume"])
            )
            if not has_discount:
                corrections.append(
                    f"Recalculated line item {idx} ('{it.item}') amount from {it.amount} to {expected_amt}"
                )
                it = it.model_copy(update={"amount": expected_amt})
                has_item_changes = True
        new_items.append(it)

    # 2. Inventory name fuzzy-alignment with catalog
    if database and hasattr(database, "get_products"):
        try:
            catalog = database.get_products()
            cat_map = {
                p["name"].lower().replace(" ", "").replace("-", "_"): p["name"]
                for p in catalog
            }
            aligned_items: list[LineItem] = []
            for it in new_items:
                key = it.item.lower().replace(" ", "").replace("-", "_")
                if key in cat_map and it.item != cat_map[key]:
                    corrected_name = cat_map[key]
                    corrections.append(
                        f"Aligned line item name '{it.item}' to catalog name '{corrected_name}'"
                    )
                    it = it.model_copy(update={"item": corrected_name})
                    has_item_changes = True
                aligned_items.append(it)
            new_items = aligned_items
        except Exception as e:
            logger.warning("Could not cross-reference catalog during self-correction: %s", e)

    # 3. Subtotal & Total recomputation
    computed_subtotal = sum(
        (li.amount for li in new_items if li.amount is not None),
        Decimal("0.00"),
    )
    new_subtotal = invoice.subtotal
    new_tax_amt = invoice.tax_amount
    new_total = invoice.total

    if invoice.subtotal is None or (repair_stated_totals and abs(invoice.subtotal - computed_subtotal) > Decimal("0.01")):
        corrections.append(f"Corrected subtotal from {invoice.subtotal} to {computed_subtotal}")
        new_subtotal = computed_subtotal

    if invoice.tax_rate is not None and new_subtotal is not None:
        expected_tax = (new_subtotal * invoice.tax_rate).quantize(Decimal("0.01"))
        if invoice.tax_amount is None or (repair_stated_totals and abs(invoice.tax_amount - expected_tax) > Decimal("0.01")):
            corrections.append(f"Corrected tax_amount from {invoice.tax_amount} to {expected_tax}")
            new_tax_amt = expected_tax

    shipping = invoice.shipping or Decimal("0.00")
    tax = new_tax_amt or Decimal("0.00")
    base_subtotal = new_subtotal if new_subtotal is not None else computed_subtotal
    expected_total = base_subtotal + tax + shipping

    if invoice.total is None or (repair_stated_totals and abs(invoice.total - expected_total) > Decimal("0.01")):
        corrections.append(f"Corrected total from {invoice.total} to {expected_total}")
        new_total = expected_total

    # 4. Due date deduction if identical to invoice date and payment terms specify days
    new_due_date = invoice.due_date
    if (
        new_due_date == invoice.date
        and invoice.payment_terms_days
        and invoice.payment_terms_days > 0
    ):
        inferred = invoice.date + timedelta(days=invoice.payment_terms_days)
        corrections.append(f"Inferred due_date from payment terms days: {inferred}")
        new_due_date = inferred

    if not corrections:
        return invoice, []

    corrected_invoice = invoice.model_copy(
        update={
            "line_items": new_items,
            "subtotal": new_subtotal,
            "tax_amount": new_tax_amt,
            "total": new_total,
            "due_date": new_due_date,
        }
    )
    return corrected_invoice, corrections
