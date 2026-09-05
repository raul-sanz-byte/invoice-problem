"""Unit tests for Pydantic models in the invoice pipeline."""

from datetime import date
from decimal import Decimal

import pytest
from invoice_pipeline.models import (
    FileFormat,
    Invoice,
    LineItem,
    Product,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
    Vendor,
)


def test_line_item_auto_computation():
    """Test that LineItem automatically computes amount = qty * unit_price when missing."""
    item = LineItem(item="WidgetA", quantity=10, unit_price=250.00)
    assert item.amount == Decimal("2500.00")
    assert isinstance(item.quantity, Decimal)
    assert isinstance(item.unit_price, Decimal)
    assert isinstance(item.amount, Decimal)


def test_line_item_explicit_amount():
    """Test that explicit amount is preserved (e.g. For discounted items)."""
    item = LineItem(
        item="WidgetA",
        quantity=5,
        unit_price=240.00,
        amount=1200.00,
        note="Volume discount",
    )
    assert item.amount == Decimal("1200.00")
    assert item.note == "Volume discount"


def test_vendor_model():
    """Test vendor model creation with and without address."""
    v1 = Vendor(name="Widgets Inc.")
    assert v1.name == "Widgets Inc."
    assert v1.address is None

    v2 = Vendor(name="Precision Parts Ltd.", address="742 Evergreen Terrace")
    assert v2.name == "Precision Parts Ltd."
    assert v2.address == "742 Evergreen Terrace"


def test_invoice_model():
    """Test full Invoice model with Decimal values."""
    inv = Invoice(
        invoice_id="INV-1001",
        date=date(2026, 1, 15),
        due_date=date(2026, 2, 1),
        vendor=Vendor(name="Widgets Inc."),
        line_items=[
            LineItem(item="WidgetA", quantity=10, unit_price=250.00),
            LineItem(item="WidgetB", quantity=5, unit_price=500.00),
        ],
        subtotal=5000.00,
        tax_rate=0.00,
        tax_amount=0.00,
        total=5000.00,
        payment_terms="Net 15",
        payment_terms_days=15,
    )
    assert inv.invoice_id == "INV-1001"
    assert inv.total == Decimal("5000.00")
    assert len(inv.line_items) == 2
    assert inv.payment_terms_days == 15


def test_validation_result_methods():
    """Test ValidationResult helper methods."""
    vr = ValidationResult()
    assert vr.passed is True
    assert vr.is_suspicious is False

    vr.add_issue(ValidationSeverity.WARNING, "Minor issue")
    assert vr.passed is True  # Warnings do not fail validation

    vr.add_issue(ValidationSeverity.ERROR, "Critical issue")
    assert vr.passed is False  # Errors do fail validation

    vr.flag_suspicious("Pressure language detected")
    assert vr.is_suspicious is True
    assert "Pressure language detected" in vr.suspicion_reasons
