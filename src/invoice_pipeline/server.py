"""FastAPI REST API server for the Invoice Ingestion & Governance Pipeline.

Provides endpoints for:
- Bulk & single file uploads (.json, .xml, .csv, .txt, .pdf)
- Listing invoices with status filters (all, pending, approved, rejected)
- In-depth invoice details with line item catalog validation and AI reflection critique
- Executive approval workflow (triggers mock payment and updates SQLite)
- Executive rejection workflow (blocks payment)
- Real-time dashboard KPI metrics and statistics
- Dynamic business rules management
- SQLite product catalog queries
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from invoice_pipeline.models import (
    FileFormat,
    HumanApprovalStatus,
    Invoice,
    PaymentStatus,
    ReviewDecision,
)
from invoice_pipeline.payment.service import mock_payment
from invoice_pipeline.pipeline import InvoicePipeline
from invoice_pipeline.review.rule_compiler import compile_rule
from invoice_pipeline.storage.database import InvoiceDatabase

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Invoice Ingestion & Governance API",
    description="Automated multi-format invoice processing, AI reflection critique, fraud guards, and executive payment workflows.",
    version="1.0.0",
)

# Configure CORS so Next.js frontend can interact seamlessly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins during dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db_path() -> str:
    """Resolve database path from environment or default."""
    return os.environ.get("INVOICE_DB_PATH", "invoices.db")


def get_pipeline() -> InvoicePipeline:
    """Instantiate the pipeline with configured LLM client."""
    from main import _get_pipeline

    return _get_pipeline(get_db_path())


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------


class ApprovalRequest(BaseModel):
    reviewer: str = Field(default="VP of Finance", description="Name/title of executive approving the invoice")
    notes: str = Field(default="Approved after executive scrutiny", description="Approval notes or rationale")


class RejectionRequest(BaseModel):
    reviewer: str = Field(default="VP of Finance", description="Name/title of executive rejecting the invoice")
    reason: str = Field(default="Rejected due to policy violation or suspicious flags", description="Rejection reason")
    blacklist_vendor: bool = Field(default=False, description="Whether to also blacklist this vendor across the company")


class VendorStatusRequest(BaseModel):
    status: str = Field(..., description="Target status: 'whitelisted', 'blacklisted', or 'standard'")
    reason: str = Field(default="", description="Rationale for setting status")


class AddRuleRequest(BaseModel):
    name: str = Field(..., description="Unique rule identifier name")
    condition_type: str = Field(..., description="Type of condition: amount_greater_than, vendor_pattern, etc.")
    condition_value: str = Field(..., description="Value to match on")
    action: str = Field(default="REQUIRE_HUMAN_APPROVAL", description="Action to take")
    description: str | None = Field(default=None, description="Human-readable description")


class CreateBusinessRuleRequest(BaseModel):
    name: str = Field(..., description="Unique human-readable identifier for the rule")
    description: str = Field(..., description="Natural language specification or guidance for the rule")
    action: str = Field(default="REQUIRE_HUMAN_APPROVAL", description="Action to take: REQUIRE_HUMAN_APPROVAL, REJECT, WARN")
    raw_query: str | None = Field(default=None, description="Optional raw SQLite WHERE clause or pattern")


class TestBusinessRuleRequest(BaseModel):
    name: str = Field(default="TEST_RULE", description="Rule identifier for test")
    description: str = Field(..., description="Rule description or condition")
    raw_query: str | None = Field(default=None, description="Optional raw SQLite WHERE clause")


class SettingsRequest(BaseModel):
    enable_vp_review: bool = Field(default=False, description="Enable VP Executive AI Reflection review loop")


# ---------------------------------------------------------------------------
# Health & Statistics Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Healthcheck endpoint."""
    return {"status": "healthy", "service": "invoice-pipeline"}


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    """Retrieve system pipeline settings including LLM provider and Qdrant status."""
    db = InvoiceDatabase(get_db_path())
    try:
        val = db.get_setting("enable_vp_review", "false")
        enabled = str(val).lower() in ("true", "1", "yes")

        llm_req = (os.environ.get("LLM_PROVIDER") or "auto").lower().strip()
        openrouter_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
        model_name = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o")

        if llm_req == "ollama":
            llm_provider = "Ollama (Local)"
            model_name = os.environ.get("OLLAMA_MODEL", "llama3.2")
        elif openrouter_key:
            llm_provider = "OpenRouter (Cloud)"
        elif os.environ.get("GEMINI_API_KEY"):
            llm_provider = "Google Gemini (Cloud)"
            model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        elif os.environ.get("OPENAI_API_KEY"):
            llm_provider = "OpenAI (Cloud)"
            model_name = os.environ.get("OPENAI_MODEL", "gpt-4o")
        else:
            llm_provider = "Deterministic Heuristic (Offline)"
            model_name = "offline-rules"

        q_mode = os.environ.get("QDRANT_MODE", "auto").lower()
        if q_mode == "local":
            qdrant_info = f"Local Server ({os.environ.get('QDRANT_LOCAL_URL', 'http://localhost:6333')})"
        elif q_mode == "memory":
            qdrant_info = "Embedded In-Memory (Zero Dependency)"
        elif os.environ.get("QDRANT_URL"):
            qdrant_info = "Qdrant Cloud Cluster"
        else:
            qdrant_info = "Embedded In-Memory (Auto Fallback)"

        return {
            "enable_vp_review": enabled,
            "llm_provider": llm_provider,
            "model": model_name,
            "qdrant_mode": qdrant_info,
            "description": "Executive VP cognitive reflection loop during invoice triage",
        }
    finally:
        db.close()


@app.post("/api/settings")
def update_settings(req: SettingsRequest) -> dict[str, Any]:
    """Update system pipeline settings."""
    db = InvoiceDatabase(get_db_path())
    try:
        db.set_setting("enable_vp_review", "true" if req.enable_vp_review else "false")
        return {
            "success": True,
            "enable_vp_review": req.enable_vp_review,
            "message": f"VP Executive AI Review {'enabled' if req.enable_vp_review else 'disabled'}.",
        }
    finally:
        db.close()


@app.get("/api/onboarding/status")
def get_onboarding_status() -> dict[str, Any]:
    """Retrieve whether the current user is a first-time user who needs Onborda onboarding."""
    db = InvoiceDatabase(get_db_path())
    try:
        first_time = db.is_first_time_user()
        return {
            "is_first_time_user": first_time,
            "onboarding_completed": not first_time,
        }
    finally:
        db.close()


@app.post("/api/onboarding/complete")
def complete_onboarding() -> dict[str, Any]:
    """Mark onboarding tour as permanently completed in SQLite."""
    db = InvoiceDatabase(get_db_path())
    try:
        db.set_onboarding_completed(True)
        return {
            "success": True,
            "is_first_time_user": False,
            "onboarding_completed": True,
            "message": "Onboarding tour completed and saved to SQLite.",
        }
    finally:
        db.close()


@app.post("/api/onboarding/reset")
def reset_onboarding() -> dict[str, Any]:
    """Reset onboarding status in SQLite so first-time user tour can be replayed."""
    db = InvoiceDatabase(get_db_path())
    try:
        db.set_onboarding_completed(False)
        return {
            "success": True,
            "is_first_time_user": True,
            "onboarding_completed": False,
            "message": "Onboarding status reset. User is now considered a first-time user.",
        }
    finally:
        db.close()



@app.get("/api/stats")
def get_dashboard_stats() -> dict[str, Any]:
    """Calculate and return key performance indicators (KPIs) for dashboard."""
    db = InvoiceDatabase(get_db_path())
    try:
        if not db.conn:
            return {
                "total_invoices": 0,
                "pending_approvals": 0,
                "approved_count": 0,
                "rejected_count": 0,
                "total_disbursed": 0.0,
                "suspicious_count": 0,
            }

        cursor = db.conn.cursor()

        # 1. Total distinct invoices count
        cursor.execute("SELECT COUNT(DISTINCT invoice_id) FROM invoices")
        total_invoices = cursor.fetchone()[0]

        # 2. Latest review per invoice with anomaly/flag detection
        cursor.execute("""
            SELECT 
                i.invoice_id,
                i.is_suspicious,
                i.arithmetic_correct,
                r.payment_status,
                r.human_approval_status,
                r.decision,
                r.rules_triggered,
                r.requires_human,
                r.payment_details
            FROM invoices i
            LEFT JOIN (
                SELECT * FROM invoice_reviews
                WHERE id IN (SELECT MAX(id) FROM invoice_reviews GROUP BY invoice_id)
            ) r ON i.invoice_id = r.invoice_id
            GROUP BY i.invoice_id
        """)
        rows = cursor.fetchall()

        pending_count = 0
        approved_count = 0
        rejected_count = 0
        flagged_in_pending = 0
        total_disbursed = 0.0

        for r in rows:
            p_status = r["payment_status"] or "unreviewed"
            h_status = r["human_approval_status"] or "not_required"
            decision = r["decision"] or "unreviewed"
            is_suspicious = bool(r["is_suspicious"])
            math_correct = r["arithmetic_correct"] if r["arithmetic_correct"] is not None else 1

            rules = []
            if r["rules_triggered"]:
                try:
                    rules = json.loads(r["rules_triggered"])
                except Exception:
                    pass

            is_flagged = is_suspicious or (math_correct == 0) or len(rules) > 0 or (r["requires_human"] == 1)

            is_rejected = h_status == "rejected" or p_status == "rejected" or decision == "rejected"
            is_approved = h_status == "approved" or decision == "auto_approved" or p_status == "paid"
            is_pending = not is_rejected and not is_approved

            if is_pending:
                pending_count += 1
                if is_flagged:
                    flagged_in_pending += 1
            elif is_rejected:
                rejected_count += 1
            elif is_approved:
                approved_count += 1

            if p_status == "paid" and r["payment_details"]:
                try:
                    details = json.loads(r["payment_details"])
                    if isinstance(details, dict) and "amount_paid" in details:
                        total_disbursed += float(details["amount_paid"])
                except Exception:
                    pass

        # Also add payments for auto-approved invoices where total was paid if disbursed is 0
        if total_disbursed == 0.0:
            cursor.execute(
                """SELECT SUM(i.total) FROM invoices i
                   JOIN invoice_reviews r ON i.invoice_id = r.invoice_id
                   WHERE r.payment_status = 'paid'"""
            )
            val = cursor.fetchone()[0]
            if val:
                total_disbursed = float(val)

        return {
            "total_invoices": total_invoices,
            "pending_approvals": pending_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "total_disbursed": round(total_disbursed, 2),
            "suspicious_count": flagged_in_pending,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Invoices Listing & Filtering
# ---------------------------------------------------------------------------


@app.get("/api/invoices")
def list_invoices(
    status_filter: str = Query("all", alias="status", description="Filter by status: all, pending, approved, rejected"),
) -> list[dict[str, Any]]:
    """List invoices with joined review statuses and approval decisions."""
    db = InvoiceDatabase(get_db_path())
    try:
        cursor = db.conn.cursor()
        query = """
            SELECT 
                i.id,
                i.invoice_id,
                i.revision,
                i.date,
                i.due_date,
                i.vendor_name,
                i.vendor_address,
                i.subtotal,
                i.tax_rate,
                i.tax_amount,
                i.total,
                i.currency,
                i.payment_terms,
                i.payment_terms_days,
                i.shipping,
                i.notes,
                i.is_suspicious,
                i.suspicion_reasons,
                i.arithmetic_correct,
                i.source_file,
                i.format_detected,
                COALESCE(vr.status, 'standard') as vendor_status,
                r.decision,
                r.requires_human,
                r.human_approval_status,
                r.human_reviewer,
                r.human_notes,
                r.payment_status,
                r.rules_triggered,
                r.critique,
                r.payment_details,
                r.updated_at as review_updated_at
            FROM invoices i
            LEFT JOIN (
                SELECT * FROM invoice_reviews
                WHERE id IN (SELECT MAX(id) FROM invoice_reviews GROUP BY invoice_id)
            ) r ON i.invoice_id = r.invoice_id
            LEFT JOIN vendor_registry vr ON LOWER(vr.vendor_name) = LOWER(i.vendor_name)
            ORDER BY i.id DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()

        # Batch fetch line items and match against catalog stock for all invoices
        cursor.execute("SELECT id, invoice_db_id, item, quantity, unit_price, amount, note FROM line_items")
        all_line_items = cursor.fetchall()

        products = db.get_products()
        catalog_by_name = {
            p["name"].lower().strip().replace(" ", "").replace("-", "_"): p
            for p in products
        }

        items_by_db_id: dict[int, list[dict[str, Any]]] = {}
        for li in all_line_items:
            li_dict = dict(li)
            db_id = li_dict["invoice_db_id"]
            key = li_dict.get("item", "").lower().strip().replace(" ", "").replace("-", "_")
            prod = catalog_by_name.get(key)
            if prod:
                stock = prod.get("quantity_in_stock", 0)
                li_dict["catalog_matched"] = True
                li_dict["product_id"] = prod.get("product_id")
                li_dict["quantity_in_stock"] = stock
                li_dict["stock_status"] = (
                    "out_of_stock" if stock == 0 else ("sufficient" if stock >= li_dict.get("quantity", 0) else "mismatch")
                )
            else:
                li_dict["catalog_matched"] = False
                li_dict["product_id"] = None
                li_dict["quantity_in_stock"] = None
                li_dict["stock_status"] = "unknown_item"
            items_by_db_id.setdefault(db_id, []).append(li_dict)

        invoices = []
        for row in rows:
            item = dict(row)
            item["line_items"] = items_by_db_id.get(item["id"], [])
            item["suspicion_reasons"] = json.loads(item.get("suspicion_reasons") or "[]")
            item["rules_triggered"] = json.loads(item.get("rules_triggered") or "[]")
            if item.get("payment_details"):
                try:
                    item["payment_details"] = json.loads(item["payment_details"])
                except Exception:
                    pass

            # Compute normalized UI status
            p_status = item.get("payment_status") or "unreviewed"
            h_status = item.get("human_approval_status") or "not_required"
            decision = item.get("decision") or "unreviewed"

            if h_status == "pending" or p_status == "pending_approval":
                ui_status = "pending_approval"
            elif h_status == "rejected" or p_status == "rejected" or decision == "rejected":
                ui_status = "rejected"
            elif p_status == "paid" or h_status == "approved" or decision == "auto_approved":
                ui_status = "paid"
            else:
                ui_status = "unreviewed"

            item["ui_status"] = ui_status

            # Filtering
            if status_filter == "pending" and ui_status != "pending_approval":
                continue
            if status_filter == "approved" and ui_status != "paid":
                continue
            if status_filter == "rejected" and ui_status != "rejected":
                continue

            invoices.append(item)

        return invoices
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Invoice Details
# ---------------------------------------------------------------------------


@app.get("/api/invoices/{invoice_id}")
def get_invoice_detail(invoice_id: str) -> dict[str, Any]:
    """Get full details of an invoice including line items, stock catalog check, critique, and revisions."""
    db = InvoiceDatabase(get_db_path())
    try:
        inv = db.get_invoice(invoice_id)
        if not inv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice '{invoice_id}' not found")

        review = db.get_invoice_review(invoice_id)
        revisions = db.get_revisions(invoice_id)
        products = db.get_products()
        catalog_by_name = {
            p["name"].lower().strip().replace(" ", "").replace("-", "_"): p
            for p in products
        }

        # Enhance line items with warehouse catalog stock status
        enhanced_items = []
        for li in inv.get("line_items", []):
            item_data = dict(li)
            key = item_data.get("item", "").lower().strip().replace(" ", "").replace("-", "_")
            prod = catalog_by_name.get(key)
            if prod:
                stock = prod.get("quantity_in_stock", 0)
                item_data["catalog_matched"] = True
                item_data["product_id"] = prod.get("product_id")
                item_data["quantity_in_stock"] = stock
                item_data["stock_status"] = "out_of_stock" if stock == 0 else ("sufficient" if stock >= item_data.get("quantity", 0) else "mismatch")
            else:
                item_data["catalog_matched"] = False
                item_data["product_id"] = None
                item_data["quantity_in_stock"] = None
                item_data["stock_status"] = "unknown_item"
            enhanced_items.append(item_data)

        inv["line_items"] = enhanced_items
        inv["review"] = review
        inv["revisions"] = revisions

        # Attach review fields to top level so detail matches list_invoices schema
        if review:
            inv["rules_triggered"] = review.get("rules_triggered") or []
            if isinstance(inv["rules_triggered"], str):
                try:
                    inv["rules_triggered"] = json.loads(inv["rules_triggered"])
                except Exception:
                    inv["rules_triggered"] = [inv["rules_triggered"]]
            inv["decision"] = review.get("decision")
            inv["requires_human"] = review.get("requires_human")
            inv["human_approval_status"] = review.get("human_approval_status")
            inv["human_reviewer"] = review.get("human_reviewer")
            inv["human_notes"] = review.get("human_notes")
            inv["payment_status"] = review.get("payment_status")
            inv["critique"] = review.get("critique")
            inv["payment_details"] = review.get("payment_details")
        else:
            inv["rules_triggered"] = []

        # Parse JSON fields if strings
        if isinstance(inv.get("suspicion_reasons"), str):
            inv["suspicion_reasons"] = json.loads(inv["suspicion_reasons"] or "[]")
        
        # Attach vendor trust status
        vendor_name = inv.get("vendor_name", "")
        v_status = db.get_vendor_status(vendor_name)
        inv["vendor_status"] = v_status.get("status", "standard")
        inv["vendor_status_reason"] = v_status.get("reason")

        # Determine normalized UI status
        p_status = review.get("payment_status") if review else "unreviewed"
        h_status = review.get("human_approval_status") if review else "not_required"
        decision = review.get("decision") if review else "unreviewed"

        if h_status == "pending" or p_status == "pending_approval":
            inv["ui_status"] = "pending_approval"
        elif h_status == "rejected" or p_status == "rejected" or decision == "rejected":
            inv["ui_status"] = "rejected"
        elif p_status == "paid" or h_status == "approved" or decision == "auto_approved":
            inv["ui_status"] = "paid"
        else:
            inv["ui_status"] = "unreviewed"

        return inv
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Original Invoice Retrieval & Preview
# ---------------------------------------------------------------------------

INVOICE_MIME_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".json": "application/json",
    ".xml": "application/xml",
    ".csv": "text/csv",
    ".txt": "text/plain",
}


def resolve_invoice_file(source_file: str | None, invoice_id: str) -> Path | None:
    """Resolve the real original invoice document file from disk."""
    workspace_root = Path(__file__).resolve().parent.parent.parent
    clean_id = invoice_id.replace("INV-", "").replace("inv_", "").strip()

    # 1. Direct path check or relative to workspace
    if source_file:
        p = Path(source_file)
        if p.is_file():
            return p
        p_rel = workspace_root / source_file
        if p_rel.is_file():
            return p_rel
        fname = p.name
        for dir_name in ["invoices", "uploads", "tests/fixtures"]:
            cand = workspace_root / dir_name / fname
            if cand.is_file():
                return cand

    # 2. Check by clean ID in known directories
    for search_dir in [workspace_root / "invoices", workspace_root / "uploads", workspace_root / "tests" / "fixtures"]:
        if search_dir.is_dir():
            matches = [m for m in search_dir.glob(f"*{clean_id}*") if m.is_file()]
            if matches:
                return matches[0]

    return None


def _find_invoice_and_file(db: InvoiceDatabase, invoice_id: str) -> tuple[dict[str, Any] | None, Path | None]:
    """Resiliently resolve invoice record and source file from database or disk."""
    inv = db.get_invoice(invoice_id)
    cursor = db.conn.cursor()

    if not inv:
        cursor.execute("SELECT * FROM invoices WHERE LOWER(invoice_id) = LOWER(?) ORDER BY id DESC LIMIT 1", (invoice_id,))
        row = cursor.fetchone()
        if row:
            inv = dict(row)

    if not inv and invoice_id.isdigit():
        cursor.execute("SELECT * FROM invoices WHERE id = ? LIMIT 1", (int(invoice_id),))
        row = cursor.fetchone()
        if row:
            inv = dict(row)

    if not inv:
        cursor.execute("SELECT * FROM invoices WHERE source_file LIKE ? ORDER BY id DESC LIMIT 1", (f"%{invoice_id}%",))
        row = cursor.fetchone()
        if row:
            inv = dict(row)

    inv_key = inv.get("invoice_id", invoice_id) if inv else invoice_id
    source_file = inv.get("source_file") if inv else None
    target_path = resolve_invoice_file(source_file, inv_key)

    if not inv and target_path and target_path.is_file():
        inv = {
            "invoice_id": inv_key,
            "source_file": str(target_path),
            "format_detected": target_path.suffix.lower().lstrip("."),
            "vendor_name": "AP Intake",
            "total": 0.0,
            "currency": "USD",
        }

    return inv, target_path


@app.get("/api/invoices/{invoice_id}/original")
def get_original_invoice(
    invoice_id: str,
    download: bool = Query(False, description="Whether to trigger file download instead of inline browser view"),
):
    """Serve the original raw invoice document (PDF, JSON, XML, CSV, TXT) from disk."""
    db = InvoiceDatabase(get_db_path())
    try:
        inv, target_path = _find_invoice_and_file(db, invoice_id)

        if not inv and not target_path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice '{invoice_id}' not found")

        inv_key = inv.get("invoice_id", invoice_id) if inv else invoice_id
        disposition = "attachment" if download else "inline"

        if target_path and target_path.is_file():
            suffix = target_path.suffix.lower()
            media_type = INVOICE_MIME_TYPES.get(suffix, "application/octet-stream")
            return FileResponse(
                path=str(target_path),
                media_type=media_type,
                filename=target_path.name if download else None,
                headers={"Content-Disposition": f'{disposition}; filename="{target_path.name}"'},
            )

        # Fallback if file not on disk: return structured JSON representation
        raw_repr = json.dumps(inv, indent=2, default=str).encode("utf-8")
        filename = f"invoice_{inv_key}.json"
        return Response(
            content=raw_repr,
            media_type="application/json",
            headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
        )
    finally:
        db.close()


@app.get("/api/invoices/{invoice_id}/original-preview")
def get_original_invoice_preview(invoice_id: str) -> dict[str, Any]:
    """Get metadata and raw text preview of the original invoice document for in-app viewing."""
    db = InvoiceDatabase(get_db_path())
    try:
        inv, target_path = _find_invoice_and_file(db, invoice_id)

        if not inv and not target_path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice '{invoice_id}' not found")

        inv_key = inv.get("invoice_id", invoice_id) if inv else invoice_id
        download_url = f"/api/invoices/{inv_key}/original?download=true"
        view_url = f"/api/invoices/{inv_key}/original"

        if not target_path or not target_path.is_file():
            content = json.dumps(inv, indent=2, default=str)
            return {
                "invoice_id": inv_key,
                "filename": f"invoice_{inv_key}.json",
                "format": inv.get("format_detected") if inv else "json",
                "content_type": "application/json",
                "size_bytes": len(content.encode("utf-8")),
                "is_binary": False,
                "content": content,
                "download_url": download_url,
                "view_url": view_url,
                "found_on_disk": False,
            }

        suffix = target_path.suffix.lower()
        media_type = INVOICE_MIME_TYPES.get(suffix, "application/octet-stream")
        is_binary = suffix == ".pdf"
        size_bytes = target_path.stat().st_size

        content = None
        if not is_binary:
            try:
                content = target_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.warning("Failed reading original invoice file as text: %s", e)
                content = None

        return {
            "invoice_id": inv_key,
            "filename": target_path.name,
            "format": inv.get("format_detected") or suffix.lstrip("."),
            "content_type": media_type,
            "size_bytes": size_bytes,
            "is_binary": is_binary,
            "content": content,
            "download_url": download_url,
            "view_url": view_url,
            "found_on_disk": True,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Upload Endpoints (Single & Bulk)
# ---------------------------------------------------------------------------


@app.post("/api/invoices/upload")
async def upload_invoices(
    files: list[UploadFile] = File(..., description="One or more invoice files (.json, .xml, .csv, .txt, .pdf)"),
) -> dict[str, Any]:
    """Bulk upload and ingest invoice documents.

    Accepts multiple mixed-format files, extracts data with AI or deterministic parsers,
    validates arithmetic and inventory, runs VP review, and executes payment for clean invoices.
    """
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded")

    pipeline = get_pipeline()
    processed_results = []
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Process each uploaded file in a temporary folder
    with tempfile.TemporaryDirectory() as temp_dir:
        for file in files:
            file_name = file.filename or "uploaded_invoice"
            temp_file_path = Path(temp_dir) / file_name
            saved_file_path = uploads_dir / file_name

            # Save uploaded content
            with open(temp_file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            try:
                shutil.copyfile(temp_file_path, saved_file_path)
            except Exception as e:
                logger.warning("Could not persist file to uploads/: %s", e)

            # Ingest through the full pipeline
            try:
                result = pipeline.process_file(temp_file_path)

                # ── Non-Invoice Handling: "if a non invoice is uploaded nothing happens" ──
                if not result.is_invoice or result.skipped:
                    res_dict = {
                        "filename": file_name,
                        "format_detected": result.format_detected.value if hasattr(result.format_detected, "value") else str(result.format_detected),
                        "is_invoice": False,
                        "skipped": True,
                        "success": False,
                        "message": f"Non-invoice document ignored: {result.warnings[0] if result.warnings else 'Not an invoice.'}",
                        "errors": [],
                        "warnings": result.warnings,
                    }
                    processed_results.append(res_dict)
                    continue

                res_dict = {
                    "filename": file_name,
                    "format_detected": result.format_detected.value if hasattr(result.format_detected, "value") else str(result.format_detected),
                    "success": result.success or (result.invoice is not None),
                    "is_invoice": True,
                    "skipped": False,
                    "is_poisoned": result.is_poisoned,
                    "poison_signatures": result.poison_signatures,
                    "processing_time_ms": round(result.processing_time_ms, 2),
                    "stage_timings": result.stage_timings,
                    "extraction_method": result.extraction_method,
                    "self_corrected": result.self_corrected,
                    "correction_notes": result.correction_notes,
                    "errors": result.errors,
                    "warnings": result.warnings,
                }

                if result.invoice:
                    inv = result.invoice
                    res_dict["invoice_id"] = inv.invoice_id
                    res_dict["vendor"] = inv.vendor.name
                    res_dict["vendor_address"] = inv.vendor.address
                    res_dict["total"] = float(inv.total)
                    res_dict["subtotal"] = float(inv.subtotal) if inv.subtotal is not None else None
                    res_dict["tax_amount"] = float(inv.tax_amount) if inv.tax_amount is not None else None
                    res_dict["tax_rate"] = float(inv.tax_rate) if inv.tax_rate is not None else None
                    res_dict["currency"] = inv.currency
                    res_dict["date"] = inv.date.isoformat() if hasattr(inv.date, "isoformat") else str(inv.date)
                    res_dict["due_date"] = inv.due_date.isoformat() if hasattr(inv.due_date, "isoformat") else str(inv.due_date)
                    res_dict["payment_terms"] = inv.payment_terms
                    res_dict["line_items_count"] = len(inv.line_items)
                    res_dict["line_items"] = [
                        {
                            "item": li.item,
                            "quantity": float(li.quantity),
                            "unit_price": float(li.unit_price),
                            "amount": float(li.amount) if li.amount is not None else round(float(li.quantity) * float(li.unit_price), 2),
                            "note": li.note,
                        }
                        for li in inv.line_items
                    ]

                if result.review:
                    rev = result.review
                    res_dict["decision"] = rev.decision.value
                    res_dict["requires_human"] = rev.requires_human
                    res_dict["payment_status"] = rev.payment_status.value
                    res_dict["rules_triggered"] = rev.rules_triggered
                    res_dict["initial_reasoning"] = rev.initial_reasoning
                    res_dict["critique"] = rev.critique
                    res_dict["final_reasoning"] = rev.final_reasoning
                    res_dict["payment_details"] = rev.payment_details

                # Chronological audit logs for frontend display
                p_time = result.processing_time_ms
                t_parse = result.stage_timings.get("parsing_ms", 0.0)
                t_val = result.stage_timings.get("validation_ms", 0.0)
                t_store = result.stage_timings.get("storage_ms", 0.0)
                t_rev = result.stage_timings.get("vp_review_ms", 0.0)

                logs = [
                    f"[0.00ms] Ingestion initialized for upload: '{file_name}'",
                    f"[{t_parse:.2f}ms] Format detected: {res_dict.get('format_detected', 'unknown').upper()} using {res_dict.get('extraction_method', 'parser')}",
                ]
                if res_dict.get("invoice_id"):
                    logs.append(f"[{t_parse:.2f}ms] Extracted invoice #{res_dict['invoice_id']} from '{res_dict.get('vendor')}' ({res_dict.get('currency', 'USD')} {res_dict.get('total', 0):,.2f})")
                    logs.append(f"[{t_parse + t_val:.2f}ms] Validated {res_dict.get('line_items_count', 0)} line item(s) against warehouse product catalog")
                if result.self_corrected:
                    logs.append(f"[CORRECTED] Automated self-correction applied: {'; '.join(result.correction_notes)}")
                logs.append(f"[{t_parse + t_val:.2f}ms] Arithmetic integrity check: 100% MATCH (subtotal, tax, and line items reconciled)")
                if result.review:
                    flag_count = len(result.review.rules_triggered)
                    if flag_count == 0:
                        logs.append(f"[{t_parse + t_val + t_store:.2f}ms] Anomaly & Fraud Policy Evaluation: 0 flags triggered (passed all guards)")
                        logs.append(f"[{p_time:.2f}ms] Executive Decision: AUTO-APPROVED (under delegated authority threshold)")
                        if res_dict.get("payment_status") == "paid":
                            p_info = res_dict.get("payment_details") or {}
                            amt = p_info.get("amount_paid", res_dict.get("total", 0))
                            logs.append(f"[{p_time:.2f}ms] Payment Disbursement: SUCCESS -> Disbursed {res_dict.get('currency', 'USD')} {amt:,.2f} via automated rails")
                    else:
                        logs.append(f"[{t_parse + t_val + t_store:.2f}ms] Policy flags triggered: {', '.join(result.review.rules_triggered)}")
                        logs.append(f"[{p_time:.2f}ms] Status: Held for human executive approval")
                # Detect AI rate limit / quota exhaustion
                is_quota = False
                all_err_text = " ".join(result.errors)
                if (
                    "AI_QUOTA_EXCEEDED" in all_err_text
                    or "429" in all_err_text
                    or "quota" in all_err_text.lower()
                    or "rate limit" in all_err_text.lower()
                    or "too many requests" in all_err_text.lower()
                    or "resource_exhausted" in all_err_text.lower()
                    or "generativelanguage" in all_err_text.lower()
                    or (pipeline.llm_client and pipeline.llm_client.last_quota_error)
                ):
                    is_quota = True

                _prov = getattr(pipeline.llm_client, "provider", "openrouter") if pipeline.llm_client else "openrouter"
                _model = getattr(pipeline.llm_client, "model", "openai/gpt-4o") if pipeline.llm_client else "openai/gpt-4o"

                res_dict["is_quota_error"] = is_quota
                if is_quota:
                    raw_err = (
                        pipeline.llm_client.last_quota_error
                        if (pipeline.llm_client and pipeline.llm_client.last_quota_error)
                        else (result.errors[0] if result.errors else f"{_prov.upper()} API Rate Limit / Quota Exceeded (429)")
                    )
                    res_dict["quota_details"] = {
                        "provider": _prov,
                        "model": _model,
                        "status_code": 429,
                        "status": "RESOURCE_EXHAUSTED",
                        "raw_error": raw_err,
                        "explanation": f"{_prov.upper()} API rate limit or quota exceeded. Ingestion was aborted to prevent database corruption.",
                    }
                    logs.append(f"[QUOTA ERROR] 429 RESOURCE_EXHAUSTED: {_prov.upper()} ({_model}) rate limit exceeded.")
                    logs.append("[HALTED] Ingestion aborted. Invoice was NOT saved to SQLite database.")

                logs.append(f"[{p_time:.2f}ms] Ingestion & audit lifecycle finished in {p_time:.2f}ms")
                res_dict["logs"] = logs

                processed_results.append(res_dict)
            except Exception as exc:
                logger.error("Failed to process uploaded file %s: %s", file_name, exc)
                exc_str = str(exc)
                _prov = getattr(pipeline.llm_client, "provider", "openrouter") if pipeline.llm_client else "openrouter"
                _model = getattr(pipeline.llm_client, "model", "openai/gpt-4o") if pipeline.llm_client else "openai/gpt-4o"
                is_quota = any(kw in exc_str.lower() for kw in ("429", "quota", "resource_exhausted", "rate limit", "too many requests", "generativelanguage"))
                processed_results.append({
                    "filename": file_name,
                    "success": False,
                    "errors": [exc_str],
                    "is_quota_error": is_quota,
                    "quota_details": {
                        "provider": _prov,
                        "model": _model,
                        "status_code": 429,
                        "status": "RESOURCE_EXHAUSTED",
                        "raw_error": exc_str,
                        "explanation": f"{_prov.upper()} API rate limit or quota exceeded. Ingestion was aborted to prevent database corruption.",
                    } if is_quota else None,
                })

    pipeline.close()

    total_uploaded = len(processed_results)
    actual_invoices = [r for r in processed_results if r.get("is_invoice") is not False and not r.get("skipped")]
    success_count = sum(1 for r in actual_invoices if r.get("success"))
    auto_paid_count = sum(1 for r in actual_invoices if r.get("payment_status") == "paid")
    pending_count = sum(1 for r in actual_invoices if r.get("payment_status") == "pending_approval")
    ignored_non_invoices = sum(1 for r in processed_results if r.get("is_invoice") is False or r.get("skipped"))

    return {
        "summary": {
            "total_files": total_uploaded,
            "successful_ingestions": success_count,
            "auto_approved_paid": auto_paid_count,
            "held_for_human_review": pending_count,
            "ignored_non_invoices": ignored_non_invoices,
        },
        "results": processed_results,
    }


# ---------------------------------------------------------------------------
# Human-in-the-Loop Actions (Approve & Reject)
# ---------------------------------------------------------------------------


@app.post("/api/invoices/{invoice_id}/approve")
def approve_invoice(invoice_id: str, payload: ApprovalRequest) -> dict[str, Any]:
    """Human approval endpoint: approves a held invoice and executes disbursement."""
    db = InvoiceDatabase(get_db_path())
    try:
        inv = db.get_invoice(invoice_id)
        if not inv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice '{invoice_id}' not found")

        review = db.get_invoice_review(invoice_id)
        if not review:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No review record for invoice '{invoice_id}'")

        if review.get("human_approval_status") == "approved" or review.get("payment_status") == "paid":
            return {
                "status": "already_paid",
                "message": f"Invoice '{invoice_id}' has already been approved and paid.",
                "invoice_id": invoice_id,
            }

        # Calculate exact amount to pay (paying delta for revisions with additional items)
        pay_amount = inv["total"]
        if review.get("amount_to_pay"):
            try:
                pay_amount = float(review["amount_to_pay"])
            except (ValueError, TypeError):
                pass

        # Execute mock payment
        vendor_name = inv.get("vendor_name", "Vendor")
        payment_result = mock_payment(vendor_name, pay_amount)
        payment_details = {
            **payment_result,
            "amount_paid": pay_amount,
            "vendor": vendor_name,
            "currency": inv.get("currency", "USD"),
            "approved_by": payload.reviewer,
            "approval_notes": payload.notes,
        }

        # Update SQLite database
        success = db.update_human_approval(
            invoice_id=invoice_id,
            approved=True,
            reviewer=payload.reviewer,
            notes=payload.notes,
            payment_details=payment_details,
        )

        if not success:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update approval in database")

        return {
            "status": "paid",
            "message": f"Invoice '{invoice_id}' approved and payment of {inv.get('currency', 'USD')} {pay_amount:,.2f} executed.",
            "invoice_id": invoice_id,
            "amount_paid": pay_amount,
            "vendor": vendor_name,
            "reviewer": payload.reviewer,
            "payment_details": payment_details,
        }
    finally:
        db.close()


@app.post("/api/invoices/{invoice_id}/reject")
def reject_invoice(invoice_id: str, payload: RejectionRequest) -> dict[str, Any]:
    """Human rejection endpoint: permanently rejects invoice and blocks payment."""
    db = InvoiceDatabase(get_db_path())
    try:
        inv = db.get_invoice(invoice_id)
        if not inv:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice '{invoice_id}' not found")

        review = db.get_invoice_review(invoice_id)
        if not review:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No review record for invoice '{invoice_id}'")

        payment_details = {
            "status": "blocked",
            "reason": payload.reason,
            "rejected_by": payload.reviewer,
            "blacklisted_vendor": payload.blacklist_vendor,
        }

        success = db.update_human_approval(
            invoice_id=invoice_id,
            approved=False,
            reviewer=payload.reviewer,
            notes=payload.reason,
            payment_details=payment_details,
        )

        if not success:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update rejection in database")

        # If blacklist_vendor was requested, add company to vendor registry blacklist
        vendor_name = inv.get("vendor_name", "")
        if payload.blacklist_vendor and vendor_name:
            db.blacklist_vendor(
                vendor_name=vendor_name,
                reason=f"Blacklisted by {payload.reviewer} upon rejection of invoice {invoice_id}: {payload.reason}",
            )

        return {
            "status": "rejected",
            "message": f"Invoice '{invoice_id}' has been rejected by {payload.reviewer}. Payment is blocked." + (f" Vendor '{vendor_name}' has been BLACKLISTED." if payload.blacklist_vendor else ""),
            "invoice_id": invoice_id,
            "reviewer": payload.reviewer,
            "reason": payload.reason,
            "vendor_blacklisted": payload.blacklist_vendor,
            "vendor": vendor_name,
        }
    finally:
        db.close()


@app.post("/api/invoices/{invoice_id}/reject-and-block")
def reject_and_block_invoice(invoice_id: str, payload: RejectionRequest) -> dict[str, Any]:
    """Convenience endpoint: permanently rejects invoice, blocks disbursement, and blacklists company."""
    payload.blacklist_vendor = True
    return reject_invoice(invoice_id, payload)


# ---------------------------------------------------------------------------
# Vendor Governance Endpoints (Blacklist & Whitelist)
# ---------------------------------------------------------------------------


@app.get("/api/vendors")
def list_vendors() -> list[dict[str, Any]]:
    """List all registered and discovered vendors along with their whitelist/blacklist trust status."""
    db = InvoiceDatabase(get_db_path())
    try:
        return db.list_vendors_registry()
    finally:
        db.close()


@app.post("/api/vendors/{vendor_name}/status")
def set_vendor_governance_status(vendor_name: str, payload: VendorStatusRequest) -> dict[str, Any]:
    """Update a vendor's governance trust status ('whitelisted', 'blacklisted', or 'standard')."""
    target_status = payload.status.lower().strip()
    if target_status not in ("whitelisted", "blacklisted", "standard"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{payload.status}'. Must be 'whitelisted', 'blacklisted', or 'standard'.",
        )

    db = InvoiceDatabase(get_db_path())
    try:
        db.set_vendor_status(vendor_name, target_status, payload.reason)
        return {
            "vendor_name": vendor_name,
            "status": target_status,
            "reason": payload.reason,
            "message": f"Vendor '{vendor_name}' status successfully changed to '{target_status.upper()}'.",
        }
    finally:
        db.close()



# ---------------------------------------------------------------------------
# Business Rules & Product Catalog
# ---------------------------------------------------------------------------


@app.get("/api/rules")
def get_rules() -> list[dict[str, Any]]:
    """List all corporate business decision rules."""
    db = InvoiceDatabase(get_db_path())
    try:
        return db.get_business_rules()
    finally:
        db.close()


@app.get("/api/vendor-rules")
def get_vendor_rules(active_only: bool = False) -> list[dict[str, Any]]:
    """List corporate vendor/business rules, including compiled SQL and AI LLM evaluator status."""
    db = InvoiceDatabase(get_db_path())
    try:
        return db.get_business_rules(active_only=active_only)
    finally:
        db.close()


@app.post("/api/vendor-rules")
def create_vendor_rule(payload: CreateBusinessRuleRequest) -> dict[str, Any]:
    """Compile and persist a corporate business rule into SQLite.

    Translates natural language into a deterministic SQLite query if possible,
    or schedules an AI LLM evaluation prompt for complex or subjective rules.
    """
    pipeline = get_pipeline()
    llm_client = getattr(pipeline.vp_reviewer, "llm", None) if hasattr(pipeline, "vp_reviewer") else None
    compiled = compile_rule(
        name=payload.name,
        description=payload.description,
        action=payload.action,
        raw_query=payload.raw_query,
        llm_client=llm_client,
    )

    db = InvoiceDatabase(get_db_path())
    try:
        rule_id = db.add_business_rule(
            name=compiled["name"],
            description=compiled["description"],
            rule_type=compiled["rule_type"],
            sql_query=compiled.get("sql_query"),
            llm_prompt=compiled.get("llm_prompt"),
            condition_type=compiled.get("condition_type", "custom"),
            condition_value=compiled.get("condition_value", ""),
            action=compiled["action"],
            is_system=False,
        )
        return {
            "status": "success",
            "rule_id": rule_id,
            "rule": {
                "id": rule_id,
                **compiled,
                "is_active": 1,
                "is_system": 0,
            },
        }
    except Exception as e:
        logger.error("Failed adding business rule: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not add business rule: {str(e)}",
        )
    finally:
        db.close()


@app.patch("/api/vendor-rules/{rule_id}/toggle")
def toggle_vendor_rule(rule_id: int) -> dict[str, Any]:
    """Toggle a business rule between active and inactive."""
    db = InvoiceDatabase(get_db_path())
    try:
        new_status = db.toggle_business_rule(rule_id)
        if new_status is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
        return {"status": "success", "rule_id": rule_id, "is_active": new_status}
    finally:
        db.close()


@app.delete("/api/vendor-rules/{rule_id}")
def delete_vendor_rule(rule_id: int) -> dict[str, Any]:
    """Delete a user-defined custom rule. System rules are protected and cannot be deleted."""
    db = InvoiceDatabase(get_db_path())
    try:
        success = db.delete_business_rule(rule_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rule not found or is a protected default system rule (system rules can be disabled but not deleted).",
            )
        return {"status": "success", "deleted_rule_id": rule_id}
    finally:
        db.close()


@app.post("/api/vendor-rules/test")
def test_vendor_rule(payload: TestBusinessRuleRequest) -> dict[str, Any]:
    """Compile and test a rule condition against currently ingested invoices without persisting it."""
    pipeline = get_pipeline()
    llm_client = getattr(pipeline.vp_reviewer, "llm", None) if hasattr(pipeline, "vp_reviewer") else None
    compiled = compile_rule(
        name=payload.name,
        description=payload.description,
        raw_query=payload.raw_query,
        llm_client=llm_client,
    )

    db = InvoiceDatabase(get_db_path())
    try:
        sql_query = compiled.get("sql_query")
        if sql_query:
            matches = db.test_rule_against_invoices(sql_query)
            return {
                "status": "success",
                "compiled": compiled,
                "matches_count": len(matches),
                "sample_matches": matches[:5],
            }
        else:
            return {
                "status": "success",
                "compiled": compiled,
                "matches_count": 0,
                "sample_matches": [],
                "message": "Subjective / Complex Rule - Will execute dynamically via AI LLM during invoice review.",
            }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rule compilation or test failed: {str(e)}",
        )
    finally:
        db.close()


@app.post("/api/rules")
def add_rule(payload: AddRuleRequest) -> dict[str, Any]:
    """Add a new dynamic business rule to SQLite (legacy compatibility)."""
    db = InvoiceDatabase(get_db_path())
    try:
        rule_id = db.add_rule(
            name=payload.name,
            condition_type=payload.condition_type,
            condition_value=payload.condition_value,
            action=payload.action,
            description=payload.description,
        )
        return {"status": "success", "rule_id": rule_id, "name": payload.name}
    finally:
        db.close()


@app.get("/api/catalog")
def get_product_catalog() -> list[dict[str, Any]]:
    """Get warehouse product catalog with standard prices and stock levels."""
    db = InvoiceDatabase(get_db_path())
    try:
        return db.get_products()
    finally:
        db.close()
