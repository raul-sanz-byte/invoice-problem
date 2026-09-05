from datetime import date
from decimal import Decimal
import tempfile
from pathlib import Path
import pytest

from invoice_pipeline.models import Invoice, LineItem, Vendor, ValidationSeverity
from invoice_pipeline.storage.database import InvoiceDatabase
from invoice_pipeline.validation.inventory_validator import validate_inventory
from invoice_pipeline.validation.schema_validator import validate_schema
from invoice_pipeline.validation.anomaly_detector import detect_anomalies
from invoice_pipeline.pipeline import InvoicePipeline


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / 'test_scenario.db'
        with InvoiceDatabase(db_path) as db:
            yield db


def test_scenario_1_normal_order_within_stock(temp_db):
    # INV-1001: WidgetA: 10 (stock: 500), WidgetB: 5 (stock: 300)
    inv_1001 = Invoice(
        invoice_id='INV-1001',
        date=date(2026, 1, 15),
        due_date=date(2026, 2, 1),
        vendor=Vendor(name='Widgets Inc.'),
        line_items=[
            LineItem(item='WidgetA', quantity=Decimal('10'), unit_price=Decimal('250.00'), amount=Decimal('2500.00')),
            LineItem(item='WidgetB', quantity=Decimal('5'), unit_price=Decimal('500.00'), amount=Decimal('2500.00')),
        ],
        subtotal=Decimal('5000.00'),
        total=Decimal('5000.00'),
        payment_terms='Net 15',
    )
    res_1001 = validate_inventory(inv_1001, database=temp_db)
    assert len(res_1001.issues) == 0, f'INV-1001 should pass inventory check, got: {res_1001.issues}'
    assert not res_1001.is_suspicious

    # INV-1004: WidgetA: 3, WidgetB: 2
    inv_1004 = Invoice(
        invoice_id='INV-1004',
        date=date(2026, 1, 22),
        due_date=date(2026, 2, 22),
        vendor=Vendor(name='Precision Parts Ltd.'),
        line_items=[
            LineItem(item='WidgetA', quantity=Decimal('3'), unit_price=Decimal('250.00'), amount=Decimal('750.00')),
            LineItem(item='WidgetB', quantity=Decimal('2'), unit_price=Decimal('500.00'), amount=Decimal('1000.00')),
        ],
        subtotal=Decimal('1750.00'),
        total=Decimal('1890.00'),
        payment_terms='Net 30',
    )
    res_1004 = validate_inventory(inv_1004, database=temp_db)
    assert len(res_1004.issues) == 0, f'INV-1004 should pass inventory check, got: {res_1004.issues}'
    assert not res_1004.is_suspicious

    # INV-1006: WidgetA: 5, WidgetB: 3
    inv_1006 = Invoice(
        invoice_id='INV-1006',
        date=date(2026, 1, 25),
        due_date=date(2026, 2, 10),
        vendor=Vendor(name='Acme Industrial Supplies'),
        line_items=[
            LineItem(item='WidgetA', quantity=Decimal('5'), unit_price=Decimal('250.00'), amount=Decimal('1250.00')),
            LineItem(item='WidgetB', quantity=Decimal('3'), unit_price=Decimal('500.00'), amount=Decimal('1500.00')),
        ],
        subtotal=Decimal('2750.00'),
        total=Decimal('2750.00'),
        payment_terms='Net 15',
    )
    res_1006 = validate_inventory(inv_1006, database=temp_db)
    assert len(res_1006.issues) == 0, f'INV-1006 should pass inventory check, got: {res_1006.issues}'
    assert not res_1006.is_suspicious


def test_scenario_2_quantity_exceeds_stock(temp_db):
    inv_1002 = Invoice(
        invoice_id='INV-1002',
        date=date(2026, 1, 30),
        due_date=date(2026, 1, 30),
        vendor=Vendor(name='Gadgets Co.'),
        line_items=[
            LineItem(item='GadgetX', quantity=Decimal('20'), unit_price=Decimal('750.00'), amount=Decimal('15000.00')),
        ],
        total=Decimal('15000.00'),
        payment_terms='Net 30',
    )
    res = validate_inventory(inv_1002, database=temp_db)
    assert len(res.issues) >= 1
    mismatch_issues = [i for i in res.issues if 'Stock mismatch' in i.message]
    assert len(mismatch_issues) == 1
    assert 'requested 20 units, but only 5 in stock' in mismatch_issues[0].message


def test_scenario_3_fraudulent_zero_stock_item(temp_db):
    inv_1003 = Invoice(
        invoice_id='INV-1003',
        date=date(2026, 1, 20),
        due_date=date(2026, 1, 19),
        vendor=Vendor(name='Fraudster LLC'),
        line_items=[
            LineItem(item='FakeItem', quantity=Decimal('100'), unit_price=Decimal('1000.00'), amount=Decimal('100000.00')),
        ],
        total=Decimal('100000.00'),
        payment_terms='Immediate',
        notes='URGENT - Pay immediately to avoid penalties!!! Wire transfer preferred.',
    )
    temp_db.conn.execute(
        "INSERT INTO products (product_id, name, standard_price, currency, quantity_in_stock, category) VALUES (?, ?, ?, ?, ?, ?)",
        ("TEST-ZERO", "FakeItem", 1000.00, "USD", 0, "TestZeroStock")
    )
    temp_db.conn.commit()
    res = validate_inventory(inv_1003, database=temp_db)
    assert res.is_suspicious
    assert any('zero stock' in reason.lower() for reason in res.suspicion_reasons)
    assert any('out of stock' in i.message.lower() for i in res.issues)

    anom_res = detect_anomalies(inv_1003)
    assert anom_res.is_suspicious
    assert any('suspicious keywords' in r.lower() for r in anom_res.suspicion_reasons)


def test_scenario_4_item_not_in_database_at_all(temp_db):
    inv_1008 = Invoice(
        invoice_id='INV-1008',
        date=date(2026, 1, 10),
        due_date=date(2026, 1, 20),
        vendor=Vendor(name='NoProd Industries'),
        line_items=[
            LineItem(item='SuperGizmo', quantity=Decimal('12'), unit_price=Decimal('400.00'), amount=Decimal('4800.00')),
            LineItem(item='MegaSprocket', quantity=Decimal('6'), unit_price=Decimal('850.00'), amount=Decimal('5100.00')),
        ],
        total=Decimal('9900.00'),
    )
    res_1008 = validate_inventory(inv_1008, database=temp_db)
    unknown_1008 = [i for i in res_1008.issues if 'Unknown item' in i.message]
    assert len(unknown_1008) == 2
    assert any('SuperGizmo' in i.message for i in unknown_1008)
    assert any('MegaSprocket' in i.message for i in unknown_1008)

    inv_1016 = Invoice(
        invoice_id='INV-1016',
        date=date(2026, 1, 27),
        due_date=date(2026, 2, 27),
        vendor=Vendor(name='Gizmo World Ltd.'),
        line_items=[
            LineItem(item='WidgetC', quantity=Decimal('10'), unit_price=Decimal('150.00'), amount=Decimal('1500.00')),
        ],
        total=Decimal('1500.00'),
        payment_terms='Net 30',
    )
    res_1016 = validate_inventory(inv_1016, database=temp_db)
    unknown_1016 = [i for i in res_1016.issues if 'Unknown item' in i.message]
    assert len(unknown_1016) == 1
    assert 'WidgetC' in unknown_1016[0].message


def test_scenario_5_invalid_data_negative_quantity():
    inv_1009 = Invoice(
        invoice_id='INV-1009',
        date=date(2026, 1, 25),
        due_date=date(2026, 2, 25),
        vendor=Vendor(name='Acme Tools Inc.'),
        line_items=[
            LineItem(item='WidgetA', quantity=Decimal('-5'), unit_price=Decimal('250.00'), amount=Decimal('-1250.00')),
        ],
        total=Decimal('1250.00'),
        payment_terms='Net 30',
    )
    res = validate_schema(inv_1009)
    assert not res.passed
    integrity_issues = [i for i in res.issues if 'Data integrity issue' in i.message]
    assert len(integrity_issues) == 1
    assert 'invalid/negative quantity (-5)' in integrity_issues[0].message


def test_pipeline_integration_with_scenarios(temp_db):
    pipeline = InvoicePipeline(database=temp_db)

    # Negative quantity fixture -> error
    res_1009 = pipeline.process_file('tests/fixtures/invoice_negative_qty.json')
    assert any('Data integrity issue' in err for err in res_1009.errors)

    # Unknown item fixture -> warning
    res_1016 = pipeline.process_file('tests/fixtures/invoice_unknown_item.json')
    assert any('Unknown item' in w for w in res_1016.warnings)
    assert any('WidgetC' in w for w in res_1016.warnings)

    # Normal order fixture -> passes cleanly
    res_1004 = pipeline.process_file('tests/fixtures/invoice_json_1.json')
    assert res_1004.success
    assert not any('Unknown item' in w for w in res_1004.warnings)
    assert not any('Stock mismatch' in w for w in res_1004.warnings)