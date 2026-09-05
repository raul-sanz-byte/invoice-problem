"""Pydantic models for the invoice ingestion pipeline.

All financial amounts use Decimal for precision.
These models serve as the strict contract for data flowing through the pipeline.
"""

from __future__ import annotations

from datetime import date as dt_date
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FileFormat(str, Enum):
    """Detected file format of an input invoice."""

    PDF = "pdf"
    JSON = "json"
    CSV = "csv"
    XML = "xml"
    EMAIL = "email"
    TEXT = "text"


class ValidationSeverity(str, Enum):
    """Severity level for validation issues."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# ---------------------------------------------------------------------------
# Core Invoice Models
# ---------------------------------------------------------------------------


class LineItem(BaseModel):
    """A single line item in an invoice."""

    item: str = Field(description="Product/service name")
    quantity: Decimal = Field(description="Quantity ordered")
    unit_price: Decimal = Field(description="Price per unit")
    amount: Decimal | None = Field(
        default=None, description="Line total (qty × unit_price, or stated amount)"
    )
    note: str | None = Field(
        default=None, description="Optional note (e.g., 'Volume discount', 'Expedited')"
    )

    @field_validator("quantity", "unit_price", "amount", mode="before")
    @classmethod
    def coerce_to_decimal(cls, v: Any) -> Any:
        """Convert floats/ints/strings to Decimal for financial precision."""
        if v is None:
            return v
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError):
            return v  # Let Pydantic's own validation catch it

    @model_validator(mode="after")
    def compute_amount_if_missing(self) -> LineItem:
        """Auto-compute amount = quantity × unit_price when not provided."""
        if self.amount is None and self.quantity is not None and self.unit_price is not None:
            self.amount = self.quantity * self.unit_price
        return self


class Vendor(BaseModel):
    """Invoice vendor/supplier information."""

    name: str = Field(description="Vendor name (required)")
    address: str | None = Field(default=None, description="Vendor address (optional)")


class Invoice(BaseModel):
    """Fully extracted and normalized invoice data."""

    invoice_id: str = Field(description="Unique invoice identifier (e.g., 'INV-1001')")
    date: dt_date = Field(description="Invoice issue date")
    due_date: dt_date = Field(description="Payment due date")
    vendor: Vendor = Field(description="Vendor/supplier information")
    line_items: list[LineItem] = Field(description="List of line items", min_length=1)
    subtotal: Decimal | None = Field(default=None, description="Sum of line item amounts")
    tax_rate: Decimal | None = Field(
        default=None, description="Tax rate as decimal (e.g., 0.08 for 8%)"
    )
    tax_amount: Decimal | None = Field(default=None, description="Total tax amount")
    total: Decimal = Field(description="Total invoice amount")
    currency: str = Field(default="USD", description="ISO 4217 currency code")
    payment_terms: str | None = Field(
        default=None, description="Payment terms string (e.g., 'Net 30')"
    )
    payment_terms_days: int | None = Field(
        default=None, description="Number of days until payment due (e.g., 30)"
    )
    shipping: Decimal | None = Field(default=None, description="Shipping cost (optional)")
    notes: str | None = Field(default=None, description="Additional invoice notes")
    revision: str | None = Field(
        default=None, description="Revision identifier (e.g., 'R1')"
    )
    db_id: int | None = Field(
        default=None, description="Database row ID in SQLite"
    )

    @field_validator(
        "subtotal", "tax_rate", "tax_amount", "total", "shipping", mode="before"
    )
    @classmethod
    def coerce_to_decimal(cls, v: Any) -> Any:
        """Convert floats/ints/strings to Decimal."""
        if v is None:
            return v
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError):
            return v


# ---------------------------------------------------------------------------
# Validation & Result Models
# ---------------------------------------------------------------------------


class ValidationIssue(BaseModel):
    """A single issue found during validation."""

    severity: ValidationSeverity
    field: str | None = None
    message: str
    expected: str | None = None
    actual: str | None = None


class ValidationResult(BaseModel):
    """Aggregate result of all validation checks on an invoice."""

    passed: bool = True
    issues: list[ValidationIssue] = Field(default_factory=list)
    arithmetic_correct: bool = True
    is_suspicious: bool = False
    suspicion_reasons: list[str] = Field(default_factory=list)

    def add_issue(
        self,
        severity: ValidationSeverity,
        message: str,
        field: str | None = None,
        expected: str | None = None,
        actual: str | None = None,
    ) -> None:
        """Add a validation issue and update passed status if ERROR."""
        self.issues.append(
            ValidationIssue(
                severity=severity,
                field=field,
                message=message,
                expected=expected,
                actual=actual,
            )
        )
        if severity == ValidationSeverity.ERROR:
            self.passed = False

    def flag_suspicious(self, reason: str) -> None:
        """Flag the invoice as suspicious with a reason."""
        self.is_suspicious = True
        self.suspicion_reasons.append(reason)


class IngestionResult(BaseModel):
    """Complete result of ingesting a single invoice file with observability telemetry."""

    invoice: Invoice | None = None
    source_file: str
    format_detected: FileFormat
    raw_text: str = ""
    validation: ValidationResult = Field(default_factory=ValidationResult)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    success: bool = False
    extraction_method: str = "unspecified"
    processing_time_ms: float = 0.0
    stage_timings: dict[str, float] = Field(default_factory=dict)
    self_corrected: bool = False
    correction_attempts: int = 0
    correction_notes: list[str] = Field(default_factory=list)
    review: InvoiceReview | None = None
    is_invoice: bool = True
    skipped: bool = False
    is_poisoned: bool = False
    poison_signatures: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Product Catalog Model (for the fake products database)
# ---------------------------------------------------------------------------


class Product(BaseModel):
    """A product in the catalog with standard pricing and stock."""

    product_id: str
    name: str
    standard_price: Decimal
    currency: str = "USD"
    quantity_in_stock: int = 0
    category: str | None = None

    @field_validator("standard_price", mode="before")
    @classmethod
    def coerce_price(cls, v: Any) -> Any:
        if v is None:
            return v
        if isinstance(v, Decimal):
            return v
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError):
            return v


# ---------------------------------------------------------------------------
# VP Review, Business Rules & Payment Models
# ---------------------------------------------------------------------------


class ReviewDecision(str, Enum):
    """VP-level review decision."""

    AUTO_APPROVED = "auto_approved"
    REQUIRES_HUMAN_APPROVAL = "requires_human_approval"
    REJECTED = "rejected"


class PaymentStatus(str, Enum):
    """Payment state of an invoice."""

    PAID = "paid"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class HumanApprovalStatus(str, Enum):
    """Human-in-the-loop review status."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class BusinessRule(BaseModel):
    """A business decision rule evaluated during VP review."""

    id: int | None = None
    name: str
    description: str | None = None
    condition_type: str
    condition_value: str
    action: str = "REQUIRE_HUMAN_APPROVAL"
    is_active: bool = True


class InvoiceReview(BaseModel):
    """Audit record of VP reflection, rule evaluation, and payment outcome."""

    invoice_id: str
    decision: ReviewDecision
    rules_triggered: list[str] = Field(default_factory=list)
    initial_reasoning: str
    critique: str
    final_reasoning: str
    requires_human: bool
    human_approval_status: HumanApprovalStatus = HumanApprovalStatus.NOT_REQUIRED
    human_reviewer: str | None = None
    human_notes: str | None = None
    payment_status: PaymentStatus = PaymentStatus.PENDING_APPROVAL
    payment_details: dict[str, Any] | None = None
    amount_to_pay: Decimal | None = None
    is_revision: bool = False
    previous_total: Decimal | None = None
