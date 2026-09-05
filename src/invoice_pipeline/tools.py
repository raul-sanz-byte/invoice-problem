"""Tools and function-calling schemas for agentic invoice extraction and validation.
Equips the LLM with executable tools:
1. lookup_product_catalog: Cross-references products against warehouse stock and prices.
2. compute_financial_totals: Deterministically computes financial math with Decimal precision.
3. resolve_vocabulary_alias: Resolves ambiguous document labels to canonical schema keys.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

from invoice_pipeline.extraction.vocabulary import get_vocabulary_manager

logger = logging.getLogger(__name__)

INVOICE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_product_catalog",
            "description": "Look up a product in the warehouse catalog to verify existence, standard pricing, and inventory stock level.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "Name or identifier of the product (e.g., WidgetA, GadgetX, NanoBolt)",
                    }
                },
                "required": ["product_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_financial_totals",
            "description": "Deterministically compute line item amounts, subtotal, tax amount, and final total with exact decimal precision.",
            "parameters": {
                "type": "object",
                "properties": {
                    "line_items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item": {"type": "string"},
                                "quantity": {"type": "number"},
                                "unit_price": {"type": "number"},
                                "stated_amount": {"type": "number"},
                            },
                            "required": ["item", "quantity", "unit_price"],
                        },
                        "description": "List of invoice line items",
                    },
                    "tax_rate": {
                        "type": "number",
                        "description": "Tax rate as decimal (e.g. 0.08 for 8%). Optional.",
                    },
                    "shipping": {
                        "type": "number",
                        "description": "Shipping or freight charge. Optional.",
                    },
                },
                "required": ["line_items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_vocabulary_alias",
            "description": "Look up an unfamiliar or non-standard field name in the system vocabulary to find its canonical equivalent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "raw_alias": {
                        "type": "string",
                        "description": "The raw key or label found in the document (e.g., vndr, pymnt_terms, folio)",
                    },
                },
                "required": ["raw_alias"],
            },
        },
    },
]


def execute_tool(
    name: str,
    args: dict[str, Any] | str,
    database: Any = None,
    vocab_mgr: Any = None,
) -> dict[str, Any]:
    """Execute a tool call and return structured output for LLM consumption."""
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return {"error": f"Invalid JSON arguments: {args}"}

    if name == "lookup_product_catalog":
        product_name = str(args.get("product_name", "")).strip()
        if not product_name:
            return {"error": "product_name is required"}

        products = []
        if database and hasattr(database, "get_products"):
            products = database.get_products()

        norm_query = product_name.lower().replace(" ", "").replace("-", "_")
        matched = None
        for p in products:
            p_name = p["name"].lower().replace(" ", "").replace("-", "_")
            p_id = p.get("product_id", "").lower()
            if norm_query in (p_name, p_id):
                matched = p
                break

        if matched:
            return {
                "found": True,
                "product_id": matched.get("product_id"),
                "name": matched.get("name"),
                "standard_price": matched.get("standard_price"),
                "quantity_in_stock": matched.get("quantity_in_stock"),
                "category": matched.get("category"),
            }
        return {"found": False, "message": f"Inventory item '{product_name}' not found in database"}

    elif name == "compute_financial_totals":
        items = args.get("line_items", [])
        tax_rate = Decimal(str(args.get("tax_rate") or 0))
        shipping = Decimal(str(args.get("shipping") or 0))

        computed_items = []
        subtotal = Decimal("0.00")

        for it in items:
            q = Decimal(str(it.get("quantity", 0)))
            p = Decimal(str(it.get("unit_price", 0)))
            amt = q * p
            subtotal += amt
            computed_items.append({
                "item": it.get("item"),
                "quantity": float(q),
                "unit_price": float(p),
                "amount": float(amt),
            })

        tax_amount = (subtotal * tax_rate).quantize(Decimal("0.01"))
        total = subtotal + tax_amount + shipping

        return {
            "line_items": computed_items,
            "subtotal": float(subtotal.quantize(Decimal("0.01"))),
            "tax_rate": float(tax_rate),
            "tax_amount": float(tax_amount),
            "shipping": float(shipping.quantize(Decimal("0.01"))),
            "total": float(total.quantize(Decimal("0.01"))),
        }

    elif name == "resolve_vocabulary_alias":
        raw_alias = str(args.get("raw_alias", "")).strip()
        mgr = vocab_mgr or get_vocabulary_manager()
        canonical = mgr.resolve(raw_alias)
        return {
            "raw_alias": raw_alias,
            "canonical_field": canonical or raw_alias,
            "is_known": canonical is not None,
        }


    return {"error": f"Unknown tool: {name}"}
