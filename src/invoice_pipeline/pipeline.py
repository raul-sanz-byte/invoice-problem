"""Main pipeline orchestrator.

Flow:
    Input File → Detect Format → Extract Text → Extract Fields (LLM) → Validate → Store
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from invoice_pipeline.extraction.field_extractor import build_invoice_from_dict
from invoice_pipeline.ingestion.file_detector import detect_format
from invoice_pipeline.ingestion.text_extractor import extract_text
from invoice_pipeline.llm_client import LLMClient
from invoice_pipeline.models import (
    FileFormat,
    IngestionResult,
    Invoice,
    PaymentStatus,
    ReviewDecision,
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)
from invoice_pipeline.security.context_guard import (
    is_invoice_document,
    sanitize_text,
    detect_prompt_injection,
    defang_poisoned_content,
)
from invoice_pipeline.storage.database import InvoiceDatabase
from invoice_pipeline.validation.anomaly_detector import detect_anomalies
from invoice_pipeline.validation.arithmetic_validator import validate_arithmetic
from invoice_pipeline.validation.inventory_validator import validate_inventory
from invoice_pipeline.validation.schema_validator import validate_schema

logger = logging.getLogger(__name__)


class InvoicePipeline:
    """End-to-end invoice ingestion pipeline.

    Orchestrates:
      1. File format detection
      2. Text/content extraction
      3. Structured field extraction (LLM or deterministic)
      4. Schema validation
      5. Arithmetic validation
      6. Anomaly detection
      7. Database storage
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        database: InvoiceDatabase | None = None,
        db_path: str = "invoices.db",
        enable_vp_review: bool | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.database = database or InvoiceDatabase(db_path)
        if enable_vp_review is None:
            val = self.database.get_setting("enable_vp_review", "false")
            self.enable_vp_review = str(val).lower() in ("true", "1", "yes")
        else:
            self.enable_vp_review = bool(enable_vp_review)

    def __enter__(self) -> InvoicePipeline:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def process_file(self, file_path: str | Path) -> IngestionResult:
        """Process a single invoice file through the full pipeline.

        Args:
            file_path: Path to the invoice file.

        Returns:
            IngestionResult with extracted invoice, validation results,
            timing telemetry, and any warnings/errors.
        """
        start_time = time.perf_counter()
        file_path = Path(file_path)
        logger.info("Processing file: %s", file_path)

        result = IngestionResult(
            source_file=str(file_path),
            format_detected=FileFormat.TEXT,
        )

        if self.llm_client:
            self.llm_client.last_quota_error = None
            self.llm_client.last_error = None

        try:
            if not file_path.exists():
                err_msg = f"File not found: {file_path}"
                result.errors.append(err_msg)
                logger.error(err_msg)
                return result

            # ── Step 1: Detect Format ───────────────────────────────────────
            t0 = time.perf_counter()
            try:
                file_format = detect_format(file_path)
                result.format_detected = file_format
                result.stage_timings["detection_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                logger.info("Detected format: %s (%.2f ms)", file_format.value, result.stage_timings["detection_ms"])
            except Exception as e:
                result.errors.append(f"Format detection failed: {e}")
                logger.error("Format detection failed: %s", e)
                return result

            # ── Step 2: Extract Text / Structured Data ──────────────────────
            t1 = time.perf_counter()
            try:
                raw_text, structured_data = extract_text(
                    file_path, file_format, self.llm_client
                )
                result.raw_text = raw_text
                result.stage_timings["text_extraction_ms"] = round((time.perf_counter() - t1) * 1000, 2)
                logger.info(
                    "Text extraction complete: %d chars, structured=%s (%.2f ms)",
                    len(raw_text),
                    structured_data is not None,
                    result.stage_timings["text_extraction_ms"],
                )
            except Exception as e:
                result.errors.append(f"Text extraction failed: {e}")
                logger.error("Text extraction failed: %s", e)
                return result

            # ── Step 2.5: Security Screening & Invoice Classification ──────
            # A. Check if document is an invoice: if a non-invoice is uploaded, nothing happens
            is_inv, inv_reason = is_invoice_document(raw_text, structured_data, file_format)
            if not is_inv:
                result.is_invoice = False
                result.skipped = True
                result.success = False
                result.warnings.append(f"Ignored non-invoice document: {inv_reason}")
                logger.info(
                    "Non-invoice file uploaded ('%s'). Ingestion halted silently: %s",
                    file_path.name,
                    inv_reason,
                )
                return result

            # B. Sanitize raw text to strip zero-width chars and invisible overrides
            raw_text = sanitize_text(raw_text)
            result.raw_text = raw_text

            # C. Detect prompt injection and context poisoning attempts
            is_poisoned, signatures = detect_prompt_injection(raw_text)
            if not is_poisoned and structured_data:
                is_poisoned, signatures = detect_prompt_injection(structured_data)

            if is_poisoned:
                result.is_poisoned = True
                result.poison_signatures = signatures
                result.warnings.append(
                    f"SECURITY ALERT: Potential context poisoning / prompt injection detected: {', '.join(signatures)}"
                )
                logger.warning(
                    "Context poisoning attempt in '%s' (%s). Neutralizing content and enforcing human review.",
                    file_path.name,
                    signatures,
                )
                raw_text = defang_poisoned_content(raw_text, signatures)
                result.raw_text = raw_text

            # ── Step 3: Extract Structured Fields ───────────────────────────
            t2 = time.perf_counter()
            invoice_data: dict[str, Any] | None = None
            try:
                invoice_data, method = self._extract_fields(
                    raw_text, structured_data, file_format
                )
                result.extraction_method = method
                result.stage_timings["field_extraction_ms"] = round((time.perf_counter() - t2) * 1000, 2)
                logger.info(
                    "Field extraction complete via %s (%.2f ms)",
                    method,
                    result.stage_timings["field_extraction_ms"],
                )
            except Exception as e:
                err_str = str(e)
                if self.llm_client and self.llm_client.last_quota_error and "[AI_QUOTA_EXCEEDED]" not in err_str:
                    err_str = f"[AI_QUOTA_EXCEEDED] Google Gemini API Quota Exceeded (429 RESOURCE_EXHAUSTED): {self.llm_client.last_quota_error}. {err_str}"
                result.errors.append(f"Field extraction failed: {err_str}")
                logger.error("Field extraction failed: %s", err_str)
                return result

            # ── Step 4: Build Invoice Model ─────────────────────────────────
            t3 = time.perf_counter()
            try:
                invoice = build_invoice_from_dict(invoice_data)
                result.invoice = invoice
                result.stage_timings["model_construction_ms"] = round((time.perf_counter() - t3) * 1000, 2)
                logger.info("Invoice built: %s (%.2f ms)", invoice.invoice_id, result.stage_timings["model_construction_ms"])
            except Exception as e:
                err_str = str(e)
                if self.llm_client and self.llm_client.last_quota_error and "[AI_QUOTA_EXCEEDED]" not in err_str:
                    err_str = f"[AI_QUOTA_EXCEEDED] Document contained unrecognized fields that could not be mapped due to Gemini API Quota limit: {self.llm_client.last_quota_error}. {err_str}"
                result.errors.append(f"Invoice model construction failed: {err_str}")
                logger.error("Invoice model construction failed: %s", err_str)
                return result

            # ── Step 5: Validate & Self-Correction Loop ─────────────────
            t4 = time.perf_counter()
            validation = self._run_validations(invoice)

            if result.is_poisoned:
                validation.flag_suspicious(
                    f"Context poisoning / prompt injection detected ({', '.join(result.poison_signatures)})"
                )
                validation.issues.append(
                    ValidationIssue(
                        field="security_context",
                        severity=ValidationSeverity.ERROR,
                        message=f"SECURITY ALERT: Context poisoning attack payload detected ({', '.join(result.poison_signatures)}). Auto-approval blocked.",
                    )
                )
                validation.passed = False

            # Self-correction loop: if validation has arithmetic or schema issues, attempt repairs
            max_corrections = 2
            correction_round = 0
            while correction_round < max_corrections and (
                not validation.passed or not validation.arithmetic_correct
            ):
                correction_round += 1
                logger.info(
                    "Self-correction loop triggered for %s (round %d/%d)",
                    invoice.invoice_id,
                    correction_round,
                    max_corrections,
                )

                corrected_invoice = None
                applied_notes: list[str] = []

                # Strategy A: LLM-powered self-correction with tool use if LLM is enabled
                if self.llm_client and invoice_data:
                    try:
                        issues_text = [i.message for i in validation.issues]
                        corrected_dict = self.llm_client.self_correct_invoice(
                            raw_text,
                            invoice_data,
                            issues_text,
                            database=self.database,
                        )
                        if corrected_dict:
                            candidate = build_invoice_from_dict(corrected_dict)
                            cand_val = self._run_validations(candidate)
                            if len(cand_val.issues) < len(validation.issues) or (cand_val.passed and cand_val.arithmetic_correct):
                                corrected_invoice = candidate
                                validation = cand_val
                                invoice_data = corrected_dict
                                applied_notes.append("LLM self-corrected discrepancies using tools and context")
                    except Exception as e:
                        logger.warning("LLM self-correction round failed: %s", e)

                # Strategy B: Deterministic self-correction engine
                if not corrected_invoice:
                    try:
                        from invoice_pipeline.validation.self_corrector import deterministic_self_correct
                        candidate, det_notes = deterministic_self_correct(
                            invoice, validation, database=self.database
                        )
                        if det_notes:
                            cand_val = self._run_validations(candidate)
                            if len(cand_val.issues) <= len(validation.issues):
                                corrected_invoice = candidate
                                validation = cand_val
                                applied_notes.extend(det_notes)
                    except Exception as e:
                        logger.warning("Deterministic self-correction failed: %s", e)

                if corrected_invoice:
                    invoice = corrected_invoice
                    result.invoice = invoice
                    result.self_corrected = True
                    result.correction_attempts = correction_round
                    result.correction_notes.extend(applied_notes)
                    logger.info("Self-correction round %d succeeded: %s", correction_round, applied_notes)
                else:
                    break

            result.validation = validation
            result.stage_timings["validation_ms"] = round((time.perf_counter() - t4) * 1000, 2)

            for issue in validation.issues:
                if issue.severity == ValidationSeverity.WARNING:
                    result.warnings.append(issue.message)
                elif issue.severity == ValidationSeverity.ERROR:
                    result.errors.append(issue.message)

            # ── Step 6: Store ───────────────────────────────────────────────
            t5 = time.perf_counter()
            saved_id = None
            try:
                saved_id = self.database.save_invoice(invoice, result)
                result.stage_timings["storage_ms"] = round((time.perf_counter() - t5) * 1000, 2)
                result.success = True
                logger.info("Invoice %s stored successfully (%.2f ms)", invoice.invoice_id, result.stage_timings["storage_ms"])
            except Exception as e:
                result.errors.append(f"Database storage failed: {e}")
                logger.error("Database storage failed: %s", e)

            # ── Step 7: VP Review & Executive Payment Decision ───────────────
            t6 = time.perf_counter()
            try:
                from invoice_pipeline.review.vp_reviewer import VPReviewer
                from invoice_pipeline.payment.service import process_payment

                vp_reviewer = VPReviewer(
                    database=self.database,
                    llm_client=self.llm_client,
                    enable_llm_review=self.enable_vp_review,
                )
                review = vp_reviewer.review_invoice(
                    invoice=invoice,
                    validation=validation,
                    warnings=result.warnings,
                    errors=result.errors,
                    current_db_id=saved_id,
                )

                # Process mock payment if auto-approved, or hold if human review required
                if result.is_poisoned:
                    review.rules_triggered.append(f"CONTEXT_POISONING_ATTACK: {', '.join(result.poison_signatures)}")
                    review.decision = ReviewDecision.REQUIRES_HUMAN_APPROVAL
                    review.requires_human = True
                    review.payment_status = PaymentStatus.PENDING_APPROVAL

                payment_status, payment_details = process_payment(invoice, review)
                review.payment_status = payment_status
                review.payment_details = payment_details

                # Persist review record with payment details in SQLite
                if self.database and hasattr(self.database, "save_invoice_review"):
                    self.database.save_invoice_review(review.model_dump(mode="json"))

                result.review = review
                result.stage_timings["vp_review_ms"] = round((time.perf_counter() - t6) * 1000, 2)
                logger.info(
                    "VP Review complete for %s: Decision=%s, Payment=%s (%.2f ms)",
                    invoice.invoice_id,
                    review.decision.value,
                    payment_status.value,
                    result.stage_timings["vp_review_ms"],
                )
            except Exception as rev_err:
                logger.error("VP Review & Payment processing failed: %s", rev_err)

            if result.invoice and not result.errors:
                result.success = True

            return result
        finally:
            result.processing_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            try:
                self.database.log_ingestion(result)
            except Exception as log_err:
                logger.warning("Could not log ingestion record: %s", log_err)

    def _extract_fields(
        self,
        raw_text: str,
        structured_data: dict[str, Any] | None,
        file_format: FileFormat,
    ) -> tuple[dict[str, Any], str]:
        """Extract invoice fields from text or structured data.

        Returns:
            Tuple of (invoice_data_dict, extraction_method_name).
        """
        # If we already have structured data from deterministic parsing
        if structured_data and file_format in (
            FileFormat.JSON,
            FileFormat.XML,
            FileFormat.CSV,
        ):
            logger.info(
                "Using deterministically extracted data for %s", file_format.value
            )
            return structured_data, f"deterministic_{file_format.value}"

        # For unstructured text, PDF, email — use the LLM if configured
        if self.llm_client:
            try:
                logger.info("Using LLM for field extraction")
                model_name = getattr(self.llm_client, "model", "openai")
                fields = self.llm_client.extract_invoice_fields(
                    raw_text, database=self.database, enable_tools=True
                )
                return fields, f"llm_{model_name}"
            except Exception as e:
                logger.warning("LLM extraction failed (%s), falling back to deterministic extraction", e)

        # Try deterministic regex extraction as fallback
        from invoice_pipeline.extraction.regex_extractor import extract_from_raw_text
        regex_data = extract_from_raw_text(raw_text)
        if regex_data.get("invoice_id") or regex_data.get("line_items"):
            logger.info("Successfully extracted fields using deterministic regex fallback")
            return regex_data, "deterministic_regex_fallback"

        # Partial structured data fallback
        if structured_data:
            logger.warning("Using partial structured data as last resort")
            return structured_data, "partial_structured_fallback"

        if self.llm_client and self.llm_client.last_quota_error:
            raise ValueError(
                f"[AI_QUOTA_EXCEEDED] Google Gemini API Quota Exceeded (429 RESOURCE_EXHAUSTED): {self.llm_client.last_quota_error}"
            )

        raise ValueError(
            "Cannot extract fields: LLM unavailable and deterministic extraction could not find invoice fields. "
            "Please provide a GEMINI_API_KEY or OPENAI_API_KEY."
        )

    def _run_validations(self, invoice: Invoice) -> ValidationResult:
        """Run all validation checks on the invoice.

        Combines results from:
          1. Schema validation
          2. Arithmetic validation
          3. Anomaly detection
        """
        combined = ValidationResult()

        # Schema validation
        try:
            schema_result = validate_schema(invoice)
            for issue in schema_result.issues:
                combined.issues.append(issue)
                if issue.severity == ValidationSeverity.ERROR:
                    combined.passed = False
        except Exception as e:
            logger.error("Schema validation error: %s", e)
            combined.add_issue(
                ValidationSeverity.WARNING,
                f"Schema validation could not run: {e}",
            )

        # Arithmetic validation
        try:
            arith_result = validate_arithmetic(invoice)
            combined.arithmetic_correct = arith_result.arithmetic_correct
            for issue in arith_result.issues:
                combined.issues.append(issue)
                if issue.severity == ValidationSeverity.ERROR:
                    combined.passed = False
        except Exception as e:
            logger.error("Arithmetic validation error: %s", e)
            combined.add_issue(
                ValidationSeverity.WARNING,
                f"Arithmetic validation could not run: {e}",
            )

        # Anomaly detection
        try:
            anomaly_result = detect_anomalies(invoice)
            if anomaly_result.is_suspicious:
                combined.is_suspicious = True
                combined.suspicion_reasons.extend(
                    anomaly_result.suspicion_reasons
                )
            for issue in anomaly_result.issues:
                combined.issues.append(issue)
        except Exception as e:
            logger.error("Anomaly detection error: %s", e)
            combined.add_issue(
                ValidationSeverity.WARNING,
                f"Anomaly detection could not run: {e}",
            )

        # Inventory validation (stock check, zero-stock check, unknown items)
        try:
            inv_result = validate_inventory(invoice, database=self.database)
            if inv_result.is_suspicious:
                combined.is_suspicious = True
                combined.suspicion_reasons.extend(
                    inv_result.suspicion_reasons
                )
            for issue in inv_result.issues:
                combined.issues.append(issue)
                if issue.severity == ValidationSeverity.ERROR:
                    combined.passed = False
        except Exception as e:
            logger.error("Inventory validation error: %s", e)
            combined.add_issue(
                ValidationSeverity.WARNING,
                f"Inventory validation could not run: {e}",
            )

        return combined

    def process_directory(self, dir_path: str | Path) -> list[IngestionResult]:
        """Process all invoice files in a directory.

        Supports: .pdf, .json, .txt, .csv, .xml

        Args:
            dir_path: Path to directory containing invoice files.

        Returns:
            List of IngestionResult for each file processed.
        """
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {dir_path}")

        supported_extensions = {".pdf", ".json", ".txt", ".csv", ".xml"}
        results = []

        for file_path in sorted(dir_path.iterdir()):
            if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                logger.info("Processing: %s", file_path.name)
                result = self.process_file(file_path)
                results.append(result)

        logger.info(
            "Directory processing complete: %d files, %d successful",
            len(results),
            sum(1 for r in results if r.success),
        )
        return results

    def close(self) -> None:
        """Close database connection."""
        if self.database:
            self.database.close()
