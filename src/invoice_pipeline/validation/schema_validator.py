from datetime import date
from invoice_pipeline.models import Invoice, ValidationResult, ValidationSeverity

def validate_schema(invoice: Invoice) -> ValidationResult:
    result = ValidationResult()
    
    if not invoice.invoice_id:
        result.add_issue(ValidationSeverity.ERROR, "Invoice ID is empty", field="invoice_id")
        
    if invoice.date.year > date.today().year + 5:
        result.add_issue(ValidationSeverity.ERROR, "Invoice date is in the far future", field="date")
        
    if not invoice.vendor or not invoice.vendor.name or invoice.vendor.name.strip().lower() in ("[missing vendor name]", "unknown vendor"):
        result.add_issue(ValidationSeverity.ERROR, "Vendor name is missing or empty", field="vendor.name")
        
    if not invoice.line_items:
        result.add_issue(ValidationSeverity.ERROR, "Line items must have at least one item", field="line_items")
    else:
        for idx, item in enumerate(invoice.line_items):
            if not item.item:
                result.add_issue(ValidationSeverity.ERROR, f"Line item {idx} missing item description", field=f"line_items[{idx}].item")
            if item.quantity <= 0:
                result.add_issue(
                    ValidationSeverity.ERROR,
                    f"Data integrity issue: Line item {idx} ('{item.item}') has invalid/negative quantity ({item.quantity})",
                    field=f"line_items[{idx}].quantity",
                    expected="> 0",
                    actual=str(item.quantity),
                )
            if item.unit_price < 0:
                result.add_issue(
                    ValidationSeverity.ERROR,
                    f"Data integrity issue: Line item {idx} ('{item.item}') has negative unit price ({item.unit_price})",
                    field=f"line_items[{idx}].unit_price",
                    expected=">= 0",
                    actual=str(item.unit_price),
                )
                
    if invoice.total <= 0:
        result.add_issue(ValidationSeverity.ERROR, "Total is <= 0", field="total")
        
    if invoice.currency:
        if len(invoice.currency) != 3:
            result.add_issue(ValidationSeverity.ERROR, "Currency code is invalid", field="currency")
            
    if invoice.tax_rate is not None:
        if invoice.tax_rate < 0 or invoice.tax_rate > 1:
            result.add_issue(ValidationSeverity.ERROR, "Tax rate should be between 0 and 1", field="tax_rate")
            
    if any(i.severity == ValidationSeverity.ERROR for i in result.issues):
        result.passed = False
        
    return result
