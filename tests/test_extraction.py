"""Unit tests for format extractors and normalizers."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from invoice_pipeline.extraction.field_extractor import build_invoice_from_dict
from invoice_pipeline.extraction.normalizers import (
    normalize_currency_amount,
    normalize_date,
    normalize_invoice_id,
    normalize_payment_terms,
)
from invoice_pipeline.extraction.regex_extractor import extract_from_raw_text
from invoice_pipeline.ingestion.csv_extractor import extract_from_csv
from invoice_pipeline.ingestion.file_detector import detect_format
from invoice_pipeline.ingestion.json_extractor import extract_from_json
from invoice_pipeline.ingestion.xml_extractor import extract_from_xml
from invoice_pipeline.models import FileFormat

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_normalizers():
    """Test date, currency, terms, and ID normalizers."""
    assert normalize_date("2026-01-15") == date(2026, 1, 15)
    assert normalize_date("Jan 30 2026") == date(2026, 1, 30)
    assert normalize_date("01/28/2026") == date(2026, 1, 28)
    assert normalize_date("yesterday") is None

    assert normalize_currency_amount("$5,000.00") == Decimal("5000.00")
    assert normalize_currency_amount("@ $750 ea") == Decimal("750")
    assert normalize_currency_amount("1,000.00") == Decimal("1000.00")

    terms, days = normalize_payment_terms("Net 15")
    assert terms == "Net 15"
    assert days == 15

    terms, days = normalize_payment_terms("Immediate")
    assert days == 0

    terms, days = normalize_payment_terms("Immediately")
    assert days == 0

    assert normalize_invoice_id("  INV-1001  ") == "INV-1001"


def test_format_detector():
    """Test format detection on all fixture types."""
    assert detect_format(FIXTURES_DIR / "invoice_json_1.json") == FileFormat.JSON
    assert detect_format(FIXTURES_DIR / "invoice_xml.xml") == FileFormat.XML
    assert detect_format(FIXTURES_DIR / "invoice_csv_kv.csv") == FileFormat.CSV
    assert detect_format(FIXTURES_DIR / "invoice_csv_tabular.csv") == FileFormat.CSV
    assert detect_format(FIXTURES_DIR / "invoice_email.txt") == FileFormat.EMAIL
    assert detect_format(FIXTURES_DIR / "invoice_text_1.txt") == FileFormat.TEXT


def test_json_extractor():
    """Test deterministic extraction of Payment 4 JSON invoice."""
    json_path = FIXTURES_DIR / "invoice_json_1.json"
    content = json_path.read_text(encoding="utf-8")
    extracted = extract_from_json(content)

    assert extracted["invoice_id"] == "INV-1004"
    assert extracted["vendor"]["name"] == "Precision Parts Ltd."
    assert "742 Evergreen Terrace" in extracted["vendor"]["address"]
    assert extracted["total"] == Decimal("1890.00")
    assert extracted["currency"] == "USD"
    assert len(extracted["line_items"]) == 2

    invoice = build_invoice_from_dict(extracted)
    assert invoice.invoice_id == "INV-1004"
    assert invoice.total == Decimal("1890.00")
    assert invoice.due_date == date(2026, 2, 22)


def test_xml_extractor():
    """Test deterministic extraction of XML invoice (Payment example from user)."""
    xml_path = FIXTURES_DIR / "invoice_xml.xml"
    content = xml_path.read_text(encoding="utf-8")
    extracted = extract_from_xml(content)

    assert extracted["invoice_id"] == "INV-1014"
    assert extracted["vendor"]["name"] == "TechParts International"
    assert extracted["total"] == Decimal("4125.00")
    assert extracted["currency"] == "EUR"
    assert len(extracted["line_items"]) == 2

    invoice = build_invoice_from_dict(extracted)
    assert invoice.invoice_id == "INV-1014"
    assert invoice.currency == "EUR"
    assert invoice.total == Decimal("4125.00")


def test_csv_key_value_extractor():
    """Test deterministic extraction of Payment 6 2-column CSV."""
    csv_path = FIXTURES_DIR / "invoice_csv_kv.csv"
    content = csv_path.read_text(encoding="utf-8")
    extracted = extract_from_csv(content)
    assert isinstance(extracted, dict)

    assert extracted["invoice_id"] == "INV-1006"
    assert extracted["vendor"]["name"] == "Acme Industrial Supplies"
    assert extracted["total"] == Decimal("2750.00")
    assert len(extracted["line_items"]) == 2

    invoice = build_invoice_from_dict(extracted)
    assert invoice.invoice_id == "INV-1006"
    assert invoice.total == Decimal("2750.00")


def test_csv_tabular_extractor():
    """Test deterministic extraction of Payment 7 tabular CSV."""
    csv_path = FIXTURES_DIR / "invoice_csv_tabular.csv"
    content = csv_path.read_text(encoding="utf-8")
    extracted = extract_from_csv(content)
    assert isinstance(extracted, dict)

    assert extracted["invoice_id"] == "INV-1007"
    assert extracted["vendor"]["name"] == "MegaWidgets Corp"
    assert extracted["total"] == Decimal("15525.00")
    assert len(extracted["line_items"]) == 3

    invoice = build_invoice_from_dict(extracted)
    assert invoice.invoice_id == "INV-1007"
    assert invoice.total == Decimal("15525.00")


def test_regex_fallback_extractor():
    """Test deterministic regex extraction on unstructured text (Payment 1)."""
    text_path = FIXTURES_DIR / "invoice_text_1.txt"
    content = text_path.read_text(encoding="utf-8")
    extracted = extract_from_raw_text(content)

    assert extracted["invoice_id"] == "INV-1001"
    assert extracted["vendor"]["name"] == "Widgets Inc."
    assert extracted["total"] == Decimal("5000.00")
    assert len(extracted["line_items"]) == 2

    invoice = build_invoice_from_dict(extracted)
    assert invoice.invoice_id == "INV-1001"
    assert invoice.total == Decimal("5000.00")
