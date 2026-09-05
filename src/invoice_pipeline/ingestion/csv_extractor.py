"""Deterministic extraction of invoice data from CSV with dynamic vocabulary resolution."""

from __future__ import annotations

import csv
import io
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from invoice_pipeline.extraction.vocabulary import get_vocabulary_manager, VocabularyManager


def _to_decimal(val: Any) -> Decimal | None:
    if val is None or val == "":
        return None
    try:
        cleaned = str(val).replace("$", "").replace(",", "").replace("ea", "").replace("%", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _parse_key_value_csv(
    content: str,
    llm_client: Any = None,
    vocab: VocabularyManager | None = None,
) -> dict[str, Any]:
    """Parse 2-column key-value CSV format with vocabulary resolution."""
    vocab = vocab or get_vocabulary_manager()
    result: dict[str, Any] = {}
    reader = csv.reader(io.StringIO(content))

    line_items: list[dict[str, Any]] = []
    current_item: dict[str, Any] = {}

    rows = [r for r in reader if len(r) >= 2 and r[1].strip()]
    raw_keys_present = [r[0].strip() for r in rows]
    sample_key_vals = {r[0].strip(): r[1].strip() for r in rows}

    # Pass 1: standard vocabulary lookup
    for row in rows:
        key_raw = row[0].strip()
        val = row[1].strip()
        canonical = vocab.resolve(key_raw)

        # Line item sub-keys
        li_canonical = vocab.resolve(key_raw, is_line_item=True)

        if canonical == "invoice_id":
            result["invoice_id"] = val
        elif canonical == "vendor":
            result["vendor"] = {"name": val}
        elif canonical == "date":
            result["date"] = val
        elif canonical == "due_date":
            result["due_date"] = val
        elif canonical == "payment_terms":
            result["payment_terms"] = val
        elif canonical == "currency":
            result["currency"] = val
        elif canonical == "notes":
            result["notes"] = val
        elif canonical == "revision":
            result["revision"] = val
        elif canonical == "subtotal":
            dec = _to_decimal(val)
            if dec is not None: result["subtotal"] = dec
        elif canonical == "tax_amount":
            dec = _to_decimal(val)
            if dec is not None: result["tax_amount"] = dec
        elif canonical == "tax_rate":
            dec = _to_decimal(val)
            if dec is not None: result["tax_rate"] = dec
        elif canonical == "shipping":
            dec = _to_decimal(val)
            if dec is not None: result["shipping"] = dec
        elif canonical == "total":
            dec = _to_decimal(val)
            if dec is not None: result["total"] = dec
        elif li_canonical == "item":
            if current_item and "item" in current_item:
                line_items.append(current_item)
                current_item = {}
            current_item["item"] = val
        elif li_canonical == "quantity":
            dec = _to_decimal(val)
            if dec is not None: current_item["quantity"] = dec
        elif li_canonical == "unit_price":
            dec = _to_decimal(val)
            if dec is not None: current_item["unit_price"] = dec
        elif li_canonical == "amount":
            dec = _to_decimal(val)
            if dec is not None: current_item["amount"] = dec

    if current_item and "item" in current_item:
        line_items.append(current_item)

    # Pass 2: Light LLM resolution for missing mandatory fields
    missing_mandatory = [f for f in ["invoice_id", "date", "vendor", "total"] if f not in result]
    unmatched_keys = [k for k in raw_keys_present if not vocab.resolve(k) and not vocab.resolve(k, is_line_item=True)]

    if missing_mandatory and unmatched_keys and llm_client is not None:
        learned = vocab.learn_mappings_with_llm(
            unmatched_keys=unmatched_keys,
            missing_fields=missing_mandatory,
            sample_values=sample_key_vals,
            llm_client=llm_client,
            is_line_item=False,
        )
        for raw_k, canonical in learned.items():
            val = sample_key_vals[raw_k]
            if canonical == "invoice_id": result["invoice_id"] = val
            elif canonical == "date": result["date"] = val
            elif canonical == "vendor": result["vendor"] = {"name": val}
            elif canonical == "total":
                dec = _to_decimal(val)
                if dec is not None: result["total"] = dec

    if line_items:
        result["line_items"] = line_items

    return result


def _parse_tabular_csv(
    content: str,
    llm_client: Any = None,
    vocab: VocabularyManager | None = None,
) -> dict[str, Any]:
    """Parse multi-column tabular CSV format with vocabulary resolution."""
    vocab = vocab or get_vocabulary_manager()
    result: dict[str, Any] = {}
    lines = [line for line in content.splitlines() if line.strip()]
    if not lines:
        return result

    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return result

    header = [c.strip() for c in rows[0]]

    # Map column positions using vocabulary
    col_map: dict[str, int] = {}
    unmatched_cols: list[str] = []

    for idx, col in enumerate(header):
        canonical = vocab.resolve(col) or vocab.resolve(col, is_line_item=True)
        if canonical:
            col_map[canonical] = idx
        elif col:
            unmatched_cols.append(col)

    # If critical columns are missing, consult light LLM and update vocabulary
    needed_cols = [f for f in ["invoice_id", "vendor", "date", "item", "quantity", "unit_price", "amount"] if f not in col_map]
    if needed_cols and unmatched_cols and llm_client is not None and len(rows) > 1:
        first_row_samples = {header[i]: rows[1][i] for i in range(min(len(header), len(rows[1])))}
        learned = vocab.learn_mappings_with_llm(
            unmatched_keys=unmatched_cols,
            missing_fields=needed_cols,
            sample_values=first_row_samples,
            llm_client=llm_client,
            is_line_item=False,
        )
        for raw_col, canonical in learned.items():
            if raw_col in header:
                col_map[canonical] = header.index(raw_col)

    line_items: list[dict[str, Any]] = []

    for row in rows[1:]:
        non_empty = [c.strip() for c in row if c.strip()]
        if not non_empty:
            continue

        # Check for summary rows like "Subtotal: 14750.00"
        row_str = " ".join(non_empty)
        if any(term in row_str.lower() for term in ("subtotal", "tax", "total:")):
            for cell in non_empty:
                cell_lower = cell.lower()
                if "subtotal" in cell_lower:
                    m = re.search(r"subtotal:?\s*\$?([\d,.]+)", cell_lower)
                    if m:
                        result["subtotal"] = _to_decimal(m.group(1))
                    elif len(non_empty) > 1:
                        result["subtotal"] = _to_decimal(non_empty[-1])
                elif "tax" in cell_lower:
                    rate_m = re.search(r"\((\d+(?:\.\d+)?)%\)", cell)
                    if rate_m:
                        result["tax_rate"] = Decimal(rate_m.group(1)) / Decimal("100")
                    amt_m = re.search(r":\s*\$?([\d,.]+)", cell)
                    if amt_m:
                        result["tax_amount"] = _to_decimal(amt_m.group(1))
                    elif len(non_empty) > 1:
                        result["tax_amount"] = _to_decimal(non_empty[-1])
                elif "total:" in cell_lower or cell_lower.startswith("total"):
                    m = re.search(r"total:?\s*\$?([\d,.]+)", cell_lower)
                    if m:
                        result["total"] = _to_decimal(m.group(1))
                    elif len(non_empty) > 1:
                        result["total"] = _to_decimal(non_empty[-1])
            continue

        # Regular line item row
        if "invoice_id" in col_map and col_map["invoice_id"] < len(row) and row[col_map["invoice_id"]].strip():
            result.setdefault("invoice_id", row[col_map["invoice_id"]].strip())
        if "vendor" in col_map and col_map["vendor"] < len(row) and row[col_map["vendor"]].strip():
            result.setdefault("vendor", {"name": row[col_map["vendor"]].strip()})
        if "date" in col_map and col_map["date"] < len(row) and row[col_map["date"]].strip():
            result.setdefault("date", row[col_map["date"]].strip())
        if "due_date" in col_map and col_map["due_date"] < len(row) and row[col_map["due_date"]].strip():
            result.setdefault("due_date", row[col_map["due_date"]].strip())

        item_name = row[col_map["item"]].strip() if "item" in col_map and col_map["item"] < len(row) else ""
        if not item_name:
            continue

        qty = _to_decimal(row[col_map["quantity"]]) if "quantity" in col_map and col_map["quantity"] < len(row) else Decimal("1")
        price = _to_decimal(row[col_map["unit_price"]]) if "unit_price" in col_map and col_map["unit_price"] < len(row) else Decimal("0")
        amount = _to_decimal(row[col_map["amount"]]) if "amount" in col_map and col_map["amount"] < len(row) else None

        li: dict[str, Any] = {
            "item": item_name,
            "quantity": qty if qty is not None else Decimal("1"),
            "unit_price": price if price is not None else Decimal("0"),
        }
        if amount is not None:
            li["amount"] = amount
        line_items.append(li)

    if line_items:
        result["line_items"] = line_items

    return result


def extract_from_csv(
    content: str,
    llm_client: Any = None,
    vocab_mgr: VocabularyManager | None = None,
) -> dict[str, Any] | str:
    """Extracts data from CSV format with dynamic vocabulary resolution."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return ""

    vocab = vocab_mgr or get_vocabulary_manager()
    first_line_lower = lines[0].lower()

    # Check if first line contains column headers (known or in vocab)
    cols = [c.strip() for c in lines[0].split(",")]
    if any(vocab.resolve(c) or vocab.resolve(c, is_line_item=True) for c in cols):
        tabular = _parse_tabular_csv(content, llm_client, vocab)
        if tabular.get("invoice_id") and tabular.get("line_items"):
            return tabular

    # Try key-value format
    kv = _parse_key_value_csv(content, llm_client, vocab)
    if kv.get("invoice_id") and (kv.get("line_items") or kv.get("total")):
        return kv

    # Fallback to tabular
    tabular = _parse_tabular_csv(content, llm_client, vocab)
    if tabular.get("invoice_id") or tabular.get("line_items"):
        return tabular

    return content
