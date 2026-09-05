"""
Qdrant collection initialisation for dual-vector invoice field retrieval.

Collection layout
─────────────────
  name: "invoice_schema_fields"
  dense  vector (384-dim, Cosine) → paraphrase-multilingual-MiniLM-L12-v2
  sparse vector (SPLADE)          → prithivMLmods/Splade_PP_en_v1  (via fastembed)

Each point represents one canonical invoice field (or its known alias).
The payload carries:
  • canonical_key  – target schema field name
  • aliases        – list of known string aliases
  • description    – human-readable definition
  • examples       – sample values / example strings

Usage
─────
Call `init_qdrant_collection()` once at startup or during CI seeding.
The mapper then calls `search_dual_vector()` per unmapped key.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ── Canonical field corpus ────────────────────────────────────────────────────
# Each entry defines one canonical schema field.  The searcher embeds the
# incoming *raw* key string and finds the closest match from this corpus.

CANONICAL_CORPUS: list[dict[str, Any]] = [
    {
        "canonical_key": "invoice_id",
        "aliases": [
            "invoice_number", "invoice_no", "inv_number", "inv_no", "bill_no",
            "numero_facture", "numero_de_facture", "num_facture", "rechnungsnummer",
            "numero_factura", "folio", "ref_no", "doc_no", "reference",
        ],
        "description": "Unique identifier for this invoice document",
        "examples": ["INV-1001", "BILL-2024-0042", "F-00123"],
    },
    {
        "canonical_key": "date",
        "aliases": [
            "invoice_date", "issue_date", "bill_date", "date_issued",
            "date_facture", "date_emission", "rechnungsdatum", "fecha_factura",
        ],
        "description": "Date the invoice was issued (ISO 8601 YYYY-MM-DD)",
        "examples": ["2026-01-22", "2025-11-30"],
    },
    {
        "canonical_key": "due_date",
        "aliases": [
            "payment_due", "due", "pay_by", "settlement_date", "payment_due_date",
            "date_echeance", "echeance", "faelligkeitsdatum", "fecha_vencimiento",
        ],
        "description": "Date by which payment must be received",
        "examples": ["2026-02-22", "2025-12-30"],
    },
    {
        "canonical_key": "vendor_name",
        "aliases": [
            "vendor", "supplier", "seller", "biller", "company", "merchant",
            "fournisseur", "vendeur", "lieferant", "proveedor", "fornecedor",
        ],
        "description": "Name of the company or individual issuing the invoice",
        "examples": ["Acme Corp", "Precision Parts Ltd."],
    },
    {
        "canonical_key": "vendor_address",
        "aliases": [
            "supplier_address", "seller_address", "billing_address",
            "adresse_fournisseur", "lieferantenadresse",
        ],
        "description": "Postal address of the vendor",
        "examples": ["742 Evergreen Terrace, Springfield, IL 62704"],
    },
    {
        "canonical_key": "line_items",
        "aliases": [
            "items", "lines", "articles", "products", "entries", "order_lines",
            "lignes", "postes", "positionen", "articulos",
        ],
        "description": "Array of individual goods or services billed",
        "examples": [{"item": "WidgetA", "quantity": 3, "unit_price": 250.0}],
    },
    {
        "canonical_key": "subtotal",
        "aliases": [
            "net_amount", "pre_tax_amount", "base_amount", "sub_total",
            "sous_total", "montant_ht", "nettobetrag", "subtotal",
        ],
        "description": "Sum of line items before taxes and fees",
        "examples": [1750.0, 4200.00],
    },
    {
        "canonical_key": "tax_rate",
        "aliases": [
            "vat_rate", "tax_pct", "tax_percentage", "gst_rate",
            "taux_taxe", "taux_tva", "steuersatz", "tasa_iva",
        ],
        "description": "Tax rate as a decimal (e.g. 0.08 for 8%)",
        "examples": [0.08, 0.20, 0.07],
    },
    {
        "canonical_key": "tax_amount",
        "aliases": [
            "tax", "vat_amount", "vat", "gst", "tax_total",
            "montant_taxe", "montant_tva", "steuerbetrag", "importe_iva",
        ],
        "description": "Absolute tax amount charged",
        "examples": [140.0, 840.00],
    },
    {
        "canonical_key": "total",
        "aliases": [
            "total_amount", "grand_total", "final_amount", "amount_due",
            "net_payable", "balance_due", "total_ttc", "gesamtbetrag",
            "total_a_pagar", "montant_total",
        ],
        "description": "Total amount payable including all taxes and fees",
        "examples": [1890.0, 5040.00],
    },
    {
        "canonical_key": "currency",
        "aliases": [
            "curr", "currency_code", "monetary_unit",
            "devise", "monnaie", "waehrung", "moneda",
        ],
        "description": "ISO 4217 currency code",
        "examples": ["USD", "EUR", "GBP"],
    },
    {
        "canonical_key": "payment_terms",
        "aliases": [
            "terms", "payment_term", "payment_conditions", "credit_terms",
            "conditions_paiement", "zahlungsbedingungen", "condiciones_pago",
        ],
        "description": "Payment terms string (e.g. 'Net 30', 'Immediate')",
        "examples": ["Net 30", "Net 30 jours", "Due on receipt"],
    },
    {
        "canonical_key": "shipping",
        "aliases": [
            "shipping_cost", "freight", "delivery", "postage",
            "frais_livraison", "versandkosten", "gastos_envio",
        ],
        "description": "Shipping or freight charge",
        "examples": [25.0, 0.0],
    },
    {
        "canonical_key": "notes",
        "aliases": [
            "note", "comment", "remarks", "memo", "instructions",
            "remarques", "anmerkungen", "observaciones",
        ],
        "description": "Free-text notes or special instructions",
        "examples": ["Wire transfer only", "No returns after 30 days"],
    },
    {
        "canonical_key": "line_item_description",
        "aliases": [
            "description", "name", "product", "service", "article",
            "libelle", "designation", "bezeichnung", "descripcion",
        ],
        "description": "Name or description of a line-item product or service",
        "examples": ["WidgetA", "Consulting - 10h @ $150"],
    },
    {
        "canonical_key": "line_item_quantity",
        "aliases": [
            "quantity", "qty", "count", "units", "volume",
            "quantite", "menge", "cantidad", "quantidade",
        ],
        "description": "Quantity of units for a line item",
        "examples": [3, 10, 0.5],
    },
    {
        "canonical_key": "line_item_unit_price",
        "aliases": [
            "unit_price", "price", "rate", "unit_cost", "each",
            "prix_unitaire", "prix", "einzelpreis", "precio_unitario",
        ],
        "description": "Price per single unit for a line item",
        "examples": [250.0, 150.0],
    },
    {
        "canonical_key": "line_item_amount",
        "aliases": [
            "amount", "line_total", "line_amount", "cost", "total_price",
            "montant", "betrag", "importe",
        ],
        "description": "Total amount for a single line item (qty × unit_price)",
        "examples": [750.0, 1500.0],
    },
]


def _build_text_for_field(field: dict[str, Any]) -> str:
    """
    Construct a single string representation of a canonical field
    for embedding. Combines key + aliases + description for richer recall.
    """
    alias_str = " | ".join(str(a) for a in field.get("aliases", []))
    return (
        f"{field['canonical_key']} : {field['description']} : {alias_str}"
    )


def init_qdrant_collection(
    client: Any,
    collection_name: str = "invoice_schema_fields",
    dense_dim: int = 384,
    dense_model: Any = None,
    sparse_model: Any = None,
    recreate: bool = False,
) -> None:
    """
    Create (or recreate) the Qdrant collection and populate it with
    embeddings for every entry in CANONICAL_CORPUS.

    Parameters
    ----------
    client        : qdrant_client.QdrantClient
    collection_name : str
    dense_dim     : int   – output dimension of the dense model (384 for MiniLM)
    dense_model   : SentenceTransformer (or any model with .encode())
    sparse_model  : fastembed SparseTextEmbedding (SPLADE)
    recreate      : bool  – drop and recreate if collection already exists
    """
    from qdrant_client.models import (
        Distance,
        SparseIndexParams,
        SparseVectorParams,
        VectorParams,
        PointStruct,
        SparseVector,
    )

    existing = {c.name for c in client.get_collections().collections}
    if collection_name in existing:
        if recreate:
            logger.info("Dropping existing collection '%s'", collection_name)
            client.delete_collection(collection_name)
        else:
            logger.info(
                "Collection '%s' already exists – skipping init. "
                "Pass recreate=True to force rebuild.",
                collection_name,
            )
            return

    # ── Create collection with dual-vector config ─────────────────────────
    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            # Dense semantic vector: cosine similarity
            "dense": VectorParams(
                size=dense_dim,
                distance=Distance.COSINE,
            ),
        },
        sparse_vectors_config={
            # Sparse lexical vector: SPLADE – inner product (dot) distance
            "sparse": SparseVectorParams(
                index=SparseIndexParams(
                    on_disk=False,   # keep in RAM for fast retrieval
                )
            )
        },
    )
    logger.info(
        "Created Qdrant collection '%s' with dense(%d) + sparse(SPLADE) vectors",
        collection_name,
        dense_dim,
    )

    # ── Embed and upsert each canonical field ────────────────────────────
    points: list[PointStruct] = []

    for idx, field in enumerate(CANONICAL_CORPUS):
        text = _build_text_for_field(field)

        # Dense embedding
        if dense_model is not None:
            if hasattr(dense_model, "embed"):
                dense_vec: list[float] = list(dense_model.embed([text]))[0].tolist()
            else:
                dense_vec: list[float] = dense_model.encode(
                    text, normalize_embeddings=True
                ).tolist()
        else:
            # Zero-vector placeholder when model is not loaded (for testing)
            dense_vec = [0.0] * dense_dim

        # Sparse SPLADE embedding
        if sparse_model is not None:
            sparse_result = list(sparse_model.embed([text]))[0]
            # fastembed returns SparseEmbedding with .indices and .values
            sparse_vec = SparseVector(
                indices=sparse_result.indices.tolist(),
                values=sparse_result.values.tolist(),
            )
        else:
            # Empty sparse placeholder
            sparse_vec = SparseVector(indices=[], values=[])

        payload = {
            "canonical_key": field["canonical_key"],
            "aliases": field.get("aliases", []),
            "description": field.get("description", ""),
            "examples": [str(e) for e in field.get("examples", [])],
        }

        points.append(
            PointStruct(
                id=idx,
                vector={
                    "dense": dense_vec,
                    "sparse": sparse_vec,
                },
                payload=payload,
            )
        )

    client.upsert(collection_name=collection_name, points=points)
    logger.info(
        "Upserted %d canonical field embeddings into '%s'",
        len(points),
        collection_name,
    )


def search_dual_vector(
    client: Any,
    query_text: str,
    dense_model: Any,
    sparse_model: Any,
    collection_name: str = "invoice_schema_fields",
    top_k: int = 3,
    dense_weight: float = 0.6,
    sparse_weight: float = 0.4,
) -> list[dict[str, Any]]:
    """
    Hybrid search: run dense and sparse queries in parallel (Qdrant Fusion),
    then return the top_k merged results with payload.

    Parameters
    ----------
    query_text    : raw unmapped key string (e.g. "taux_taxe", "prix unitaire")
    dense_model   : SentenceTransformer with .encode() or fastembed.TextEmbedding with .embed()
    sparse_model  : fastembed SparseTextEmbedding
    top_k         : number of candidates to return
    dense_weight  : relative weight for dense results in RRF fusion
    sparse_weight : relative weight for sparse results in RRF fusion

    Returns
    -------
    list of dicts: [{"canonical_key": str, "score": float, "payload": dict}, ...]
    """
    from qdrant_client.models import (
        SparseVector,
        Prefetch,
        FusionQuery,
        Fusion,
    )

    # Embed the query
    if hasattr(dense_model, "embed"):
        dense_q: list[float] = list(dense_model.embed([query_text]))[0].tolist()
    else:
        dense_q: list[float] = dense_model.encode(
            query_text, normalize_embeddings=True
        ).tolist()

    sparse_result = list(sparse_model.embed([query_text]))[0]
    sparse_q = SparseVector(
        indices=sparse_result.indices.tolist(),
        values=sparse_result.values.tolist(),
    )

    # Qdrant Hybrid Search with RRF Fusion
    results = client.query_points(
        collection_name=collection_name,
        prefetch=[
            # Dense branch
            Prefetch(
                query=dense_q,
                using="dense",
                limit=top_k * 2,
            ),
            # Sparse branch
            Prefetch(
                query=sparse_q,
                using="sparse",
                limit=top_k * 2,
            ),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=top_k,
        with_payload=True,
    )

    return [
        {
            "canonical_key": hit.payload.get("canonical_key", ""),
            "score": hit.score,
            "payload": hit.payload,
        }
        for hit in results.points
    ]


def get_qdrant_client(
    mode: str | None = None,
    url: str | None = None,
    api_key: str | None = None,
    local_url: str | None = None,
    local_path: str | None = None,
    timeout: float = 3.0,
) -> tuple[Any | None, str]:
    """Resolve and connect to Qdrant according to the requested mode with seamless fallbacks.

    Modes:
      - 'cloud': Connect to Qdrant Cloud cluster (QDRANT_URL, QDRANT_API_KEY)
      - 'local': Connect to local Qdrant server (default: http://localhost:6333)
      - 'memory': Embedded in-memory (:memory:) or local disk path (zero installation required)
      - 'auto': Cloud -> Local Server -> Embedded In-Memory (:memory:)

    Returns:
        tuple of (client, resolved_mode_description)
    """
    import os

    mode = (mode or os.getenv("QDRANT_MODE", "auto")).lower().strip()
    cloud_url = url or os.getenv("QDRANT_URL")
    cloud_key = api_key or os.getenv("QDRANT_API_KEY")
    local_srv_url = local_url or os.getenv("QDRANT_LOCAL_URL", "http://localhost:6333")
    local_disk_path = local_path or os.getenv("QDRANT_LOCAL_PATH", "./qdrant_storage")

    try:
        from qdrant_client import QdrantClient
    except ImportError:
        logger.warning("qdrant_client package is not installed; vector search disabled.")
        return None, "Not Installed"

    # 1. Explicit Cloud Mode
    if mode == "cloud":
        if not cloud_url:
            logger.warning("QDRANT_MODE=cloud but QDRANT_URL is not provided.")
            return None, "Cloud Config Missing"
        try:
            client = QdrantClient(url=cloud_url, api_key=cloud_key, timeout=timeout)
            client.get_collections()
            return client, f"Qdrant Cloud Cluster ({cloud_url[:35]}...)"
        except Exception as e:
            logger.error("Failed connecting to Qdrant Cloud: %s", e)
            return None, f"Cloud Error ({e})"

    # 2. Explicit Local Server Mode
    if mode == "local":
        try:
            client = QdrantClient(url=local_srv_url, timeout=timeout)
            client.get_collections()
            return client, f"Qdrant Local Daemon ({local_srv_url})"
        except Exception as e:
            logger.warning("Local Qdrant server at %s unreachable: %s", local_srv_url, e)
            return None, f"Local Server Unreachable ({e})"

    # 3. Explicit Memory / Embedded Mode
    if mode in ("memory", "embedded", "offline"):
        try:
            client = QdrantClient(":memory:")
            return client, "Qdrant Embedded In-Memory (Zero Dependency)"
        except Exception as e:
            logger.error("Failed creating embedded Qdrant in-memory client: %s", e)
            return None, f"Memory Mode Error ({e})"

    # 4. Auto Mode: Cloud -> Local Server -> Embedded In-Memory Fallback
    # First: Try Cloud if credentials exist
    if cloud_url and cloud_key:
        try:
            client = QdrantClient(url=cloud_url, api_key=cloud_key, timeout=timeout)
            client.get_collections()
            logger.info("Connected to Qdrant Cloud cluster: %s", cloud_url)
            return client, f"Qdrant Cloud Cluster"
        except Exception as e:
            logger.warning("Qdrant Cloud unreachable or offline (%s). Falling back to local/embedded...", e)

    # Second: Try Local Server
    try:
        client = QdrantClient(url=local_srv_url, timeout=1.0)
        client.get_collections()
        logger.info("Connected to local Qdrant daemon at %s", local_srv_url)
        return client, f"Qdrant Local Daemon ({local_srv_url})"
    except Exception:
        pass

    # Third: Embedded In-Memory (guaranteed offline resilience with zero external dependencies)
    try:
        client = QdrantClient(":memory:")
        logger.info("Using Qdrant Embedded In-Memory mode for vector retrieval.")
        return client, "Qdrant Embedded In-Memory (Offline Safe)"
    except Exception as e:
        logger.warning("Could not initialize embedded Qdrant in-memory: %s", e)
        return None, "Unavailable"

