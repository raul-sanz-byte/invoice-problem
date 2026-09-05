"""
Phase 2 – Exhaustive Multi-Tiered Invoice Schema Mapper.

Maps raw, heterogeneous, multilingual, and abbreviated keys from Phase 1
Intermediate Representation (IR) into a canonical invoice schema using a 4-tier
fallback pipeline:

  Tier 1 (Deterministic):
    O(1) dictionary lookup against canonical fields, known aliases, and abbreviations.
  Tier 2 (Dual-Vector Search in Qdrant):
    Hybrid retrieval using dense (paraphrase-multilingual-MiniLM-L12-v2) and
    sparse (SPLADE) embeddings to retrieve top-k candidate canonical concepts.
  Tier 3 (Cross-Encoder Reranking):
    Cross-encoder (e.g. cross-encoder/ms-marco-MiniLM-L-6-v2) scoring candidate pairs.
    Matches exceeding the confidence threshold are accepted.
  Tier 4 (LLM Schema Evolution):
    Local LLM (Ollama structured output, with OpenRouter/OpenAI fallback) evaluates
    unresolved keys within full document context to propose a canonical mapping or
    new schema entity (Schema Evolution).

Produces a fully typed MappingResult with per-field provenance and stats.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

from .qdrant_setup import CANONICAL_CORPUS, search_dual_vector
from .schemas import (
    BatchSchemaEvolutionResult,
    EntityType,
    IntermediateRepresentation,
    MappedField,
    MappingResult,
    SchemaEvolutionProposal,
    UnmappedField,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Key Normalization Helper
# ---------------------------------------------------------------------------

def normalize_key_string(key: str) -> str:
    """
    Standardize a key string: strip whitespace, lowercase, remove punctuation,
    and collapse delimiters into single underscores.
    """
    s = key.strip().lower()
    # Remove common punctuation like quotes, colons, hashes
    s = re.sub(r"[\"'#:\(\)\[\]\{\}]", "", s)
    # Replace non-alphanumeric (spaces, hyphens, dots, slashes) with underscore
    s = re.sub(r"[\s\-\.\/\\_]+", "_", s)
    return s.strip("_")


# ---------------------------------------------------------------------------
# Tier 1: Deterministic Hardcoded Dictionary
# ---------------------------------------------------------------------------

class DeterministicMatcher:
    """
    Tier 1 matcher: O(1) dictionary lookup for exact and normalized key matches.
    Seeded with all aliases from CANONICAL_CORPUS, plus common invoice abbreviations.
    """

    def __init__(self, corpus: list[dict[str, Any]] | None = None) -> None:
        self.lookup_table: dict[str, str] = {}
        self._build_table(corpus or CANONICAL_CORPUS)

    def _build_table(self, corpus: list[dict[str, Any]]) -> None:
        for entry in corpus:
            canon = entry["canonical_key"]
            self._register(canon, canon)
            for alias in entry.get("aliases", []):
                self._register(alias, canon)

        # Common industrial invoice abbreviations across EN / FR / DE / ES
        extra_abbreviations = {
            # Invoice ID
            "inv": "invoice_id",
            "inv_no": "invoice_id",
            "inv_num": "invoice_id",
            "inv_#": "invoice_id",
            "fact_no": "invoice_id",
            "n_fact": "invoice_id",
            "re_nr": "invoice_id",
            # Dates
            "inv_dt": "date",
            "dt": "date",
            "due_dt": "due_date",
            "dd": "due_date",
            "f_ech": "due_date",
            # Vendor
            "vend": "vendor_name",
            "supp": "vendor_name",
            "fourn": "vendor_name",
            "vend_addr": "vendor_address",
            "supp_addr": "vendor_address",
            # Financials
            "sub": "subtotal",
            "subtot": "subtotal",
            "stot": "subtotal",
            "net": "subtotal",
            "ht": "subtotal",
            "sous_tot": "subtotal",
            "tax_rt": "tax_rate",
            "tax_%": "tax_rate",
            "tva_tx": "tax_rate",
            "tax_amt": "tax_amount",
            "tot_tax": "tax_amount",
            "tva_amt": "tax_amount",
            "tot": "total",
            "tot_amt": "total",
            "gr_tot": "total",
            "ttc": "total",
            "curr": "currency",
            "cur": "currency",
            "dev": "currency",
            # Line items & terms
            "pmt_terms": "payment_terms",
            "terms_cond": "payment_terms",
            "cond_pmt": "payment_terms",
            "shp": "shipping",
            "ship": "shipping",
            "frt": "shipping",
            "rem": "notes",
            # Line item level fields
            "desc": "line_item_description",
            "item_desc": "line_item_description",
            "qty": "line_item_quantity",
            "qte": "line_item_quantity",
            "pr": "line_item_unit_price",
            "unit_pr": "line_item_unit_price",
            "pu": "line_item_unit_price",
            "lin_amt": "line_item_amount",
            "lin_tot": "line_item_amount",
            "tot_lin": "line_item_amount",
        }
        for abbr, canon in extra_abbreviations.items():
            self._register(abbr, canon)

    def _register(self, key: str, canonical: str) -> None:
        raw_clean = key.strip().lower()
        norm = normalize_key_string(key)
        self.lookup_table[raw_clean] = canonical
        self.lookup_table[norm] = canonical
        # Strip all underscores for squeezed matching (e.g., 'subtotal' matches 'sub_total')
        self.lookup_table[norm.replace("_", "")] = canonical

    def match(self, raw_key: str) -> tuple[str, float] | None:
        """
        Attempts exact and normalized match.
        Returns (canonical_key, confidence=1.0) or None.
        """
        raw_clean = raw_key.strip().lower()
        if raw_clean in self.lookup_table:
            return self.lookup_table[raw_clean], 1.0

        norm = normalize_key_string(raw_key)
        if norm in self.lookup_table:
            return self.lookup_table[norm], 1.0

        squeezed = norm.replace("_", "")
        if squeezed in self.lookup_table:
            return self.lookup_table[squeezed], 1.0

        # Sub-key suffix check: e.g. "fournisseur.nom" -> "vendor_name"
        if "." in raw_key:
            parts = [normalize_key_string(p) for p in raw_key.split(".")]
            prefix, sub = parts[0], parts[-1]
            prefix_canon = self.lookup_table.get(prefix)

            # Vendor nested sub-fields
            if prefix_canon in ("vendor_name", "vendor"):
                if sub in ("nom", "name", "nombre", "razao_social", "bezeichnung", "company", "societe"):
                    return "vendor_name", 1.0
                if sub in ("adresse", "address", "direccion", "anschrift", "endereco", "addr"):
                    return "vendor_address", 1.0

            # Direct lookup of subkey
            if sub in self.lookup_table:
                composite = f"{prefix}_{sub}"
                if composite in self.lookup_table:
                    return self.lookup_table[composite], 1.0
                return self.lookup_table[sub], 0.95

        return None


# ---------------------------------------------------------------------------
# Tier 2: Dual-Vector Search (SPLADE Sparse + MiniLM Dense) in Qdrant
# ---------------------------------------------------------------------------

class DualVectorMatcher:
    """
    Tier 2 matcher: Dual-vector hybrid retrieval against Qdrant.
    Combines SPLADE sparse lexical embeddings with MiniLM dense multilingual embeddings.
    """

    def __init__(
        self,
        qdrant_client: Any = None,
        dense_model: Any = None,
        sparse_model: Any = None,
        collection_name: str = "invoice_schema_fields",
    ) -> None:
        if qdrant_client is not None:
            self.client = qdrant_client
            self.mode_description = "Custom Client"
        else:
            try:
                from invoice_pipeline.universal.qdrant_setup import get_qdrant_client
                self.client, self.mode_description = get_qdrant_client()
                logger.info("DualVectorMatcher Qdrant backend: %s", self.mode_description)
            except Exception as exc:
                logger.debug("Could not initialize Qdrant backend: %s", exc)
                self.client = None
                self.mode_description = "None"

        self.dense_model = dense_model
        self.sparse_model = sparse_model
        self.collection_name = os.getenv("QDRANT_COLLECTION_NAME", collection_name)

    @property
    def is_available(self) -> bool:
        return (
            self.client is not None
            and self.dense_model is not None
            and self.sparse_model is not None
        )

    def retrieve_candidates(self, query_key: str, top_k: int = 5) -> list[dict[str, Any]]:
        """
        Runs dual-vector search in Qdrant to retrieve candidate canonical fields.
        Returns list of dicts: [{'canonical_key': str, 'score': float, 'payload': dict}]
        """
        if not self.is_available:
            return []

        try:
            return search_dual_vector(
                client=self.client,
                query_text=query_key,
                dense_model=self.dense_model,
                sparse_model=self.sparse_model,
                collection_name=self.collection_name,
                top_k=top_k,
            )
        except Exception as exc:
            logger.warning("Dual-vector search failed for '%s': %s", query_key, exc)
            return []


# ---------------------------------------------------------------------------
# Tier 3: Cross-Encoder Reranker
# ---------------------------------------------------------------------------

class CrossEncoderReranker:
    """
    Tier 3 matcher: Re-ranks top-k candidates from Tier 2 using a Cross-Encoder
    model (e.g. cross-encoder/ms-marco-MiniLM-L-6-v2) for deep semantic relevance.
    """

    def __init__(
        self,
        cross_encoder_model: Any = None,
        confidence_threshold: float = 0.65,
    ) -> None:
        self.model = cross_encoder_model
        self.threshold = confidence_threshold

    @property
    def is_available(self) -> bool:
        return self.model is not None

    def rerank(
        self,
        query_key: str,
        candidates: list[dict[str, Any]],
        corpus_lookup: dict[str, dict[str, Any]],
    ) -> tuple[str, float] | None:
        """
        Scores candidate pairs (query_key, candidate_description) with the Cross-Encoder.
        If top score exceeds confidence threshold, returns (canonical_key, score), else None.
        """
        if not self.is_available or not candidates:
            return None

        pairs = []
        candidate_keys = []
        for cand in candidates:
            c_key = cand.get("canonical_key", "")
            meta = corpus_lookup.get(c_key, {})
            desc = meta.get("description", "")
            aliases = ", ".join(meta.get("aliases", [])[:5])
            cand_text = f"Field: {c_key}. Description: {desc}. Common names: {aliases}"
            pairs.append([f"Invoice field name: {query_key}", cand_text])
            candidate_keys.append(c_key)

        try:
            scores = self.model.predict(pairs)
            # Normalize or inspect scores
            best_idx = int(scores.argmax())
            best_score = float(scores[best_idx])
            # Handle logits conversion if unbounded
            if best_score > 1.0 or best_score < 0.0:
                import math
                prob = 1.0 / (1.0 + math.exp(-best_score))
            else:
                prob = best_score

            if prob >= self.threshold:
                return candidate_keys[best_idx], round(prob, 4)

            logger.debug(
                "Tier 3 top candidate '%s' scored %.3f < threshold %.3f",
                candidate_keys[best_idx],
                prob,
                self.threshold,
            )
            return None
        except Exception as exc:
            logger.warning("Tier 3 cross-encoder reranking failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Tier 4: LLM Schema Evolution (Ollama with OpenRouter / OpenAI Fallback)
# ---------------------------------------------------------------------------

class LLMSchemaEvolver:
    """
    Tier 4: Agentic Schema Evolution.
    For fields failing Tiers 1-3, queries an LLM with full context.
    The model proposes either an existing canonical key or evolves the schema
    with a new valid canonical entity, producing a Pydantic-validated output.
    """

    def __init__(
        self,
        ollama_model: str = "qwen2.5:7b",
        openai_client: Any = None,
        openai_model: str = "openai/gpt-4o-mini",
        confidence_threshold: float = 0.50,
    ) -> None:
        self.ollama_model = ollama_model
        self.openai_client = openai_client
        self.openai_model = openai_model
        self.confidence_threshold = confidence_threshold

    def evolve_schema_batch(
        self,
        unmapped_items: list[tuple[str, Any]],
        context_pairs: dict[str, Any],
    ) -> list[SchemaEvolutionProposal]:
        """
        Executes schema evolution for a batch of unmapped key-value pairs.
        Tries Ollama first; if unavailable, falls back to OpenRouter/OpenAI.
        """
        if not unmapped_items:
            return []

        prompt_data = {
            "unmapped_fields": [
                {"key": k, "sample_value": v} for k, v in unmapped_items
            ],
            "document_context": {
                k: str(v)[:60] for k, v in list(context_pairs.items())[:10]
            },
            "canonical_schema_fields": [
                entry["canonical_key"] for entry in CANONICAL_CORPUS
            ],
        }

        # Try Ollama first
        proposals = self._call_ollama(prompt_data)
        if proposals is not None:
            return proposals

        # Fallback to OpenAI / OpenRouter client
        proposals = self._call_openai(prompt_data)
        if proposals is not None:
            return proposals

        return []

    def _call_ollama(self, prompt_data: dict[str, Any]) -> list[SchemaEvolutionProposal] | None:
        try:
            import ollama
            system_prompt = (
                "You are an expert financial ontology engineer. "
                "Analyze unmapped invoice fields. For each field, determine whether it matches an "
                "existing canonical invoice field (even under abbreviations or multilingual terms), "
                "or represents a genuinely new invoice entity (Schema Evolution, e.g. vat_id, iban, discount). "
                "Return JSON conforming to BatchSchemaEvolutionResult."
            )
            schema_json = BatchSchemaEvolutionResult.model_json_schema()
            user_prompt = (
                f"Analyze these unmapped invoice fields:\n{json.dumps(prompt_data, indent=2)}\n\n"
                f"Return JSON adhering to schema:\n{json.dumps(schema_json, indent=2)}"
            )

            res = ollama.chat(
                model=self.ollama_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                format="json",
                options={"temperature": 0.0},
            )
            raw = res["message"]["content"]
            result = BatchSchemaEvolutionResult.model_validate_json(raw)
            return result.proposals
        except Exception as exc:
            logger.debug("Ollama schema evolution unavailable or failed: %s", exc)
            return None

    def _call_openai(self, prompt_data: dict[str, Any]) -> list[SchemaEvolutionProposal] | None:
        client = self.openai_client
        if client is None:
            # Check environment for OPENROUTER_API_KEY or OPENAI_API_KEY
            api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
            if not api_key:
                return None
            try:
                from openai import OpenAI
                base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
                client = OpenAI(api_key=api_key, base_url=base_url)
            except Exception as e:
                logger.debug("Failed to initialize OpenAI client: %s", e)
                return None

        try:
            system_prompt = (
                "You are an expert financial ontology engineer. "
                "Analyze unmapped invoice fields and map them to canonical invoice field names, "
                "or propose new valid snake_case schema fields. Return strict JSON matching BatchSchemaEvolutionResult."
            )
            schema_json = BatchSchemaEvolutionResult.model_json_schema()
            user_prompt = (
                f"Input data:\n{json.dumps(prompt_data, indent=2)}\n\n"
                f"JSON Schema:\n{json.dumps(schema_json, indent=2)}"
            )

            model = os.getenv("OPENROUTER_LIGHT_MODEL", self.openai_model)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            raw_content = response.choices[0].message.content or "{}"
            result = BatchSchemaEvolutionResult.model_validate_json(raw_content)
            return result.proposals
        except Exception as exc:
            logger.warning("OpenAI/OpenRouter schema evolution fallback failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# InvoiceSchemaMapper (Phase 2 Master Pipeline)
# ---------------------------------------------------------------------------

class InvoiceSchemaMapper:
    """
    Phase 2 – Universal Invoice Schema Mapper.

    Processes unmapped fields through the multi-tiered fallback architecture:
      - Tier 1: Deterministic dictionary lookup (exact & normalized)
      - Tier 2: Qdrant dual-vector search (SPLADE + MiniLM)
      - Tier 3: Cross-Encoder reranking (> threshold)
      - Tier 4: LLM schema evolution (Ollama / OpenRouter fallback)

    Also normalizes line items and produces the final canonical dictionary.
    """

    def __init__(
        self,
        qdrant_client: Any = None,
        dense_model: Any = None,
        sparse_model: Any = None,
        cross_encoder_model: Any = None,
        ollama_model: str = "qwen2.5:7b",
        openai_client: Any = None,
        cross_encoder_threshold: float = 0.65,
    ) -> None:
        self.corpus_lookup = {
            entry["canonical_key"]: entry for entry in CANONICAL_CORPUS
        }

        # Initialize tiers
        self.tier1 = DeterministicMatcher(CANONICAL_CORPUS)
        self.tier2 = DualVectorMatcher(
            qdrant_client=qdrant_client,
            dense_model=dense_model,
            sparse_model=sparse_model,
        )
        self.tier3 = CrossEncoderReranker(
            cross_encoder_model=cross_encoder_model,
            confidence_threshold=cross_encoder_threshold,
        )
        self.tier4 = LLMSchemaEvolver(
            ollama_model=ollama_model,
            openai_client=openai_client,
        )

    # ── Public Mapping APIs ───────────────────────────────────────────────

    def map_intermediate_representation(
        self, ir: IntermediateRepresentation
    ) -> MappingResult:
        """
        Primary entry point for Phase 2: consumes an IR from Phase 1 router
        and returns a complete MappingResult.
        """
        return self.map_dict(
            raw_pairs=ir.raw_pairs,
            source_format=ir.source_format,
            source_file=ir.source_file,
        )

    def map_dict(
        self,
        raw_pairs: dict[str, Any],
        source_format: str = "generic",
        source_file: str = "",
    ) -> MappingResult:
        """
        Executes multi-tiered mapping on a dictionary of raw key-value pairs.
        """
        mapped_fields: list[MappedField] = []
        unmapped_fields: list[UnmappedField] = []
        stats = {"tier_1": 0, "tier_2": 0, "tier_3": 0, "tier_4": 0, "failed": 0}

        # Separate special composite keys (like 'line_items') from flat KV pairs
        line_items_raw = raw_pairs.get("line_items") or raw_pairs.get("articles") or raw_pairs.get("items")
        flat_pairs = {
            k: v
            for k, v in raw_pairs.items()
            if k not in ("line_items", "articles", "items", "__raw_pdf_text__")
        }

        # Step 1: Process flat pairs through Tier 1 (Deterministic)
        pending_tier2: list[tuple[str, Any]] = []

        for key, value in flat_pairs.items():
            t1_hit = self.tier1.match(key)
            if t1_hit is not None:
                canon_key, conf = t1_hit
                mapped_fields.append(
                    MappedField(
                        canonical_key=canon_key,
                        value=value,
                        original_key=key,
                        mapping_tier=1,
                        confidence=conf,
                    )
                )
                stats["tier_1"] += 1
            else:
                pending_tier2.append((key, value))

        # Step 2: Process remaining fields through Tier 2 (Dual-Vector) + Tier 3 (Cross-Encoder)
        pending_tier4: list[tuple[str, Any]] = []

        for key, value in pending_tier2:
            resolved = False
            candidates = self.tier2.retrieve_candidates(key, top_k=5)

            if candidates:
                # If Tier 3 is available, rerank candidates
                if self.tier3.is_available:
                    t3_hit = self.tier3.rerank(key, candidates, self.corpus_lookup)
                    if t3_hit is not None:
                        canon_key, conf = t3_hit
                        mapped_fields.append(
                            MappedField(
                                canonical_key=canon_key,
                                value=value,
                                original_key=key,
                                mapping_tier=3,
                                confidence=conf,
                            )
                        )
                        stats["tier_3"] += 1
                        resolved = True
                else:
                    # If no Tier 3 reranker, use top Tier 2 vector hit if score is high
                    top_cand = candidates[0]
                    # RRF scores are typically lower than cosine; check relative confidence
                    if top_cand.get("score", 0.0) >= 0.02:
                        mapped_fields.append(
                            MappedField(
                                canonical_key=top_cand["canonical_key"],
                                value=value,
                                original_key=key,
                                mapping_tier=2,
                                confidence=min(1.0, float(top_cand["score"]) * 10),
                            )
                        )
                        stats["tier_2"] += 1
                        resolved = True

            if not resolved:
                pending_tier4.append((key, value))

        # Step 3: Process remaining unresolved fields through Tier 4 (LLM Schema Evolution)
        if pending_tier4:
            proposals = self.tier4.evolve_schema_batch(
                unmapped_items=pending_tier4,
                context_pairs=flat_pairs,
            )
            proposal_map = {p.original_key: p for p in proposals}

            for key, value in pending_tier4:
                prop = proposal_map.get(key)
                if (
                    prop is not None
                    and prop.is_known_invoice_entity
                    and prop.confidence >= self.tier4.confidence_threshold
                ):
                    mapped_fields.append(
                        MappedField(
                            canonical_key=prop.proposed_canonical_key,
                            value=prop.proposed_canonical_value or value,
                            original_key=key,
                            mapping_tier=4,
                            confidence=prop.confidence,
                        )
                    )
                    stats["tier_4"] += 1
                else:
                    reason = (
                        prop.rationale
                        if prop
                        else "No match found across all 4 tiers"
                    )
                    unmapped_fields.append(
                        UnmappedField(original_key=key, value=value, reason=reason)
                    )
                    stats["failed"] += 1

        # Step 4: Normalize and assemble final invoice dictionary
        normalized_invoice = self._assemble_normalized_invoice(
            mapped_fields=mapped_fields,
            line_items_raw=line_items_raw,
        )

        logger.info(
            "Mapping complete for %s (%s): %d mapped (T1:%d, T2:%d, T3:%d, T4:%d), %d unmapped",
            source_file or "<memory>",
            source_format,
            len(mapped_fields),
            stats["tier_1"],
            stats["tier_2"],
            stats["tier_3"],
            stats["tier_4"],
            len(unmapped_fields),
        )

        return MappingResult(
            source_format=source_format,
            source_file=source_file,
            mapped=mapped_fields,
            unmapped=unmapped_fields,
            normalized_invoice=normalized_invoice,
            stats=stats,
        )

    # ── Internal Helpers ─────────────────────────────────────────────────

    def _normalize_line_items(self, raw_items: list[Any]) -> list[dict[str, Any]]:
        """
        Normalizes an array of line items by mapping their internal keys
        (e.g., 'quantite' -> 'quantity', 'prix_unitaire' -> 'unit_price').
        """
        normalized: list[dict[str, Any]] = []

        for item in raw_items:
            if not isinstance(item, dict):
                continue

            item_mapped: dict[str, Any] = {}
            for k, v in item.items():
                hit = self.tier1.match(k)
                if hit:
                    canon, _ = hit
                    # Map line_item_ prefix to clean line item keys
                    clean_k = canon.replace("line_item_", "")
                    if clean_k == "description":
                        clean_k = "item"
                    item_mapped[clean_k] = v
                else:
                    item_mapped[normalize_key_string(k)] = v

            # Coerce numerical types
            try:
                if "quantity" in item_mapped:
                    item_mapped["quantity"] = float(item_mapped["quantity"])
                if "unit_price" in item_mapped:
                    item_mapped["unit_price"] = float(item_mapped["unit_price"])
                if "amount" in item_mapped:
                    item_mapped["total_price"] = float(item_mapped["amount"])
                elif "total" in item_mapped:
                    item_mapped["total_price"] = float(item_mapped["total"])
                elif "quantity" in item_mapped and "unit_price" in item_mapped:
                    item_mapped["total_price"] = round(
                        item_mapped["quantity"] * item_mapped["unit_price"], 2
                    )
            except (ValueError, TypeError):
                pass

            normalized.append(item_mapped)

        return normalized

    def _assemble_normalized_invoice(
        self,
        mapped_fields: list[MappedField],
        line_items_raw: Any,
    ) -> dict[str, Any]:
        """
        Combines mapped fields into a unified canonical invoice dictionary
        with vendor sub-objects and structured line items.
        """
        res: dict[str, Any] = {}
        vendor_dict: dict[str, str] = {}

        for mf in mapped_fields:
            ck = mf.canonical_key
            val = mf.value

            if ck == "vendor_name":
                vendor_dict["name"] = str(val)
            elif ck == "vendor_address":
                vendor_dict["address"] = str(val)
            elif ck == "vendor":
                if isinstance(val, dict):
                    vendor_dict.update({str(k): str(v) for k, v in val.items()})
                else:
                    vendor_dict["name"] = str(val)
            elif ck in ("subtotal", "tax_rate", "tax_amount", "total", "shipping"):
                try:
                    res[ck] = float(val)
                except (ValueError, TypeError):
                    res[ck] = val
            else:
                res[ck] = val

        if vendor_dict:
            res["vendor"] = vendor_dict

        # Line items
        if line_items_raw and isinstance(line_items_raw, list):
            res["line_items"] = self._normalize_line_items(line_items_raw)

        return res
