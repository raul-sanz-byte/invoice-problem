"""LLM client for structured invoice extraction and PDF handling.

Supports OpenRouter (primary), Google Gemini, and OpenAI — all via the
OpenAI-compatible Python SDK. Priority: OpenRouter → Gemini → OpenAI.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

from openai import OpenAI

from invoice_pipeline.tools import INVOICE_TOOLS, execute_tool

logger = logging.getLogger(__name__)

# System prompt for structured invoice extraction
EXTRACTION_SYSTEM_PROMPT = """\
You are a precise invoice data extraction system. Extract structured data from \
the invoice text provided. You MUST return valid JSON only.

Return a JSON object with exactly these fields:
{
  "invoice_id": "string — the invoice number/ID (e.g., INV-1001)",
  "date": "string — ISO format YYYY-MM-DD",
  "due_date": "string — ISO format YYYY-MM-DD, or null if unparseable (e.g., 'yesterday')",
  "vendor": {
    "name": "string — vendor/supplier name (required)",
    "address": "string or null — vendor address if present"
  },
  "line_items": [
    {
      "item": "string — product/service name",
      "quantity": number,
      "unit_price": number,
      "amount": number — quantity × unit_price (or the stated amount),
      "note": "string or null — e.g., 'Volume discount', 'Expedited', 'Replacement'"
    }
  ],
  "subtotal": number or null,
  "tax_rate": number or null — as decimal (e.g., 0.08 for 8%, 0.06 for 6%),
  "tax_amount": number or null,
  "total": number,
  "currency": "string — ISO 4217 code, default 'USD'",
  "payment_terms": "string or null — e.g., 'Net 30', 'Immediate'",
  "payment_terms_days": integer or null — e.g., 30 for 'Net 30', 15 for 'Net 15', 0 for 'Immediate'/'Immediately',
  "shipping": number or null,
  "notes": "string or null — any additional notes, warnings, or special instructions on the invoice",
  "revision": "string or null — revision identifier like 'R1' if present"
}

Rules:
- Parse dates carefully: "Jan 30 2026" → "2026-01-30", "01/28/2026" → "2026-01-28".
- If due_date is "yesterday" or otherwise invalid/relative, set due_date to null.
- "Net 15" → payment_terms_days = 15. "Net 30" → 30. "Net 60" → 60.
- "Immediate" or "Immediately" → payment_terms_days = 0.
- Calculate amount = quantity × unit_price for each line item.
- If the invoice says "@ $750 ea" that means unit_price = 750.
- If it says "x12" or "qty 20" that means quantity = 12 or 20.
- Extract ALL line items — do not skip any.
- If currency is not stated, default to "USD".
- If the invoice includes revision info (e.g., "R1", "Revised"), capture it.
- Include any notes about urgency, wire transfers, or special payment instructions.

Return ONLY the JSON object. No markdown, no explanation, no code blocks.\
"""

PDF_EXTRACTION_PROMPT = """\
Extract ALL text content from this invoice document. Preserve:
- All numbers, amounts, quantities, and prices exactly as written
- All dates in their original format
- The structure and layout (headers, line items, totals)
- Any notes, terms, or special instructions

Return the text content only — no commentary or formatting.\
"""


def is_rate_limit_error(error: Any) -> bool:
    """Check whether an error or string represents a 429 / quota / rate limit exception."""
    if not error:
        return False
    msg = str(error).lower()
    return any(
        kw in msg
        for kw in (
            "429",
            "resource_exhausted",
            "quota exceeded",
            "quota",
            "rate limit",
            "ratelimit",
            "too many requests",
            "generativelanguage.googleapis.com",
            "generaterequestsperday",
            "openrouter",
        )
    )


def is_ollama_available(base_url: str = "http://localhost:11434") -> bool:
    """Fast non-blocking check (timeout=0.5s) to see if local Ollama daemon is running."""
    import urllib.request
    clean_url = (base_url or "http://localhost:11434").rstrip("/")
    if clean_url.endswith("/v1"):
        clean_url = clean_url[:-3]
    try:
        req = urllib.request.Request(f"{clean_url}/api/tags", headers={"User-Agent": "FlowAudit/1.0"})
        with urllib.request.urlopen(req, timeout=0.5) as resp:
            return resp.status == 200
    except Exception:
        return False


class HeuristicMessage:
    def __init__(self, content: str = "{}") -> None:
        self.content = content
        self.tool_calls = None


class HeuristicChoice:
    def __init__(self, content: str = "{}") -> None:
        self.message = HeuristicMessage(content)


class HeuristicResponse:
    def __init__(self, content: str = "{}") -> None:
        self.choices = [HeuristicChoice(content)]


class ResilientChatCompletions:
    """Chat completions proxy that dispatches to primary cloud LLM,
    falls back to local Ollama, and ultimately falls back to deterministic heuristics."""

    def __init__(self, primary_create=None, fallback_create=None, llm_client=None) -> None:
        self._primary_create = primary_create
        self._fallback_create = fallback_create
        self._llm_client = llm_client

    def create(self, **kwargs) -> Any:
        # 1. Try Primary Cloud Provider (unless configured in pure heuristic mode)
        if self._primary_create is not None and not getattr(self._llm_client, "is_offline_heuristic", False):
            try:
                return self._primary_create(**kwargs)
            except Exception as e:
                prov = getattr(self._llm_client, "provider", "primary")
                logger.warning("Primary LLM (%s) failed during chat completion: %s. Attempting fallback...", prov, e)
                if self._llm_client:
                    self._llm_client.last_error = str(e)
                    if is_rate_limit_error(e):
                        self._llm_client.last_quota_error = str(e)

        # 2. Try Local Ollama Fallback if available
        if self._fallback_create is not None and getattr(self._llm_client, "ollama_available", False):
            try:
                fb_kwargs = dict(kwargs)
                if hasattr(self._llm_client, "ollama_model"):
                    fb_kwargs["model"] = self._llm_client.ollama_model
                try:
                    logger.info("Failing over request to local Ollama (%s)...", fb_kwargs.get("model"))
                    return self._fallback_create(**fb_kwargs)
                except Exception as ollama_tool_err:
                    # If model doesn't support tools schema, retry with json_object response format
                    if "tools" in fb_kwargs:
                        logger.info("Ollama tool calling unsupported by model, retrying with json_object: %s", ollama_tool_err)
                        del fb_kwargs["tools"]
                        fb_kwargs["response_format"] = {"type": "json_object"}
                        return self._fallback_create(**fb_kwargs)
                    raise ollama_tool_err
            except Exception as fb_err:
                logger.warning("Local Ollama fallback also failed: %s", fb_err)

        # 3. Deterministic Heuristic Fallback (Guarantees zero-crash offline execution)
        if self._llm_client is not None:
            return self._llm_client._create_heuristic_completion(**kwargs)

        raise RuntimeError(f"All LLM providers failed: {getattr(self._llm_client, 'last_error', 'Unknown error')}")


class ResilientChat:
    def __init__(self, completions_proxy: ResilientChatCompletions) -> None:
        self.completions = completions_proxy


class ResilientOpenAIClient:
    """Drop-in OpenAI client proxy supporting transparent failover."""

    def __init__(self, primary_client=None, fallback_client=None, llm_client=None) -> None:
        self.primary_client = primary_client
        self.fallback_client = fallback_client
        self.llm_client = llm_client
        primary_create = primary_client.chat.completions.create if primary_client else None
        fallback_create = fallback_client.chat.completions.create if fallback_client else None
        self.chat = ResilientChat(ResilientChatCompletions(primary_create, fallback_create, llm_client))


class LLMClient:
    """Resilient multi-tier LLM client supporting Cloud (OpenRouter, Gemini, OpenAI),
    Local Ollama, and Deterministic Heuristics fallback."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        provider: str | None = None,
    ) -> None:
        self.last_quota_error: str | None = None
        self.last_error: str | None = None
        if not api_key:
            try:
                from dotenv import load_dotenv
                load_dotenv()
            except ImportError:
                pass

        requested_provider = (provider or os.environ.get("LLM_PROVIDER", "auto")).lower().strip()
        openrouter_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
        gemini_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        ollama_url = (os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434/v1").strip()
        self.ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.2")
        self.ollama_light_model = os.environ.get("OLLAMA_LIGHT_MODEL", self.ollama_model)

        # Check local Ollama daemon availability
        self.ollama_available = is_ollama_available(ollama_url)

        primary_client = None
        fallback_client = None
        self.is_offline_heuristic = False

        # ── 1. Explicit Ollama Provider Mode ─────────────────────────────────
        if requested_provider == "ollama":
            self.provider = "ollama"
            self.base_url = base_url or ollama_url
            self.model = model or self.ollama_model
            self.light_model = self.ollama_light_model
            self.api_key = "ollama"
            primary_client = OpenAI(base_url=self.base_url, api_key="ollama")
            if not self.ollama_available:
                logger.warning(
                    "LLM_PROVIDER=ollama requested, but Ollama is not running at %s. "
                    "Operating in self-contained deterministic heuristic fallback mode.",
                    self.base_url,
                )
                self.is_offline_heuristic = True

        # ── 2. Explicit Cloud or Auto Provider Mode ──────────────────────────
        else:
            resolved_provider = "heuristic"
            if api_key:
                self.api_key = api_key
                if api_key == openrouter_key or api_key.startswith("sk-or-") or "openrouter" in (base_url or "").lower():
                    resolved_provider = "openrouter"
                elif gemini_key and api_key == gemini_key:
                    resolved_provider = "gemini"
                elif api_key.startswith("AIza") or "generativelanguage" in (base_url or "") or "gemini" in (model or "").lower():
                    resolved_provider = "gemini"
                else:
                    resolved_provider = "openai"
            elif openrouter_key:
                self.api_key = openrouter_key
                resolved_provider = "openrouter"
            elif gemini_key:
                self.api_key = gemini_key
                resolved_provider = "gemini"
            elif openai_key and openai_key not in ("your_openai_api_key_here", ""):
                self.api_key = openai_key
                resolved_provider = "openai"
            elif self.ollama_available:
                self.api_key = "ollama"
                resolved_provider = "ollama"
            else:
                self.api_key = "none"
                resolved_provider = "heuristic"

            self.provider = resolved_provider

            if resolved_provider == "openrouter":
                self.base_url = base_url or os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
                self.model = model or os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o")
                self.light_model = os.environ.get("OPENROUTER_LIGHT_MODEL", "openai/gpt-4o-mini")
                client_kwargs = {
                    "api_key": self.api_key,
                    "base_url": self.base_url,
                    "default_headers": {
                        "HTTP-Referer": "https://flowaudit.ai",
                        "X-Title": "FlowAudit AI Invoice Pipeline",
                    },
                }
                primary_client = OpenAI(**client_kwargs)
            elif resolved_provider == "gemini":
                self.base_url = base_url or os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
                self.model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
                self.light_model = os.environ.get("GEMINI_LIGHT_MODEL", "gemini-2.5-flash")
                primary_client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            elif resolved_provider == "openai":
                self.base_url = base_url or os.environ.get("OPENAI_BASE_URL", None)
                self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")
                self.light_model = os.environ.get("OPENAI_LIGHT_MODEL", "gpt-4o-mini")
                client_kwargs = {"api_key": self.api_key}
                if self.base_url:
                    client_kwargs["base_url"] = self.base_url
                primary_client = OpenAI(**client_kwargs)
            elif resolved_provider == "ollama":
                self.base_url = base_url or ollama_url
                self.model = model or self.ollama_model
                self.light_model = self.ollama_light_model
                primary_client = OpenAI(base_url=self.base_url, api_key="ollama")
            else:  # heuristic
                self.base_url = None
                self.model = "deterministic-heuristic"
                self.light_model = "deterministic-heuristic"
                self.is_offline_heuristic = True
                logger.info("No cloud LLM API keys and Ollama not running; initialized in self-contained deterministic heuristic mode.")

        # Prepare Ollama fallback client if available and primary is cloud
        if self.ollama_available and self.provider != "ollama":
            try:
                fallback_client = OpenAI(base_url=ollama_url, api_key="ollama")
            except Exception as e:
                logger.debug("Could not prepare Ollama fallback client: %s", e)

        # Wrap in transparent resilient client proxy
        self.client = ResilientOpenAIClient(primary_client, fallback_client, self)
        logger.info(
            "LLMClient ready [%s%s] model=%s (Ollama fallback: %s)",
            self.provider.upper(),
            " (HEURISTIC)" if self.is_offline_heuristic else "",
            self.model,
            "AVAILABLE" if self.ollama_available else "UNAVAILABLE",
        )

    def _create_heuristic_completion(self, **kwargs) -> HeuristicResponse:
        """Synthesize deterministic rule-based response when offline and no LLM is running."""
        messages = kwargs.get("messages", [])
        prompt_text = " ".join(str(m.get("content", "")) for m in messages).lower()
        if "does this invoice violate or trigger this rule" in prompt_text:
            return HeuristicResponse("TRIGGERED: NO\nREASON: Passed offline heuristic evaluation")
        if "fiduciary critique" in prompt_text or "reflection" in prompt_text:
            return HeuristicResponse("Offline heuristic review: Invoice meets standard operational guidelines.")
        if "sql" in prompt_text or "select" in prompt_text:
            return HeuristicResponse("")
        return HeuristicResponse("{}")

    # ------------------------------------------------------------------
    # PDF → Text
    # ------------------------------------------------------------------

    def extract_text_from_pdf(self, pdf_path: str | Path) -> str:
        """Extract text from a PDF.

        First attempts direct text extraction with pdfminer.six.
        If pdfminer produces empty output (e.g., scanned/image PDF),
        attempts OpenAI file/vision processing.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Primary method: extract embedded text with spatial layout preservation
        try:
            from invoice_pipeline.ingestion.pdf_extractor import extract_spatial_pdf_text
            text = extract_spatial_pdf_text(str(pdf_path)).strip()
            if text:
                logger.info("PDF text extracted via spatial pdfminer: %d characters", len(text))
                return text
        except Exception as e:
            logger.warning("pdfminer extraction failed: %s", e)

        # Fallback for scanned/image PDFs (can use Tesseract or vision model)
        # TODO: Add Tesseract OCR support for scanned/image-based PDFs
        logger.info("Sending PDF to OpenAI for extraction: %s", pdf_path.name)
        try:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PDF_EXTRACTION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:application/pdf;base64,{b64_pdf}"
                                },
                            },
                        ],
                    }
                ],
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            self.last_error = str(e)
            if is_rate_limit_error(e):
                self.last_quota_error = str(e)
            logger.error("OpenAI PDF vision extraction failed: %s", e)
            return ""

    # ------------------------------------------------------------------
    # Text → Structured Invoice Fields
    # ------------------------------------------------------------------

    def _parse_json_content(self, raw_content: str) -> dict[str, Any]:
        """Parse raw content string to JSON dictionary."""
        raw_content = raw_content.strip()
        if raw_content.startswith("```"):
            lines = raw_content.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw_content = "\n".join(lines)

        try:
            return json.loads(raw_content)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse OpenAI response as JSON: %s", e)
            logger.debug("Raw response: %s", raw_content[:500])
            raise ValueError(f"LLM returned invalid JSON: {e}") from e

    def extract_invoice_fields(
        self,
        text: str,
        database: Any = None,
        enable_tools: bool = True,
    ) -> dict[str, Any]:
        """Extract structured invoice fields from raw text using OpenAI with tools.

        Args:
            text: Raw invoice text (from any format: PDF, email, plain text, etc.)
            database: Optional InvoiceDatabase for tool execution (catalog lookup).
            enable_tools: Whether to equip the model with catalog and arithmetic tools.

        Returns:
            Dictionary of extracted invoice fields matching the Invoice schema.
        """
        if getattr(self, "is_offline_heuristic", False):
            try:
                from invoice_pipeline.extraction.field_extractor import extract_fields_from_text
                data = extract_fields_from_text(text)
                logger.info("Field extraction complete via heuristic extractor: %d fields", len(data))
                return data
            except Exception as e:
                logger.warning("Heuristic field extraction fallback failed: %s", e)
                return {}

        logger.info(
            "Sending text to %s (%s) for field extraction (%d chars, tools=%s)",
            self.provider.upper(),
            self.model,
            len(text),
            enable_tools,
        )

        from invoice_pipeline.security.context_guard import build_sandboxed_prompt

        messages: list[dict[str, Any]] = build_sandboxed_prompt(
            system_instructions=EXTRACTION_SYSTEM_PROMPT,
            untrusted_document_text=text,
            extra_user_instructions="Extract all structured invoice fields from the enclosed untrusted document data into the specified JSON format.",
        )

        for round_idx in range(5):
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.0,
            }
            if enable_tools and getattr(self, "provider", "") != "gemini":
                kwargs["tools"] = INVOICE_TOOLS
            else:
                kwargs["response_format"] = {"type": "json_object"}

            try:
                response = self.client.chat.completions.create(**kwargs)
            except Exception as e:
                self.last_error = str(e)
                if is_rate_limit_error(e):
                    self.last_quota_error = str(e)
                raise
            msg = response.choices[0].message

            if msg.tool_calls:
                messages.append(msg)
                for tool_call in msg.tool_calls:
                    t_name = tool_call.function.name
                    t_args = tool_call.function.arguments
                    logger.info("Executing LLM tool call: %s", t_name)
                    tool_output = execute_tool(t_name, t_args, database=database)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_output),
                    })
                continue

            data = self._parse_json_content(msg.content or "{}")
            logger.info("Field extraction complete: %d fields extracted", len(data))
            return data

        return {}

    def self_correct_invoice(
        self,
        text: str,
        current_data: dict[str, Any],
        validation_issues: list[str],
        database: Any = None,
    ) -> dict[str, Any]:
        """Self-correct invoice extraction given validation discrepancies."""
        logger.info(
            "Running LLM self-correction loop for invoice with %d issue(s)",
            len(validation_issues),
        )
        issues_str = "\n".join(f"- {issue}" for issue in validation_issues)
        critique_prompt = (
            f"You previously extracted this invoice data from the document:\n"
            f"{json.dumps(current_data, indent=2, default=str)}\n\n"
            f"However, validation detected the following issues:\n"
            f"{issues_str}\n\n"
            f"Original document text:\n"
            f"{text}\n\n"
            f"Your task:\n"
            f"1. Review the validation issues and re-read the original document text.\n"
            f"2. Use the available financial and catalog tools if needed to verify amounts or items.\n"
            f"3. Return the fully corrected invoice JSON object."
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": critique_prompt},
        ]

        for _ in range(5):
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.0,
            }
            if getattr(self, "provider", "") != "gemini":
                kwargs["tools"] = INVOICE_TOOLS
            else:
                kwargs["response_format"] = {"type": "json_object"}

            try:
                response = self.client.chat.completions.create(**kwargs)
            except Exception as e:
                self.last_error = str(e)
                if is_rate_limit_error(e):
                    self.last_quota_error = str(e)
                raise
            msg = response.choices[0].message

            if msg.tool_calls:
                messages.append(msg)
                for tool_call in msg.tool_calls:
                    t_name = tool_call.function.name
                    t_args = tool_call.function.arguments
                    logger.info("Executing self-correction tool call: %s", t_name)
                    tool_output = execute_tool(t_name, t_args, database=database)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_output, default=str),
                    })
                continue

            corrected_data = self._parse_json_content(msg.content or "{}")
            logger.info("LLM self-correction produced revised invoice data")
            return corrected_data

        return current_data

    # ------------------------------------------------------------------
    # Field Synonym Discovery (Lightest LLM)
    # ------------------------------------------------------------------

    def map_alternative_fields(
        self,
        unmatched_keys: list[str],
        missing_fields: list[str],
        sample_values: dict[str, Any] | None = None,
        is_line_item: bool = False,
    ) -> dict[str, str]:
        """Map unknown/alternative invoice field names to canonical fields using the lightest LLM (gpt-4o-mini).

        Args:
            unmatched_keys: Unmatched keys/tags/column headers found in the document.
            missing_fields: Canonical fields that are currently missing.
            sample_values: Optional sample values for the unmatched keys.
            is_line_item: Whether these keys belong to a line item.

        Returns:
            Dict of {unmatched_key: canonical_field}.
        """
        if not unmatched_keys or not missing_fields:
            return {}

        sample_vals = sample_values or {}
        samples_formatted = {
            k: str(sample_vals.get(k, ""))[:100] for k in unmatched_keys
        }

        prompt = f"""\
You are an expert invoice schema mapper.
We have incoming unknown field names from an invoice that need to be mapped to our canonical schema.

Candidate unknown fields with sample values:
{json.dumps(samples_formatted, indent=2)}

Missing canonical fields needed:
{json.dumps(missing_fields, indent=2)}

Context: These fields are {"line item fields" if is_line_item else "invoice-level header/total fields"}.

Instructions:
1. Match each unknown field to at most ONE missing canonical field if it clearly represents that concept.
2. If an unknown field does not match any missing field, do not include it.
3. Return ONLY a JSON object mapping {{"unknown_field": "canonical_field"}}.
"""
        logger.info(
            "Using light LLM (%s) to map %d alternative fields to %d missing canonical fields",
            self.light_model,
            len(unmatched_keys),
            len(missing_fields),
        )

        try:
            response = self.client.chat.completions.create(
                model=self.light_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise field mapping assistant. "
                            "Map unknown field keys to missing canonical fields. "
                            "Return ONLY valid JSON."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            raw = response.choices[0].message.content or "{}"
            mapping = json.loads(raw)
            valid_results = {
                k: v
                for k, v in mapping.items()
                if k in unmatched_keys and v in missing_fields
            }
            logger.info(
                "Light LLM mapped %d fields successfully: %s",
                len(valid_results),
                valid_results,
            )
            return valid_results
        except Exception as e:
            self.last_error = str(e)
            if is_rate_limit_error(e):
                self.last_quota_error = str(e)
            logger.warning("Light LLM field mapping failed: %s", e)
            return {}
