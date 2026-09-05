"""
Pydantic schemas for the Universal Invoice Ingestion Pipeline.

Used across:
  - Phase 1 (TXT extraction via Ollama structured output)
  - Phase 2 Tier 4 (Schema evolution proposals from Ollama)
  - Intermediate Representation (IR) shared between phases
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared Intermediate Representation
# ---------------------------------------------------------------------------

class IntermediateRepresentation(BaseModel):
    """
    Flat key-value dictionary produced by Phase 1.
    All subsequent mapping operates on this structure.
    """
    source_format: str = Field(description="Detected format: json | xml | csv | txt | pdf")
    source_file: str = Field(default="", description="Original filename or URI")
    raw_pairs: dict[str, Any] = Field(
        description="Flattened key-value pairs as extracted from the source document"
    )


# ---------------------------------------------------------------------------
# Phase 1 – TXT Ingestion via Ollama
# ---------------------------------------------------------------------------

class ExtractedKVPair(BaseModel):
    """A single key-value pair extracted from unstructured text."""

    original_key: str = Field(
        description="The key exactly as it appears or is implied in the document text"
    )
    value: Any = Field(
        description="The extracted value (string, number, list, or nested dict)"
    )
    value_type: str = Field(
        default="string",
        description="Inferred type: string | number | date | list | object | boolean",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Extraction confidence [0, 1]",
    )


class TXTIngestionResult(BaseModel):
    """
    Structured result produced by the Ollama LLM when parsing
    a free-form plain-text invoice.
    """

    document_language: str = Field(
        default="en",
        description="ISO 639-1 language code of the document (e.g. 'fr', 'de', 'en')",
    )
    document_type: str = Field(
        default="invoice",
        description="Document classification: invoice | receipt | purchase_order | quote | other",
    )
    pairs: list[ExtractedKVPair] = Field(
        description="All key-value pairs visible in the document, exhaustively extracted"
    )
    line_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Structured line items, each with at minimum: "
            "{'item': str, 'quantity': number, 'unit_price': number}"
        ),
    )
    extraction_notes: str = Field(
        default="",
        description="Free-text notes about ambiguities, OCR artefacts, or missing fields",
    )


# ---------------------------------------------------------------------------
# Phase 2 Tier 4 – Agentic Schema Evolution via Ollama
# ---------------------------------------------------------------------------

class EntityType(str, Enum):
    FINANCIAL_AMOUNT = "financial_amount"
    IDENTIFIER = "identifier"
    DATE = "date"
    ADDRESS = "address"
    PERSON_NAME = "person_name"
    QUANTITY = "quantity"
    TEXT_DESCRIPTION = "text_description"
    BOOLEAN_FLAG = "boolean_flag"
    UNKNOWN = "unknown"


class SchemaEvolutionProposal(BaseModel):
    """
    Ollama's proposal for how to canonicalize an unmapped field
    that was not resolved by Tiers 1–3.
    """

    original_key: str = Field(description="The raw key from the source document")
    original_value: Any = Field(description="The value associated with the key")

    is_known_invoice_entity: bool = Field(
        description=(
            "True if this field represents a known invoice concept "
            "(amount, date, identifier, address, etc.)"
        )
    )
    proposed_canonical_key: str = Field(
        description=(
            "Normalized snake_case English key name that best represents "
            "this field in a universal invoice schema"
        )
    )
    proposed_canonical_value: Any = Field(
        description="The value normalized to the proposed canonical type"
    )
    entity_type: EntityType = Field(
        description="Semantic category of this field"
    )
    rationale: str = Field(
        description="One-sentence explanation of the mapping decision"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the proposed canonical mapping [0, 1]",
    )


class BatchSchemaEvolutionResult(BaseModel):
    """Container for multiple schema evolution proposals from one Ollama call."""

    proposals: list[SchemaEvolutionProposal]
    new_fields_discovered: int = Field(
        default=0,
        description="Count of proposals that represent genuinely new schema fields",
    )


# ---------------------------------------------------------------------------
# Phase 2 – Final Mapped Output
# ---------------------------------------------------------------------------

class MappedField(BaseModel):
    """One successfully mapped field, with full provenance."""

    canonical_key: str
    value: Any
    original_key: str
    mapping_tier: int = Field(
        description="Tier that resolved this mapping: 1=deterministic, 2=vector, 3=cross-encoder, 4=llm"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class UnmappedField(BaseModel):
    """A field that could not be mapped by any tier."""

    original_key: str
    value: Any
    reason: str


class MappingResult(BaseModel):
    """Final output of the InvoiceSchemaMapper."""

    source_format: str
    source_file: str
    mapped: list[MappedField]
    unmapped: list[UnmappedField]
    normalized_invoice: dict[str, Any] = Field(
        description="Final flat dict of canonical_key → value ready for Pydantic Invoice model"
    )
    stats: dict[str, int] = Field(
        description="Per-tier mapping counts: {tier_1: N, tier_2: N, tier_3: N, tier_4: N, failed: N}"
    )
