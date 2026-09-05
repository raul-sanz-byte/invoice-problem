"""Rule compiler that translates natural language and structured vendor rules
into deterministic SQLite queries or classifies them for AI LLM evaluation.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any


ALLOWED_INVOICE_COLUMNS = {
    "total",
    "subtotal",
    "tax_amount",
    "tax_rate",
    "shipping",
    "vendor_name",
    "payment_terms",
    "payment_terms_days",
    "currency",
    "due_date",
    "date",
    "is_suspicious",
    "arithmetic_correct",
    "notes",
}


def compile_rule(
    name: str,
    description: str,
    action: str = "REQUIRE_HUMAN_APPROVAL",
    raw_query: str | None = None,
    llm_client: Any = None,
) -> dict[str, Any]:
    """Compiles a user-defined rule into a deterministic SQLite query or LLM evaluation spec.

    Returns:
        dict with keys:
            - name: sanitized uppercase rule code
            - description: human-readable rule explanation
            - rule_type: 'deterministic_query' | 'llm_eval'
            - sql_query: SQLite WHERE clause or None
            - llm_prompt: evaluation prompt if llm_eval or None
            - condition_type: categorized rule type
            - condition_value: trigger threshold or value
            - action: 'REQUIRE_HUMAN_APPROVAL' | 'REJECT' | 'WARN'
    """
    clean_name = re.sub(r"[^A-Za-z0-9_]", "_", name.strip()).upper()
    if not clean_name:
        clean_name = "CUSTOM_RULE"
    clean_action = action.upper() if action in ("REQUIRE_HUMAN_APPROVAL", "REJECT", "WARN") else "REQUIRE_HUMAN_APPROVAL"

    text = f"{name} {description}".strip()

    # 1. Direct custom SQL query provided
    if raw_query and raw_query.strip():
        sanitized_sql = raw_query.strip()
        # Basic security check: disallow statements other than expressions
        if not re.search(r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|ATTACH|DETACH|PRAGMA)\b", sanitized_sql, re.IGNORECASE):
            return {
                "name": clean_name,
                "description": description or name,
                "rule_type": "deterministic_query",
                "sql_query": sanitized_sql,
                "llm_prompt": None,
                "condition_type": "custom_sql",
                "condition_value": sanitized_sql,
                "action": clean_action,
            }

    # 2. Deterministic Pattern Matching

    # Pattern A: Vendor + Amount (e.g. "Invoices from Acme Corp over $3,000", "Vendor Widgets Inc total > 5000", "vendor is Acme Corp and total > 500")
    m_vend_amt = re.search(
        r"(?:vendor|from|supplier)(?:\s+is)?\s+['\"]?([A-Za-z0-9\s\-&]+?)['\"]?\s+(?:and\s+)?(?:with\s+)?(?:total|amount|invoices?)?\s*(?:>|>=|over|greater than|exceeding|more than)\s*\$?([\d,]+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if m_vend_amt:
        raw_vendor = m_vend_amt.group(1).strip()
        vendor = re.sub(r"^(?:is\s+)", "", raw_vendor, flags=re.IGNORECASE).strip()
        vendor = re.sub(r"(?:\s+and)$", "", vendor, flags=re.IGNORECASE).strip()
        amt = Decimal(m_vend_amt.group(2).replace(",", ""))
        return {
            "name": clean_name,
            "description": description or f"Invoices from {vendor} exceeding ${amt:,.2f}",
            "rule_type": "deterministic_query",
            "sql_query": f"LOWER(vendor_name) LIKE '%{vendor.lower()}%' AND total > {amt}",
            "llm_prompt": None,
            "condition_type": "vendor_amount_gt",
            "condition_value": f"{vendor}:{amt}",
            "action": clean_action,
        }

    # Pattern B: Specific Vendor Rule (e.g. "Flag all invoices from Fraudster LLC", "Vendor is FastShip")
    m_vend_only = re.search(
        r"(?:flag|block|hold|review)?\s*(?:all\s+)?invoices?\s+(?:from|by|vendor)\s+['\"]?([A-Za-z0-9\s\-&]{2,})['\"]?\b",
        text,
        re.IGNORECASE,
    )
    if m_vend_only and not any(k in text.lower() for k in ["over", "under", "greater", "less", "between", "$"]):
        vendor = m_vend_only.group(1).strip()
        return {
            "name": clean_name,
            "description": description or f"Invoices from vendor {vendor}",
            "rule_type": "deterministic_query",
            "sql_query": f"LOWER(vendor_name) LIKE '%{vendor.lower()}%'",
            "llm_prompt": None,
            "condition_type": "vendor_match",
            "condition_value": vendor,
            "action": clean_action,
        }

    # Pattern C: Payment Terms (e.g. "No Net 90 payment terms", "Require approval for terms Net 60", "terms like Net 90")
    m_terms = re.search(
        r"(?:terms?|payment terms?)?\s*['\"]?(net\s*\d+|immediate|cash on delivery|cod|due on receipt)['\"]?\s*(?:terms?|payment terms?)?",
        text,
        re.IGNORECASE,
    )
    if m_terms and m_terms.group(1):
        term_val = m_terms.group(1).strip()
        return {
            "name": clean_name,
            "description": description or f"Payment terms matching {term_val.upper()}",
            "rule_type": "deterministic_query",
            "sql_query": f"LOWER(payment_terms) LIKE '%{term_val.lower()}%'",
            "llm_prompt": None,
            "condition_type": "payment_terms",
            "condition_value": term_val,
            "action": clean_action,
        }

    # Pattern D: Amount Range (e.g. "Total between $5,000 and $8,000")
    m_range = re.search(
        r"(?:total|amount)\s+(?:is\s+)?between\s*\$?([\d,]+(?:\.\d+)?)\s*(?:and|to|-)\s*\$?([\d,]+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if m_range:
        low = Decimal(m_range.group(1).replace(",", ""))
        high = Decimal(m_range.group(2).replace(",", ""))
        return {
            "name": clean_name,
            "description": description or f"Total between ${low:,.2f} and ${high:,.2f}",
            "rule_type": "deterministic_query",
            "sql_query": f"total >= {low} AND total <= {high}",
            "llm_prompt": None,
            "condition_type": "amount_range",
            "condition_value": f"{low}:{high}",
            "action": clean_action,
        }

    # Pattern E: Amount Threshold (e.g. "Total over $5,000", "Amount > $10,000", "Total greater than 2500")
    m_amt_gt = re.search(
        r"(?:total|amount|invoice value)\s*(?:>|>=|over|greater than|exceeds?|more than)\s*\$?([\d,]+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if m_amt_gt:
        amt = Decimal(m_amt_gt.group(1).replace(",", ""))
        return {
            "name": clean_name,
            "description": description or f"Invoice total exceeds ${amt:,.2f}",
            "rule_type": "deterministic_query",
            "sql_query": f"total > {amt}",
            "llm_prompt": None,
            "condition_type": "amount_gt",
            "condition_value": str(amt),
            "action": clean_action,
        }

    # Pattern F: Amount Less Than (e.g. "Total under $100", "Amount < 50")
    m_amt_lt = re.search(
        r"(?:total|amount)\s*(?:<|<=|under|less than|below)\s*\$?([\d,]+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if m_amt_lt:
        amt = Decimal(m_amt_lt.group(1).replace(",", ""))
        return {
            "name": clean_name,
            "description": description or f"Invoice total below ${amt:,.2f}",
            "rule_type": "deterministic_query",
            "sql_query": f"total < {amt}",
            "llm_prompt": None,
            "condition_type": "amount_lt",
            "condition_value": str(amt),
            "action": clean_action,
        }

    # Pattern G: Shipping Threshold (e.g. "Shipping over $150", "Freight greater than $300")
    m_shipping = re.search(
        r"(?:shipping|freight|delivery)\s*(?:fee|cost)?\s*(?:>|>=|over|greater than|exceeds?)\s*\$?([\d,]+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if m_shipping:
        amt = Decimal(m_shipping.group(1).replace(",", ""))
        return {
            "name": clean_name,
            "description": description or f"Shipping fee exceeds ${amt:,.2f}",
            "rule_type": "deterministic_query",
            "sql_query": f"shipping > {amt}",
            "llm_prompt": None,
            "condition_type": "shipping_gt",
            "condition_value": str(amt),
            "action": clean_action,
        }

    # Pattern H: Currency Constraint (e.g. "Currency not USD", "Non-USD currency", "Foreign currency")
    if re.search(r"\b(?:non-usd|foreign currency|not usd|currency != 'usd')\b", text, re.IGNORECASE):
        return {
            "name": clean_name,
            "description": description or "Non-USD currency transactions",
            "rule_type": "deterministic_query",
            "sql_query": "UPPER(currency) != 'USD'",
            "llm_prompt": None,
            "condition_type": "currency_not_usd",
            "condition_value": "USD",
            "action": clean_action,
        }

    # Pattern I: Line Item Unit Price Ceiling (e.g. "Item WidgetA unit price over $300", "unit price > 500 for GadgetX")
    m_item_price = re.search(
        r"(?:item|product)\s+['\"]?([A-Za-z0-9_\-]+)['\"]?\s+(?:unit\s+price|price|rate)\s*(?:>|over|greater than)\s*\$?([\d,]+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if m_item_price:
        item_name = m_item_price.group(1).strip()
        price = Decimal(m_item_price.group(2).replace(",", ""))
        subquery = (
            f"EXISTS (SELECT 1 FROM line_items li WHERE li.invoice_db_id = invoices.id "
            f"AND LOWER(li.item) LIKE '%{item_name.lower()}%' AND li.unit_price > {price})"
        )
        return {
            "name": clean_name,
            "description": description or f"Unit price of {item_name} exceeds ${price:,.2f}",
            "rule_type": "deterministic_query",
            "sql_query": subquery,
            "llm_prompt": None,
            "condition_type": "item_price_gt",
            "condition_value": f"{item_name}:{price}",
            "action": clean_action,
        }

    # Pattern J: Line Item Quantity Threshold (e.g. "Quantity over 100 for any item", "Order qty > 50")
    m_item_qty = re.search(
        r"(?:quantity|qty)\s*(?:>|over|greater than|exceeding)\s*(\d+)",
        text,
        re.IGNORECASE,
    )
    if m_item_qty:
        qty = int(m_item_qty.group(1))
        subquery = (
            f"EXISTS (SELECT 1 FROM line_items li WHERE li.invoice_db_id = invoices.id "
            f"AND li.quantity > {qty})"
        )
        return {
            "name": clean_name,
            "description": description or f"Line item quantity exceeds {qty} units",
            "rule_type": "deterministic_query",
            "sql_query": subquery,
            "llm_prompt": None,
            "condition_type": "item_qty_gt",
            "condition_value": str(qty),
            "action": clean_action,
        }

    # 3. LLM Translation Attempt (if LLM is provided and rule has not matched known regex)
    if llm_client:
        try:
            sql_attempt = _try_llm_sql_translation(name, description, llm_client)
            if sql_attempt:
                return {
                    "name": clean_name,
                    "description": description or name,
                    "rule_type": "deterministic_query",
                    "sql_query": sql_attempt,
                    "llm_prompt": None,
                    "condition_type": "llm_translated_sql",
                    "condition_value": sql_attempt,
                    "action": clean_action,
                }
        except Exception:
            pass

    # 4. Complex Semantic / Subjective Rule -> Fallback to AI LLM Evaluator
    llm_prompt = (
        f"Evaluate the invoice against the business rule:\n"
        f"Rule Name: {name}\n"
        f"Rule Description: {description}\n"
        f"Check whether this invoice violates or triggers this condition. "
        f"Answer YES with a concise reason if triggered, or NO if compliant."
    )

    return {
        "name": clean_name,
        "description": description or name,
        "rule_type": "llm_eval",
        "sql_query": None,
        "llm_prompt": llm_prompt,
        "condition_type": "llm_eval",
        "condition_value": description or name,
        "action": clean_action,
    }


def _try_llm_sql_translation(name: str, description: str, llm_client: Any) -> str | None:
    """Attempts to translate a rule into a safe SQLite WHERE clause using the LLM."""
    prompt = f"""You are a SQL compiler. Translate this business policy rule into a single SQLite WHERE condition.
Available table: invoices (id, invoice_id, vendor_name, subtotal, tax_amount, total, currency, payment_terms, shipping, notes, date, due_date)
Available joined child: line_items (id, invoice_db_id, item, quantity, unit_price, amount, note)

Rule Name: {name}
Description: {description}

Requirements:
- Output ONLY the WHERE clause condition (e.g. "total > 5000 AND LOWER(vendor_name) LIKE '%acme%'").
- Do NOT include the word WHERE.
- Return "CANNOT_TRANSLATE" if the rule is subjective, vague, requires human visual inspection, or semantic text analysis.
- Do NOT output any markdown formatting or explanations.
"""
    try:
        response = llm_client.client.chat.completions.create(
            model=getattr(llm_client, "light_model", "gemini-2.5-flash"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        sql = (response.choices[0].message.content or "").strip()
        sql = re.sub(r"^```[a-z]*\s*", "", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\s*```$", "", sql)
        sql = sql.strip()
        if "CANNOT_TRANSLATE" in sql.upper() or not sql:
            return None
        # Basic validation: ensure no harmful keywords
        if re.search(r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|ATTACH|PRAGMA)\b", sql, re.IGNORECASE):
            return None
        return sql
    except Exception:
        return None
