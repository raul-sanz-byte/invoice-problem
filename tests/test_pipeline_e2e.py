"""End-to-end integration tests for the InvoicePipeline."""

from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile

from invoice_pipeline.pipeline import InvoicePipeline
from invoice_pipeline.storage.database import InvoiceDatabase

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_e2e_pipeline_batch_ingest():
    """Test running the full InvoicePipeline across all test fixture documents."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_e2e.db"
        pipeline = InvoicePipeline(llm_client=None, db_path=str(db_path))

        try:
            results = pipeline.process_directory(FIXTURES_DIR)
            assert len(results) >= 8

            # Collect results by invoice_id
            by_id = {r.invoice.invoice_id: r for r in results if r.invoice}

            # 1. Payment 1 (Text)
            assert "INV-1001" in by_id
            r1 = by_id["INV-1001"]
            assert r1.invoice.total == Decimal("5000.00")
            assert r1.invoice.vendor.name == "Widgets Inc."
            assert r1.validation.arithmetic_correct is True

            # 2. Payment 3 (Suspicious Fraudster invoice)
            assert "INV-1003" in by_id
            r3 = by_id["INV-1003"]
            assert r3.validation.is_suspicious is True
            assert len(r3.validation.suspicion_reasons) > 0

            # 3. Payment 4 & 5 (JSON and Revision)
            assert "INV-1004" in by_id
            revs = pipeline.database.get_revisions("INV-1004")
            assert len(revs) == 1
            assert revs[0]["revision"] == "R1"

            # 4. Payment 6 (CSV Key-Value)
            assert "INV-1006" in by_id
            r6 = by_id["INV-1006"]
            assert r6.invoice.total == Decimal("2750.00")

            # 5. Payment 7 (CSV Tabular)
            assert "INV-1007" in by_id
            r7 = by_id["INV-1007"]
            assert r7.invoice.total == Decimal("15525.00")

            # 6. Payment 8 (Email)
            assert "INV-1008" in by_id
            r8 = by_id["INV-1008"]
            assert r8.invoice.total == Decimal("9900.00")

            # 7. XML Example
            assert "INV-1014" in by_id
            r_xml = by_id["INV-1014"]
            assert r_xml.invoice.currency == "EUR"
            assert r_xml.invoice.total == Decimal("4125.00")

            # 8. Check database listings
            all_invoices = pipeline.database.get_all_invoices()
            assert len(all_invoices) >= 7

            # Verify fake product inventory exists
            products = pipeline.database.get_products()
            assert len(products) >= 9

        finally:
            pipeline.close()
