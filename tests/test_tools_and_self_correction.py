"""Unit tests for agentic tools and self-correction loops."""

from datetime import date
from decimal import Decimal
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from invoice_pipeline.models import Invoice, LineItem, Vendor, ValidationResult, ValidationSeverity
from invoice_pipeline.storage.database import InvoiceDatabase
from invoice_pipeline.tools import INVOICE_TOOLS, execute_tool
from invoice_pipeline.validation.self_corrector import deterministic_self_correct
from invoice_pipeline.pipeline import InvoicePipeline
from invoice_pipeline.llm_client import LLMClient


@pytest.fixture
def test_db():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "tools_test.db"
        with InvoiceDatabase(db_path) as db:
            yield db


def test_tool_definitions_structure():
    """Verify tool schemas conform to OpenAI function calling specifications."""
    assert len(INVOICE_TOOLS) >= 3
    tool_names = [t["function"]["name"] for t in INVOICE_TOOLS]
    assert "lookup_product_catalog" in tool_names
    assert "compute_financial_totals" in tool_names
    assert "resolve_vocabulary_alias" in tool_names


def test_tool_lookup_product_catalog(test_db):
    """Test lookup_product_catalog tool execution."""
    # Known product in catalog
    res = execute_tool("lookup_product_catalog", {"product_name": "WidgetA"}, database=test_db)
    assert res["found"] is True
    assert res["name"] == "WidgetA"
    assert res["standard_price"] == 250.0
    assert res["quantity_in_stock"] == 500

    # Unknown product
    res_unknown = execute_tool("lookup_product_catalog", {"product_name": "NonExistentItem"}, database=test_db)
    assert res_unknown["found"] is False


def test_tool_compute_financial_totals():
    """Test compute_financial_totals tool execution."""
    args = {
        "line_items": [
            {"item": "WidgetA", "quantity": 10, "unit_price": 250.00},
            {"item": "WidgetB", "quantity": 5, "unit_price": 500.00},
        ],
        "tax_rate": 0.08,
        "shipping": 50.00,
    }
    res = execute_tool("compute_financial_totals", args)
    assert res["subtotal"] == 5000.00
    assert res["tax_amount"] == 400.00
    assert res["shipping"] == 50.00
    assert res["total"] == 5450.00
    assert len(res["line_items"]) == 2
    assert res["line_items"][0]["amount"] == 2500.00


def test_tool_resolve_vocabulary_alias():
    """Test resolve_vocabulary_alias tool execution."""
    res = execute_tool("resolve_vocabulary_alias", {"raw_alias": "vndr"})
    assert res["canonical_field"] == "vendor"
    assert res["is_known"] is True


def test_deterministic_self_correction_math(test_db):
    """Verify deterministic self-correction repairs arithmetic discrepancies."""
    # Invoice with wrong subtotal, wrong line item amount, and wrong total
    flawed_invoice = Invoice(
        invoice_id="INV-REPAIR-1",
        date=date(2026, 1, 15),
        due_date=date(2026, 2, 1),
        vendor=Vendor(name="Widgets Inc."),
        line_items=[
            LineItem(item="WidgetA", quantity=Decimal("10"), unit_price=Decimal("250.00"), amount=Decimal("999.00")), # Wrong amount
            LineItem(item="WidgetB", quantity=Decimal("2"), unit_price=Decimal("500.00"), amount=Decimal("1000.00")),
        ],
        subtotal=Decimal("1999.00"),  # Wrong subtotal
        tax_rate=Decimal("0.10"),
        tax_amount=Decimal("50.00"),  # Wrong tax amount
        total=Decimal("9999.00"),     # Wrong total
    )

    from invoice_pipeline.validation.arithmetic_validator import validate_arithmetic
    initial_val = validate_arithmetic(flawed_invoice)
    assert not initial_val.arithmetic_correct

    # Run self-correction with explicit total repair
    repaired, notes = deterministic_self_correct(
        flawed_invoice, initial_val, database=test_db, repair_stated_totals=True
    )
    assert len(notes) >= 3

    # Re-validate
    new_val = validate_arithmetic(repaired)
    assert new_val.arithmetic_correct
    assert repaired.line_items[0].amount == Decimal("2500.00")
    assert repaired.subtotal == Decimal("3500.00")
    assert repaired.tax_amount == Decimal("350.00")
    assert repaired.total == Decimal("3850.00")


def test_pipeline_self_correction_integration(test_db):
    """Test end-to-end self-correction inside the pipeline."""
    pipeline = InvoicePipeline(database=test_db)

    # Ingest tabular CSV fixture (INV-1007) which has an arithmetic discrepancy in raw file
    res = pipeline.process_file("tests/fixtures/invoice_csv_tabular.csv")
    # Pipeline processed file
    assert res.invoice is not None
    # Self-correction attempted and repaired math if possible
    assert res.processing_time_ms > 0
    assert "storage_ms" in res.stage_timings


def test_llm_tool_execution_loop():
    """Verify that LLMClient executes tool calls and returns final data."""
    mock_client = MagicMock()

    # Step 1: LLM requests tool call
    tool_call = MagicMock()
    tool_call.id = "call_abc123"
    tool_call.function.name = "compute_financial_totals"
    tool_call.function.arguments = '{"line_items": [{"item": "WidgetA", "quantity": 2, "unit_price": 250}]}'

    msg1 = MagicMock()
    msg1.tool_calls = [tool_call]
    msg1.content = None

    # Step 2: LLM receives tool output and returns final JSON
    msg2 = MagicMock()
    msg2.tool_calls = None
    msg2.content = '{"invoice_id": "INV-MOCK-1", "date": "2026-01-15", "due_date": "2026-02-15", "vendor": {"name": "Test"}, "line_items": [{"item": "WidgetA", "quantity": 2, "unit_price": 250, "amount": 500}], "total": 500}'

    choice1 = MagicMock(message=msg1)
    choice2 = MagicMock(message=msg2)

    resp1 = MagicMock(choices=[choice1])
    resp2 = MagicMock(choices=[choice2])

    mock_client.chat.completions.create.side_effect = [resp1, resp2]

    llm = LLMClient(api_key="mock-key")
    llm.client = mock_client

    extracted = llm.extract_invoice_fields("Invoice text...", enable_tools=True)
    assert extracted["invoice_id"] == "INV-MOCK-1"
    assert extracted["total"] == 500
    assert mock_client.chat.completions.create.call_count == 2


def test_llm_self_correction_critique_loop():
    """Verify that self_correct_invoice feeds validation issues and returns corrected data."""
    mock_client = MagicMock()

    msg_corrected = MagicMock()
    msg_corrected.tool_calls = None
    msg_corrected.content = '{"invoice_id": "INV-CORRECTED", "date": "2026-01-20", "due_date": "2026-02-20", "vendor": {"name": "Corrected Vendor"}, "line_items": [{"item": "WidgetA", "quantity": 1, "unit_price": 250, "amount": 250}], "total": 250}'

    choice = MagicMock(message=msg_corrected)
    mock_client.chat.completions.create.return_value = MagicMock(choices=[choice])

    llm = LLMClient(api_key="mock-key")
    llm.client = mock_client

    corrected = llm.self_correct_invoice(
        text="Sample text",
        current_data={"invoice_id": "INV-CORRECTED", "total": 999},
        validation_issues=["Total mismatch: expected 250, got 999"],
    )
    assert corrected["total"] == 250
    assert mock_client.chat.completions.create.call_count == 1
