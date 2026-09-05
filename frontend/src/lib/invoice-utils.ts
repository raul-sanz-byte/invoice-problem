import { InvoiceItem } from "@/lib/api";

// ─── Original invoice format & size helpers ───────────────────────────
export function getFormatIconAndColor(format?: string, filename?: string): { icon: string; bg: string; text: string; border: string } {
  const ext = (filename?.split(".").pop() || format || "").toLowerCase();
  if (ext === "pdf") {
    return { icon: "picture_as_pdf", bg: "bg-red-500/10", text: "text-red-500", border: "border-red-500/20" };
  }
  if (ext === "json") {
    return { icon: "data_object", bg: "bg-amber-500/10", text: "text-amber-500", border: "border-amber-500/20" };
  }
  if (ext === "xml") {
    return { icon: "code", bg: "bg-purple-500/10", text: "text-purple-500", border: "border-purple-500/20" };
  }
  if (ext === "csv") {
    return { icon: "table_chart", bg: "bg-emerald-500/10", text: "text-emerald-500", border: "border-emerald-500/20" };
  }
  return { icon: "description", bg: "bg-indigo-500/10", text: "text-indigo-500", border: "border-indigo-500/20" };
}

export function formatFileSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

// ─── Flag analysis helpers ────────────────────────────────────────────
export function getFlagType(inv: InvoiceItem): "error" | "warning" | "success" | "info" {
  if (inv.is_suspicious) return "error";
  const rules: string[] = (inv.rules_triggered?.length ? inv.rules_triggered : (inv.review?.rules_triggered || [])) as string[];
  if (rules.some((r: string) => r.toUpperCase().includes("BLACKLISTED"))) return "error";
  if (rules.some((r: string) => r.toUpperCase().includes("DUPLICATE"))) return "error";
  if (rules.some((r: string) => r.toUpperCase().includes("ARITHMETIC"))) return "error";
  if (rules.some((r: string) => r.toUpperCase().includes("STRUCTURING"))) return "warning";
  if (!inv.arithmetic_correct) return "error";
  if (rules.length) return "warning";
  if (inv.ui_status === "paid") return "success";
  return "info";
}

export function getFlagLabel(inv: InvoiceItem): string {
  const rules: string[] = (inv.rules_triggered?.length ? inv.rules_triggered : (inv.review?.rules_triggered || [])) as string[];
  if (rules.length) {
    const r = rules[0];
    const upper = r.toUpperCase();
    if (upper.includes("BLACKLISTED")) return "Blacklisted Vendor";
    if (upper.includes("DUPLICATE")) return "Suspected Duplicate";
    if (upper.includes("STOCK_MISMATCH")) return "Stock Mismatch";
    if (upper.includes("AMOUNT_OVER")) return "Amount Over $10K";
    if (upper.includes("ARITHMETIC")) return "Arithmetic Error";
    if (upper.includes("STRUCTURING")) return "Suspicious Structuring";
    if (upper.includes("UNKNOWN_ITEMS")) return "Unknown Line Items";
    if (upper.includes("FRAUD") || upper.includes("SUSPICIOUS")) return "Fraud Anomaly";
    return r.split(":")[0] || "Rule Triggered";
  }
  if (inv.is_suspicious) return "Suspicious Activity";
  if (!inv.arithmetic_correct) return "Math Error Detected";
  if (inv.ui_status === "paid") return "3-Way Matched";
  return "Pending Review";
}

export function hasRaisedFlags(inv: InvoiceItem): boolean {
  if (inv.is_suspicious) return true;
  if (!inv.arithmetic_correct) return true;
  const rules: string[] = (inv.rules_triggered?.length ? inv.rules_triggered : (inv.review?.rules_triggered || [])) as string[];
  if (rules.length > 0) return true;
  if (inv.suspicion_reasons && inv.suspicion_reasons.length > 0) return true;
  if (inv.vendor_status === "blacklisted") return true;
  if (inv.decision === "requires_human_approval" || inv.review?.decision === "requires_human_approval") return true;
  if (inv.requires_human === 1 || inv.review?.requires_human === 1 || inv.review?.requires_human === true) return true;
  if (inv.line_items?.some(li => li.stock_status === "out_of_stock" || li.stock_status === "mismatch")) {
    return true;
  }
  return false;
}

export function isProcessedSuccessfullyWithoutFlags(inv: InvoiceItem): boolean {
  if (hasRaisedFlags(inv)) return false;
  if (inv.ui_status === "pending_approval" || inv.payment_status === "pending_approval" || inv.review?.payment_status === "pending_approval") {
    return false;
  }
  return (
    inv.ui_status === "paid" ||
    inv.payment_status === "paid" ||
    inv.decision === "auto_approved" ||
    inv.human_approval_status === "approved"
  );
}

export function isInvoiceApproved(inv: InvoiceItem): boolean {
  if (
    inv.ui_status === "pending_approval" ||
    inv.payment_status === "pending_approval" ||
    inv.review?.payment_status === "pending_approval" ||
    inv.human_approval_status === "pending" ||
    inv.review?.human_approval_status === "pending" ||
    inv.decision === "requires_human_approval" ||
    inv.review?.decision === "requires_human_approval" ||
    inv.ui_status === "rejected" ||
    inv.payment_status === "rejected" ||
    inv.human_approval_status === "rejected"
  ) {
    return false;
  }

  if (hasRaisedFlags(inv)) {
    return inv.human_approval_status === "approved" || inv.review?.human_approval_status === "approved";
  }

  return (
    inv.ui_status === "paid" ||
    inv.payment_status === "paid" ||
    inv.decision === "auto_approved" ||
    inv.human_approval_status === "approved" ||
    inv.review?.human_approval_status === "approved" ||
    inv.review?.decision === "auto_approved"
  );
}

export function isInvoiceWithheld(inv: InvoiceItem): boolean {
  if (isProcessedSuccessfullyWithoutFlags(inv)) {
    return false;
  }
  return true;
}

export function getAIConfidence(inv: InvoiceItem): { value: number; label: string; color: string } {
  if (inv.is_suspicious || inv.rules_triggered?.some(r => r.toUpperCase().includes("BLACKLISTED") || r.toUpperCase().includes("DUPLICATE"))) {
    return { value: 46, label: "High Risk", color: "text-red-600" };
  }
  if (!inv.arithmetic_correct) return { value: 52, label: "Math Error", color: "text-red-600" };
  if (inv.rules_triggered?.length && inv.rules_triggered.length > 1) {
    return { value: 68, label: "Incomplete", color: "text-slate-700" };
  }
  if (inv.rules_triggered?.length === 1) {
    return { value: 78, label: "Review", color: "text-amber-600" };
  }
  if (inv.ui_status === "paid") return { value: 99.8, label: "Verified", color: "text-emerald-600" };
  return { value: 82, label: "Attention", color: "text-slate-700" };
}

export function getVendorInitials(name: string): string {
  return name
    .split(/\s+/)
    .filter(w => w.length > 0)
    .slice(0, 2)
    .map(w => w[0].toUpperCase())
    .join("");
}

export const VENDOR_COLORS = [
  "bg-indigo-600", "bg-sky-600", "bg-amber-500", "bg-purple-700",
  "bg-teal-700", "bg-orange-600", "bg-rose-600", "bg-emerald-600",
  "bg-cyan-700", "bg-pink-600",
];

export function getVendorColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return VENDOR_COLORS[Math.abs(hash) % VENDOR_COLORS.length];
}

export function formatCurrency(amount: number, currency: string = "USD"): string {
  const symbol = currency === "EUR" ? "€" : "$";
  return `${symbol}${amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// ─── Date Parsing & Urgency Helpers ────────────────────────────────────
export function parseDate(dStr?: string | null): Date | null {
  if (!dStr) return null;
  const parts = dStr.split("-");
  if (parts.length === 3) {
    const y = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10) - 1;
    const d = parseInt(parts[2], 10);
    if (!isNaN(y) && !isNaN(m) && !isNaN(d)) return new Date(y, m, d);
  }
  const dt = new Date(dStr);
  return isNaN(dt.getTime()) ? null : dt;
}

export function getDueUrgencyInfo(dueDateStr?: string | null): {
  diffDays: number;
  label: string;
  color: string;
  isOverdue: boolean;
  isToday: boolean;
  isSoon: boolean;
} | null {
  const d = parseDate(dueDateStr);
  if (!d) return null;

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diffDays = Math.round((d.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays < 0) {
    const days = Math.abs(diffDays);
    return {
      diffDays,
      label: `Overdue (${days}d)`,
      color: "bg-red-100 text-red-700 border-red-200 font-bold",
      isOverdue: true,
      isToday: false,
      isSoon: true,
    };
  }
  if (diffDays === 0) {
    return {
      diffDays,
      label: "Due Today",
      color: "bg-amber-100 text-amber-900 border-amber-300 font-bold",
      isOverdue: false,
      isToday: true,
      isSoon: true,
    };
  }
  if (diffDays <= 7) {
    return {
      diffDays,
      label: `Due in ${diffDays}d`,
      color: "bg-amber-50 text-amber-800 border-amber-200 font-semibold",
      isOverdue: false,
      isToday: false,
      isSoon: true,
    };
  }
  return {
    diffDays,
    label: `In ${diffDays}d`,
    color: "bg-slate-100 text-slate-700 border-slate-200 font-medium",
    isOverdue: false,
    isToday: false,
    isSoon: false,
  };
}

// ─── Available Flags Registry ─────────────────────────────────────────
export interface FilterFlagOption {
  id: string;
  label: string;
  shortLabel: string;
  icon: string;
  badgeClass: string;
}

export const AVAILABLE_FLAGS: FilterFlagOption[] = [
  { id: "EXACT_DUPLICATE", label: "Suspected Duplicate", shortLabel: "Duplicate", icon: "content_copy", badgeClass: "bg-rose-100 text-rose-800 border-rose-200" },
  { id: "STOCK_MISMATCH", label: "Warehouse Stock Mismatch", shortLabel: "Stock Mismatch", icon: "inventory_2", badgeClass: "bg-orange-100 text-orange-800 border-orange-200" },
  { id: "AMOUNT_OVER_10K", label: "Amount Over $10K (VP Scrutiny)", shortLabel: "Amount > $10K", icon: "payments", badgeClass: "bg-purple-100 text-purple-800 border-purple-200" },
  { id: "SUSPICIOUS_STRUCTURING", label: "Suspicious Structuring (<$10K)", shortLabel: "Structuring", icon: "tune", badgeClass: "bg-amber-100 text-amber-900 border-amber-200" },
  { id: "ARITHMETIC_ERROR", label: "Arithmetic Mismatch", shortLabel: "Math Error", icon: "calculate", badgeClass: "bg-red-100 text-red-800 border-red-200" },
  { id: "UNKNOWN_ITEMS", label: "Unknown Line Items", shortLabel: "Unknown Items", icon: "help_outline", badgeClass: "bg-yellow-100 text-yellow-800 border-yellow-200" },
  { id: "BLACKLISTED_VENDOR", label: "Blacklisted Vendor", shortLabel: "Blacklisted", icon: "block", badgeClass: "bg-slate-800 text-white border-slate-700" },
  { id: "UNBUNDLED_BILLING", label: "Unbundled Split Billing", shortLabel: "Unbundled", icon: "call_split", badgeClass: "bg-blue-100 text-blue-800 border-blue-200" },
  { id: "SEQUENTIAL_INVOICE_GAP", label: "Sequential Gap Anomaly", shortLabel: "Seq. Gap", icon: "timeline", badgeClass: "bg-indigo-100 text-indigo-800 border-indigo-200" },
  { id: "DATE_ANOMALY", label: "Weekend / Holiday Anomaly", shortLabel: "Date Anomaly", icon: "calendar_today", badgeClass: "bg-teal-100 text-teal-800 border-teal-200" },
];

export function invoiceMatchesFlag(inv: InvoiceItem, flagId: string): boolean {
  if (flagId === "ZERO_FLAGS") {
    return isProcessedSuccessfullyWithoutFlags(inv) || !hasRaisedFlags(inv);
  }
  if (flagId === "EXACT_DUPLICATE") {
    return Boolean((inv.rules_triggered || []).some(r => r.toUpperCase().includes("DUPLICATE")));
  }
  if (flagId === "STOCK_MISMATCH") {
    return Boolean(
      (inv.rules_triggered || []).some(r => r.toUpperCase().includes("STOCK_MISMATCH")) ||
      inv.line_items?.some(li => li.stock_status === "mismatch" || li.stock_status === "out_of_stock")
    );
  }
  if (flagId === "AMOUNT_OVER_10K") {
    return Boolean((inv.rules_triggered || []).some(r => r.toUpperCase().includes("AMOUNT_OVER")) || inv.total > 10000);
  }
  if (flagId === "SUSPICIOUS_STRUCTURING") {
    return Boolean((inv.rules_triggered || []).some(r => r.toUpperCase().includes("STRUCTURING")));
  }
  if (flagId === "ARITHMETIC_ERROR") {
    return Boolean(!inv.arithmetic_correct || (inv.rules_triggered || []).some(r => r.toUpperCase().includes("ARITHMETIC")));
  }
  if (flagId === "UNKNOWN_ITEMS") {
    return Boolean(
      (inv.rules_triggered || []).some(r => r.toUpperCase().includes("UNKNOWN_ITEMS")) ||
      inv.line_items?.some(li => li.stock_status === "unknown_item")
    );
  }
  if (flagId === "SUSPICIOUS_OR_FRAUD") {
    return Boolean(inv.is_suspicious || (inv.rules_triggered || []).some(r => r.toUpperCase().includes("FRAUD") || r.toUpperCase().includes("SUSPICIOUS")));
  }
  if (flagId === "BLACKLISTED_VENDOR") {
    return Boolean(inv.vendor_status === "blacklisted" || (inv.rules_triggered || []).some(r => r.toUpperCase().includes("BLACKLIST")));
  }
  if (flagId === "UNBUNDLED_BILLING") {
    return Boolean((inv.rules_triggered || []).some(r => r.toUpperCase().includes("UNBUNDLED")));
  }
  if (flagId === "SEQUENTIAL_INVOICE_GAP") {
    return Boolean((inv.rules_triggered || []).some(r => r.toUpperCase().includes("SEQUENTIAL")));
  }
  if (flagId === "DATE_ANOMALY") {
    return Boolean((inv.rules_triggered || []).some(r => r.toUpperCase().includes("DATE_ANOMALY")));
  }
  return false;
}

// ─── Badge color maps ─────────────────────────────────────────────────
export function flagBadgeClasses(type: "error" | "warning" | "success" | "info") {
  switch (type) {
    case "error": return "bg-red-100 text-red-700";
    case "warning": return "bg-amber-100 text-amber-800";
    case "success": return "bg-emerald-100 text-emerald-800";
    default: return "bg-purple-100 text-purple-800";
  }
}
