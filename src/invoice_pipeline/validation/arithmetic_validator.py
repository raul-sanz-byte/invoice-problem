from decimal import Decimal
from invoice_pipeline.models import Invoice, ValidationResult, ValidationSeverity

def validate_arithmetic(invoice: Invoice) -> ValidationResult:
    result = ValidationResult()
    tolerance = Decimal('0.01')
    
    computed_sum = Decimal('0')
    for idx, item in enumerate(invoice.line_items):
        if item.note and any(k in item.note.lower() for k in ['discount', 'volume']):
            computed_sum += (item.amount or (item.quantity * item.unit_price))
            continue
            
        expected = item.quantity * item.unit_price
        item_amount = item.amount if item.amount is not None else expected
        if abs(item_amount - expected) > tolerance:
            result.add_issue(
                ValidationSeverity.WARNING,
                f"Line item {idx} amount mismatch",
                field=f"line_items[{idx}].amount",
                expected=str(expected),
                actual=str(item_amount)
            )
        computed_sum += item_amount

    if invoice.subtotal is not None:
        if abs(invoice.subtotal - computed_sum) > tolerance:
            result.add_issue(
                ValidationSeverity.ERROR,
                "Subtotal mismatch",
                field="subtotal",
                expected=str(computed_sum),
                actual=str(invoice.subtotal)
            )
            result.arithmetic_correct = False
    
    effective_subtotal = invoice.subtotal if invoice.subtotal is not None else computed_sum
    
    if invoice.tax_rate is not None and invoice.tax_amount is not None and invoice.subtotal is not None:
        expected_tax = invoice.subtotal * invoice.tax_rate
        if abs(invoice.tax_amount - expected_tax) > tolerance:
            result.add_issue(
                ValidationSeverity.WARNING,
                "Tax amount mismatch",
                field="tax_amount",
                expected=str(expected_tax),
                actual=str(invoice.tax_amount)
            )
            
    computed_total = effective_subtotal + (invoice.tax_amount or Decimal('0')) + (invoice.shipping or Decimal('0'))
    if abs(invoice.total - computed_total) > tolerance:
        result.add_issue(
            ValidationSeverity.ERROR,
            "Total mismatch",
            field="total",
            expected=str(computed_total),
            actual=str(invoice.total)
        )
        result.arithmetic_correct = False
        
    if any(i.severity == ValidationSeverity.ERROR for i in result.issues):
        result.passed = False
        
    return result
