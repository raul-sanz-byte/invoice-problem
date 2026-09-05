"""
Tests for the Universal Invoice Ingestion & Schema Mapping Pipeline.

Validates:
  1. DocumentIngestionRouter (JSON, XML, CSV, TXT sniffing)
  2. InvoiceSchemaMapper:
     - Tier 1 Deterministic (multilingual + abbreviations)
     - Line items parsing and calculation
     - Tier 2 Dual-Vector integration (when Qdrant is available)
     - Tier 3 Cross-Encoder integration
     - Tier 4 LLM Schema Evolution fallback
"""

import json
import pytest
from pathlib import Path

from invoice_pipeline.universal import (
    DocumentIngestionRouter,
    InvoiceSchemaMapper,
    DeterministicMatcher,
    IntermediateRepresentation,
    MappingResult,
    CANONICAL_CORPUS,
    normalize_key_string,
)
from invoice_pipeline.universal.schemas import (
    BatchSchemaEvolutionResult,
    SchemaEvolutionProposal,
    EntityType,
)


def test_normalize_key_string():
    assert normalize_key_string("  Invoice-Number #1: ") == "invoice_number_1"
    assert normalize_key_string("Total TTC (EUR)") == "total_ttc_eur"
    assert normalize_key_string("prix_unitaire") == "prix_unitaire"


def test_deterministic_matcher_multilingual_and_abbreviations():
    matcher = DeterministicMatcher()

    # English
    hit = matcher.match("invoice_number")
    assert hit is not None and hit[0] == "invoice_id"

    # French
    hit = matcher.match("numero_facture")
    assert hit is not None and hit[0] == "invoice_id"
    hit = matcher.match("sous_total")
    assert hit is not None and hit[0] == "subtotal"
    hit = matcher.match("taux_taxe")
    assert hit is not None and hit[0] == "tax_rate"
    hit = matcher.match("conditions_paiement")
    assert hit is not None and hit[0] == "payment_terms"

    # German
    hit = matcher.match("rechnungsnummer")
    assert hit is not None and hit[0] == "invoice_id"
    hit = matcher.match("nettobetrag")
    assert hit is not None and hit[0] == "subtotal"

    # Abbreviations
    hit = matcher.match("inv_no")
    assert hit is not None and hit[0] == "invoice_id"
    hit = matcher.match("subtot")
    assert hit is not None and hit[0] == "subtotal"
    hit = matcher.match("tax_rt")
    assert hit is not None and hit[0] == "tax_rate"
    hit = matcher.match("qty")
    assert hit is not None and hit[0] == "line_item_quantity"


def test_router_json_ingestion():
    router = DocumentIngestionRouter()
    json_sample = json.dumps({
        "invoice_number": "INV-2026-01",
        "vendor": {"name": "Acme Widgets", "address": "123 Main St"},
        "total": 99.50,
        "articles": [
            {"description": "Item A", "quantite": 2, "prix_unitaire": 40.0},
            {"description": "Item B", "quantite": 1, "prix_unitaire": 19.50}
        ]
    })

    ir = router.ingest_string(json_sample, hint_format="json", source_name="test.json")
    assert ir.source_format == "json"
    assert "invoice_number" in ir.raw_pairs
    assert "vendor.name" in ir.raw_pairs
    assert "articles" in ir.raw_pairs


def test_router_xml_ingestion():
    router = DocumentIngestionRouter()
    xml_sample = """<?xml version="1.0" encoding="UTF-8"?>
    <invoice>
        <invoice_id>XML-9988</invoice_id>
        <total>250.00</total>
        <devise>EUR</devise>
    </invoice>
    """
    ir = router.ingest_string(xml_sample, hint_format="xml", source_name="test.xml")
    assert ir.source_format == "xml"
    assert ir.raw_pairs.get("invoice_id") == "XML-9988"
    assert ir.raw_pairs.get("total") == "250.00"
    assert ir.raw_pairs.get("devise") == "EUR"


def test_router_csv_ingestion():
    router = DocumentIngestionRouter()
    csv_sample = "inv_no,vendor,total,currency\nINV-554,Global Corp,1200.00,USD\n"
    ir = router.ingest_string(csv_sample, hint_format="csv", source_name="test.csv")
    assert ir.source_format == "csv"
    assert ir.raw_pairs.get("inv_no") == "INV-554"
    assert ir.raw_pairs.get("vendor") == "Global Corp"
    assert ir.raw_pairs.get("total") == "1200.00"


def test_mapper_end_to_end_facture_1200():
    router = DocumentIngestionRouter()
    mapper = InvoiceSchemaMapper()

    # Test with the actual French invoice in the workspace
    facture_path = Path("invoices/facture_1200.json")
    if facture_path.exists():
        ir = router.ingest(facture_path)
        res = mapper.map_intermediate_representation(ir)

        assert res.stats["failed"] == 0
        assert res.stats["tier_1"] >= 8

        norm = res.normalized_invoice
        assert norm["invoice_id"] == "INV-1200"
        assert norm["vendor"]["name"] == "Precision Parts Ltd."
        assert "742 Evergreen Terrace" in norm["vendor"]["address"]
        assert norm["date"] == "2026-01-22"
        assert norm["due_date"] == "2026-02-22"
        assert norm["subtotal"] == 1750.0
        assert norm["tax_rate"] == 0.08
        assert norm["tax_amount"] == 140.0
        assert norm["total"] == 1890.0
        assert norm["currency"] == "USD"
        assert norm["payment_terms"] == "Net 30 jours"

        # Check line items normalization
        assert len(norm["line_items"]) == 2
        assert norm["line_items"][0]["item"] == "WidgetA"
        assert norm["line_items"][0]["quantity"] == 3.0
        assert norm["line_items"][0]["unit_price"] == 250.0
        assert norm["line_items"][0]["total_price"] == 750.0

        assert norm["line_items"][1]["item"] == "WidgetB"
        assert norm["line_items"][1]["quantity"] == 2.0
        assert norm["line_items"][1]["unit_price"] == 500.0
        assert norm["line_items"][1]["total_price"] == 1000.0


def test_mapper_tier4_schema_evolution_mock():
    mapper = InvoiceSchemaMapper()

    # Provide an unknown field that fails Tiers 1-3
    raw_input = {
        "invoice_number": "INV-999",
        "custom_vat_reg_identifier": "FR88990011223",
        "early_payment_rebate_pct": "0.02",
    }

    # Mock the LLM evolver output
    mock_proposals = [
        SchemaEvolutionProposal(
            original_key="custom_vat_reg_identifier",
            original_value="FR88990011223",
            is_known_invoice_entity=True,
            proposed_canonical_key="vat_number",
            proposed_canonical_value="FR88990011223",
            entity_type=EntityType.IDENTIFIER,
            rationale="Tax registration identifier mapped to vat_number",
            confidence=0.95,
        ),
        SchemaEvolutionProposal(
            original_key="early_payment_rebate_pct",
            original_value="0.02",
            is_known_invoice_entity=True,
            proposed_canonical_key="discount_rate",
            proposed_canonical_value=0.02,
            entity_type=EntityType.FINANCIAL_AMOUNT,
            rationale="Early payment rebate corresponds to discount_rate",
            confidence=0.92,
        ),
    ]

    mapper.tier4.evolve_schema_batch = lambda unmapped_items, context_pairs: mock_proposals

    res = mapper.map_dict(raw_input)
    assert res.stats["tier_1"] == 1
    assert res.stats["tier_4"] == 2
    assert res.stats["failed"] == 0
    assert res.normalized_invoice["vat_number"] == "FR88990011223"
    assert res.normalized_invoice["discount_rate"] == 0.02


def test_qdrant_dual_vector_and_tier3():
    from qdrant_client import QdrantClient
    import numpy as np
    from invoice_pipeline.universal import init_qdrant_collection

    client = QdrantClient(":memory:")

    class MockDense:
        def encode(self, text, normalize_embeddings=True):
            vec = np.zeros(384, dtype=np.float32)
            vec[0] = 1.0
            return vec

    class MockSparseEmbedding:
        def __init__(self, indices, values):
            self.indices = np.array(indices, dtype=np.int32)
            self.values = np.array(values, dtype=np.float32)

    class MockSparse:
        def embed(self, texts):
            for _ in texts:
                yield MockSparseEmbedding([42], [1.0])

    class MockCrossEncoder:
        def predict(self, pairs):
            return np.array([0.92] * len(pairs))

    # Initialize collection in memory
    init_qdrant_collection(
        client=client,
        collection_name="test_schema_fields",
        dense_dim=384,
        dense_model=MockDense(),
        sparse_model=MockSparse(),
        recreate=True,
    )

    collections = client.get_collections().collections
    assert any(c.name == "test_schema_fields" for c in collections)

    mapper = InvoiceSchemaMapper(
        qdrant_client=client,
        dense_model=MockDense(),
        sparse_model=MockSparse(),
        cross_encoder_model=MockCrossEncoder(),
        cross_encoder_threshold=0.60,
    )
    mapper.tier2.collection_name = "test_schema_fields"

    # Input an obscure field that is not in Tier 1 dictionary
    raw_input = {"obscure_mysterious_date_label": "2026-05-10"}
    res = mapper.map_dict(raw_input)

    # Should be resolved by Tier 3 (CrossEncoder)
    assert res.stats["tier_3"] == 1
    assert len(res.mapped) == 1
    assert res.mapped[0].mapping_tier == 3
    assert res.mapped[0].confidence >= 0.60

