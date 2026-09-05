"""Unit tests for the dynamic vocabulary manager and field resolution."""

from decimal import Decimal
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from invoice_pipeline.extraction.vocabulary import VocabularyManager, get_vocabulary_manager
from invoice_pipeline.ingestion.json_extractor import extract_from_json
from invoice_pipeline.ingestion.xml_extractor import extract_from_xml
from invoice_pipeline.ingestion.csv_extractor import extract_from_csv


def test_vocabulary_resolution_defaults():
    vocab = VocabularyManager()

    # Default canonical fields
    assert vocab.resolve("invoice_number") == "invoice_id"
    assert vocab.resolve("inv_no") == "invoice_id"
    assert vocab.resolve("bill_no") == "invoice_id"
    assert vocab.resolve("folio") == "invoice_id"

    assert vocab.resolve("issue_date") == "date"
    assert vocab.resolve("bill_date") == "date"

    assert vocab.resolve("payee") == "vendor"
    assert vocab.resolve("supplier") == "vendor"
    assert vocab.resolve("remit_to") == "vendor"

    assert vocab.resolve("grand_total") == "total"
    assert vocab.resolve("amount_due") == "total"

    # Line item fields
    assert vocab.resolve("article", is_line_item=True) == "item"
    assert vocab.resolve("count", is_line_item=True) == "quantity"
    assert vocab.resolve("rate", is_line_item=True) == "unit_price"
    assert vocab.resolve("line_amount", is_line_item=True) == "amount"


def test_vocabulary_persistence_in_sqlite():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = Path(tmpdir) / "vocab_test.db"
        vocab1 = VocabularyManager(db_path)

        # Register novel aliases
        vocab1.register_alias("custom_bill_code", "invoice_id")
        vocab1.register_alias("seller_org", "vendor")
        vocab1.register_alias("sku_label", "item", is_line_item=True)

        assert vocab1.resolve("custom_bill_code") == "invoice_id"
        assert vocab1.resolve("seller_org") == "vendor"
        assert vocab1.resolve("sku_label", is_line_item=True) == "item"

        # Initialize a new VocabularyManager pointing to the same DB
        vocab2 = VocabularyManager(db_path)
        assert vocab2.resolve("custom_bill_code") == "invoice_id"
        assert vocab2.resolve("seller_org") == "vendor"
        assert vocab2.resolve("sku_label", is_line_item=True) == "item"


def test_json_extraction_with_alternative_field_names():
    """Test extracting JSON with uncommon alternative field names using vocabulary."""
    alt_json = """{
        "folio": "INV-ALT-9001",
        "bill_date": "2026-03-01",
        "payee": "Alternative Tech Corp",
        "order_lines": [
            {"article": "CustomPartA", "count": 4, "rate": 50.00},
            {"article": "CustomPartB", "count": 2, "rate": 100.00}
        ],
        "sub_total": 400.00,
        "tax_total": 40.00,
        "grand_total": 440.00
    }"""
    vocab = VocabularyManager()
    extracted = extract_from_json(alt_json, vocab_mgr=vocab)

    assert extracted["invoice_id"] == "INV-ALT-9001"
    assert extracted["date"] == "2026-03-01"
    assert extracted["vendor"]["name"] == "Alternative Tech Corp"
    assert extracted["total"] == Decimal("440.00")
    assert len(extracted["line_items"]) == 2
    assert extracted["line_items"][0]["item"] == "CustomPartA"
    assert extracted["line_items"][0]["quantity"] == Decimal("4")
    assert extracted["line_items"][0]["unit_price"] == Decimal("50.00")


def test_dynamic_learning_via_mock_light_llm():
    """Test that when brand new unknown keys appear, the light LLM is consulted and learns them."""
    brand_new_json = """{
        "x_transaction_record_id": "REC-9999",
        "x_originating_party": "Dynamic Vendor Co.",
        "x_generation_timestamp": "2026-04-15",
        "x_bottom_line_settlement": 1250.00,
        "items": [
            {"item": "DynamicItem", "quantity": 1, "unit_price": 1250.00}
        ]
    }"""
    # Create mock LLM client returning mapping for unknown keys
    mock_llm = MagicMock()
    mock_llm.map_alternative_fields.return_value = {
        "x_transaction_record_id": "invoice_id",
        "x_originating_party": "vendor",
        "x_generation_timestamp": "date",
        "x_bottom_line_settlement": "total",
    }

    vocab = VocabularyManager()
    extracted = extract_from_json(brand_new_json, llm_client=mock_llm, vocab_mgr=vocab)

    # Verify extraction succeeded
    assert extracted["invoice_id"] == "REC-9999"
    assert extracted["vendor"]["name"] == "Dynamic Vendor Co."
    assert extracted["date"] == "2026-04-15"
    assert extracted["total"] == Decimal("1250.00")

    # Verify that the vocabulary learned these mappings permanently
    assert vocab.resolve("x_transaction_record_id") == "invoice_id"
    assert vocab.resolve("x_originating_party") == "vendor"
    assert vocab.resolve("x_generation_timestamp") == "date"
    assert vocab.resolve("x_bottom_line_settlement") == "total"

    # Now a second document with these fields can be extracted with ZERO LLM calls!
    extracted_second = extract_from_json(brand_new_json, llm_client=None, vocab_mgr=vocab)
    assert extracted_second["invoice_id"] == "REC-9999"


def test_regex_extractor_with_vocabulary():
    """Test that regex extractor dynamically recognizes newly registered vocabulary aliases."""
    from invoice_pipeline.extraction.regex_extractor import extract_from_raw_text

    vocab = VocabularyManager()
    # Register novel terms that default regex didn't know about
    vocab.register_alias("folio_record", "invoice_id")
    vocab.register_alias("payee_entity", "vendor")
    vocab.register_alias("settlement_cap", "total")

    invoice_text = """
    INVOICE RECEIPT

    Folio Record: FOLIO-2026-X
    Payee Entity: Global Supplies Ltd.
    Date: 2026-05-01
    Due Date: 2026-05-15

    Items:
      GadgetX   count: 5   rate: $100.00

    Settlement Cap: $500.00
    """

    extracted = extract_from_raw_text(invoice_text, vocab_mgr=vocab)

    assert extracted["invoice_id"] == "FOLIO-2026-X"
    assert extracted["vendor"]["name"] == "Global Supplies Ltd."
    assert extracted["date"] == "2026-05-01"
    assert extracted["total"] == Decimal("500.00")
    assert len(extracted["line_items"]) == 1
    assert extracted["line_items"][0]["item"] == "GadgetX"
    assert extracted["line_items"][0]["quantity"] == Decimal("5")
    assert extracted["line_items"][0]["unit_price"] == Decimal("100.00")
