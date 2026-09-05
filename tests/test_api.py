"""Unit and integration tests for FastAPI REST API endpoints."""

import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from invoice_pipeline.server import app
from invoice_pipeline.storage.database import InvoiceDatabase


@pytest.fixture
def client(tmp_path: Path):
    db_path = tmp_path / "test_api.db"
    os.environ["INVOICE_DB_PATH"] = str(db_path)
    # Initialize and seed database
    db = InvoiceDatabase(db_path=db_path)
    db.close()

    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client: TestClient):
    """Verify health endpoint returns healthy."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "invoice-pipeline"}


def test_stats_endpoint_empty(client: TestClient):
    """Verify stats endpoint returns valid numbers on fresh DB."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_invoices" in data
    assert "pending_approvals" in data
    assert "total_disbursed" in data


def test_upload_json_invoice_and_auto_payment(client: TestClient):
    """Uploading clean invoice under $10K should auto-approve and execute mock payment."""
    fixture_path = Path("tests/fixtures/invoice_json_1.json")
    with open(fixture_path, "rb") as f:
        response = client.post(
            "/api/invoices/upload",
            files=[("files", (fixture_path.name, f, "application/json"))],
        )

    assert response.status_code == 200
    data = response.json()
    summary = data["summary"]
    assert summary["total_files"] == 1
    assert summary["successful_ingestions"] == 1
    assert summary["auto_approved_paid"] == 1

    result = data["results"][0]
    assert result["invoice_id"] == "INV-1004"
    assert result["payment_status"] == "paid"
    assert result["decision"] == "auto_approved"


def test_upload_suspicious_invoice_held_for_review(client: TestClient):
    """Uploading suspicious invoice must hold payment and require human review."""
    fixture_path = Path("tests/fixtures/invoice_suspicious.txt")
    with open(fixture_path, "rb") as f:
        response = client.post(
            "/api/invoices/upload",
            files=[("files", (fixture_path.name, f, "text/plain"))],
        )

    assert response.status_code == 200
    data = response.json()
    result = data["results"][0]
    assert result["payment_status"] == "pending_approval"
    assert result["requires_human"] is True


def test_invoices_list_and_filter(client: TestClient):
    """Test listing and filtering invoices by status."""
    # Upload clean invoice
    with open("tests/fixtures/invoice_json_1.json", "rb") as f1:
        client.post("/api/invoices/upload", files=[("files", ("inv1.json", f1, "application/json"))])

    # Upload suspicious invoice
    with open("tests/fixtures/invoice_suspicious.txt", "rb") as f2:
        client.post("/api/invoices/upload", files=[("files", ("inv3.txt", f2, "text/plain"))])

    # 1. List all
    all_res = client.get("/api/invoices?status=all")
    assert all_res.status_code == 200
    assert len(all_res.json()) >= 2

    # 2. Filter pending
    pending_res = client.get("/api/invoices?status=pending")
    assert pending_res.status_code == 200
    for inv in pending_res.json():
        assert inv["ui_status"] == "pending_approval"


def test_invoice_detail_endpoint(client: TestClient):
    """Test retrieving invoice detail with enhanced line items and stock matching."""
    with open("tests/fixtures/invoice_json_1.json", "rb") as f:
        client.post("/api/invoices/upload", files=[("files", ("inv1.json", f, "application/json"))])

    detail_res = client.get("/api/invoices/INV-1004")
    assert detail_res.status_code == 200
    data = detail_res.json()
    assert data["invoice_id"] == "INV-1004"
    assert len(data["line_items"]) == 2
    # Verify line items have catalog matching status
    assert "catalog_matched" in data["line_items"][0]
    assert "stock_status" in data["line_items"][0]


def test_human_approval_workflow_triggers_payment(client: TestClient):
    """Human approval should disburse funds and mark status as paid."""
    # Upload suspicious invoice ($100k, held)
    with open("tests/fixtures/invoice_suspicious.txt", "rb") as f:
        client.post("/api/invoices/upload", files=[("files", ("inv3.txt", f, "text/plain"))])

    # Approve invoice
    approve_res = client.post(
        "/api/invoices/INV-1003/approve",
        json={"reviewer": "CFO Jane Smith", "notes": "Approved after CEO authorization"},
    )
    assert approve_res.status_code == 200
    data = approve_res.json()
    assert data["status"] == "paid"
    assert data["amount_paid"] == 100000.0
    assert data["reviewer"] == "CFO Jane Smith"

    # Verify updated in listing
    inv_res = client.get("/api/invoices/INV-1003")
    rev = inv_res.json()["review"]
    assert rev["payment_status"] == "paid"
    assert rev["human_approval_status"] == "approved"
    assert rev["human_reviewer"] == "CFO Jane Smith"


def test_human_rejection_workflow_blocks_payment(client: TestClient):
    """Human rejection should block payment permanently."""
    with open("tests/fixtures/invoice_suspicious.txt", "rb") as f:
        client.post("/api/invoices/upload", files=[("files", ("inv3.txt", f, "text/plain"))])

    reject_res = client.post(
        "/api/invoices/INV-1003/reject",
        json={"reviewer": "VP Finance", "reason": "Confirmed fraudulent shell company"},
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "rejected"

    inv_res = client.get("/api/invoices/INV-1003")
    rev = inv_res.json()["review"]
    assert rev["payment_status"] == "rejected"
    assert rev["human_approval_status"] == "rejected"


def test_rules_and_catalog_endpoints(client: TestClient):
    """Verify rules list/add and product catalog endpoints."""
    # 1. Catalog
    cat_res = client.get("/api/catalog")
    assert cat_res.status_code == 200
    assert len(cat_res.json()) >= 9

    # 2. Rules list
    rules_res = client.get("/api/rules")
    assert rules_res.status_code == 200
    assert len(rules_res.json()) >= 2

    # 3. Add custom rule
    add_res = client.post(
        "/api/rules",
        json={
            "name": "CUSTOM_VIP_RULE",
            "condition_type": "vendor_pattern",
            "condition_value": "VIP Vendor",
            "action": "REQUIRE_HUMAN_APPROVAL",
            "description": "Scrutinize VIP invoices",
        },
    )
    assert add_res.status_code == 200
    assert add_res.json()["status"] == "success"


def test_vendor_blacklist_and_whitelist_flow(client: TestClient):
    """Test blacklisting, listing vendors, and whitelisting."""
    # 1. Blacklist a vendor via status endpoint
    bl_res = client.post(
        "/api/vendors/ShadyCorp/status",
        json={"status": "blacklisted", "reason": "Known phishing entity"},
    )
    assert bl_res.status_code == 200
    assert bl_res.json()["status"] == "blacklisted"

    # 2. Verify in vendors list
    v_list = client.get("/api/vendors")
    assert v_list.status_code == 200
    vendors = v_list.json()
    shady = next((v for v in vendors if v["vendor_name"].lower() == "shadycorp"), None)
    assert shady is not None
    assert shady["status"] == "blacklisted"

    # 3. Whitelist the vendor
    wl_res = client.post(
        "/api/vendors/ShadyCorp/status",
        json={"status": "whitelisted", "reason": "Audited and verified"},
    )
    assert wl_res.status_code == 200
    assert wl_res.json()["status"] == "whitelisted"


def test_reject_and_block_invoice(client: TestClient):
    """Test reject-and-block convenience endpoint blocks payment and blacklists vendor."""
    # Ingest an invoice to reject and block
    with open("tests/fixtures/invoice_text_2.txt", "rb") as f:
        upload_res = client.post(
            "/api/invoices/upload",
            files={"files": ("invoice_text_2.txt", f, "text/plain")},
        )
    assert upload_res.status_code == 200
    inv_id = upload_res.json()["results"][0]["invoice_id"]
    vendor = upload_res.json()["results"][0]["vendor"]

    # Reject and block
    block_res = client.post(
        f"/api/invoices/{inv_id}/reject-and-block",
        json={"reviewer": "VP of Finance", "reason": "Fraudulent billing detected"},
    )
    assert block_res.status_code == 200
    assert block_res.json()["status"] == "rejected"
    assert block_res.json()["vendor_blacklisted"] is True

    # Check vendor status in registry
    v_res = client.get("/api/vendors")
    assert v_res.status_code == 200
    v_entry = next((v for v in v_res.json() if v["vendor_name"].lower() == vendor.lower()), None)
    assert v_entry is not None
    assert v_entry["status"] == "blacklisted"


def test_get_original_invoice_endpoints(client: TestClient):
    """Test retrieving original invoice document and preview metadata."""
    with open("tests/fixtures/invoice_json_1.json", "rb") as f:
        upload_res = client.post(
            "/api/invoices/upload",
            files=[("files", ("invoice_json_1.json", f, "application/json"))],
        )
    assert upload_res.status_code == 200
    inv_id = upload_res.json()["results"][0]["invoice_id"]

    # 1. Test preview endpoint
    prev_res = client.get(f"/api/invoices/{inv_id}/original-preview")
    assert prev_res.status_code == 200
    pdata = prev_res.json()
    assert pdata["invoice_id"] == inv_id
    assert pdata["filename"] is not None
    assert pdata["content"] is not None
    assert pdata["is_binary"] is False
    assert f"/api/invoices/{inv_id}/original" in pdata["view_url"]

    # 2. Test original file retrieval (inline)
    orig_res = client.get(f"/api/invoices/{inv_id}/original")
    assert orig_res.status_code == 200
    assert "inline" in orig_res.headers.get("content-disposition", "")

    # 3. Test original file download
    dl_res = client.get(f"/api/invoices/{inv_id}/original?download=true")
    assert dl_res.status_code == 200
    assert "attachment" in dl_res.headers.get("content-disposition", "")


