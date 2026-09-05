import sqlite3
from pathlib import Path
from datetime import date
from decimal import Decimal
import json
import logging
from typing import Any

from invoice_pipeline.models import Invoice, IngestionResult, Product

logger = logging.getLogger(__name__)


def are_line_items_identical(items_a: list, items_b: list) -> bool:
    """Check if two sets of line items match 100% in item name, quantity, and unit price."""
    if len(items_a) != len(items_b):
        return False

    def _key(x):
        name = str(x.get("item") if isinstance(x, dict) else getattr(x, "item", "")).strip().lower()
        qty = float(x.get("quantity") if isinstance(x, dict) else getattr(x, "quantity", 0))
        price = float(x.get("unit_price") if isinstance(x, dict) else getattr(x, "unit_price", 0))
        return (name, round(qty, 4), round(price, 4))

    return sorted([_key(x) for x in items_a]) == sorted([_key(x) for x in items_b])


class InvoiceDatabase:
    def __init__(self, db_path: str | Path = 'invoices.db'):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self._init_tables(self.conn)
        if self._is_products_empty(self.conn):
            self._seed_products(self.conn)
        if self._is_rules_empty(self.conn):
            self._seed_rules(self.conn)

    def __enter__(self):
        if not self.conn:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self) -> None:
        if self.conn:
            try:
                self.conn.commit()
            except Exception:
                pass
            self.conn.close()
            self.conn = None

    def _init_tables(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            standard_price REAL NOT NULL,
            currency TEXT DEFAULT 'USD',
            quantity_in_stock INTEGER DEFAULT 0,
            category TEXT
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id TEXT NOT NULL,
            revision TEXT,
            date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            vendor_name TEXT NOT NULL,
            vendor_address TEXT,
            subtotal REAL,
            tax_rate REAL,
            tax_amount REAL,
            total REAL NOT NULL,
            currency TEXT DEFAULT 'USD',
            payment_terms TEXT,
            payment_terms_days INTEGER,
            shipping REAL,
            notes TEXT,
            source_file TEXT,
            format_detected TEXT,
            is_suspicious INTEGER DEFAULT 0,
            suspicion_reasons TEXT,
            arithmetic_correct INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(invoice_id, revision)
        );

        CREATE TABLE IF NOT EXISTS line_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_db_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit_price REAL NOT NULL,
            amount REAL,
            note TEXT,
            FOREIGN KEY (invoice_db_id) REFERENCES invoices(id)
        );

        CREATE TABLE IF NOT EXISTS invoice_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id TEXT NOT NULL,
            revision TEXT,
            previous_data TEXT NOT NULL,
            new_data TEXT NOT NULL,
            changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            change_summary TEXT
        );

        CREATE TABLE IF NOT EXISTS ingestion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            format_detected TEXT,
            success INTEGER NOT NULL,
            errors TEXT,
            warnings TEXT,
            extraction_method TEXT,
            processing_time_ms REAL DEFAULT 0.0,
            self_corrected INTEGER DEFAULT 0,
            correction_attempts INTEGER DEFAULT 0,
            processed_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS field_vocabulary (
            raw_alias TEXT PRIMARY KEY,
            canonical_field TEXT NOT NULL,
            is_line_item INTEGER DEFAULT 0,
            learned_from TEXT DEFAULT 'llm',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS business_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            condition_type TEXT NOT NULL,
            condition_value TEXT NOT NULL,
            action TEXT NOT NULL DEFAULT 'REQUIRE_HUMAN_APPROVAL',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS invoice_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            rules_triggered TEXT NOT NULL,
            initial_reasoning TEXT NOT NULL,
            critique TEXT NOT NULL,
            final_reasoning TEXT NOT NULL,
            requires_human INTEGER NOT NULL,
            human_approval_status TEXT NOT NULL,
            human_reviewer TEXT,
            human_notes TEXT,
            payment_status TEXT NOT NULL,
            payment_details TEXT,
            reviewed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS vendor_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_name TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'standard',
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()

        # Ensure migration columns exist on older tables
        for col, col_type in [
            ("extraction_method", "TEXT"),
            ("processing_time_ms", "REAL DEFAULT 0.0"),
            ("self_corrected", "INTEGER DEFAULT 0"),
            ("correction_attempts", "INTEGER DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE ingestion_log ADD COLUMN {col} {col_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass

        for col, col_type in [
            ("rule_type", "TEXT DEFAULT 'deterministic_query'"),
            ("sql_query", "TEXT"),
            ("llm_prompt", "TEXT"),
            ("is_system", "INTEGER DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE business_rules ADD COLUMN {col} {col_type}")
                conn.commit()
            except sqlite3.OperationalError:
                pass

    def _is_products_empty(self, conn: sqlite3.Connection) -> bool:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM products")
        return cursor.fetchone()[0] == 0

    def _is_rules_empty(self, conn: sqlite3.Connection) -> bool:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM business_rules WHERE sql_query IS NOT NULL")
        return cursor.fetchone()[0] == 0

    def _seed_rules(self, conn: sqlite3.Connection):
        system_rules = [
            (
                "AMOUNT_OVER_10K",
                "Invoices over $10,000 threshold require executive review",
                "deterministic_query",
                "total > 10000.00",
                "amount_gt",
                "10000.00",
                None,
                "REQUIRE_HUMAN_APPROVAL",
                1,
                1,
            ),
            (
                "SUSPICIOUS_STRUCTURING",
                "Invoices structured between $9,000 and $9,999.99 to bypass VP approval",
                "deterministic_query",
                "total >= 9000.00 AND total < 10000.00",
                "amount_range",
                "9000.00:9999.99",
                None,
                "REQUIRE_HUMAN_APPROVAL",
                1,
                1,
            ),
            (
                "BLACKLISTED_VENDOR",
                "Invoices from vendors registered on the compliance blacklist",
                "deterministic_query",
                "EXISTS (SELECT 1 FROM vendor_registry vr WHERE LOWER(vr.vendor_name) = LOWER(invoices.vendor_name) AND vr.status = 'blacklisted')",
                "vendor_blacklist",
                "blacklisted",
                None,
                "REJECT",
                1,
                1,
            ),
            (
                "STOCK_MISMATCH",
                "Line items where requested quantity exceeds warehouse stock",
                "deterministic_query",
                "EXISTS (SELECT 1 FROM line_items li JOIN products p ON LOWER(REPLACE(REPLACE(REPLACE(li.item, ' ', ''), '-', '_'), '.', '')) = LOWER(REPLACE(REPLACE(REPLACE(p.name, ' ', ''), '-', '_'), '.', '')) WHERE li.invoice_db_id = invoices.id AND (p.quantity_in_stock < li.quantity OR p.quantity_in_stock = 0))",
                "stock_check",
                "mismatch",
                None,
                "REQUIRE_HUMAN_APPROVAL",
                1,
                1,
            ),
            (
                "UNKNOWN_ITEMS",
                "Line items not matched to any registered product catalog item",
                "deterministic_query",
                "EXISTS (SELECT 1 FROM line_items li WHERE li.invoice_db_id = invoices.id AND NOT EXISTS (SELECT 1 FROM products p WHERE LOWER(REPLACE(REPLACE(REPLACE(li.item, ' ', ''), '-', '_'), '.', '')) = LOWER(REPLACE(REPLACE(REPLACE(p.name, ' ', ''), '-', '_'), '.', ''))))",
                "catalog_check",
                "unknown",
                None,
                "REQUIRE_HUMAN_APPROVAL",
                1,
                1,
            ),
            (
                "ARITHMETIC_ERROR",
                "Discrepancies in line item arithmetic or subtotal + tax + shipping summation",
                "deterministic_query",
                "arithmetic_correct = 0",
                "math_check",
                "0",
                None,
                "REQUIRE_HUMAN_APPROVAL",
                1,
                1,
            ),
            (
                "DATE_ANOMALY",
                "Invoices dated on weekends (Saturday/Sunday)",
                "deterministic_query",
                "strftime('%w', date) IN ('0', '6')",
                "date_anomaly",
                "weekend",
                None,
                "REQUIRE_HUMAN_APPROVAL",
                1,
                1,
            ),
            (
                "EXACT_DUPLICATE",
                "Identical invoice submitted multiple times (same vendor, total, and date)",
                "deterministic_query",
                "EXISTS (SELECT 1 FROM invoices prev WHERE prev.id != invoices.id AND LOWER(prev.vendor_name) = LOWER(invoices.vendor_name) AND prev.total = invoices.total AND prev.date = invoices.date)",
                "duplicate_check",
                "1",
                None,
                "REQUIRE_HUMAN_APPROVAL",
                1,
                1,
            ),
            (
                "UNBUNDLED_BILLING",
                "Multiple invoices from same vendor within 7 days exceeding $10,000 threshold",
                "deterministic_query",
                "(SELECT COALESCE(SUM(prev.total), 0) FROM invoices prev WHERE prev.id != invoices.id AND LOWER(prev.vendor_name) = LOWER(invoices.vendor_name) AND abs(julianday(prev.date) - julianday(invoices.date)) <= 7) + total > 10000.00 AND total <= 10000.00",
                "unbundled_check",
                "7d_10k",
                None,
                "REQUIRE_HUMAN_APPROVAL",
                1,
                1,
            ),
            (
                "SEQUENTIAL_INVOICE_GAP",
                "Invoices with sequential numbers but separated by 20+ day gaps (shell company flag)",
                "deterministic_query",
                "EXISTS (SELECT 1 FROM invoices prev WHERE prev.id != invoices.id AND LOWER(prev.vendor_name) = LOWER(invoices.vendor_name) AND abs(julianday(prev.date) - julianday(invoices.date)) >= 20)",
                "gap_check",
                "20d",
                None,
                "REQUIRE_HUMAN_APPROVAL",
                1,
                1,
            ),
            (
                "SUSPICIOUS_OR_FRAUD",
                "Invoices flagged with heuristic anomaly reasons, pressure phrases, or suspicious patterns",
                "llm_eval",
                "is_suspicious = 1",
                "fraud_check",
                "1",
                "Assess if the invoice exhibits signs of fraudulent manipulation, urgent pressure language, unusual remittance/routing instructions, or shell company indicators.",
                "REQUIRE_HUMAN_APPROVAL",
                1,
                1,
            ),
        ]
        conn.cursor().executemany(
            """INSERT OR REPLACE INTO business_rules 
               (name, description, rule_type, sql_query, condition_type, condition_value, llm_prompt, action, is_active, is_system)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            system_rules,
        )
        conn.commit()

    def _seed_products(self, conn: sqlite3.Connection):
        products = [
            ("PROD-001", "WidgetA", 250.00, "USD", 500, "Widgets"),
            ("PROD-002", "WidgetB", 500.00, "USD", 300, "Widgets"),
            ("PROD-003", "GadgetX", 750.00, "USD", 5, "Gadgets"),      # 5 in stock -> 20x triggers stock mismatch
            ("PROD-005", "NanoBolt", 15.00, "USD", 10000, "Fasteners"),
            ("PROD-006", "TurboValve", 320.00, "USD", 75, "Valves"),
            ("PROD-007", "FlexCoupling", 180.00, "EUR", 250, "Couplings"),
            ("PROD-008", "PowerUnit", 1200.00, "USD", 50, "Power"),
            ("PROD-009", "EchoSensor", 95.00, "USD", 150, "Sensors"),
            ("PROD-010", "AlphaAdapter", 45.00, "USD", 500, "Adapters"),
        ]
        conn.cursor().executemany(
            "INSERT INTO products (product_id, name, standard_price, currency, quantity_in_stock, category) VALUES (?, ?, ?, ?, ?, ?)",
            products
        )
        conn.commit()

    def save_invoice(self, invoice: Invoice, ingestion_result: IngestionResult) -> int:
        if not self.conn:
            raise RuntimeError("Database connection not open. Use with context manager.")
        
        cursor = self.conn.cursor()
        
        # Check if an exact (invoice_id, revision) record already exists
        cursor.execute(
            "SELECT id FROM invoices WHERE invoice_id = ? AND (revision = ? OR (revision IS NULL AND ? IS NULL))",
            (invoice.invoice_id, invoice.revision, invoice.revision)
        )
        existing_exact = cursor.fetchone()

        # Check latest record for this invoice_id (to record revision audit trail)
        cursor.execute("SELECT id, revision, vendor_name FROM invoices WHERE invoice_id = ? ORDER BY id DESC LIMIT 1", (invoice.invoice_id,))
        latest_existing = cursor.fetchone()

        if latest_existing and invoice.revision and latest_existing['revision'] != invoice.revision:
            cursor.execute("SELECT * FROM invoices WHERE id = ?", (latest_existing['id'],))
            old_inv_row = cursor.fetchone()
            cursor.execute("SELECT * FROM line_items WHERE invoice_db_id = ?", (latest_existing['id'],))
            old_lines = cursor.fetchall()

            old_data = dict(old_inv_row)
            old_data['line_items'] = [dict(li) for li in old_lines]
            new_data = invoice.model_dump(mode='json')
            change_summary = f"Revision updated from {latest_existing['revision']} to {invoice.revision}"

            cursor.execute(
                "INSERT INTO invoice_revisions (invoice_id, revision, previous_data, new_data, change_summary) VALUES (?, ?, ?, ?, ?)",
                (invoice.invoice_id, invoice.revision, json.dumps(old_data), json.dumps(new_data), change_summary)
            )

        if existing_exact:
            invoice_db_id = existing_exact['id']
            cursor.execute("DELETE FROM line_items WHERE invoice_db_id = ?", (invoice_db_id,))
            cursor.execute(
                '''UPDATE invoices SET
                    date=?, due_date=?, vendor_name=?, vendor_address=?,
                    subtotal=?, tax_rate=?, tax_amount=?, total=?, currency=?,
                    payment_terms=?, payment_terms_days=?, shipping=?, notes=?,
                    source_file=?, format_detected=?, is_suspicious=?,
                    suspicion_reasons=?, arithmetic_correct=?
                   WHERE id = ?''',
                (
                    invoice.date.isoformat(), invoice.due_date.isoformat(),
                    invoice.vendor.name, invoice.vendor.address,
                    float(invoice.subtotal) if invoice.subtotal is not None else None,
                    float(invoice.tax_rate) if invoice.tax_rate is not None else None,
                    float(invoice.tax_amount) if invoice.tax_amount is not None else None,
                    float(invoice.total), invoice.currency, invoice.payment_terms,
                    invoice.payment_terms_days,
                    float(invoice.shipping) if invoice.shipping is not None else None,
                    invoice.notes,
                    getattr(ingestion_result, "source_file", "direct_input") if ingestion_result else "direct_input",
                    (ingestion_result.format_detected.value if hasattr(ingestion_result.format_detected, "value") else str(ingestion_result.format_detected)) if (ingestion_result and ingestion_result.format_detected) else "unknown",
                    1 if (ingestion_result and ingestion_result.validation and ingestion_result.validation.is_suspicious) else 0,
                    json.dumps(ingestion_result.validation.suspicion_reasons if (ingestion_result and ingestion_result.validation) else []),
                    1 if (ingestion_result and ingestion_result.validation and ingestion_result.validation.arithmetic_correct) else 1,
                    invoice_db_id
                )
            )
        else:
            cursor.execute(
                '''INSERT INTO invoices (
                    invoice_id, revision, date, due_date, vendor_name, vendor_address,
                    subtotal, tax_rate, tax_amount, total, currency, payment_terms,
                    payment_terms_days, shipping, notes, source_file, format_detected,
                    is_suspicious, suspicion_reasons, arithmetic_correct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    invoice.invoice_id, invoice.revision, invoice.date.isoformat(), invoice.due_date.isoformat(),
                    invoice.vendor.name, invoice.vendor.address,
                    float(invoice.subtotal) if invoice.subtotal is not None else None,
                    float(invoice.tax_rate) if invoice.tax_rate is not None else None,
                    float(invoice.tax_amount) if invoice.tax_amount is not None else None,
                    float(invoice.total), invoice.currency, invoice.payment_terms,
                    invoice.payment_terms_days,
                    float(invoice.shipping) if invoice.shipping is not None else None,
                    invoice.notes,
                    getattr(ingestion_result, "source_file", "direct_input") if ingestion_result else "direct_input",
                    (ingestion_result.format_detected.value if hasattr(ingestion_result.format_detected, "value") else str(ingestion_result.format_detected)) if (ingestion_result and ingestion_result.format_detected) else "unknown",
                    1 if (ingestion_result and ingestion_result.validation and ingestion_result.validation.is_suspicious) else 0,
                    json.dumps(ingestion_result.validation.suspicion_reasons if (ingestion_result and ingestion_result.validation) else []),
                    1 if (ingestion_result and ingestion_result.validation and ingestion_result.validation.arithmetic_correct) else 1
                )
            )
            invoice_db_id = cursor.lastrowid
        
        try:
            for li in invoice.line_items:
                cursor.execute(
                    '''INSERT INTO line_items (
                        invoice_db_id, item, quantity, unit_price, amount, note
                    ) VALUES (?, ?, ?, ?, ?, ?)''',
                    (
                        invoice_db_id, li.item, float(li.quantity), float(li.unit_price),
                        float(li.amount) if li.amount is not None else None, li.note
                    )
                )
                
            self.conn.commit()
            invoice.db_id = invoice_db_id
            return invoice_db_id
        except Exception:
            self.conn.rollback()
            raise

    def log_ingestion(self, result: IngestionResult) -> None:
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                '''INSERT INTO ingestion_log (
                    source_file, format_detected, success, errors, warnings,
                    extraction_method, processing_time_ms, self_corrected,
                    correction_attempts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    result.source_file,
                    result.format_detected.value if result.format_detected and hasattr(result.format_detected, 'value') else str(result.format_detected),
                    int(result.success),
                    json.dumps(result.errors),
                    json.dumps(result.warnings),
                    result.extraction_method,
                    round(result.processing_time_ms, 2),
                    int(result.self_corrected),
                    result.correction_attempts,
                )
            )
            self.conn.commit()
        except Exception as e:
            logger.warning("Failed to log ingestion record: %s", e)

    def get_ingestion_metrics(self) -> dict[str, Any]:
        """Aggregate ingestion telemetry metrics for observability."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")

        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ingestion_log")
        total_ingested = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM ingestion_log WHERE success = 1")
        successful = cursor.fetchone()[0]
        failed = total_ingested - successful
        success_rate = (successful / total_ingested * 100.0) if total_ingested > 0 else 0.0

        cursor.execute("SELECT AVG(processing_time_ms) FROM ingestion_log")
        avg_latency = cursor.fetchone()[0] or 0.0

        cursor.execute("SELECT COUNT(*) FROM ingestion_log WHERE self_corrected = 1")
        self_corrected_count = cursor.fetchone()[0]

        # Formats breakdown
        cursor.execute("SELECT format_detected, COUNT(*) FROM ingestion_log GROUP BY format_detected")
        format_breakdown = {row[0] or "unknown": row[1] for row in cursor.fetchall()}

        # Extraction methods breakdown
        cursor.execute("SELECT extraction_method, COUNT(*) FROM ingestion_log GROUP BY extraction_method")
        method_breakdown = {row[0] or "unspecified": row[1] for row in cursor.fetchall()}

        # Invoices stats
        cursor.execute("SELECT COUNT(*) FROM invoices WHERE is_suspicious = 1")
        suspicious_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM invoices WHERE arithmetic_correct = 0")
        arithmetic_errors = cursor.fetchone()[0]

        return {
            "total_ingested": total_ingested,
            "successful": successful,
            "failed": failed,
            "success_rate_pct": round(success_rate, 1),
            "avg_latency_ms": round(avg_latency, 2),
            "self_corrected_invoices": self_corrected_count,
            "suspicious_invoices": suspicious_count,
            "arithmetic_errors": arithmetic_errors,
            "formats": format_breakdown,
            "extraction_methods": method_breakdown,
        }

    def get_invoice(self, invoice_id: str) -> dict | None:
        if not self.conn:
            raise RuntimeError("Database connection not open.")
            
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM invoices WHERE invoice_id = ? ORDER BY id DESC LIMIT 1", (invoice_id,))
        row = cursor.fetchone()
        if not row:
            return None
            
        invoice_data = dict(row)
        cursor.execute("SELECT * FROM line_items WHERE invoice_db_id = ?", (invoice_data['id'],))
        invoice_data['line_items'] = [dict(li) for li in cursor.fetchall()]
        return invoice_data

    def get_all_invoices(self) -> list[dict]:
        if not self.conn:
            raise RuntimeError("Database connection not open.")
            
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, invoice_id, vendor_name, total, date, is_suspicious FROM invoices ORDER BY date DESC")
        return [dict(row) for row in cursor.fetchall()]

    def get_products(self) -> list[dict]:
        if not self.conn:
            raise RuntimeError("Database connection not open.")
            
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM products")
        return [dict(row) for row in cursor.fetchall()]

    def get_revisions(self, invoice_id: str) -> list[dict]:
        if not self.conn:
            raise RuntimeError("Database connection not open.")
            
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM invoice_revisions WHERE invoice_id = ? ORDER BY changed_at DESC", (invoice_id,))
        return [dict(row) for row in cursor.fetchall()]

    # -----------------------------------------------------------------------
    # Business Rules & VP Review Audit
    # -----------------------------------------------------------------------

    def get_business_rules(self, active_only: bool = False) -> list[dict[str, Any]]:
        """Fetch all configured business rules."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        cursor = self.conn.cursor()
        query = (
            "SELECT id, name, description, rule_type, sql_query, llm_prompt, "
            "condition_type, condition_value, action, is_active, is_system, created_at "
            "FROM business_rules"
        )
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY is_system DESC, id ASC"
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]

    def get_active_rules(self) -> list[dict[str, Any]]:
        """Fetch all active decision rules from database."""
        return self.get_business_rules(active_only=True)

    def add_business_rule(
        self,
        rule: dict[str, Any] | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
        rule_type: str = "deterministic_query",
        sql_query: str | None = None,
        llm_prompt: str | None = None,
        condition_type: str = "custom",
        condition_value: str = "",
        action: str = "REQUIRE_HUMAN_APPROVAL",
        is_active: bool = True,
        is_system: bool = False,
        **kwargs: Any,
    ) -> int:
        """Add a dynamic business rule to the database."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        if rule and isinstance(rule, dict):
            r_name = rule["name"]
            r_desc = rule.get("description")
            r_type = rule.get("rule_type", "deterministic_query")
            r_sql = rule.get("sql_query")
            r_llm = rule.get("llm_prompt")
            r_ctype = rule.get("condition_type", "custom")
            r_cval = str(rule.get("condition_value", ""))
            r_act = rule.get("action", "REQUIRE_HUMAN_APPROVAL")
            r_actv = 1 if rule.get("is_active", True) else 0
            r_sys = 1 if rule.get("is_system", False) else 0
        else:
            r_name = name or kwargs.get("name", "")
            r_desc = description or kwargs.get("description")
            r_type = rule_type or kwargs.get("rule_type", "deterministic_query")
            r_sql = sql_query or kwargs.get("sql_query")
            r_llm = llm_prompt or kwargs.get("llm_prompt")
            r_ctype = condition_type or kwargs.get("condition_type", "custom")
            r_cval = str(condition_value or kwargs.get("condition_value", ""))
            r_act = action or kwargs.get("action", "REQUIRE_HUMAN_APPROVAL")
            r_actv = 1 if is_active else 0
            r_sys = 1 if is_system else 0

        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO business_rules 
               (name, description, rule_type, sql_query, llm_prompt, condition_type, condition_value, action, is_active, is_system)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (r_name, r_desc, r_type, r_sql, r_llm, r_ctype, r_cval, r_act, r_actv, r_sys),
        )
        self.conn.commit()
        return cursor.lastrowid

    # Alias for legacy compatibility
    add_rule = add_business_rule

    def toggle_business_rule(self, rule_id: int) -> int | None:
        """Toggle active state of a business rule and return new status (1 or 0)."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        cursor = self.conn.cursor()
        cursor.execute("UPDATE business_rules SET is_active = 1 - is_active WHERE id = ?", (rule_id,))
        if cursor.rowcount == 0:
            return None
        self.conn.commit()
        cursor.execute("SELECT is_active FROM business_rules WHERE id = ?", (rule_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def delete_business_rule(self, rule_id: int) -> bool:
        """Delete custom user rule (system rules are protected)."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM business_rules WHERE id = ? AND is_system = 0", (rule_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def test_rule_against_invoices(self, rule_or_sql: Any) -> list[dict[str, Any]]:
        """Tests a compiled rule or raw SQL condition against currently stored invoices."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        if isinstance(rule_or_sql, str):
            sql_query = rule_or_sql
            rule_type = "deterministic_query"
        elif isinstance(rule_or_sql, dict):
            sql_query = rule_or_sql.get("sql_query")
            rule_type = rule_or_sql.get("rule_type", "deterministic_query")
        else:
            sql_query = getattr(rule_or_sql, "sql_query", None)
            rule_type = getattr(rule_or_sql, "rule_type", "deterministic_query")

        cursor = self.conn.cursor()
        if rule_type == "deterministic_query" and sql_query:
            try:
                test_sql = f"SELECT id, invoice_id, vendor_name, total, currency, date FROM invoices WHERE {sql_query} LIMIT 10"
                cursor.execute(test_sql)
                return [dict(r) for r in cursor.fetchall()]
            except Exception:
                return []
        return []

    def save_invoice_review(self, review_data: dict) -> int:
        """Save or update invoice review audit record."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO invoice_reviews (
                invoice_id, decision, rules_triggered, initial_reasoning, critique,
                final_reasoning, requires_human, human_approval_status, human_reviewer,
                human_notes, payment_status, payment_details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                review_data["invoice_id"],
                review_data["decision"],
                json.dumps(review_data.get("rules_triggered", [])),
                review_data.get("initial_reasoning", ""),
                review_data.get("critique", ""),
                review_data.get("final_reasoning", ""),
                1 if review_data.get("requires_human") else 0,
                review_data.get("human_approval_status", "not_required"),
                review_data.get("human_reviewer"),
                review_data.get("human_notes"),
                review_data.get("payment_status", "pending_approval"),
                json.dumps(review_data.get("payment_details")) if review_data.get("payment_details") else None,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_invoice_review(self, invoice_id: str) -> dict | None:
        """Get the latest review audit record for an invoice."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM invoice_reviews WHERE invoice_id = ? ORDER BY id DESC LIMIT 1",
            (invoice_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        res = dict(row)
        res["rules_triggered"] = json.loads(res.get("rules_triggered") or "[]")
        res["payment_details"] = json.loads(res.get("payment_details") or "null")
        return res

    def get_pending_approvals(self) -> list[dict]:
        """Fetch all invoices pending human review/approval."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT r.*, i.vendor_name, i.total, i.currency, i.date, i.due_date, i.is_suspicious
               FROM invoice_reviews r
               LEFT JOIN invoices i ON r.invoice_id = i.invoice_id
               WHERE r.requires_human = 1 AND r.human_approval_status = 'pending'
               GROUP BY r.invoice_id
               ORDER BY MAX(r.id) DESC"""
        )
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            item["rules_triggered"] = json.loads(item.get("rules_triggered") or "[]")
            results.append(item)
        return results

    def update_human_approval(
        self,
        invoice_id: str,
        approved: bool,
        reviewer: str = "Human Reviewer",
        notes: str = "",
        payment_details: dict | None = None,
    ) -> bool:
        """Update review decision following human in the loop action."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        cursor = self.conn.cursor()
        status = "approved" if approved else "rejected"
        payment_status = "paid" if approved else "rejected"

        cursor.execute(
            """UPDATE invoice_reviews
               SET human_approval_status = ?,
                   human_reviewer = ?,
                   human_notes = ?,
                   payment_status = ?,
                   payment_details = COALESCE(?, payment_details),
                   updated_at = CURRENT_TIMESTAMP
               WHERE invoice_id = ? AND human_approval_status = 'pending'""",
            (
                status,
                reviewer,
                notes,
                payment_status,
                json.dumps(payment_details) if payment_details else None,
                invoice_id,
            ),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_invoice_line_items(self, invoice_db_id: int) -> list[dict]:
        """Fetch line items for a given invoice database row id."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        cursor = self.conn.cursor()
        cursor.execute("SELECT item, quantity, unit_price, amount, note FROM line_items WHERE invoice_db_id = ?", (invoice_db_id,))
        return [dict(r) for r in cursor.fetchall()]

    def get_previous_invoice_version(self, invoice_id: str, exclude_id: int | None = None) -> dict | None:
        """Fetch prior version of an invoice if revised, from revisions or previous invoice records."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT previous_data FROM invoice_revisions WHERE invoice_id = ? ORDER BY id DESC LIMIT 1",
            (invoice_id,),
        )
        rev_row = cursor.fetchone()
        if rev_row:
            try:
                return json.loads(rev_row[0])
            except Exception:
                pass

        if exclude_id is not None:
            cursor.execute(
                "SELECT * FROM invoices WHERE invoice_id = ? AND id != ? ORDER BY id DESC LIMIT 1",
                (invoice_id, exclude_id),
            )
        else:
            cursor.execute(
                "SELECT * FROM invoices WHERE invoice_id = ? ORDER BY id DESC LIMIT 1",
                (invoice_id,),
            )
        row = cursor.fetchone()
        if row:
            inv_dict = dict(row)
            inv_dict["line_items"] = self.get_invoice_line_items(inv_dict["id"])
            return inv_dict
        return None

    def find_duplicate_invoice(
        self,
        invoice_id: str,
        vendor_name: str,
        total: float,
        invoice_date: str,
        exclude_id: int | None = None,
        incoming_items: list[Any] | None = None,
    ) -> dict | None:
        """Detect exact duplicate invoices already stored in SQLite.

        Only triggers if the candidate invoice has 100% identical line items!
        If incoming has more or different items, it is a revision/amendment, not a duplicate.
        """
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        cursor = self.conn.cursor()
        if exclude_id is not None:
            cursor.execute(
                """SELECT id, invoice_id, vendor_name, total, date, created_at
                   FROM invoices
                   WHERE id != ? AND (invoice_id = ? OR (LOWER(vendor_name) = LOWER(?) AND ABS(total - ?) < 0.01 AND date = ?))
                   ORDER BY id DESC""",
                (exclude_id, invoice_id, vendor_name, total, invoice_date),
            )
        else:
            cursor.execute(
                """SELECT id, invoice_id, vendor_name, total, date, created_at
                   FROM invoices
                   WHERE invoice_id = ? OR (LOWER(vendor_name) = LOWER(?) AND ABS(total - ?) < 0.01 AND date = ?)
                   ORDER BY id DESC""",
                (invoice_id, vendor_name, total, invoice_date),
            )
        candidates = [dict(r) for r in cursor.fetchall()]
        if not candidates:
            return None

        # If incoming items are provided, verify 100% item match
        if incoming_items is not None:
            for cand in candidates:
                cand_items = self.get_invoice_line_items(cand["id"])
                if cand_items and are_line_items_identical(incoming_items, cand_items):
                    return cand
            return None

        return candidates[0]


    def are_line_items_identical(self, items_a: list, items_b: list) -> bool:
        """Check if two sets of line items match 100% in item name, quantity, and unit price."""
        return are_line_items_identical(items_a, items_b)

    def get_vendor_recent_invoices(
        self,
        vendor_name: str,
        exclude_invoice_id: str | None = None,
    ) -> list[dict]:
        """Get history of invoices for a vendor to analyze patterns (unbundling, sequential numbers)."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        cursor = self.conn.cursor()
        if exclude_invoice_id:
            cursor.execute(
                """SELECT id, invoice_id, vendor_name, total, date, created_at
                   FROM invoices
                   WHERE LOWER(vendor_name) = LOWER(?) AND invoice_id != ?
                   ORDER BY date DESC, id DESC""",
                (vendor_name, exclude_invoice_id),
            )
        else:
            cursor.execute(
                """SELECT id, invoice_id, vendor_name, total, date, created_at
                   FROM invoices
                   WHERE LOWER(vendor_name) = LOWER(?)
                   ORDER BY date DESC, id DESC""",
                (vendor_name,),
            )
        return [dict(row) for row in cursor.fetchall()]

    # -----------------------------------------------------------------------
    # Vendor Registry & Governance (Blacklist / Whitelist)
    # -----------------------------------------------------------------------

    def get_vendor_status(self, vendor_name: str) -> dict:
        """Get the blacklist/whitelist status of a vendor."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM vendor_registry WHERE LOWER(vendor_name) = LOWER(?) LIMIT 1",
            (vendor_name.strip(),),
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {"vendor_name": vendor_name.strip(), "status": "standard", "reason": None}

    def set_vendor_status(self, vendor_name: str, status: str, reason: str = "") -> bool:
        """Set vendor status to 'whitelisted', 'blacklisted', or 'standard'."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO vendor_registry (vendor_name, status, reason, updated_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(vendor_name) DO UPDATE SET
                   status = excluded.status,
                   reason = excluded.reason,
                   updated_at = CURRENT_TIMESTAMP""",
            (vendor_name.strip(), status.lower().strip(), reason.strip()),
        )
        self.conn.commit()
        return True

    def blacklist_vendor(self, vendor_name: str, reason: str = "") -> bool:
        """Convenience method to blacklist a vendor."""
        return self.set_vendor_status(vendor_name, "blacklisted", reason or "Blacklisted due to fraud / policy violation")

    def whitelist_vendor(self, vendor_name: str, reason: str = "") -> bool:
        """Convenience method to whitelist a vendor."""
        return self.set_vendor_status(vendor_name, "whitelisted", reason or "Whitelisted as trusted vendor")

    def list_vendors_registry(self) -> list[dict]:
        """List all vendors known across invoices and the registry with aggregated stats."""
        if not self.conn:
            raise RuntimeError("Database connection not open.")
        cursor = self.conn.cursor()

        # Gather all distinct vendors from invoices and registry
        cursor.execute("""
            SELECT 
                COALESCE(vr.vendor_name, inv.vendor_name) AS vendor_name,
                COALESCE(vr.status, 'standard') AS status,
                vr.reason,
                vr.updated_at,
                COUNT(inv.id) AS total_invoices,
                COALESCE(SUM(inv.total), 0.0) AS total_amount,
                SUM(CASE WHEN inv.is_suspicious = 1 THEN 1 ELSE 0 END) AS suspicious_count
            FROM (
                SELECT DISTINCT vendor_name FROM invoices
                UNION
                SELECT vendor_name FROM vendor_registry
            ) v
            LEFT JOIN vendor_registry vr ON LOWER(vr.vendor_name) = LOWER(v.vendor_name)
            LEFT JOIN invoices inv ON LOWER(inv.vendor_name) = LOWER(v.vendor_name)
            GROUP BY v.vendor_name
            ORDER BY 
                CASE WHEN vr.status = 'blacklisted' THEN 1 
                     WHEN vr.status = 'whitelisted' THEN 2 
                     ELSE 3 END,
                total_invoices DESC
        """)
        return [dict(row) for row in cursor.fetchall()]

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Fetch a system setting value by key."""
        if not self.conn:
            return default
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default
        except Exception:
            return default

    def set_setting(self, key: str, value: str) -> None:
        """Set or update a system setting value."""
        if not self.conn:
            return
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO system_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """, (key, value))
            self.conn.commit()
        except Exception as e:
            logger.warning("Failed to save setting %s: %s", key, e)

    def is_first_time_user(self) -> bool:
        """Check if the current user is a first-time user who has not finished onboarding."""
        val = self.get_setting("onboarding_completed", "false")
        return str(val).lower() not in ("true", "1", "yes")

    def set_onboarding_completed(self, completed: bool = True) -> None:
        """Persist whether onboarding has been completed to SQLite."""
        self.set_setting("onboarding_completed", "true" if completed else "false")


