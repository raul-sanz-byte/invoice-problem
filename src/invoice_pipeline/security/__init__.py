"""Security module for FlowAudit AI.

Includes context poisoning defense, prompt injection detection, and document classification.
"""

from .context_guard import (
    sanitize_text,
    detect_prompt_injection,
    defang_poisoned_content,
    is_invoice_document,
    build_sandboxed_prompt,
)

__all__ = [
    "sanitize_text",
    "detect_prompt_injection",
    "defang_poisoned_content",
    "is_invoice_document",
    "build_sandboxed_prompt",
]
