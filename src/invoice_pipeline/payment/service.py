"""Payment execution service with human-in-the-loop and fraud guards."""

from __future__ import annotations

import logging
from typing import Any

from invoice_pipeline.models import (
    HumanApprovalStatus,
    Invoice,
    InvoiceReview,
    PaymentStatus,
    ReviewDecision,
)

logger = logging.getLogger(__name__)


def mock_payment(vendor: str, amount: Any) -> dict[str, Any]:
    """Mock payment execution requested by user specification."""
    print(f"Paid {amount} to {vendor}")
    return {"status": "success"}


def process_payment(
    invoice: Invoice,
    review: InvoiceReview,
    amount_to_pay: Any = None,
) -> tuple[PaymentStatus, dict[str, Any] | None]:
    """Evaluate whether an invoice can be paid and execute payment if approved.

    Rules:
    - If review requires human approval, payment is HELD (PENDING_APPROVAL).
    - If review decision is REJECTED, payment is REJECTED (no money sent).
    - If review is AUTO_APPROVED or has HumanApprovalStatus.APPROVED, payment is executed.
    - If invoice is a revision with additional items, only the delta amount is paid.
    """
    # Guard 1: Rejection
    if review.decision == ReviewDecision.REJECTED or review.human_approval_status == HumanApprovalStatus.REJECTED:
        logger.warning(
            "Payment BLOCKED for invoice %s: Decision is REJECTED",
            invoice.invoice_id,
        )
        return PaymentStatus.REJECTED, {
            "status": "blocked",
            "reason": "Invoice review rejected",
        }

    # Guard 2: Requires Human Approval but not yet approved
    if review.requires_human and review.human_approval_status != HumanApprovalStatus.APPROVED:
        logger.info(
            "Payment HELD for invoice %s: Pending human approval",
            invoice.invoice_id,
        )
        return PaymentStatus.PENDING_APPROVAL, {
            "status": "held",
            "reason": "Pending human approval",
        }

    # If approved (either auto-approved or human approved)
    pay_amount = amount_to_pay if amount_to_pay is not None else (review.amount_to_pay if review.amount_to_pay is not None else invoice.total)
    try:
        payment_result = mock_payment(invoice.vendor.name, pay_amount)
        logger.info(
            "Payment EXECUTED for invoice %s: %s %s to %s",
            invoice.invoice_id,
            invoice.currency,
            pay_amount,
            invoice.vendor.name,
        )
        return PaymentStatus.PAID, {
            "status": "success",
            "amount_paid": float(pay_amount),
            "is_revision": getattr(review, "is_revision", False),
            "previous_total": float(review.previous_total) if getattr(review, "previous_total", None) else None,
            "new_total": float(invoice.total),
        }
    except Exception as e:
        logger.error(
            "Payment FAILED for invoice %s: %s",
            invoice.invoice_id,
            e,
        )
        return PaymentStatus.FAILED, {
            "status": "failed",
            "error": str(e),
        }
