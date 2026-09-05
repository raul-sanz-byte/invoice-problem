"""CLI entry point for the invoice ingestion pipeline.

Usage:
    python main.py ingest <file_or_dir>   Process invoice file(s)
    python main.py list                    List all ingested invoices
    python main.py show <invoice_id>       Show invoice details
    python main.py products               List products in catalog
    python main.py revisions <invoice_id>  Show revision history
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import click

# Load .env file if present
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _get_pipeline(db_path: str = "invoices.db"):
    """Create pipeline instance with optional resilient LLM client."""
    from invoice_pipeline.pipeline import InvoicePipeline
    from invoice_pipeline.llm_client import LLMClient

    llm_client = None
    try:
        llm_client = LLMClient()
    except Exception as e:
        logging.getLogger(__name__).warning("Could not initialize LLMClient: %s", e)

    return InvoicePipeline(llm_client=llm_client, db_path=db_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.option("--db", default="invoices.db", help="Database file path")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, db: str) -> None:
    """Invoice Ingestion Pipeline — Process, validate, and store invoices."""
    _setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db


@cli.command()
@click.argument("path")
@click.pass_context
def ingest(ctx: click.Context, path: str) -> None:
    """Ingest invoice file(s). PATH can be a file or directory."""
    pipeline = _get_pipeline(ctx.obj["db_path"])

    try:
        target = Path(path)
        if not target.exists():
            click.secho(f"Error: '{path}' does not exist", fg="red")
            sys.exit(1)

        if target.is_dir():
            results = pipeline.process_directory(target)
        else:
            results = [pipeline.process_file(target)]

        # Print results
        click.echo()
        click.secho(
            f"{'='*60}", fg="blue"
        )
        click.secho(
            f"  Processed {len(results)} file(s)", fg="blue", bold=True
        )
        click.secho(
            f"{'='*60}", fg="blue"
        )

        for r in results:
            click.echo()
            status_color = "green" if r.success else "red"
            status_icon = "[OK]" if r.success else "[FAIL]"
            click.secho(
                f"  {status_icon} {r.source_file} [{r.format_detected.value}]",
                fg=status_color,
            )

            if r.invoice:
                inv = r.invoice
                click.echo(f"    Invoice ID:  {inv.invoice_id}")
                click.echo(f"    Vendor:      {inv.vendor.name}")
                click.echo(f"    Date:        {inv.date}")
                click.echo(f"    Due Date:    {inv.due_date}")
                click.echo(f"    Subtotal:    {inv.currency} {inv.subtotal if inv.subtotal is not None else 'N/A'}")
                if inv.tax_amount is not None or inv.tax_rate is not None:
                    rate_pct = f" ({float(inv.tax_rate)*100:.1f}%)" if inv.tax_rate is not None else ""
                    click.echo(f"    Tax{rate_pct}:   {inv.currency} {inv.tax_amount if inv.tax_amount is not None else 'N/A'}")
                click.echo(f"    Total:       {inv.currency} {inv.total}")
                if inv.notes:
                    click.echo(f"    Notes:       {inv.notes}")
                if inv.revision:
                    click.secho(f"    Revision:    {inv.revision}", fg="yellow")

                # Show extracted line item entries
                click.echo(f"    Extracted Entries ({len(inv.line_items)}):")
                products = pipeline.database.get_products() if hasattr(pipeline, "database") and pipeline.database else []
                catalog_by_name = {p["name"].lower().strip().replace(" ", "").replace("-", "_"): p for p in products}
                for li in inv.line_items:
                    amt = f" | Amount: {inv.currency} {li.amount}" if li.amount is not None else ""
                    item_note = f" [Note: {li.note}]" if li.note else ""
                    prod = catalog_by_name.get(li.item.lower().strip().replace(" ", "").replace("-", "_"))
                    if prod:
                        stock = prod.get("quantity_in_stock", 0)
                        if stock == 0:
                            cat_status = click.style(f" -> DB: Exists (PROD ID: {prod.get('product_id')}, Stock: 0 - FRAUD/OUT-OF-STOCK FLAG)", fg="red")
                        else:
                            cat_status = click.style(f" -> DB: Exists (PROD ID: {prod.get('product_id')}, Stock: {stock})", fg="green")
                    else:
                        cat_status = click.style(f" -> DB: NOT FOUND in catalog", fg="yellow")
                    click.echo(f"      - {li.item}: Qty {li.quantity} @ {inv.currency} {li.unit_price}{amt}{item_note} | {cat_status}")

                click.echo(f"    Latency:     {r.processing_time_ms:.1f} ms [{r.extraction_method}]")

            # Calculation verification status
            if r.self_corrected:
                click.secho(
                    f"    [*] Calculations / fields corrected by self-correction loop ({r.correction_attempts} round(s)):",
                    fg="cyan",
                )
                for note in r.correction_notes:
                    click.secho(f"        -> {note}", fg="cyan")
            elif r.validation and r.validation.arithmetic_correct:
                click.secho("    [OK] Calculations: Verified 100% correct", fg="green")
            elif r.validation and not r.validation.arithmetic_correct:
                click.secho("    [!] Calculations: Arithmetic errors detected", fg="red", bold=True)

            # Fraud and anomaly reporting
            if r.validation and r.validation.is_suspicious:
                click.secho(
                    "    [!] FRAUD / SUSPICIOUS INVOICE DETECTED", fg="red", bold=True
                )
                for reason in r.validation.suspicion_reasons:
                    click.secho(f"       -> {reason}", fg="red")

            # VP Review & Executive Payment reporting
            if r.review:
                rev = r.review
                click.echo()
                if rev.decision.value == "auto_approved":
                    click.secho("    [VP REVIEW] AUTO-APPROVED (Under $10K, zero fraud flags, verified inventory)", fg="green", bold=True)
                elif rev.decision.value == "requires_human_approval":
                    click.secho("    [VP REVIEW] REQUIRES HUMAN / VP APPROVAL", fg="yellow", bold=True)
                else:
                    click.secho("    [VP REVIEW] REJECTED", fg="red", bold=True)

                if rev.rules_triggered:
                    for rule in rev.rules_triggered:
                        click.secho(f"       -> [Rule Triggered] {rule}", fg="yellow")

                if rev.critique:
                    short_critique = rev.critique if len(rev.critique) < 180 else rev.critique[:180] + "..."
                    click.echo(f"       -> [Reflection Critique] {short_critique}")

                if rev.payment_status.value == "paid":
                    if getattr(rev, "is_revision", False) and rev.amount_to_pay and rev.amount_to_pay < inv.total:
                        click.secho(f"    [PAYMENT] EXECUTED: Paid {inv.currency} {rev.amount_to_pay} to {inv.vendor.name} (Delta for additional items; full total {inv.currency} {inv.total})", fg="green", bold=True)
                    else:
                        click.secho(f"    [PAYMENT] EXECUTED: Paid {inv.currency} {inv.total} to {inv.vendor.name}", fg="green", bold=True)
                elif rev.payment_status.value == "pending_approval":
                    click.secho(f"    [PAYMENT] HELD: Pending human executive approval (no funds disbursed)", fg="yellow", bold=True)
                elif rev.payment_status.value == "rejected":
                    click.secho("    [PAYMENT] BLOCKED: Invoice rejected", fg="red", bold=True)

            if r.warnings:
                for w in r.warnings:
                    click.secho(f"    [!] {w}", fg="yellow")

            if r.errors:
                for e in r.errors:
                    click.secho(f"    [x] {e}", fg="red")

        click.echo()
        success_count = sum(1 for r in results if r.success)
        suspicious_count = sum(
            1 for r in results if r.validation and r.validation.is_suspicious
        )
        arith_error_count = sum(
            1
            for r in results
            if r.validation and not r.validation.arithmetic_correct
        )
        total_time_ms = sum(r.processing_time_ms for r in results)

        click.secho(f"  Summary:", bold=True)
        click.echo(f"    Successful:       {success_count}/{len(results)}")
        click.echo(f"    Total Latency:    {total_time_ms:.1f} ms (avg {total_time_ms/len(results):.1f} ms/file)" if results else "")
        if suspicious_count:
            click.secho(
                f"    Suspicious:       {suspicious_count}", fg="red"
            )
        if arith_error_count:
            click.secho(
                f"    Arithmetic Errors: {arith_error_count}", fg="red"
            )
        click.echo()

    finally:
        pipeline.close()


@cli.command("list")
@click.pass_context
def list_invoices(ctx: click.Context) -> None:
    """List all ingested invoices."""
    from invoice_pipeline.storage.database import InvoiceDatabase

    db = InvoiceDatabase(ctx.obj["db_path"])
    try:
        invoices = db.get_all_invoices()
        if not invoices:
            click.echo("No invoices found in database.")
            return

        # Table header
        click.echo()
        click.secho(
            f"{'ID':<15} {'Vendor':<25} {'Date':<12} {'Total':>12} {'Currency':<5} {'Suspicious':<12}",
            bold=True,
        )
        click.echo("-" * 85)

        for inv in invoices:
            suspicious = "[SUSPICIOUS]" if inv.get("is_suspicious") else ""
            click.echo(
                f"{inv.get('invoice_id', '?'):<15} "
                f"{inv.get('vendor_name', '?'):<25} "
                f"{inv.get('date', '?'):<12} "
                f"{inv.get('total', 0):>12.2f} "
                f"{inv.get('currency', 'USD'):<5} "
                f"{suspicious:<12}"
            )

        click.echo(f"\nTotal: {len(invoices)} invoice(s)")
    finally:
        db.close()


@cli.command()
@click.argument("invoice_id")
@click.pass_context
def show(ctx: click.Context, invoice_id: str) -> None:
    """Show detailed information for a specific invoice."""
    from invoice_pipeline.storage.database import InvoiceDatabase

    db = InvoiceDatabase(ctx.obj["db_path"])
    try:
        inv = db.get_invoice(invoice_id)
        if not inv:
            click.secho(f"Invoice '{invoice_id}' not found.", fg="red")
            return

        click.echo()
        click.secho(f"  Invoice: {inv['invoice_id']}", bold=True, fg="blue")
        if inv.get("revision"):
            click.secho(f"  Revision: {inv['revision']}", fg="yellow")
        click.echo(f"  Vendor:       {inv['vendor_name']}")
        if inv.get("vendor_address"):
            click.echo(f"  Address:      {inv['vendor_address']}")
        click.echo(f"  Date:         {inv['date']}")
        click.echo(f"  Due Date:     {inv['due_date']}")
        click.echo(f"  Currency:     {inv.get('currency', 'USD')}")
        if inv.get("payment_terms"):
            click.echo(f"  Terms:        {inv['payment_terms']}")
        click.echo()

        # Line items
        click.secho("  Line Items:", bold=True)
        click.echo(
            f"    {'Item':<20} {'Qty':>6} {'Unit Price':>12} {'Amount':>12} {'Note':<20}"
        )
        click.echo(f"    {'-'*70}")
        for li in inv.get("line_items", []):
            note = li.get("note") or ""
            click.echo(
                f"    {li['item']:<20} {li['quantity']:>6.0f} "
                f"{li['unit_price']:>12.2f} {li.get('amount', 0):>12.2f} {note:<20}"
            )

        click.echo()
        if inv.get("subtotal") is not None:
            click.echo(f"  Subtotal:     {inv['subtotal']:>12.2f}")
        if inv.get("tax_rate") is not None:
            click.echo(
                f"  Tax ({inv['tax_rate']*100:.1f}%):   {inv.get('tax_amount', 0):>12.2f}"
            )
        if inv.get("shipping") is not None:
            click.echo(f"  Shipping:     {inv['shipping']:>12.2f}")
        click.secho(f"  Total:        {inv['total']:>12.2f}", bold=True)

        if inv.get("notes"):
            click.echo(f"\n  Notes: {inv['notes']}")

        if not inv.get("arithmetic_correct", 1):
            click.echo()
            click.secho("  [!] ARITHMETIC ERRORS DETECTED", fg="red", bold=True)

        review = db.get_invoice_review(invoice_id)
        if review:
            click.echo()
            click.secho("  Executive Review & Governance Audit:", bold=True, fg="cyan")
            click.echo(f"    Decision:       {review['decision'].upper()}")
            click.echo(f"    Human Status:   {review['human_approval_status'].upper()}")
            if review.get("human_reviewer"):
                click.echo(f"    Reviewer:       {review['human_reviewer']} ({review.get('human_notes', '')})")
            click.echo(f"    Payment Status: {review['payment_status'].upper()}")
            if review.get("rules_triggered"):
                click.echo("    Triggered Rules:")
                for rule_text in review["rules_triggered"]:
                    click.echo(f"      - {rule_text}")
            if review.get("critique"):
                click.echo(f"    VP Reflection:  {review['critique']}")

        click.echo()
    finally:
        db.close()


@cli.command()
@click.pass_context
def products(ctx: click.Context) -> None:
    """List all products in the catalog."""
    from invoice_pipeline.storage.database import InvoiceDatabase

    db = InvoiceDatabase(ctx.obj["db_path"])
    try:
        prods = db.get_products()
        if not prods:
            click.echo("No products in catalog.")
            return

        click.echo()
        click.secho(
            f"{'ID':<12} {'Name':<20} {'Price':>10} {'Currency':<5} {'Stock':>8} {'Category':<15}",
            bold=True,
        )
        click.echo("-" * 75)

        for p in prods:
            click.echo(
                f"{p['product_id']:<12} "
                f"{p['name']:<20} "
                f"{p['standard_price']:>10.2f} "
                f"{p.get('currency', 'USD'):<5} "
                f"{p.get('quantity_in_stock', 0):>8} "
                f"{p.get('category', ''):<15}"
            )

        click.echo(f"\nTotal: {len(prods)} product(s)")
    finally:
        db.close()


@cli.command()
@click.argument("invoice_id")
@click.pass_context
def revisions(ctx: click.Context, invoice_id: str) -> None:
    """Show revision history for an invoice."""
    from invoice_pipeline.storage.database import InvoiceDatabase

    db = InvoiceDatabase(ctx.obj["db_path"])
    try:
        revs = db.get_revisions(invoice_id)
        if not revs:
            click.echo(f"No revision history for '{invoice_id}'.")
            return

        click.echo()
        click.secho(
            f"  Revision history for {invoice_id}", bold=True, fg="blue"
        )
        for rev in revs:
            click.echo()
            click.echo(f"  Revision: {rev.get('revision', 'Original')}")
            click.echo(f"  Changed at: {rev.get('changed_at', '?')}")
            if rev.get("change_summary"):
                click.echo(f"  Summary: {rev['change_summary']}")
        click.echo()
    finally:
        db.close()


@cli.command()
@click.pass_context
def vocabulary(ctx: click.Context) -> None:
    """Show field vocabulary (aliases mapped to canonical fields)."""
    from invoice_pipeline.extraction.vocabulary import get_vocabulary_manager

    mgr = get_vocabulary_manager(ctx.obj["db_path"])
    click.echo()
    click.secho("  Active Field Vocabulary (Aliases -> Canonical Fields):", bold=True, fg="blue")
    click.echo("  " + "-" * 60)

    # Group by canonical field
    grouped: dict[str, list[str]] = {}
    for alias, canonical in sorted(mgr._aliases.items()):
        if alias != canonical:
            grouped.setdefault(canonical, []).append(alias)

    for canonical, aliases in sorted(grouped.items()):
        click.echo(f"  {canonical:<15} : {', '.join(sorted(set(aliases))[:8])}")

    click.echo()
    click.secho("  Line Item Sub-field Vocabulary:", bold=True, fg="blue")
    click.echo("  " + "-" * 60)
    li_grouped: dict[str, list[str]] = {}
    for alias, canonical in sorted(mgr._line_item_aliases.items()):
        if alias != canonical:
            li_grouped.setdefault(canonical, []).append(alias)

    for canonical, aliases in sorted(li_grouped.items()):
        click.echo(f"  {canonical:<15} : {', '.join(sorted(set(aliases))[:8])}")
    click.echo()


@cli.command("metrics")
@click.pass_context
def show_metrics(ctx: click.Context) -> None:
    """Show operational metrics and telemetry dashboard."""
    from invoice_pipeline.storage.database import InvoiceDatabase

    db = InvoiceDatabase(ctx.obj["db_path"])
    try:
        metrics = db.get_ingestion_metrics()
        click.echo()
        click.secho("  Pipeline Telemetry & Observability Metrics", bold=True, fg="blue")
        click.echo("  " + "=" * 55)
        click.echo(f"  Total Ingested:        {metrics['total_ingested']}")
        click.echo(f"  Successful:            {metrics['successful']}")
        click.echo(f"  Failed:                {metrics['failed']}")
        click.echo(f"  Success Rate:          {metrics['success_rate_pct']}%")
        click.echo(f"  Average Latency:       {metrics['avg_latency_ms']} ms")
        click.echo(f"  Self-Corrected:        {metrics.get('self_corrected_invoices', 0)}")
        click.echo(f"  Suspicious Invoices:   {metrics['suspicious_invoices']}")
        click.echo(f"  Arithmetic Errors:     {metrics['arithmetic_errors']}")
        click.echo()
        click.secho("  Format Distribution:", bold=True)
        for fmt, count in metrics["formats"].items():
            click.echo(f"    {fmt:<15}: {count}")
        click.echo()
        click.secho("  Extraction Methods:", bold=True)
        for method, count in metrics["extraction_methods"].items():
            click.echo(f"    {method:<30}: {count}")
        click.echo()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Human in the Loop (HITL) Commands
# ---------------------------------------------------------------------------


@cli.command("queue")
@click.pass_context
def show_queue(ctx: click.Context) -> None:
    """List all invoices currently pending human executive approval."""
    from invoice_pipeline.storage.database import InvoiceDatabase

    db = InvoiceDatabase(ctx.obj["db_path"])
    try:
        pending = db.get_pending_approvals()
        if not pending:
            click.echo()
            click.secho("  No invoices currently pending human approval. All clear!", fg="green")
            click.echo()
            return

        click.echo()
        click.secho(f"  Pending Human Approval Queue ({len(pending)} invoice(s)):", bold=True, fg="yellow")
        click.echo("  " + "=" * 80)
        click.echo(f"  {'Invoice ID':<15} {'Vendor':<25} {'Total':>12} {'Date':<12} {'Triggered Reason'}")
        click.echo("  " + "-" * 80)

        for item in pending:
            inv_id = item.get("invoice_id", "?")
            vendor = item.get("vendor_name", "?")
            total = f"{item.get('currency', 'USD')} {item.get('total', 0):,.2f}"
            inv_date = item.get("date", "?")
            rules = item.get("rules_triggered", [])
            reason = rules[0] if rules else "Held for scrutiny"
            if len(reason) > 35:
                reason = reason[:32] + "..."
            click.echo(f"  {inv_id:<15} {vendor:<25} {total:>12} {inv_date:<12} {reason}")

        click.echo()
        click.echo("  To approve an invoice: python main.py approve <INVOICE_ID>")
        click.echo("  To reject an invoice:  python main.py reject <INVOICE_ID>")
        click.echo()
    finally:
        db.close()


@cli.command("approve")
@click.argument("invoice_id")
@click.option("--reviewer", default="VP of Finance", help="Reviewer name")
@click.option("--notes", default="Approved after executive review", help="Approval notes")
@click.pass_context
def approve_invoice(ctx: click.Context, invoice_id: str, reviewer: str, notes: str) -> None:
    """Approve a pending invoice and execute payment."""
    from invoice_pipeline.payment.service import mock_payment
    from invoice_pipeline.storage.database import InvoiceDatabase

    db = InvoiceDatabase(ctx.obj["db_path"])
    try:
        inv = db.get_invoice(invoice_id)
        if not inv:
            click.secho(f"Error: Invoice '{invoice_id}' not found.", fg="red")
            return

        review = db.get_invoice_review(invoice_id)
        if not review or review.get("human_approval_status") != "pending":
            click.secho(
                f"Invoice '{invoice_id}' is not in 'pending' human approval status.",
                fg="yellow",
            )
            return

        click.echo()
        click.secho(f"  Approving Invoice {invoice_id}...", fg="cyan")
        pay_amount = inv["total"]
        if review.get("amount_to_pay"):
            try:
                pay_amount = float(review["amount_to_pay"])
            except (ValueError, TypeError):
                pass
        payment_result = mock_payment(inv["vendor_name"], pay_amount)
        success = db.update_human_approval(
            invoice_id=invoice_id,
            approved=True,
            reviewer=reviewer,
            notes=notes,
            payment_details=payment_result,
        )
        if success:
            click.secho(
                f"  [APPROVED & PAID] Invoice {invoice_id} successfully approved by {reviewer}.",
                fg="green",
                bold=True,
            )
            click.echo(f"  Notes: {notes}\n")
        else:
            click.secho(f"  Failed to update review record in database.", fg="red")
    finally:
        db.close()


@cli.command("reject")
@click.argument("invoice_id")
@click.option("--reviewer", default="VP of Finance", help="Reviewer name")
@click.option("--reason", default="Rejected during executive review", help="Rejection reason")
@click.pass_context
def reject_invoice(ctx: click.Context, invoice_id: str, reviewer: str, reason: str) -> None:
    """Reject a pending invoice and block payment."""
    from invoice_pipeline.storage.database import InvoiceDatabase

    db = InvoiceDatabase(ctx.obj["db_path"])
    try:
        success = db.update_human_approval(
            invoice_id=invoice_id,
            approved=False,
            reviewer=reviewer,
            notes=reason,
            payment_details={"status": "rejected", "reason": reason},
        )
        if success:
            click.echo()
            click.secho(
                f"  [REJECTED] Invoice {invoice_id} rejected by {reviewer}. Payment permanently blocked.",
                fg="red",
                bold=True,
            )
            click.echo(f"  Reason: {reason}\n")
        else:
            click.secho(
                f"Invoice '{invoice_id}' was not in 'pending' status or not found.",
                fg="yellow",
            )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Dynamic Business Rules Management CLI
# ---------------------------------------------------------------------------


@cli.group("rules")
def rules_group() -> None:
    """Manage dynamic business decision rules stored in SQLite."""
    pass


@rules_group.command("list")
@click.pass_context
def list_rules(ctx: click.Context) -> None:
    """List all active business rules from the database."""
    from invoice_pipeline.storage.database import InvoiceDatabase

    db = InvoiceDatabase(ctx.obj["db_path"])
    try:
        rules = db.get_active_rules()
        click.echo()
        click.secho(f"  Active Business Decision Rules ({len(rules)} total):", bold=True, fg="blue")
        click.echo("  " + "=" * 95)
        click.echo(f"  {'Rule Name':<25} {'Condition Type':<20} {'Condition Value':<18} {'Action'}")
        click.echo("  " + "-" * 95)
        for r in rules:
            click.echo(
                f"  {r['name']:<25} {r['condition_type']:<20} {r['condition_value']:<18} {r['action']}"
            )
            if r.get("description"):
                click.echo(f"    -> {r['description']}")
        click.echo()
    finally:
        db.close()


@rules_group.command("add")
@click.option("--name", required=True, help="Unique rule name (e.g. VIP_VENDOR_CAP)")
@click.option("--condition", "condition_type", required=True, help="Condition type (e.g. amount_gt, vendor_pattern)")
@click.option("--value", "condition_value", required=True, help="Condition value (e.g. 5000, Acme)")
@click.option("--action", default="REQUIRE_HUMAN_APPROVAL", help="Action when triggered")
@click.option("--description", default="", help="Rule description")
@click.pass_context
def add_rule(ctx: click.Context, name: str, condition_type: str, condition_value: str, action: str, description: str) -> None:
    """Add a new business decision rule to the SQLite database."""
    from invoice_pipeline.storage.database import InvoiceDatabase

    db = InvoiceDatabase(ctx.obj["db_path"])
    try:
        rule_id = db.add_rule(
            name=name,
            condition_type=condition_type,
            condition_value=condition_value,
            action=action,
            description=description,
        )
        click.echo()
        click.secho(f"  [OK] Successfully added business rule '{name}' (ID: {rule_id}) to database.", fg="green", bold=True)
        click.echo(f"  Condition: {condition_type} = {condition_value} -> {action}\n")
    except Exception as e:
        click.secho(f"  Error adding rule: {e}", fg="red")
    finally:
        db.close()


@cli.command("serve")
@click.option("--host", default="0.0.0.0", help="Host address to bind")
@click.option("--port", default=8000, type=int, help="Port to listen on")
@click.option("--reload/--no-reload", default=True, help="Enable auto-reload on code change (defaults to enabled)")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int, reload: bool) -> None:
    """Start the FastAPI backend server."""
    import uvicorn

    os.environ["INVOICE_DB_PATH"] = ctx.obj["db_path"]
    click.secho(f"Starting Invoice Pipeline FastAPI server on http://{host}:{port}", fg="green", bold=True)
    click.secho(f"API Docs available at: http://localhost:{port}/docs", fg="cyan")
    uvicorn.run("invoice_pipeline.server:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    cli()

