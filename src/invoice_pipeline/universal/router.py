"""
Phase 1 – Universal Document Ingestion Router.

Detects the incoming format, converts it into a flat Intermediate
Representation (IR), and hands it off to Phase 2.

Supported formats
─────────────────
  JSON  → parse directly
  XML   → xmltodict → flat dict
  CSV   → csv.DictReader → first row or multi-row
  TXT   → sniff for embedded JSON/XML; if ambiguous → Ollama structured extraction
  PDF   → placeholder for multimodal LLM / layout-aware OCR

Usage
─────
    router = DocumentIngestionRouter(ollama_model="qwen2.5:7b")
    ir = router.ingest(file_path="invoices/facture.txt")
    # ir.raw_pairs is now ready for Phase 2
"""

from __future__ import annotations

import csv
import io
import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any

import xmltodict

from .schemas import ExtractedKVPair, IntermediateRepresentation, TXTIngestionResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten(obj: Any, prefix: str = "", sep: str = ".") -> dict[str, Any]:
    """
    Recursively flatten a nested dict/list into a single-level dict.

    Lists are expanded with index-suffixed keys UNLESS they look like a
    homogeneous array of line-item dicts, in which case the whole list
    is stored as-is under its key (to be handled by line-item logic later).

    Examples
    --------
    {"vendor": {"name": "Acme"}} → {"vendor.name": "Acme"}
    {"articles": [...]}          → {"articles": [...]}   (preserved)
    """
    items: dict[str, Any] = {}

    if isinstance(obj, dict):
        for k, v in obj.items():
            full_key = f"{prefix}{sep}{k}" if prefix else k

            # Preserve list-of-dicts as a single value (line items)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                items[full_key] = v
            elif isinstance(v, (dict, list)):
                items.update(_flatten(v, full_key, sep))
            else:
                items[full_key] = v

    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            full_key = f"{prefix}{sep}{i}" if prefix else str(i)
            if isinstance(v, (dict, list)):
                items.update(_flatten(v, full_key, sep))
            else:
                items[full_key] = v

    return items


def _detect_format(file_path: Path, content: str) -> str:
    """
    Determine document format from extension + content sniffing.

    Priority: explicit extension → MIME type → content heuristics.
    """
    ext = file_path.suffix.lower().lstrip(".")

    if ext in ("json",):
        return "json"
    if ext in ("xml",):
        return "xml"
    if ext in ("csv", "tsv"):
        return "csv"
    if ext in ("pdf",):
        return "pdf"

    # For .txt or unknown: sniff the content
    stripped = content.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "json"
    if stripped.startswith("<"):
        return "xml"
    # Heuristic: >2 lines with a consistent delimiter → probably CSV
    lines = content.splitlines()
    if len(lines) > 1 and lines[0].count(",") > 2:
        return "csv"

    return "txt"


def _xml_to_flat(content: str) -> dict[str, Any]:
    """Parse XML with xmltodict and flatten the result."""
    parsed = xmltodict.parse(content, force_list=("item", "line", "entry"))
    # xmltodict wraps everything in a root element; unwrap one level
    if len(parsed) == 1:
        parsed = next(iter(parsed.values()))
    return _flatten(parsed)


def _json_to_flat(content: str) -> dict[str, Any]:
    """Parse JSON and flatten."""
    return _flatten(json.loads(content))


def _csv_to_flat(content: str) -> dict[str, Any]:
    """
    Parse CSV.  If there is exactly one data row, return it as a flat dict.
    If there are multiple rows, treat each row as a line item and return
    {"line_items": [...]}.
    """
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return {}
    if len(rows) == 1:
        return dict(rows[0])
    return {"line_items": [dict(r) for r in rows]}


def _sniff_txt(content: str) -> tuple[str, dict[str, Any] | None]:
    """
    Check if a .txt file actually contains embedded JSON or XML.

    Returns (detected_format, flat_dict) if structured, else ("txt", None).
    """
    stripped = content.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return "json", _json_to_flat(content)
        except json.JSONDecodeError:
            pass
    if stripped.startswith("<"):
        try:
            return "xml", _xml_to_flat(content)
        except Exception:
            pass
    return "txt", None


# ---------------------------------------------------------------------------
# PDF Placeholder
# ---------------------------------------------------------------------------

def _pdf_extract_placeholder(file_path: Path, llm_client: Any = None) -> dict[str, Any]:
    """
    Placeholder for layout-aware PDF extraction.

    Production implementations should swap this for one of:
      A) Multimodal LLM vision  (e.g. GPT-4o, Gemini Pro Vision, LLaVA)
         – encode page images as base64, send to vision model, get JSON back
      B) Layout-aware OCR       (e.g. AWS Textract, Google Document AI, Surya)
         – returns bounding-box annotated key-value blocks

    Current behaviour: uses the existing LLMClient PDF vision extractor
    if available, else returns an empty dict with an error note.
    """
    logger.info("PDF extraction requested for %s", file_path)

    if llm_client is not None:
        try:
            # Delegates to the existing vision-based PDF extractor
            from invoice_pipeline.ingestion.pdf_extractor import extract_from_pdf
            raw_text = extract_from_pdf(file_path, llm_client)
            # Return as single opaque text block; Phase 2 will run regex over it
            return {"__raw_pdf_text__": raw_text}
        except Exception as exc:
            logger.error("PDF extraction via LLM failed: %s", exc)

    return {
        "__error__": f"PDF extraction not implemented. File: {file_path}",
        "__note__": (
            "Swap _pdf_extract_placeholder() with a multimodal LLM call "
            "or a layout-aware OCR service (AWS Textract, Google Document AI)."
        ),
    }


# ---------------------------------------------------------------------------
# Ollama TXT Extractor
# ---------------------------------------------------------------------------

def _ollama_extract_txt(
    content: str,
    model: str = "qwen2.5:7b",
    timeout: int = 120,
) -> dict[str, Any]:
    """
    Send unstructured text to a local Ollama model and request structured
    extraction conforming to the TXTIngestionResult Pydantic schema.

    The response is validated with Pydantic before returning the flat dict.

    Requires: `pip install ollama` and `ollama serve` running locally.
    """
    try:
        import ollama
    except ImportError as e:
        raise ImportError(
            "ollama Python package not installed. Run: pip install ollama"
        ) from e

    system_prompt = (
        "You are an expert invoice data extraction system. "
        "Extract every key-value pair visible in the invoice text into structured JSON. "
        "For line items produce a list of objects each containing at minimum: "
        "item (name/description), quantity, unit_price. "
        "Normalize numbers to plain floats. Normalize dates to YYYY-MM-DD. "
        "Do not invent data not present in the text. "
        "Return only valid JSON matching the provided schema."
    )

    schema_json = TXTIngestionResult.model_json_schema()

    user_prompt = (
        f"Invoice text to extract from:\n\n```\n{content}\n```\n\n"
        f"Return JSON conforming to this schema:\n{json.dumps(schema_json, indent=2)}"
    )

    logger.info("Sending TXT document to Ollama/%s for structured extraction", model)

    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        format="json",
        options={"temperature": 0.0},
    )

    raw_json = response["message"]["content"]

    # Validate and parse through Pydantic
    result = TXTIngestionResult.model_validate_json(raw_json)
    logger.info(
        "Ollama extracted %d KV pairs + %d line items from TXT",
        len(result.pairs),
        len(result.line_items),
    )

    # Materialise to flat dict
    flat: dict[str, Any] = {
        pair.original_key: pair.value for pair in result.pairs
    }
    if result.line_items:
        flat["line_items"] = result.line_items

    return flat


# ---------------------------------------------------------------------------
# DocumentIngestionRouter
# ---------------------------------------------------------------------------

class DocumentIngestionRouter:
    """
    Phase 1 – Universal Ingestion Router.

    Converts any incoming document format into a flat Intermediate
    Representation (IR) ready for the Phase 2 mapper.

    Parameters
    ----------
    ollama_model  : Ollama model tag for TXT extraction (e.g. "qwen2.5:7b")
    llm_client    : Optional existing LLMClient for PDF vision extraction
    encoding      : Primary text encoding to try (falls back to latin-1)
    """

    def __init__(
        self,
        ollama_model: str = "qwen2.5:7b",
        llm_client: Any = None,
        encoding: str = "utf-8",
    ) -> None:
        self.ollama_model = ollama_model
        self.llm_client = llm_client
        self.encoding = encoding

    # ── Public API ────────────────────────────────────────────────────────

    def ingest(self, file_path: str | Path) -> IntermediateRepresentation:
        """
        Primary entry point.  Reads the file, detects its format,
        and returns a flat IR dict.

        Parameters
        ----------
        file_path : path to the file to ingest

        Returns
        -------
        IntermediateRepresentation
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        raw_pairs = self._route(path)
        ir = IntermediateRepresentation(
            source_format=_detect_format(path, ""),
            source_file=str(path),
            raw_pairs=raw_pairs,
        )
        logger.info(
            "Ingestion complete: %s → %d raw keys from %s",
            path.name,
            len(raw_pairs),
            ir.source_format.upper(),
        )
        return ir

    def ingest_string(
        self,
        content: str,
        hint_format: str = "txt",
        source_name: str = "<string>",
    ) -> IntermediateRepresentation:
        """
        Ingest from an in-memory string (useful for API payloads).

        Parameters
        ----------
        content     : raw document text / bytes decoded as string
        hint_format : format hint if known ('json', 'xml', 'csv', 'txt')
        source_name : label for the IR
        """
        raw_pairs = self._dispatch_content(content, hint_format)
        return IntermediateRepresentation(
            source_format=hint_format,
            source_file=source_name,
            raw_pairs=raw_pairs,
        )

    # ── Internal routing ─────────────────────────────────────────────────

    def _route(self, path: Path) -> dict[str, Any]:
        """Read file and dispatch to the appropriate format handler."""
        # PDF is binary; handle separately before reading as text
        if path.suffix.lower() == ".pdf":
            return _pdf_extract_placeholder(path, self.llm_client)

        content = self._read_text(path)
        detected = _detect_format(path, content)
        return self._dispatch_content(content, detected)

    def _dispatch_content(self, content: str, fmt: str) -> dict[str, Any]:
        """Dispatch to the right format handler given an already-loaded string."""
        if fmt == "json":
            logger.debug("Format: JSON")
            return _json_to_flat(content)

        if fmt == "xml":
            logger.debug("Format: XML")
            return _xml_to_flat(content)

        if fmt == "csv":
            logger.debug("Format: CSV")
            return _csv_to_flat(content)

        if fmt == "txt":
            # Check if it's secretly JSON or XML
            sniffed_fmt, flat = _sniff_txt(content)
            if flat is not None:
                logger.debug("TXT sniffed as embedded %s", sniffed_fmt.upper())
                return flat

            # True unstructured text → Ollama
            logger.debug("Format: plain TXT → Ollama extraction")
            return _ollama_extract_txt(content, model=self.ollama_model)

        if fmt == "pdf":
            raise ValueError(
                "Cannot dispatch PDF from string; use ingest(file_path=...) instead."
            )

        logger.warning("Unknown format '%s' – returning empty IR", fmt)
        return {}

    def _read_text(self, path: Path) -> str:
        """Read file with encoding fallback."""
        try:
            return path.read_text(encoding=self.encoding)
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1")
