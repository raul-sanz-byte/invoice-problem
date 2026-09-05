"""Inventory and product catalog validator.

Cross-references invoice line items against the product database to detect:
1. Normal order within stock -> Valid
2. Quantity exceeds stock -> Stock mismatch
3. Fraudulent / zero-stock item -> Out of stock / suspicious
4. Item not in database at all -> Unknown item
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from invoice_pipeline.models import Invoice, ValidationResult, ValidationSeverity

logger = logging.getLogger(__name__)


def validate_inventory(
    invoice: Invoice,
    database: Any = None,
    product_catalog: list[dict[str, Any]] | None = None,
) -> ValidationResult:
    """Validate invoice line items against the products database.

    Args:
        invoice: The Invoice model to validate.
        database: Optional InvoiceDatabase instance.
        product_catalog: Optional list of product dicts (product_id, name, standard_price, quantity_in_stock).

    Returns:
        ValidationResult containing inventory-specific warnings, errors, and flags.
    """
    result = ValidationResult()

    # Retrieve product catalog
    products: list[dict[str, Any]] = []
    if product_catalog is not None:
        products = product_catalog
    elif database is not None and hasattr(database, "get_products"):
        try:
            products = database.get_products()
        except Exception as e:
            logger.warning("Could not fetch products from database: %s", e)

    if not products:
        # No product catalog available to validate against
        return result

    # Index products by normalized name and product_id
    catalog_by_name: dict[str, dict[str, Any]] = {}
    for p in products:
        name_key = p["name"].lower().strip().replace(" ", "").replace("-", "_")
        catalog_by_name[name_key] = p
        if "product_id" in p:
            catalog_by_name[p["product_id"].lower().strip()] = p

    for idx, item in enumerate(invoice.line_items):
        item_key = item.item.lower().strip().replace(" ", "").replace("-", "_")
        prod = catalog_by_name.get(item_key)

        # Scenario 4: Item not in database at all
        if not prod:
            result.add_issue(
                ValidationSeverity.WARNING,
                f"Unknown item: '{item.item}' not in product database",
                field=f"line_items[{idx}].item",
                expected="Known catalog item",
                actual=item.item,
            )
            continue

        stock = prod.get("quantity_in_stock", 0)

        # Scenario 3: Fraudulent / zero-stock item
        if stock == 0:
            result.add_issue(
                ValidationSeverity.WARNING,
                f"Out of stock item: '{item.item}' has 0 units in stock",
                field=f"line_items[{idx}].item",
                expected="In-stock product (> 0)",
                actual="0 in stock",
            )
            result.flag_suspicious(
                f"Item '{item.item}' has zero stock (0 units available in product catalog)"
            )
            continue

        # Scenario 2: Quantity exceeds stock
        if item.quantity > Decimal(str(stock)):
            result.add_issue(
                ValidationSeverity.WARNING,
                f"Stock mismatch: Item '{item.item}' requested {item.quantity} units, but only {stock} in stock",
                field=f"line_items[{idx}].quantity",
                expected=f"<= {stock}",
                actual=str(item.quantity),
            )
            continue

        # Scenario 1: Normal order within stock -> passes silently!

    return result
