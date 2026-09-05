"""Unit tests for SQLite database and revision audit trail."""

from datetime import date
from decimal import Decimal
import tempfile
from pathlib import Path
import pytest

from invoice_pipeline.models import (
    FileFormat,
    IngestionResult,
    Invoice,
    LineItem,
    ValidationResult,
    Vendor,
)
from invoice_pipeline.storage.database import InvoiceDatabase


def test_database_and_revision_audit_trail():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_invoices.db"
        db = InvoiceDatabase(db_path)

        # 1. Verify fake products table is seeded
        products = db.get_products()
        assert len(products) >= 9
        prod_names = [p["name"] for p in products]
        assert "WidgetA" in prod_names
        assert "WidgetB" in prod_names
        assert "GadgetX" in prod_names

        # 2. Insert original invoice INV-1004 (Payment 4)
        inv_original = Invoice(
            invoice_id="INV-1004",
            date=date(2026, 1, 22),
            due_date=date(2026, 2, 22),
            vendor=Vendor(name="Precision Parts Ltd."),
            line_items=[
                LineItem(item="WidgetA", quantity=3, unit_price=250.00, amount=750.00),
                LineItem(item="WidgetB", quantity=2, unit_price=500.00, amount=1000.00),
            ],
            subtotal=1750.00,
            tax_rate=0.08,
            tax_amount=140.00,
            total=1890.00,
            payment_terms="Net 30",
        )
        res1 = IngestionResult(
            invoice=inv_original,
            source_file="invoice_json_1.json",
            format_detected=FileFormat.JSON,
            success=True,
            validation=ValidationResult(),
        )
        row_id1 = db.save_invoice(inv_original, res1)
        assert row_id1 is not None

        # Check retrieval
        saved = db.get_invoice("INV-1004")
        assert saved is not None
        assert saved["total"] == 1890.00
        assert len(saved["line_items"]) == 2

        # 3. Now insert revised invoice INV-1004 R1 (Payment 5)
        inv_revised = Invoice(
            invoice_id="INV-1004",
            revision="R1",
            date=date(2026, 1, 22),
            due_date=date(2026, 2, 22),
            vendor=Vendor(name="Precision Parts Ltd."),
            line_items=[
                LineItem(item="WidgetA", quantity=3, unit_price=250.00, amount=750.00),
                LineItem(item="WidgetB", quantity=2, unit_price=500.00, amount=1000.00),
                LineItem(item="GadgetX", quantity=5, unit_price=750.00, amount=3750.00),
            ],
            subtotal=5500.00,
            tax_rate=0.08,
            tax_amount=440.00,
            total=5940.00,
            payment_terms="Net 30",
            notes="Revised invoice - additional items added per PO amendment",
        )
        res2 = IngestionResult(
            invoice=inv_revised,
            source_file="invoice_json_revision.json",
            format_detected=FileFormat.JSON,
            success=True,
            validation=ValidationResult(),
        )
        row_id2 = db.save_invoice(inv_revised, res2)

        # 4. Verify audit trail: original record is NOT lost, revision is recorded
        revisions = db.get_revisions("INV-1004")
        assert len(revisions) == 1
        assert revisions[0]["revision"] == "R1"
        assert "1890" in revisions[0]["previous_data"]
        assert "5940" in revisions[0]["new_data"]

        # Latest invoice retrieval reflects revision
        latest = db.get_invoice("INV-1004")
        assert latest["revision"] == "R1"
        assert latest["total"] == 5940.00
        assert len(latest["line_items"]) == 3

        db.close()


def test_database_observability_metrics():
    """Verify that ingestion telemetry and operational metrics are tracked properly."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_metrics.db"
        with InvoiceDatabase(db_path) as db:
            # Log successful ingestion
            res1 = IngestionResult(
                source_file="file1.json",
                format_detected=FileFormat.JSON,
                success=True,
                extraction_method="deterministic_json",
                processing_time_ms=12.5,
            )
            db.log_ingestion(res1)

            # Log failed ingestion
            res2 = IngestionResult(
                source_file="file2.txt",
                format_detected=FileFormat.TEXT,
                success=False,
                errors=["Extraction failed"],
                extraction_method="deterministic_regex_fallback",
                processing_time_ms=45.0,
            )
            db.log_ingestion(res2)

            metrics = db.get_ingestion_metrics()
            assert metrics["total_ingested"] == 2
            assert metrics["successful"] == 1
            assert metrics["failed"] == 1
            assert metrics["success_rate_pct"] == 50.0
            assert metrics["avg_latency_ms"] == pytest.approx(28.75, rel=1e-2)
            assert metrics["formats"]["json"] == 1
            assert metrics["formats"]["text"] == 1
            assert metrics["extraction_methods"]["deterministic_json"] == 1
            assert metrics["extraction_methods"]["deterministic_regex_fallback"] == 1


def test_database_transaction_rollback():
    """Verify that failed saves roll back cleanly without leaving partial records."""
    import sqlite3
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "test_rollback.db"
        with InvoiceDatabase(db_path) as db:
            inv = Invoice(
                invoice_id="INV-TEST-ROLLBACK",
                date=date(2026, 1, 1),
                due_date=date(2026, 1, 15),
                vendor=Vendor(name="Test Vendor"),
                line_items=[
                    LineItem(item="WidgetA", quantity=Decimal("1"), unit_price=Decimal("100.00"), amount=Decimal("100.00"))
                ],
                total=Decimal("100.00"),
            )
            res = IngestionResult(
                invoice=inv,
                source_file="test.json",
                format_detected=FileFormat.JSON,
            )
            # Save invoice succeeds initially
            db.save_invoice(inv, res)
            assert db.get_invoice("INV-TEST-ROLLBACK") is not None

            # Simulate an operational failure during a transaction
            with pytest.raises(sqlite3.OperationalError):
                cursor = db.conn.cursor()
                try:
                    cursor.execute(
                        "INSERT INTO invoices (invoice_id, revision, date, due_date, vendor_name, total) VALUES ('INV-FAIL', 'R2', '2026-01-01', '2026-01-15', 'V', 100)"
                    )
                    # Force error
                    cursor.execute("INSERT INTO non_existent_table VALUES (1)")
                    db.conn.commit()
                except Exception:
                    db.conn.rollback()
                    raise

            # Verify that INV-FAIL was rolled back and does not exist
            c = db.conn.cursor()
            c.execute("SELECT COUNT(*) FROM invoices WHERE invoice_id = 'INV-FAIL'")
            assert c.fetchone()[0] == 0


