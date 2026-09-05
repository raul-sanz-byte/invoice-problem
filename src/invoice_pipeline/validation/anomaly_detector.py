"""Anomaly detection for invoice fraud, urgency pressure, and suspicious fields."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from invoice_pipeline.models import Invoice, ValidationResult, ValidationSeverity


def detect_anomalies(invoice: Invoice) -> ValidationResult:
    """Analyze invoice for suspicious characteristics, fraud signals, and discrepancies."""
    result = ValidationResult()
    today = date.today()

    # 1. Due date checks
    if invoice.due_date:
        # Impossible timeline: due date is BEFORE the invoice was even created
        if invoice.due_date < invoice.date:
            result.flag_suspicious(
                f"Due date {invoice.due_date} is before invoice date {invoice.date}"
            )
        elif invoice.due_date < today:
            # Informational note that the invoice is overdue
            result.add_issue(
                ValidationSeverity.INFO,
                f"Invoice is overdue (due date {invoice.due_date} is in the past)",
                field="due_date",
            )

    # 2. Urgency and pressure language
    if invoice.notes:
        notes_lower = invoice.notes.lower()
        urgent_keywords = ["urgent", "immediate", "immediately", "asap", "penalty", "penalties"]
        if any(keyword in notes_lower for keyword in urgent_keywords):
            result.flag_suspicious("Invoice contains urgent/pressure language")

        wire_keywords = ["wire transfer", "wire"]
        if any(keyword in notes_lower for keyword in wire_keywords):
            result.flag_suspicious("Invoice requests wire transfer payment")

        if "yesterday" in notes_lower:
            result.flag_suspicious("Due date specified as 'yesterday'")

    # 3. Large amounts
    if invoice.total > Decimal("50000"):
        result.flag_suspicious(f"Unusually large invoice total: ${invoice.total}")

    # 4. Vendor name checks
    if not invoice.vendor or not invoice.vendor.name or invoice.vendor.name.strip().lower() in ("[missing vendor name]", "unknown vendor"):
        result.flag_suspicious("Vendor name is missing or unknown")
    elif invoice.vendor and invoice.vendor.name:
        suspicious_vendors = ["fraud", "fake", "scam", "shady"]
        if any(keyword in invoice.vendor.name.lower() for keyword in suspicious_vendors):
            result.flag_suspicious("Vendor name contains suspicious keywords")

    # 5. Line item and financial integrity checks
    if any(li.quantity <= 0 for li in invoice.line_items):
        result.flag_suspicious("Invoice contains invalid/negative item quantities")

    if invoice.total <= Decimal("0"):
        result.flag_suspicious(f"Invoice has non-positive financial total (${invoice.total})")

    for li in invoice.line_items:
        if any(k in li.item.lower() for k in ("fake", "fraud", "scam", "dummy")):
            result.flag_suspicious(f"Line item '{li.item}' contains suspicious keywords")

    # 6. Large amount with zero tax
    if invoice.total > Decimal("10000"):
        if (invoice.tax_rate is None or invoice.tax_rate == Decimal("0")) and (
            invoice.tax_amount is None or invoice.tax_amount == Decimal("0")
        ):
            result.add_issue(
                ValidationSeverity.INFO,
                "Large invoice with zero tax",
                field="tax_amount",
            )

    return result
