"""
Universal Invoice Ingestion & Schema Mapping Pipeline.

A multi-tiered, multimodal document ingestion and semantic schema mapping system:
  - Phase 1: Universal Ingestion Router (JSON, XML, CSV, TXT with Ollama, PDF)
  - Phase 2: Exhaustive 4-Tier Mapping:
      Tier 1: Deterministic dictionary matching (O(1))
      Tier 2: Dual-vector hybrid retrieval (SPLADE + MiniLM in Qdrant)
      Tier 3: Cross-Encoder reranking
      Tier 4: LLM agentic schema evolution (Ollama / OpenRouter)
"""

from .mapper import (
    CrossEncoderReranker,
    DeterministicMatcher,
    DualVectorMatcher,
    InvoiceSchemaMapper,
    LLMSchemaEvolver,
    normalize_key_string,
)
from .qdrant_setup import (
    CANONICAL_CORPUS,
    init_qdrant_collection,
    search_dual_vector,
)
from .router import DocumentIngestionRouter
from .schemas import (
    BatchSchemaEvolutionResult,
    EntityType,
    ExtractedKVPair,
    IntermediateRepresentation,
    MappedField,
    MappingResult,
    SchemaEvolutionProposal,
    TXTIngestionResult,
    UnmappedField,
)

__all__ = [
    # Router & Mapper
    "DocumentIngestionRouter",
    "InvoiceSchemaMapper",
    "DeterministicMatcher",
    "DualVectorMatcher",
    "CrossEncoderReranker",
    "LLMSchemaEvolver",
    "normalize_key_string",
    # Qdrant Dual-Vector
    "init_qdrant_collection",
    "search_dual_vector",
    "CANONICAL_CORPUS",
    # Schemas
    "IntermediateRepresentation",
    "ExtractedKVPair",
    "TXTIngestionResult",
    "EntityType",
    "SchemaEvolutionProposal",
    "BatchSchemaEvolutionResult",
    "MappedField",
    "UnmappedField",
    "MappingResult",
]
