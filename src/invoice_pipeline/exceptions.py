"""Custom exceptions for the Invoice Pipeline.

Provides domain-specific exceptions for clear error handling across all layers.
"""

from __future__ import annotations


class InvoicePipelineError(Exception):
    """Base exception for all invoice pipeline errors."""
    pass


class IngestionError(InvoicePipelineError):
    """Raised when file ingestion or format detection fails."""
    pass


class FileReadError(IngestionError):
    """Raised when a source invoice file cannot be read."""
    pass


class UnsupportedFormatError(IngestionError):
    """Raised when an invoice file format is unsupported or unrecognized."""
    pass


class ExtractionError(InvoicePipelineError):
    """Raised when field extraction fails."""
    pass


class MissingRequiredFieldError(ExtractionError):
    """Raised when an invoice is missing mandatory schema fields."""
    pass


class LLMExtractionError(ExtractionError):
    """Raised when an LLM API call fails during extraction."""
    pass


class ValidationError(InvoicePipelineError):
    """Raised when invoice validation encounters an error."""
    pass


class SchemaValidationError(ValidationError):
    """Raised when invoice data violates the schema contract."""
    pass


class ArithmeticValidationError(ValidationError):
    """Raised when mathematical validation fails."""
    pass


class InventoryValidationError(ValidationError):
    """Raised when cross-referencing against product inventory fails."""
    pass


class StorageError(InvoicePipelineError):
    """Raised when a database storage or retrieval operation fails."""
    pass


class DatabaseConnectionError(StorageError):
    """Raised when connecting to the database fails."""
    pass


class TransactionError(StorageError):
    """Raised when a database transaction fails and is rolled back."""
    pass
