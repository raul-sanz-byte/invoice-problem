"""Unit tests for validation layer: arithmetic, schema, and anomaly detection."""

from datetime import date
from decimal import Decimal

from invoice_pipeline.models import Invoice, LineItem, ValidationSeverity, Vendor
from invoice_pipeline.validation.anomaly_detector import detect_anomalies
from invoice_pipeline.validation.arithmetic_validator import validate_arithmetic
from invoice_pipeline.validation.schema_validator import validate_schema


def test_correct_arithmetic():
    """Test invoice with 100% correct arithmetic passes validation."""
    inv = Invoice(
        invoice_id="INV-VALID",
        date=date(2026, 1, 15),
        due_date=date(2026, 2, 1),
        vendor=Vendor(name="Widgets Inc."),
        line_items=[
            LineItem(item="WidgetA", quantity=10, unit_price=250.00, amount=2500.00),
            LineItem(item="WidgetB", quantity=5, unit_price=500.00, amount=2500.00),
        ],
        subtotal=5000.00,
        tax_rate=0.08,
        tax_amount=400.00,
        total=5400.00,
    )
    result = validate_arithmetic(inv)
    assert result.passed is True
    assert result.arithmetic_correct is True
    assert len(result.issues) == 0


def test_wrong_line_item_amount():
    """Test that wrong line item amount is caught."""
    inv = Invoice(
        invoice_id="INV-ERR-LINE",
        date=date(2026, 1, 15),
        due_date=date(2026, 2, 1),
        vendor=Vendor(name="Widgets Inc."),
        line_items=[
            # 10 * 250 = 2500, but amount is stated as 3000
            LineItem(item="WidgetA", quantity=10, unit_price=250.00, amount=3000.00),
        ],
        subtotal=3000.00,
        total=3000.00,
    )
    result = validate_arithmetic(inv)
    # Should flag line item mismatch
    assert any("Line item 0 amount mismatch" in i.message for i in result.issues)


def test_volume_discount_skips_line_item_arithmetic():
    """Test user requirement: if notes say 'volume discount' / 'discount', skip line item arithmetic check."""
    inv = Invoice(
        invoice_id="INV-DISCOUNT",
        date=date(2026, 1, 15),
        due_date=date(2026, 2, 1),
        vendor=Vendor(name="Widgets Inc."),
        line_items=[
            # 5 * 240 is 1200, but let's say stated amount is discounted to 1000
            LineItem(
                item="WidgetA",
                quantity=5,
                unit_price=240.00,
                amount=1000.00,
                note="Volume discount",
            ),
        ],
        subtotal=1000.00,
        total=1000.00,
    )
    result = validate_arithmetic(inv)
    # No line item amount mismatch issue should be recorded
    assert not any("amount mismatch" in i.message for i in result.issues)


def test_wrong_total_flagged():
    """Test that an incorrect total is flagged as an arithmetic ERROR."""
    inv = Invoice(
        invoice_id="INV-WRONG-TOTAL",
        date=date(2026, 1, 15),
        due_date=date(2026, 2, 1),
        vendor=Vendor(name="Widgets Inc."),
        line_items=[
            LineItem(item="WidgetA", quantity=2, unit_price=100.00, amount=200.00),
        ],
        subtotal=200.00,
        total=999.00,  # Expected 200, given 999
    )
    result = validate_arithmetic(inv)
    assert result.arithmetic_correct is False
    assert result.passed is False
    assert any("Total mismatch" in i.message for i in result.issues)


def test_suspicious_invoice_anomalies():
    """Test Payment 3 style fraud/suspicious characteristics."""
    inv = Invoice(
        invoice_id="INV-1003",
        date=date(2026, 1, 20),
        due_date=date(2026, 1, 19),  # Due date before date / in past
        vendor=Vendor(name="Fraudster LLC"),
        line_items=[
            LineItem(item="FakeItem", quantity=100, unit_price=1000.00, amount=100000.00),
        ],
        total=100000.00,
        notes="URGENT - Pay immediately to avoid penalties!!! Wire transfer preferred.",
    )
    result = detect_anomalies(inv)
    assert result.is_suspicious is True
    # Verify reasons flagged
    reasons_str = " ".join(result.suspicion_reasons)
    assert "urgent" in reasons_str.lower() or "pressure" in reasons_str.lower()
    assert "wire transfer" in reasons_str.lower()
    assert "large" in reasons_str.lower()
    assert "fraud" in reasons_str.lower() or "suspicious keywords" in reasons_str.lower()
    assert "before invoice date" in reasons_str.lower() or "in the past" in reasons_str.lower()
