"""VP-Level Reviewer with rule-based decision-making and reflection/critique loop.

Implements executive governance:
- Invoices over $10K require VP / Human scrutiny.
- Fraud and anomaly detection (structuring, unbundling, duplicates, sequential gaps, date anomalies).
- Reflection / critique loop to challenge initial assessment before making final determination.
- Holds invoices for Human-in-the-Loop (HITL) approval when risks or thresholds are triggered.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from invoice_pipeline.models import (
    HumanApprovalStatus,
    Invoice,
    InvoiceReview,
    PaymentStatus,
    ReviewDecision,
    ValidationResult,
)

logger = logging.getLogger(__name__)


# Standard major US holidays (month, day)
MAJOR_HOLIDAYS = {
    (1, 1): "New Year's Day",
    (7, 4): "Independence Day",
    (12, 25): "Christmas Day",
}


class VPReviewer:
    """VP-level executive invoice governance and reflection engine."""

    def __init__(self, database: Any = None, llm_client: Any = None, enable_llm_review: bool = False) -> None:
        self.database = database
        self.llm_client = llm_client
        self.enable_llm_review = enable_llm_review

    def review_invoice(
        self,
        invoice: Invoice,
        validation: ValidationResult,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        current_db_id: int | None = None,
    ) -> InvoiceReview:
        """Run executive VP review on an invoice with reflection loop and dynamic rules.

        Returns:
            InvoiceReview object with initial reasoning, critique, triggered rules,
            and final decision.
        """
        warnings = warnings or []
        errors = errors or []
        current_db_id = current_db_id or getattr(invoice, "db_id", None)

        # Step 1: Evaluate dynamic rules and fraud patterns
        triggered_rules, risk_factors = self._evaluate_rules_and_risks(
            invoice=invoice,
            validation=validation,
            warnings=warnings,
            errors=errors,
            current_db_id=current_db_id,
        )

        # Step 2: Initial reasoning
        initial_reasoning = self._generate_initial_reasoning(
            invoice=invoice,
            validation=validation,
            triggered_rules=triggered_rules,
            risk_factors=risk_factors,
        )

        # Step 3: Reflection / Critique Loop
        critique = self._run_reflection_critique(
            invoice=invoice,
            initial_reasoning=initial_reasoning,
            triggered_rules=triggered_rules,
            risk_factors=risk_factors,
        )

        # Step 4: Final Decision Synthesis
        requires_human = len(triggered_rules) > 0 or len(risk_factors) > 0 or not validation.passed

        # Check if this invoice is a revision of an earlier version with additional items
        amount_to_pay = invoice.total
        is_revision = False
        previous_total = None

        if self.database and hasattr(self.database, "get_previous_invoice_version"):
            try:
                prev_ver = self.database.get_previous_invoice_version(
                    invoice.invoice_id, exclude_id=current_db_id
                )
                if prev_ver:
                    prev_total_val = Decimal(str(prev_ver.get("total", 0)))
                    previous_total = prev_total_val
                    prev_items = prev_ver.get("line_items", [])

                    from invoice_pipeline.storage.database import are_line_items_identical
                    if not are_line_items_identical(invoice.line_items, prev_items):
                        is_revision = True
                        if invoice.total > prev_total_val:
                            amount_to_pay = invoice.total - prev_total_val
                            logger.info(
                                "Revised invoice %s: paying delta of %s %s for additional items (previous: %s, new: %s)",
                                invoice.invoice_id,
                                invoice.currency,
                                amount_to_pay,
                                prev_total_val,
                                invoice.total,
                            )
            except Exception as e:
                logger.debug("Previous invoice revision check failed: %s", e)

        if requires_human:
            # Under user specifications, all flagged or high-risk invoices wait for human approval
            decision = ReviewDecision.REQUIRES_HUMAN_APPROVAL
            approval_status = HumanApprovalStatus.PENDING
            payment_status = PaymentStatus.PENDING_APPROVAL
            final_reasoning = (
                f"Held for VP / Human review due to {len(triggered_rules)} triggered rule(s) "
                f"and {len(risk_factors)} risk factor(s). Payment halted pending human decision."
            )
        else:
            decision = ReviewDecision.AUTO_APPROVED
            approval_status = HumanApprovalStatus.NOT_REQUIRED
            payment_status = PaymentStatus.PAID
            if is_revision and amount_to_pay < invoice.total:
                final_reasoning = (
                    f"Revised invoice passed all checks. Auto-approved incremental payment of "
                    f"${amount_to_pay:,.2f} for additional items (previous total: ${previous_total:,.2f}, new total: ${invoice.total:,.2f})."
                )
            else:
                final_reasoning = (
                    "Invoice passed all standard VP policies (amount under $10K, zero fraud flags, "
                    "verified catalog stock, and perfect arithmetic). Auto-approved for payment."
                )

        review = InvoiceReview(
            invoice_id=invoice.invoice_id,
            decision=decision,
            rules_triggered=triggered_rules,
            initial_reasoning=initial_reasoning,
            critique=critique,
            final_reasoning=final_reasoning,
            requires_human=requires_human,
            human_approval_status=approval_status,
            payment_status=payment_status,
            amount_to_pay=amount_to_pay,
            is_revision=is_revision,
            previous_total=previous_total,
        )

        # Step 5: Save audit trail to database if available
        if self.database and hasattr(self.database, "save_invoice_review"):
            try:
                self.database.save_invoice_review(review.model_dump(mode="json"))
            except Exception as e:
                logger.warning("Failed to persist invoice review to database: %s", e)

        return review

    def _evaluate_rules_and_risks(
        self,
        invoice: Invoice,
        validation: ValidationResult,
        warnings: list[str],
        errors: list[str],
        current_db_id: int | None = None,
    ) -> tuple[list[str], list[str]]:
        """Evaluate database rules and specific fraud patterns against the invoice."""
        triggered_rules: list[str] = []
        risk_factors: list[str] = []

        total = float(invoice.total)

        # Retrieve active rules configured in SQLite
        active_rules = []
        if self.database and hasattr(self.database, "get_business_rules"):
            try:
                active_rules = self.database.get_business_rules(active_only=True)
            except Exception as e:
                logger.debug("Could not fetch active business rules: %s", e)
        active_names = {r.get("name", ""): r for r in active_rules}

        # 0. Check Blacklisted Vendor Registry
        if ("BLACKLISTED_VENDOR" in active_names or not active_names) and self.database and hasattr(self.database, "get_vendor_status"):
            try:
                v_status = self.database.get_vendor_status(invoice.vendor.name)
                if v_status.get("status") == "blacklisted":
                    reason_desc = f" ({v_status.get('reason')})" if v_status.get('reason') else ""
                    rule_msg = (
                        f"BLACKLISTED_VENDOR: Vendor '{invoice.vendor.name}' is on executive "
                        f"blacklist for prior fraud or compliance violations{reason_desc}"
                    )
                    triggered_rules.append(rule_msg)
                    risk_factors.append(f"Vendor '{invoice.vendor.name}' is blacklisted")
            except Exception as e:
                logger.debug("Vendor blacklist check failed: %s", e)

        # 1. Check Amount > $10,000 threshold
        if ("AMOUNT_OVER_10K" in active_names or not active_names) and total > 10000.00:
            rule_msg = f"AMOUNT_OVER_10K: Invoice total ${total:,.2f} exceeds $10,000 VP scrutiny threshold"
            triggered_rules.append(rule_msg)
            risk_factors.append("Executive spend threshold exceeded ($10,000)")

        # 2. Suspicious Structuring (Smurfing): e.g., $9,000 - $9,999.99
        if ("SUSPICIOUS_STRUCTURING" in active_names or not active_names) and 9000.00 <= total < 10000.00:
            rule_msg = (
                f"SUSPICIOUS_STRUCTURING: Total ${total:,.2f} is structured just below "
                f"the $10,000 VP approval threshold"
            )
            triggered_rules.append(rule_msg)
            risk_factors.append("Intentional structuring just under executive threshold")

        # 3. Exact Duplicate Check (against SQLite database)
        if ("EXACT_DUPLICATE" in active_names or not active_names) and self.database and hasattr(self.database, "find_duplicate_invoice"):
            try:
                dup = self.database.find_duplicate_invoice(
                    invoice_id=invoice.invoice_id,
                    vendor_name=invoice.vendor.name,
                    total=total,
                    invoice_date=invoice.date.isoformat(),
                    exclude_id=current_db_id,
                    incoming_items=invoice.line_items,
                )
                if dup:
                    rule_msg = (
                        f"EXACT_DUPLICATE: Invoice {invoice.invoice_id} has 100% identical items "
                        f"to previously submitted invoice (ID: {dup.get('invoice_id')}, Date: {dup.get('date')}, Total: ${dup.get('total')}) "
                        f"— potential double-payment fraud"
                    )
                    triggered_rules.append(rule_msg)
                    risk_factors.append("Duplicate invoice submission (100% same items)")
            except Exception as e:
                logger.debug("Duplicate check failed: %s", e)

        # 4. Unbundled Billing (Split Invoices from same vendor within 7 days)
        if ("UNBUNDLED_BILLING" in active_names or not active_names) and self.database and hasattr(self.database, "get_vendor_recent_invoices"):
            try:
                recent = self.database.get_vendor_recent_invoices(
                    vendor_name=invoice.vendor.name,
                    exclude_invoice_id=invoice.invoice_id,
                )
                recent_7d_total = sum(
                    float(r["total"])
                    for r in recent
                    if self._is_within_days(r.get("date"), invoice.date, days=7)
                )
                combined_total = recent_7d_total + total
                if recent_7d_total > 0 and combined_total > 10000.00 and total <= 10000.00:
                    rule_msg = (
                        f"UNBUNDLED_BILLING: Multiple invoices from '{invoice.vendor.name}' "
                        f"within 7 days total ${combined_total:,.2f} (split to evade $10K limit)"
                    )
                    triggered_rules.append(rule_msg)
                    risk_factors.append("Unbundled split billing pattern detected")
            except Exception as e:
                logger.debug("Unbundled billing check failed: %s", e)

        # 5. Sequential Invoice Numbers across long intervals (Shell Company indicator)
        if ("SEQUENTIAL_INVOICE_GAP" in active_names or not active_names) and self.database and hasattr(self.database, "get_vendor_recent_invoices"):
            try:
                recent = self.database.get_vendor_recent_invoices(
                    vendor_name=invoice.vendor.name,
                    exclude_invoice_id=invoice.invoice_id,
                )
                current_num = self._extract_invoice_number(invoice.invoice_id)
                if current_num is not None:
                    for prev in recent:
                        prev_num = self._extract_invoice_number(prev.get("invoice_id", ""))
                        if prev_num is not None and abs(current_num - prev_num) == 1:
                            prev_date = self._parse_iso_date(prev.get("date"))
                            if prev_date and abs((invoice.date - prev_date).days) >= 20:
                                days_gap = abs((invoice.date - prev_date).days)
                                rule_msg = (
                                    f"SEQUENTIAL_INVOICE_GAP: Consecutive invoice numbers "
                                    f"({prev.get('invoice_id')} vs {invoice.invoice_id}) separated by "
                                    f"{days_gap} days from vendor '{invoice.vendor.name}' "
                                    f"— indicates sole-customer shell company risk"
                                )
                                triggered_rules.append(rule_msg)
                                risk_factors.append("Sequential numbering with large date gap (sole customer)")
                                break
            except Exception as e:
                logger.debug("Sequential invoice check failed: %s", e)

        # 6. Date Anomalies: Weekend or Major Holiday
        if ("DATE_ANOMALY" in active_names or not active_names):
            if invoice.date.weekday() in (5, 6):
                day_name = "Saturday" if invoice.date.weekday() == 5 else "Sunday"
                rule_msg = f"DATE_ANOMALY: Invoice dated on a weekend: {invoice.date} ({day_name})"
                triggered_rules.append(rule_msg)
                risk_factors.append("Weekend invoice date")

            holiday_name = MAJOR_HOLIDAYS.get((invoice.date.month, invoice.date.day))
            if holiday_name:
                rule_msg = f"DATE_ANOMALY: Invoice dated on a major federal holiday: {holiday_name} ({invoice.date})"
                triggered_rules.append(rule_msg)
                risk_factors.append(f"Holiday invoice date ({holiday_name})")

        # 7. Suspicious / Fraud flags from validation layer
        if ("SUSPICIOUS_OR_FRAUD" in active_names or not active_names) and validation.is_suspicious:
            rule_msg = f"SUSPICIOUS_OR_FRAUD: {'; '.join(validation.suspicion_reasons)}"
            triggered_rules.append(rule_msg)
            risk_factors.append("Document anomaly / fraud suspicion flags detected")

        # 7.5 Context Poisoning & Prompt Injection security flags
        has_context_poisoning = (
            any("context poisoning" in s.lower() or "prompt injection" in s.lower() for s in validation.suspicion_reasons)
            or any("SECURITY ALERT" in w or "context poisoning" in w.lower() for w in warnings)
        )
        if has_context_poisoning:
            triggered_rules.append("CONTEXT_POISONING_ATTACK: Document contains hostile prompt injection / context poisoning payloads")
            risk_factors.append("Hostile context poisoning / prompt injection attempt detected")

        # 8. Stock mismatches and unknown catalog items
        has_stock_mismatch = any("Stock mismatch" in w or "units in stock" in w for w in warnings)
        if ("STOCK_MISMATCH" in active_names or not active_names) and has_stock_mismatch:
            triggered_rules.append("STOCK_MISMATCH: One or more requested items exceed warehouse inventory")
            risk_factors.append("Insufficient inventory stock")

        has_unknown_items = any("Unknown item" in w for w in warnings)
        if ("UNKNOWN_ITEMS" in active_names or not active_names) and has_unknown_items:
            triggered_rules.append("UNKNOWN_ITEMS: Unregistered items not found in catalog")
            risk_factors.append("Uncataloged line items")

        # 9. Arithmetic calculation errors
        if ("ARITHMETIC_ERROR" in active_names or not active_names) and (not validation.arithmetic_correct or any("mismatch" in e.lower() for e in errors)):
            triggered_rules.append("ARITHMETIC_ERROR: Unresolved calculation discrepancies detected")
            risk_factors.append("Arithmetic calculation discrepancy")

        # 10. Dynamic User Rules (Deterministic SQLite queries and Complex LLM rules)
        for r in active_rules:
            if r.get("is_system"):
                continue  # System rules handled above

            r_name = r.get("name", "CUSTOM_RULE")
            r_type = r.get("rule_type", "deterministic_query")
            sql_query = r.get("sql_query")
            r_desc = r.get("description") or f"Custom rule {r_name} triggered"
            c_type = r.get("condition_type")
            c_val = r.get("condition_value")

            # Check in-memory condition types (e.g. from unit tests or legacy rules)
            triggered_by_cond = False
            if c_type == "vendor_pattern" and c_val:
                if str(c_val).lower() in invoice.vendor.name.lower():
                    triggered_by_cond = True
            elif c_type == "amount_threshold" and c_val:
                try:
                    if float(invoice.total) >= float(c_val):
                        triggered_by_cond = True
                except (ValueError, TypeError):
                    pass
            elif c_type == "item_keyword" and c_val:
                if any(str(c_val).lower() in li.item.lower() for li in invoice.line_items):
                    triggered_by_cond = True

            if triggered_by_cond:
                rule_msg = f"{r_name}: {r_desc}"
                triggered_rules.append(rule_msg)
                risk_factors.append(r_desc)
                logger.info("Custom rule '%s' triggered by condition for %s", r_name, invoice.invoice_id)
                continue

            # Execute deterministic SQLite query on the saved invoice
            if r_type == "deterministic_query" and sql_query:
                try:
                    if self.database and hasattr(self.database, "conn") and self.database.conn:
                        cur = self.database.conn.cursor()
                        cur.execute(
                            f"SELECT 1 FROM invoices WHERE (id = ? OR invoice_id = ?) AND ({sql_query})",
                            (current_db_id, invoice.invoice_id),
                        )
                        if cur.fetchone():
                            rule_msg = f"{r_name}: {r_desc}"
                            triggered_rules.append(rule_msg)
                            risk_factors.append(r_desc)
                            logger.info("Custom deterministic rule '%s' triggered for %s", r_name, invoice.invoice_id)
                except Exception as e:
                    logger.warning("Error evaluating deterministic SQL rule '%s': %s", r_name, e)

            # Complex rule: evaluate with LLM
            elif r_type == "llm_eval":
                try:
                    triggered, reason = self._evaluate_rule_with_llm(invoice, r)
                    if triggered:
                        rule_msg = f"{r_name}: {reason or r_desc}"
                        triggered_rules.append(rule_msg)
                        risk_factors.append(r_desc)
                        logger.info("Custom LLM rule '%s' triggered for %s", r_name, invoice.invoice_id)
                except Exception as e:
                    logger.warning("Error evaluating LLM rule '%s': %s", r_name, e)

        return triggered_rules, risk_factors

    def _evaluate_rule_with_llm(self, invoice: Invoice, rule: dict[str, Any]) -> tuple[bool, str]:
        """Evaluates an invoice against a complex subjective rule using LLM."""
        if not self.enable_llm_review or not self.llm_client or not hasattr(self.llm_client, "client"):
            return False, ""
        prompt = (
            f"Evaluate the following invoice against this business rule:\n"
            f"Rule Name: {rule.get('name')}\n"
            f"Rule Description: {rule.get('description')}\n"
            f"{rule.get('llm_prompt') or ''}\n\n"
            f"Invoice Details:\n"
            f"- Vendor: {invoice.vendor.name}\n"
            f"- Total: {invoice.currency} {invoice.total}\n"
            f"- Date: {invoice.date}\n"
            f"- Payment Terms: {invoice.payment_terms}\n"
            f"- Notes: {invoice.notes or 'None'}\n"
            f"- Line items: {', '.join(f'{li.quantity}x {li.item} @ {li.unit_price}' for li in invoice.line_items)}\n\n"
            f"Does this invoice violate or trigger this rule? "
            f"Reply with format:\n"
            f"TRIGGERED: YES or NO\n"
            f"REASON: concise explanation if YES"
        )
        try:
            resp = self.llm_client.client.chat.completions.create(
                model=getattr(self.llm_client, "light_model", "gemini-2.5-flash"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            content = (resp.choices[0].message.content or "").strip()
            is_yes = bool(re.search(r"TRIGGERED:\s*YES", content, re.IGNORECASE))
            m_reason = re.search(r"REASON:\s*(.+)", content, re.IGNORECASE)
            reason = m_reason.group(1).strip() if m_reason else rule.get("description", "")
            return is_yes, reason
        except Exception as e:
            logger.debug("LLM rule eval failed: %s", e)
            return False, ""

    def _generate_initial_reasoning(
        self,
        invoice: Invoice,
        validation: ValidationResult,
        triggered_rules: list[str],
        risk_factors: list[str],
    ) -> str:
        """Draft initial VP assessment."""
        if not triggered_rules and not risk_factors:
            return (
                f"Standard operating expenditure of ${float(invoice.total):,.2f} for vendor "
                f"'{invoice.vendor.name}'. All {len(invoice.line_items)} line items verified in "
                f"catalog with adequate inventory stock. Math is verified correct. Under $10K "
                f"delegated authority threshold. Initial posture: APPROVE."
            )

        risks_summary = "; ".join(risk_factors)
        return (
            f"Reviewing invoice {invoice.invoice_id} from '{invoice.vendor.name}' for ${float(invoice.total):,.2f}. "
            f"The following flags were raised: {risks_summary}. "
            f"Initial posture: HOLD for detailed scrutiny and VP/Human approval."
        )

    def _run_reflection_critique(
        self,
        invoice: Invoice,
        initial_reasoning: str,
        triggered_rules: list[str],
        risk_factors: list[str],
    ) -> str:
        """Run self-reflection / critique step to challenge the initial assessment."""
        # If LLM client is available and VP LLM review is enabled, run prompt-based critique
        if self.enable_llm_review and self.llm_client and hasattr(self.llm_client, "client"):
            try:
                critique_prompt = (
                    f"You are the Executive Vice President of Finance conducting a self-critique review.\n"
                    f"Invoice: {invoice.invoice_id}, Vendor: {invoice.vendor.name}, Total: ${invoice.total}\n"
                    f"Initial Assessment:\n{initial_reasoning}\n\n"
                    f"Triggered Rules:\n" + "\n".join(f"- {r}" for r in triggered_rules) + "\n\n"
                    f"Challenge your own initial assessment:\n"
                    f"1. Did we account for edge cases, structuring patterns, split invoices, or duplicate billing?\n"
                    f"2. Could this be a legitimate rush order or an intentional policy bypass?\n"
                    f"3. What is the appropriate corporate governance recommendation?\n"
                    f"Keep your reflection concise (2-4 sentences)."
                )
                response = self.llm_client.client.chat.completions.create(
                    model=getattr(self.llm_client, "light_model", "gpt-4o-mini"),
                    messages=[
                        {"role": "system", "content": "You are a sharp, cautious VP of Finance exercising fiduciary governance."},
                        {"role": "user", "content": critique_prompt},
                    ],
                    max_tokens=250,
                    temperature=0.2,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.debug("LLM reflection failed (%s), using deterministic critique", e)

        # Deterministic reflection / critique fallback
        if not triggered_rules:
            return (
                "Self-Critique: Evaluated potential hidden risks. Confirmed no duplicate invoice "
                "exists, no structuring just below $10K was attempted, date is a standard business day, "
                "and warehouse inventory is sufficient. Low-risk transaction confirmed."
            )

        critiques = []
        for factor in risk_factors:
            if "structuring" in factor.lower():
                critiques.append("Amount is dangerously close to $10,000 threshold, suggesting intentional structuring to evade VP review policy.")
            elif "duplicate" in factor.lower():
                critiques.append("High probability of double-billing; accounts payable must verify whether prior invoice was disbursed.")
            elif "unbundled" in factor.lower():
                critiques.append("Vendor frequency indicates split billing across 7 days to circumvent VP review authority.")
            elif "shell company" in factor.lower() or "sequential" in factor.lower():
                critiques.append("Consecutive invoice numbers across multi-week gap strongly suggests sole customer or shell entity.")
            elif "weekend" in factor.lower() or "holiday" in factor.lower():
                critiques.append("Irregular billing calendar date raises audit concerns regarding legitimate service dispatch.")
            elif "fraud" in factor.lower():
                critiques.append("High severity fraud indicators present; immediate hold warranted to prevent funds loss.")
            elif "spend threshold" in factor.lower():
                critiques.append("Material financial liability (> $10,000); requires corporate officer sign-off under procurement policy.")

        if not critiques:
            critiques.append("Discrepancies present requiring human operational sign-off before capital disbursement.")

        return "Self-Critique: " + " ".join(critiques)

    # -----------------------------------------------------------------------
    # Helper utilities
    # -----------------------------------------------------------------------

    @staticmethod
    def _extract_invoice_number(invoice_id: str) -> int | None:
        """Extract numeric digits from invoice ID (e.g., INV-1041 -> 1041)."""
        match = re.search(r"(\d+)", invoice_id)
        return int(match.group(1)) if match else None

    @staticmethod
    def _parse_iso_date(date_str: Any) -> date | None:
        """Parse string or date into datetime.date object."""
        if isinstance(date_str, date):
            return date_str
        if not date_str or not isinstance(date_str, str):
            return None
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except ValueError:
            return None

    @classmethod
    def _is_within_days(cls, date_str: Any, target_date: date, days: int = 7) -> bool:
        """Check if date_str is within `days` before or on `target_date`."""
        d = cls._parse_iso_date(date_str)
        if not d:
            return False
        diff = (target_date - d).days
        return 0 <= diff <= days
