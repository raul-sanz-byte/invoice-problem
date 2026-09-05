"""Deterministic extraction of invoice data from XML with dynamic vocabulary resolution."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from typing import Any

from invoice_pipeline.extraction.vocabulary import get_vocabulary_manager, VocabularyManager


def _to_decimal(val: Any) -> Decimal | None:
    if not val:
        return None
    try:
        cleaned = str(val).replace("$", "").replace(",", "").replace("€", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def extract_from_xml(
    content: str,
    llm_client: Any = None,
    vocab_mgr: VocabularyManager | None = None,
) -> dict[str, Any]:
    """Extracts invoice data from XML with vocabulary lookup and light LLM fallback."""
    result: dict[str, Any] = {}
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return result

    vocab = vocab_mgr or get_vocabulary_manager()

    # Flatten all text elements with their tag names for resolution
    all_elements: list[tuple[str, str]] = []
    for elem in root.iter():
        if elem.text and elem.text.strip() and len(elem) == 0:
            all_elements.append((elem.tag, elem.text.strip()))

    used_tags: set[str] = set()

    for tag, text in all_elements:
        canonical = vocab.resolve(tag)
        if not canonical:
            continue
        used_tags.add(tag)

        if canonical == "invoice_id" and "invoice_id" not in result:
            result["invoice_id"] = text
        elif canonical == "vendor" and "vendor" not in result:
            result["vendor"] = {"name": text}
        elif canonical == "date" and "date" not in result:
            result["date"] = text
        elif canonical == "due_date" and "due_date" not in result:
            result["due_date"] = text
        elif canonical == "currency" and "currency" not in result:
            result["currency"] = text
        elif canonical == "payment_terms" and "payment_terms" not in result:
            result["payment_terms"] = text
        elif canonical == "revision" and "revision" not in result:
            result["revision"] = text
        elif canonical == "notes" and "notes" not in result:
            result["notes"] = text
        elif canonical == "subtotal" and "subtotal" not in result:
            dec = _to_decimal(text)
            if dec is not None: result["subtotal"] = dec
        elif canonical == "tax_rate" and "tax_rate" not in result:
            dec = _to_decimal(text)
            if dec is not None: result["tax_rate"] = dec
        elif canonical == "tax_amount" and "tax_amount" not in result:
            dec = _to_decimal(text)
            if dec is not None: result["tax_amount"] = dec
        elif canonical == "shipping" and "shipping" not in result:
            dec = _to_decimal(text)
            if dec is not None: result["shipping"] = dec
        elif canonical == "total" and "total" not in result:
            dec = _to_decimal(text)
            if dec is not None: result["total"] = dec

    # Check for missing mandatory root fields
    missing_mandatory = [
        f for f in ["invoice_id", "date", "vendor", "total"]
        if f not in result
    ]

    unmatched_tags = list({tag for tag, _ in all_elements if tag not in used_tags})
    sample_tag_vals = {tag: text for tag, text in all_elements if tag in unmatched_tags}

    if missing_mandatory and unmatched_tags and llm_client is not None:
        learned = vocab.learn_mappings_with_llm(
            unmatched_keys=unmatched_tags,
            missing_fields=missing_mandatory,
            sample_values=sample_tag_vals,
            llm_client=llm_client,
            is_line_item=False,
        )
        for raw_tag, canonical in learned.items():
            val = sample_tag_vals.get(raw_tag, "")
            if canonical == "invoice_id" and "invoice_id" not in result:
                result["invoice_id"] = val
            elif canonical == "date" and "date" not in result:
                result["date"] = val
            elif canonical == "vendor" and "vendor" not in result:
                result["vendor"] = {"name": val}
            elif canonical == "total" and "total" not in result:
                dec = _to_decimal(val)
                if dec is not None: result["total"] = dec

    # Line Items extraction
    # Look for list containers or repeated elements
    items_elements = []
    # Search for known parent tags
    for parent in root.iter():
        parent_canonical = vocab.resolve(parent.tag)
        if parent_canonical == "line_items" or parent.tag.lower() in ("line_items", "items", "articles", "products"):
            items_elements = list(parent)
            break

    if not items_elements:
        # Check if root has direct item children
        direct_items = [e for e in root if vocab.resolve(e.tag, is_line_item=True) or e.tag.lower() in ("item", "line", "article")]
        if direct_items:
            items_elements = direct_items

    line_items = []
    if items_elements:
        # Sample first item children for unknown tags
        first_item = items_elements[0]
        first_item_tags = [child.tag for child in first_item if child.text]
        sample_li_vals = {child.tag: child.text.strip() for child in first_item if child.text}

        has_name = any(vocab.resolve(t, is_line_item=True) == "item" for t in first_item_tags)
        has_qty = any(vocab.resolve(t, is_line_item=True) == "quantity" for t in first_item_tags)
        has_price = any(vocab.resolve(t, is_line_item=True) == "unit_price" for t in first_item_tags)

        missing_li_fields = []
        if not has_name: missing_li_fields.append("item")
        if not has_qty: missing_li_fields.append("quantity")
        if not has_price: missing_li_fields.append("unit_price")

        learned_li_tags: dict[str, str] = {}
        if missing_li_fields and llm_client is not None:
            unmatched_li_tags = [t for t in first_item_tags if not vocab.resolve(t, is_line_item=True)]
            if unmatched_li_tags:
                learned_li_tags = vocab.learn_mappings_with_llm(
                    unmatched_keys=unmatched_li_tags,
                    missing_fields=missing_li_fields,
                    sample_values=sample_li_vals,
                    llm_client=llm_client,
                    is_line_item=True,
                )

        for item_el in items_elements:
            li_dict: dict[str, Any] = {}
            for child in item_el:
                if not child.text or not child.text.strip():
                    continue
                c_tag = child.tag
                c_text = child.text.strip()
                canonical = vocab.resolve(c_tag, is_line_item=True) or learned_li_tags.get(c_tag)
                if not canonical:
                    continue
                if canonical == "item":
                    li_dict["item"] = c_text
                elif canonical == "quantity":
                    dec = _to_decimal(c_text)
                    if dec is not None: li_dict["quantity"] = dec
                elif canonical == "unit_price":
                    dec = _to_decimal(c_text)
                    if dec is not None: li_dict["unit_price"] = dec
                elif canonical == "amount":
                    dec = _to_decimal(c_text)
                    if dec is not None: li_dict["amount"] = dec
                elif canonical == "note":
                    li_dict["note"] = c_text

            if "item" not in li_dict:
                # First non-numeric text
                li_dict["item"] = next((child.text.strip() for child in item_el if child.text and _to_decimal(child.text) is None), "Item")
            if "quantity" not in li_dict:
                li_dict["quantity"] = Decimal("1")
            if "unit_price" not in li_dict:
                li_dict["unit_price"] = Decimal("0")

            line_items.append(li_dict)

    if line_items:
        result["line_items"] = line_items

    return result
