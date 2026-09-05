"""Unit and integration tests for VP Review, Reflection Loop, Dynamic Rules, and Payment."""

import pytest
from datetime import date
from decimal import Decimal
from pathlib import Path

from invoice_pipeline.models import (
    HumanApprovalStatus,
    Invoice,
    LineItem,
    PaymentStatus,
    ReviewDecision,
    ValidationResult,
    Vendor,
)
from invoice_pipeline.payment.service import mock_payment, process_payment
from invoice_pipeline.review.vp_reviewer import VPReviewer
from invoice_pipeline.storage.database import InvoiceDatabase


@pytest.fixture
def temp_db(tmp_path: Path):
    db_path = tmp_path / "test_vp_review.db"
    db = InvoiceDatabase(db_path=db_path)
    yield db
    db.close()


def _make_invoice(
    invoice_id="INV-9999",
    total=1500.00,
    vendor_name="Acme Supplies",
    invoice_date=date(2026, 1, 28),  # Wednesday
    due_date=date(2026, 2, 28),
    item_name="WidgetA",
    qty=5,
    unit_price=300.00,
    notes=None,
) -> Invoice:
    return Invoice(
        invoice_id=invoice_id,
        date=invoice_date,
        due_date=due_date,
        vendor=Vendor(name=vendor_name),
        line_items=[
            LineItem(item=item_name, quantity=Decimal(str(qty)), unit_price=Decimal(str(unit_price)), amount=Decimal(str(total)))
        ],
        subtotal=Decimal(str(total)),
        total=Decimal(str(total)),
        notes=notes,
    )


def test_default_rules_seeded(temp_db: InvoiceDatabase):
    """Verify standard default rules are seeded into business_rules table."""
    rules = temp_db.get_active_rules()
    rule_names = {r["name"] for r in rules}
    assert "AMOUNT_OVER_10K" in rule_names
    assert "SUSPICIOUS_STRUCTURING" in rule_names
    assert "EXACT_DUPLICATE" in rule_names
    assert "UNBUNDLED_BILLING" in rule_names
    assert "SEQUENTIAL_INVOICE_GAP" in rule_names
    assert "DATE_ANOMALY" in rule_names


def test_clean_invoice_under_10k_auto_approved(temp_db: InvoiceDatabase):
    """Clean invoice under $10K is auto-approved and mock_payment executed."""
    inv = _make_invoice(invoice_id="INV-CLEAN-1", total=2500.00)
    validation = ValidationResult(passed=True, arithmetic_correct=True)

    reviewer = VPReviewer(database=temp_db)
    review = reviewer.review_invoice(inv, validation)

    assert review.decision == ReviewDecision.AUTO_APPROVED
    assert not review.requires_human
    assert review.rules_triggered == []
    assert "auto-approved" in review.final_reasoning.lower()

    # Process payment
    status, details = process_payment(inv, review)
    assert status == PaymentStatus.PAID
    assert details["status"] == "success"


def test_invoice_over_10k_requires_human_approval(temp_db: InvoiceDatabase):
    """Invoices exceeding $10,000 require VP scrutiny and halt auto-payment."""
    inv = _make_invoice(invoice_id="INV-BIG-1", total=15500.00)
    validation = ValidationResult(passed=True, arithmetic_correct=True)

    reviewer = VPReviewer(database=temp_db)
    review = reviewer.review_invoice(inv, validation)

    assert review.decision == ReviewDecision.REQUIRES_HUMAN_APPROVAL
    assert review.requires_human
    assert any("AMOUNT_OVER_10K" in r for r in review.rules_triggered)
    assert review.payment_status == PaymentStatus.PENDING_APPROVAL

    # Payment must be held
    status, details = process_payment(inv, review)
    assert status == PaymentStatus.PENDING_APPROVAL
    assert details["status"] == "held"


def test_suspicious_structuring_threshold_smurfing(temp_db: InvoiceDatabase):
    """Invoices structured just below $10,000 (e.g. $9,999) trigger Suspicious_Structuring."""
    inv = _make_invoice(invoice_id="INV-SMURF", total=9999.00)
    validation = ValidationResult(passed=True, arithmetic_correct=True)

    reviewer = VPReviewer(database=temp_db)
    review = reviewer.review_invoice(inv, validation)

    assert review.requires_human
    assert any("SUSPICIOUS_STRUCTURING" in r for r in review.rules_triggered)
    assert "structuring" in review.critique.lower()


def test_exact_duplicate_invoice_fraud(temp_db: InvoiceDatabase):
    """Exact duplicate submission is detected and held for human review."""
    inv1 = _make_invoice(invoice_id="INV-DUP-1", total=3000.00, vendor_name="VendorCorp")
    temp_db.save_invoice(inv1, None)

    # Re-submit invoice with 100% exact same items
    inv2 = _make_invoice(invoice_id="INV-DUP-1", total=3000.00, vendor_name="VendorCorp")
    validation = ValidationResult(passed=True, arithmetic_correct=True)

    reviewer = VPReviewer(database=temp_db)
    review = reviewer.review_invoice(inv2, validation)

    assert review.requires_human
    assert any("EXACT_DUPLICATE" in r for r in review.rules_triggered)


def test_revised_invoice_with_additional_items_pays_delta_only(temp_db: InvoiceDatabase):
    """If same invoice_id arrives with MORE items, it is NOT an exact duplicate and only the delta is paid."""
    # Original invoice: WidgetA qty 3 @ $250 = $750
    inv1 = Invoice(
        invoice_id="INV-REV-TEST",
        date=date(2026, 1, 22),
        due_date=date(2026, 2, 22),
        vendor=Vendor(name="Precision Parts Ltd."),
        line_items=[LineItem(item="WidgetA", quantity=Decimal("3"), unit_price=Decimal("250.00"), amount=Decimal("750.00"))],
        subtotal=Decimal("750.00"),
        total=Decimal("750.00"),
    )
    temp_db.save_invoice(inv1, None)

    # Revised invoice: Same ID 'INV-REV-TEST', revision 'R1', with MORE items: WidgetA + WidgetB (2 @ $500 = $1000)
    # New total: $1,750.00. Delta: $1,750 - $750 = $1,000.00
    inv2 = Invoice(
        invoice_id="INV-REV-TEST",
        revision="R1",
        date=date(2026, 1, 22),
        due_date=date(2026, 2, 22),
        vendor=Vendor(name="Precision Parts Ltd."),
        line_items=[
            LineItem(item="WidgetA", quantity=Decimal("3"), unit_price=Decimal("250.00"), amount=Decimal("750.00")),
            LineItem(item="WidgetB", quantity=Decimal("2"), unit_price=Decimal("500.00"), amount=Decimal("1000.00")),
        ],
        subtotal=Decimal("1750.00"),
        total=Decimal("1750.00"),
        notes="Revised order - added WidgetB",
    )
    temp_db.save_invoice(inv2, None)

    validation = ValidationResult(passed=True, arithmetic_correct=True)
    reviewer = VPReviewer(database=temp_db)
    review = reviewer.review_invoice(inv2, validation)

    # Must NOT trigger EXACT_DUPLICATE because items differ (additional items added)
    assert not any("EXACT_DUPLICATE" in r for r in review.rules_triggered)
    assert review.is_revision is True
    assert review.amount_to_pay == Decimal("1000.00")  # Exactly the delta for additional items!

    # Process payment: pays only the delta ($1000)
    status, details = process_payment(inv2, review)
    assert status == PaymentStatus.PAID
    assert details["amount_paid"] == 1000.00
    assert details["is_revision"] is True


def test_revised_invoice_exceeding_10k_held_for_review(temp_db: InvoiceDatabase):
    """All checks run after revised values are added; if new total > $10K, hold for VP review."""
    inv1 = Invoice(
        invoice_id="INV-AMEND-10K",
        date=date(2026, 1, 22),
        due_date=date(2026, 2, 22),
        vendor=Vendor(name="Mega Supplies"),
        line_items=[LineItem(item="WidgetA", quantity=Decimal("5"), unit_price=Decimal("250.00"), amount=Decimal("1250.00"))],
        subtotal=Decimal("1250.00"),
        total=Decimal("1250.00"),
    )
    temp_db.save_invoice(inv1, None)

    # Revised invoice adds high-value machinery: new total = $16,250.00 (> $10K)
    inv2 = Invoice(
        invoice_id="INV-AMEND-10K",
        revision="R2",
        date=date(2026, 1, 22),
        due_date=date(2026, 2, 22),
        vendor=Vendor(name="Mega Supplies"),
        line_items=[
            LineItem(item="WidgetA", quantity=Decimal("5"), unit_price=Decimal("250.00"), amount=Decimal("1250.00")),
            LineItem(item="PowerUnit", quantity=Decimal("10"), unit_price=Decimal("1500.00"), amount=Decimal("15000.00")),
        ],
        subtotal=Decimal("16250.00"),
        total=Decimal("16250.00"),
    )
    temp_db.save_invoice(inv2, None)

    validation = ValidationResult(passed=True, arithmetic_correct=True)
    reviewer = VPReviewer(database=temp_db)
    review = reviewer.review_invoice(inv2, validation)

    # Not a duplicate, but MUST be held because revised total > $10,000!
    assert not any("EXACT_DUPLICATE" in r for r in review.rules_triggered)
    assert any("AMOUNT_OVER_10K" in r for r in review.rules_triggered)
    assert review.requires_human is True
    assert review.payment_status == PaymentStatus.PENDING_APPROVAL



def test_unbundled_billing_split_invoices(temp_db: InvoiceDatabase):
    """Vendor splitting invoices across 7 days exceeding $10K triggers unbundling alert."""
    # Invoice 1 on 2026-01-20 for $6,000
    inv1 = _make_invoice(
        invoice_id="INV-SPLIT-1",
        total=6000.00,
        vendor_name="SneakyParts Co",
        invoice_date=date(2026, 1, 20),
    )
    temp_db.save_invoice(inv1, None)

    # Invoice 2 on 2026-01-23 for $5,000 (Total in 7 days = $11,000 > $10,000 threshold)
    inv2 = _make_invoice(
        invoice_id="INV-SPLIT-2",
        total=5000.00,
        vendor_name="SneakyParts Co",
        invoice_date=date(2026, 1, 23),
    )
    validation = ValidationResult(passed=True, arithmetic_correct=True)

    reviewer = VPReviewer(database=temp_db)
    review = reviewer.review_invoice(inv2, validation)

    assert review.requires_human
    assert any("UNBUNDLED_BILLING" in r for r in review.rules_triggered)


def test_sequential_invoice_gap_shell_company(temp_db: InvoiceDatabase):
    """Consecutive invoice numbers separated by a large time gap triggers shell company risk."""
    # First invoice #1041 on 2026-01-01
    inv1 = _make_invoice(
        invoice_id="INV-1041",
        total=2000.00,
        vendor_name="GhostCorp",
        invoice_date=date(2026, 1, 1),
    )
    temp_db.save_invoice(inv1, None)

    # Second invoice #1042 one month later on 2026-02-05 (35 days later)
    inv2 = _make_invoice(
        invoice_id="INV-1042",
        total=2000.00,
        vendor_name="GhostCorp",
        invoice_date=date(2026, 2, 5),
    )
    validation = ValidationResult(passed=True, arithmetic_correct=True)

    reviewer = VPReviewer(database=temp_db)
    review = reviewer.review_invoice(inv2, validation)

    assert review.requires_human
    assert any("SEQUENTIAL_INVOICE_GAP" in r for r in review.rules_triggered)


def test_date_anomaly_weekend(temp_db: InvoiceDatabase):
    """Invoices dated on weekend trigger date anomaly review."""
    # 2026-01-24 is a Saturday
    saturday_invoice = _make_invoice(
        invoice_id="INV-SAT",
        total=500.00,
        invoice_date=date(2026, 1, 24),
    )
    validation = ValidationResult(passed=True, arithmetic_correct=True)

    reviewer = VPReviewer(database=temp_db)
    review = reviewer.review_invoice(saturday_invoice, validation)

    assert review.requires_human
    assert any("DATE_ANOMALY" in r for r in review.rules_triggered)


def test_human_in_the_loop_approval_and_rejection(temp_db: InvoiceDatabase):
    """Test human approval workflow: holds payment, then human approval releases payment."""
    inv = _make_invoice(invoice_id="INV-APPROVAL-TEST", total=12000.00, vendor_name="Prime Tech")
    temp_db.save_invoice(inv, None)

    validation = ValidationResult(passed=True, arithmetic_correct=True)
    reviewer = VPReviewer(database=temp_db)
    review = reviewer.review_invoice(inv, validation)

    # Must be pending
    assert review.payment_status == PaymentStatus.PENDING_APPROVAL
    pending = temp_db.get_pending_approvals()
    assert any(p["invoice_id"] == "INV-APPROVAL-TEST" for p in pending)

    # Execute human approval
    payment_receipt = mock_payment(inv.vendor.name, inv.total)
    updated = temp_db.update_human_approval(
        invoice_id="INV-APPROVAL-TEST",
        approved=True,
        reviewer="CFO Jane Doe",
        notes="Approved special project expenditure",
        payment_details=payment_receipt,
    )
    assert updated is True

    # Check updated record
    final_rev = temp_db.get_invoice_review("INV-APPROVAL-TEST")
    assert final_rev["human_approval_status"] == "approved"
    assert final_rev["payment_status"] == "paid"
    assert final_rev["human_reviewer"] == "CFO Jane Doe"


def test_human_in_the_loop_rejection(temp_db: InvoiceDatabase):
    """Test human rejection workflow: permanently blocks payment."""
    inv = _make_invoice(invoice_id="INV-REJECT-TEST", total=25000.00, vendor_name="Shady Inc")
    temp_db.save_invoice(inv, None)

    validation = ValidationResult(passed=True, arithmetic_correct=True)
    reviewer = VPReviewer(database=temp_db)
    reviewer.review_invoice(inv, validation)

    # Human rejects invoice
    updated = temp_db.update_human_approval(
        invoice_id="INV-REJECT-TEST",
        approved=False,
        reviewer="VP Finance",
        notes="Unbudgeted spend request denied",
    )
    assert updated is True

    final_rev = temp_db.get_invoice_review("INV-REJECT-TEST")
    assert final_rev["human_approval_status"] == "rejected"
    assert final_rev["payment_status"] == "rejected"


def test_dynamic_custom_rule_addition(temp_db: InvoiceDatabase):
    """Verify user can add a dynamic rule to SQLite and have it take immediate effect."""
    # Add custom rule: flag any invoice from 'SuspiciousVendor'
    temp_db.add_rule(
        name="SUSPICIOUS_VENDOR_WATCHLIST",
        condition_type="vendor_pattern",
        condition_value="SuspiciousVendor",
        action="REQUIRE_HUMAN_APPROVAL",
        description="Flag known suspicious vendor name",
    )

    inv = _make_invoice(
        invoice_id="INV-CUSTOM-RULE",
        total=500.00,  # under $10K
        vendor_name="SuspiciousVendor LLC",
    )
    validation = ValidationResult(passed=True, arithmetic_correct=True)

    reviewer = VPReviewer(database=temp_db)
    review = reviewer.review_invoice(inv, validation)

    assert review.requires_human
    assert any("SUSPICIOUS_VENDOR_WATCHLIST" in r for r in review.rules_triggered)


def test_revised_invoice_with_additional_items_pays_delta_only(temp_db: InvoiceDatabase):
    """If revised invoice has additional items, only delta is paid and EXACT_DUPLICATE is not triggered."""
    from invoice_pipeline.models import IngestionResult, FileFormat

    # Invoice 1: Original ($1,000)
    inv1 = Invoice(
        invoice_id="INV-1004-TEST",
        date=date(2026, 1, 22),
        due_date=date(2026, 2, 22),
        vendor=Vendor(name="Precision Parts Ltd."),
        line_items=[
            LineItem(item="WidgetA", quantity=Decimal("4"), unit_price=Decimal("250.00"), amount=Decimal("1000.00")),
        ],
        subtotal=Decimal("1000.00"),
        total=Decimal("1000.00"),
    )
    res1 = IngestionResult(source_file="inv1.json", format_detected=FileFormat.JSON, raw_text="{}", validation=ValidationResult(passed=True))
    inv1_id = temp_db.save_invoice(inv1, res1)

    reviewer = VPReviewer(database=temp_db)
    review1 = reviewer.review_invoice(inv1, ValidationResult(passed=True), current_db_id=inv1_id)
    assert review1.decision == ReviewDecision.AUTO_APPROVED

    # Invoice 2: Revision with additional item GadgetX (Total $2,500, Delta $1,500)
    inv2 = Invoice(
        invoice_id="INV-1004-TEST",
        revision="R1",
        date=date(2026, 1, 22),
        due_date=date(2026, 2, 22),
        vendor=Vendor(name="Precision Parts Ltd."),
        line_items=[
            LineItem(item="WidgetA", quantity=Decimal("4"), unit_price=Decimal("250.00"), amount=Decimal("1000.00")),
            LineItem(item="GadgetX", quantity=Decimal("2"), unit_price=Decimal("750.00"), amount=Decimal("1500.00")),
        ],
        subtotal=Decimal("2500.00"),
        total=Decimal("2500.00"),
    )
    res2 = IngestionResult(source_file="inv2.json", format_detected=FileFormat.JSON, raw_text="{}", validation=ValidationResult(passed=True))
    inv2_id = temp_db.save_invoice(inv2, res2)

    review2 = reviewer.review_invoice(inv2, ValidationResult(passed=True), current_db_id=inv2_id)
    # Must NOT trigger EXACT_DUPLICATE
    assert not any("EXACT_DUPLICATE" in r for r in review2.rules_triggered)
    assert review2.decision == ReviewDecision.AUTO_APPROVED
    assert review2.is_revision is True
    assert review2.amount_to_pay == Decimal("1500.00")
    assert review2.previous_total == Decimal("1000.00")

    # Payment execution must only pay the delta ($1,500)
    status, details = process_payment(inv2, review2)
    assert status == PaymentStatus.PAID
    assert details["amount_paid"] == 1500.00
    assert details["is_revision"] is True


def test_revised_invoice_with_identical_items_flagged_as_duplicate(temp_db: InvoiceDatabase):
    """If incoming invoice has 100% identical line items to existing, trigger EXACT_DUPLICATE."""
    from invoice_pipeline.models import IngestionResult, FileFormat

    inv1 = Invoice(
        invoice_id="INV-IDENTICAL-TEST",
        date=date(2026, 1, 22),
        due_date=date(2026, 2, 22),
        vendor=Vendor(name="Standard Parts"),
        line_items=[
            LineItem(item="WidgetA", quantity=Decimal("2"), unit_price=Decimal("100.00"), amount=Decimal("200.00")),
        ],
        subtotal=Decimal("200.00"),
        total=Decimal("200.00"),
    )
    res1 = IngestionResult(source_file="inv1.json", format_detected=FileFormat.JSON, raw_text="{}", validation=ValidationResult(passed=True))
    inv1_id = temp_db.save_invoice(inv1, res1)

    reviewer = VPReviewer(database=temp_db)
    # Inv 2 has the exact same items
    inv2 = Invoice(
        invoice_id="INV-IDENTICAL-TEST",
        date=date(2026, 1, 22),
        due_date=date(2026, 2, 22),
        vendor=Vendor(name="Standard Parts"),
        line_items=[
            LineItem(item="WidgetA", quantity=Decimal("2"), unit_price=Decimal("100.00"), amount=Decimal("200.00")),
        ],
        subtotal=Decimal("200.00"),
        total=Decimal("200.00"),
    )

    review2 = reviewer.review_invoice(inv2, ValidationResult(passed=True), current_db_id=None)
    assert review2.requires_human is True
    assert any("EXACT_DUPLICATE" in r for r in review2.rules_triggered)


def test_revised_invoice_exceeding_10k_held_for_review(temp_db: InvoiceDatabase):
    """If revised invoice new total exceeds $10k, it must be held for human review."""
    from invoice_pipeline.models import IngestionResult, FileFormat

    inv1 = Invoice(
        invoice_id="INV-REVISED-BIG",
        date=date(2026, 1, 22),
        due_date=date(2026, 2, 22),
        vendor=Vendor(name="Big Supplies Ltd"),
        line_items=[
            LineItem(item="WidgetA", quantity=Decimal("10"), unit_price=Decimal("800.00"), amount=Decimal("8000.00")),
        ],
        subtotal=Decimal("8000.00"),
        total=Decimal("8000.00"),
    )
    res1 = IngestionResult(source_file="inv1.json", format_detected=FileFormat.JSON, raw_text="{}", validation=ValidationResult(passed=True))
    inv1_id = temp_db.save_invoice(inv1, res1)

    inv2 = Invoice(
        invoice_id="INV-REVISED-BIG",
        revision="R1",
        date=date(2026, 1, 22),
        due_date=date(2026, 2, 22),
        vendor=Vendor(name="Big Supplies Ltd"),
        line_items=[
            LineItem(item="WidgetA", quantity=Decimal("10"), unit_price=Decimal("800.00"), amount=Decimal("8000.00")),
            LineItem(item="WidgetB", quantity=Decimal("10"), unit_price=Decimal("500.00"), amount=Decimal("5000.00")),
        ],
        subtotal=Decimal("13000.00"),
        total=Decimal("13000.00"),
    )
    res2 = IngestionResult(source_file="inv2.json", format_detected=FileFormat.JSON, raw_text="{}", validation=ValidationResult(passed=True))
    inv2_id = temp_db.save_invoice(inv2, res2)

    reviewer = VPReviewer(database=temp_db)
    review2 = reviewer.review_invoice(inv2, ValidationResult(passed=True), current_db_id=inv2_id)

    assert review2.requires_human is True
    assert any("AMOUNT_OVER_10K" in r for r in review2.rules_triggered)
    status, details = process_payment(inv2, review2)
    assert status == PaymentStatus.PENDING_APPROVAL

