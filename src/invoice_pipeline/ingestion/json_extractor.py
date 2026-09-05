"""Deterministic extraction of invoice data from JSON with dynamic vocabulary resolution."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from invoice_pipeline.extraction.vocabulary import get_vocabulary_manager, VocabularyManager


def _to_decimal(val: Any) -> Decimal | None:
    if val is None or val == "":
        return None
    if isinstance(val, Decimal):
        return val
    try:
        cleaned = str(val).replace("$", "").replace(",", "").replace("€", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def extract_from_json(
    content: str,
    llm_client: Any = None,
    vocab_mgr: VocabularyManager | None = None,
) -> dict[str, Any]:
    """Extracts invoice data from JSON format using deterministic vocabulary and light LLM fallback."""
    data = json.loads(content)
    vocab = vocab_mgr or get_vocabulary_manager()
    result: dict[str, Any] = {}

    # Map of canonical -> raw key used
    used_keys: set[str] = set()

    # Pass 1: Resolve all root-level keys using vocabulary
    for raw_key, val in data.items():
        canonical = vocab.resolve(raw_key)
        if not canonical or val is None:
            continue
        used_keys.add(raw_key)

        if canonical == "invoice_id":
            result["invoice_id"] = str(val)
        elif canonical == "date":
            result["date"] = str(val)
        elif canonical == "due_date":
            result["due_date"] = str(val)
        elif canonical == "vendor":
            if isinstance(val, dict):
                # Support multilingual vendor sub-object keys
                name = (
                    val.get("name") or val.get("vendor_name") or
                    # French
                    val.get("nom") or val.get("raison_sociale") or val.get("societe") or
                    # Spanish
                    val.get("nombre") or val.get("empresa") or
                    # German
                    val.get("name") or val.get("firma") or
                    # Portuguese
                    val.get("nome") or
                    ""
                )
                address = (
                    val.get("address") or
                    # French
                    val.get("adresse") or
                    # Spanish
                    val.get("direccion") or
                    # German
                    val.get("adresse") or val.get("anschrift") or
                    # Portuguese
                    val.get("endereco") or
                    None
                )
                v_dict: dict[str, Any] = {"name": str(name)}
                if address:
                    v_dict["address"] = str(address)
                result["vendor"] = v_dict
            else:
                result["vendor"] = {"name": str(val)}
        elif canonical == "total":
            dec = _to_decimal(val)
            if dec is not None:
                result["total"] = dec
        elif canonical == "subtotal":
            dec = _to_decimal(val)
            if dec is not None:
                result["subtotal"] = dec
        elif canonical == "tax_rate":
            dec = _to_decimal(val)
            if dec is not None:
                result["tax_rate"] = dec
        elif canonical == "tax_amount":
            dec = _to_decimal(val)
            if dec is not None:
                result["tax_amount"] = dec
        elif canonical == "shipping":
            dec = _to_decimal(val)
            if dec is not None:
                result["shipping"] = dec
        elif canonical == "currency":
            result["currency"] = str(val)
        elif canonical == "payment_terms":
            result["payment_terms"] = str(val)
        elif canonical == "notes":
            result["notes"] = str(val)
        elif canonical == "revision":
            result["revision"] = str(val)

    # Pass 2: Check for missing mandatory root fields
    mandatory_fields = ["invoice_id", "date", "vendor", "total", "line_items"]
    missing_mandatory = [f for f in mandatory_fields if f not in result and f != "line_items"]

    unmatched_keys = [k for k in data.keys() if k not in used_keys and not isinstance(data[k], (list, dict))]

    # If mandatory fields are missing, invoke light LLM to discover new aliases and update vocabulary
    if missing_mandatory and unmatched_keys and llm_client is not None:
        sample_vals = {k: data[k] for k in unmatched_keys}
        learned = vocab.learn_mappings_with_llm(
            unmatched_keys=unmatched_keys,
            missing_fields=missing_mandatory,
            sample_values=sample_vals,
            llm_client=llm_client,
            is_line_item=False,
        )
        for raw_k, canonical in learned.items():
            val = data[raw_k]
            if canonical == "invoice_id":
                result["invoice_id"] = str(val)
            elif canonical == "date":
                result["date"] = str(val)
            elif canonical == "vendor":
                result["vendor"] = {"name": str(val)}
            elif canonical == "total":
                dec = _to_decimal(val)
                if dec is not None:
                    result["total"] = dec

    # Pass 3: Resolve Line Items
    items_raw = None
    for k, v in data.items():
        if vocab.resolve(k) == "line_items" and isinstance(v, list):
            items_raw = v
            break

    # If line items missing, check any remaining list fields
    if items_raw is None and llm_client is not None:
        list_keys = [k for k in data.keys() if isinstance(data[k], list) and k not in used_keys]
        if list_keys:
            learned = vocab.learn_mappings_with_llm(
                unmatched_keys=list_keys,
                missing_fields=["line_items"],
                sample_values={k: data[k][:1] for k in list_keys},
                llm_client=llm_client,
                is_line_item=False,
            )
            for raw_k, canonical in learned.items():
                if canonical == "line_items":
                    items_raw = data[raw_k]
                    break

    line_items = []
    if items_raw:
        # Sample the first item to see if item fields need alias resolution
        first_item = next((i for i in items_raw if isinstance(i, dict)), None)
        item_learned_aliases: dict[str, str] = {}

        if first_item and llm_client is not None:
            # Check if any standard item fields are missing in first item
            has_name = any(vocab.resolve(k, is_line_item=True) == "item" for k in first_item.keys())
            has_qty = any(vocab.resolve(k, is_line_item=True) == "quantity" for k in first_item.keys())
            has_price = any(vocab.resolve(k, is_line_item=True) == "unit_price" for k in first_item.keys())

            missing_li_fields = []
            if not has_name: missing_li_fields.append("item")
            if not has_qty: missing_li_fields.append("quantity")
            if not has_price: missing_li_fields.append("unit_price")

            if missing_li_fields:
                unmatched_li_keys = [
                    k for k in first_item.keys()
                    if not vocab.resolve(k, is_line_item=True)
                ]
                if unmatched_li_keys:
                    item_learned_aliases = vocab.learn_mappings_with_llm(
                        unmatched_keys=unmatched_li_keys,
                        missing_fields=missing_li_fields,
                        sample_values=first_item,
                        llm_client=llm_client,
                        is_line_item=True,
                    )

        for raw_item in items_raw:
            if not isinstance(raw_item, dict):
                continue

            li_data: dict[str, Any] = {}
            for k, val in raw_item.items():
                canonical = vocab.resolve(k, is_line_item=True) or item_learned_aliases.get(k)
                if not canonical or val is None:
                    continue
                if canonical == "item":
                    li_data["item"] = str(val)
                elif canonical == "quantity":
                    dec = _to_decimal(val)
                    if dec is not None:
                        li_data["quantity"] = dec
                elif canonical == "unit_price":
                    dec = _to_decimal(val)
                    if dec is not None:
                        li_data["unit_price"] = dec
                elif canonical == "amount":
                    dec = _to_decimal(val)
                    if dec is not None:
                        li_data["amount"] = dec
                elif canonical == "note":
                    li_data["note"] = str(val)

            # Fallback defaults
            if "item" not in li_data:
                # Find any non-empty string
                str_val = next((str(v) for v in raw_item.values() if isinstance(v, str) and v.strip()), "Item")
                li_data["item"] = str_val
            if "quantity" not in li_data:
                li_data["quantity"] = Decimal("1")
            if "unit_price" not in li_data:
                li_data["unit_price"] = Decimal("0")

            line_items.append(li_data)

    if line_items:
        result["line_items"] = line_items

    return result
