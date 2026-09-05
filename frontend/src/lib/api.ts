/**
 * API Client for Invoice Pipeline FastAPI backend.
 */
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface DashboardStats {
  total_invoices: number;
  pending_approvals: number;
  approved_count: number;
  rejected_count: number;
  total_disbursed: number;
  suspicious_count: number;
}

export interface LineItem {
  id?: number;
  item: string;
  quantity: number;
  unit_price: number;
  amount?: number;
  note?: string;
  catalog_matched?: boolean;
  product_id?: string | null;
  quantity_in_stock?: number | null;
  stock_status?: "sufficient" | "out_of_stock" | "mismatch" | "unknown_item";
}

export interface InvoiceReview {
  decision: string;
  requires_human: boolean;
  human_approval_status: "pending" | "approved" | "rejected" | "not_required";
  human_reviewer?: string;
  human_notes?: string;
  payment_status: "paid" | "pending_approval" | "rejected" | "skipped";
  rules_triggered: string[];
  critique?: string;
  amount_to_pay?: number;
  payment_details?: {
    payment_id?: string;
    amount_paid?: number;
    vendor?: string;
    currency?: string;
    status?: string;
    timestamp?: string;
    approved_by?: string;
    approval_notes?: string;
    note?: string;
  };
}

export interface VendorItem {
  vendor_name: string;
  status: "whitelisted" | "blacklisted" | "standard";
  reason?: string | null;
  updated_at?: string;
  total_invoices: number;
  total_amount: number;
  suspicious_count: number;
}

export interface InvoiceItem {
  id: number;
  invoice_id: string;
  revision?: string | null;
  date: string;
  due_date: string;
  vendor_name: string;
  vendor_address?: string | null;
  subtotal?: number | null;
  tax_rate?: number | null;
  tax_amount?: number | null;
  total: number;
  currency: string;
  payment_terms?: string | null;
  payment_terms_days?: number | null;
  shipping?: number | null;
  notes?: string | null;
  is_suspicious: number;
  suspicion_reasons: string[];
  arithmetic_correct: number;
  source_file: string;
  format_detected: string;
  vendor_status?: "whitelisted" | "blacklisted" | "standard";
  vendor_status_reason?: string | null;
  decision?: string;
  requires_human?: number;
  human_approval_status?: string;
  human_reviewer?: string;
  human_notes?: string;
  payment_status?: string;
  rules_triggered: string[];
  critique?: string;
  payment_details?: any;
  ui_status: "pending_approval" | "paid" | "rejected" | "unreviewed";
  line_items?: LineItem[];
  revisions?: any[];
  review?: InvoiceReview | any;
}

export interface UploadSummary {
  total_files: number;
  successful_ingestions: number;
  auto_approved_paid: number;
  held_for_human_review: number;
}

export interface UploadResultItem {
  filename: string;
  format_detected?: string;
  success: boolean;
  is_invoice?: boolean;
  skipped?: boolean;
  is_poisoned?: boolean;
  poison_signatures?: string[];
  processing_time_ms?: number;
  stage_timings?: Record<string, number>;
  extraction_method?: string;
  self_corrected?: boolean;
  correction_notes?: string[];
  invoice_id?: string;
  vendor?: string;
  vendor_address?: string | null;
  total?: number;
  subtotal?: number | null;
  tax_amount?: number | null;
  tax_rate?: number | null;
  currency?: string;
  date?: string;
  due_date?: string;
  payment_terms?: string | null;
  line_items_count?: number;
  line_items?: {
    item: string;
    quantity: number;
    unit_price: number;
    amount?: number;
    note?: string;
  }[];
  decision?: string;
  requires_human?: boolean;
  payment_status?: string;
  rules_triggered?: string[];
  initial_reasoning?: string;
  critique?: string;
  final_reasoning?: string;
  payment_details?: any;
  logs?: string[];
  errors?: string[];
  warnings?: string[];
  is_quota_error?: boolean;
  quota_details?: {
    provider?: string;
    model?: string;
    status_code?: number;
    status?: string;
    raw_error?: string;
    explanation?: string;
  } | null;
}

export interface UploadResponse {
  summary: UploadSummary;
  results: UploadResultItem[];
}

export async function fetchStats(): Promise<DashboardStats> {
  const res = await fetch(`${API_BASE_URL}/api/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch dashboard stats");
  return res.json();
}

export async function fetchInvoices(statusFilter: string = "all"): Promise<InvoiceItem[]> {
  const res = await fetch(`${API_BASE_URL}/api/invoices?status=${statusFilter}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch invoices");
  return res.json();
}

export async function fetchInvoiceDetail(invoiceId: string): Promise<InvoiceItem> {
  const res = await fetch(`${API_BASE_URL}/api/invoices/${encodeURIComponent(invoiceId)}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch invoice ${invoiceId}`);
  return res.json();
}

export async function uploadInvoices(files: File[]): Promise<UploadResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));

  const res = await fetch(`${API_BASE_URL}/api/invoices/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || "Failed to upload invoices");
  }
  return res.json();
}

export async function approveInvoice(
  invoiceId: string,
  reviewer: string = "VP of Finance",
  notes: string = "Approved after executive review"
) {
  const res = await fetch(`${API_BASE_URL}/api/invoices/${encodeURIComponent(invoiceId)}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reviewer, notes }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Approval failed" }));
    throw new Error(err.detail || "Failed to approve invoice");
  }
  return res.json();
}

export async function rejectInvoice(
  invoiceId: string,
  reviewer: string = "VP of Finance",
  reason: string = "Rejected due to policy violation or suspicious flags",
  blacklistVendor: boolean = false
) {
  const res = await fetch(`${API_BASE_URL}/api/invoices/${encodeURIComponent(invoiceId)}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reviewer, reason, blacklist_vendor: blacklistVendor }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Rejection failed" }));
    throw new Error(err.detail || "Failed to reject invoice");
  }
  return res.json();
}

export async function rejectAndBlockInvoice(
  invoiceId: string,
  reviewer: string = "VP of Finance",
  reason: string = "Blocked due to fraudulent billing and blacklisted"
) {
  return rejectInvoice(invoiceId, reviewer, reason, true);
}

export interface BusinessRule {
  id: number;
  name: string;
  condition_type: string;
  condition_value: string;
  action: "REQUIRE_HUMAN_APPROVAL" | "REJECT" | "WARN" | string;
  description: string;
  is_active: number;
  rule_type: "deterministic_query" | "llm_eval" | string;
  sql_query?: string | null;
  llm_prompt?: string | null;
  is_system: number;
  created_at?: string;
}

export interface CreateBusinessRulePayload {
  name: string;
  description: string;
  action?: string;
  raw_query?: string;
}

export interface TestBusinessRulePayload {
  name?: string;
  description: string;
  raw_query?: string;
}

export interface TestBusinessRuleResult {
  status: string;
  compiled: {
    name: string;
    description: string;
    rule_type: string;
    sql_query?: string | null;
    llm_prompt?: string | null;
    condition_type?: string;
    condition_value?: string;
    action?: string;
  };
  matches_count: number;
  sample_matches: Array<{
    id: number;
    invoice_id: string;
    vendor_name: string;
    total: number;
    currency: string;
    date: string;
  }>;
  message?: string;
}

export async function fetchRules(): Promise<BusinessRule[]> {
  const res = await fetch(`${API_BASE_URL}/api/rules`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch rules");
  return res.json();
}

export async function fetchBusinessRules(activeOnly: boolean = false): Promise<BusinessRule[]> {
  const res = await fetch(`${API_BASE_URL}/api/vendor-rules${activeOnly ? "?active_only=true" : ""}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch business rules");
  return res.json();
}

export async function createBusinessRule(
  payload: CreateBusinessRulePayload
): Promise<{ status: string; rule_id: number; rule: BusinessRule }> {
  const res = await fetch(`${API_BASE_URL}/api/vendor-rules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to create rule" }));
    throw new Error(err.detail || "Failed to create rule");
  }
  return res.json();
}

export async function toggleBusinessRule(
  ruleId: number
): Promise<{ status: string; rule_id: number; is_active: number }> {
  const res = await fetch(`${API_BASE_URL}/api/vendor-rules/${ruleId}/toggle`, {
    method: "PATCH",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to toggle rule" }));
    throw new Error(err.detail || "Failed to toggle rule");
  }
  return res.json();
}

export async function deleteBusinessRule(
  ruleId: number
): Promise<{ status: string; deleted_rule_id: number }> {
  const res = await fetch(`${API_BASE_URL}/api/vendor-rules/${ruleId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to delete rule" }));
    throw new Error(err.detail || "Failed to delete rule");
  }
  return res.json();
}

export async function testBusinessRule(
  payload: TestBusinessRulePayload
): Promise<TestBusinessRuleResult> {
  const res = await fetch(`${API_BASE_URL}/api/vendor-rules/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Rule test failed" }));
    throw new Error(err.detail || "Rule test failed");
  }
  return res.json();
}

export async function fetchVendors(): Promise<VendorItem[]> {
  const res = await fetch(`${API_BASE_URL}/api/vendors`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch vendors directory");
  return res.json();
}

export async function updateVendorStatus(
  vendorName: string,
  status: "whitelisted" | "blacklisted" | "standard",
  reason: string = ""
) {
  const res = await fetch(`${API_BASE_URL}/api/vendors/${encodeURIComponent(vendorName)}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, reason }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to update vendor status" }));
    throw new Error(err.detail || "Failed to update vendor status");
  }
  return res.json();
}

export interface OriginalInvoiceResponse {
  invoice_id: string;
  filename: string;
  format: string;
  content_type: string;
  size_bytes: number;
  is_binary: boolean;
  content: string | null;
  download_url: string;
  view_url: string;
  found_on_disk?: boolean;
}

export function getOriginalInvoiceUrl(invoiceId: string, download: boolean = false): string {
  return `${API_BASE_URL}/api/invoices/${encodeURIComponent(invoiceId)}/original${download ? "?download=true" : ""}`;
}

export async function fetchOriginalInvoiceContent(invoiceId: string): Promise<OriginalInvoiceResponse> {
  const res = await fetch(`${API_BASE_URL}/api/invoices/${encodeURIComponent(invoiceId)}/original-preview`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Failed to fetch original invoice ${invoiceId}` }));
    throw new Error(err.detail || `Failed to fetch original invoice ${invoiceId}`);
  }
  return res.json();
}

export interface SystemSettings {
  enable_vp_review: boolean;
  llm_provider: string;
  model: string;
  qdrant_mode?: string;
  description: string;
}

export async function fetchSettings(): Promise<SystemSettings> {
  const res = await fetch(`${API_BASE_URL}/api/settings`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error("Failed to fetch settings");
  }
  return res.json();
}

export async function updateSettings(settings: { enable_vp_review: boolean }): Promise<{ success: boolean; enable_vp_review: boolean; message: string }> {
  const res = await fetch(`${API_BASE_URL}/api/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Failed to update settings" }));
    throw new Error(err.detail || "Failed to update settings");
  }
  return res.json();
}

export interface OnboardingStatus {
  is_first_time_user: boolean;
  onboarding_completed: boolean;
}

export async function fetchOnboardingStatus(): Promise<OnboardingStatus> {
  const res = await fetch(`${API_BASE_URL}/api/onboarding/status`, { cache: "no-store" });
  if (!res.ok) {
    return { is_first_time_user: false, onboarding_completed: true };
  }
  return res.json();
}

export async function completeOnboarding(): Promise<{ success: boolean; is_first_time_user: boolean; onboarding_completed: boolean }> {
  const res = await fetch(`${API_BASE_URL}/api/onboarding/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    throw new Error("Failed to save onboarding completion");
  }
  return res.json();
}

export async function resetOnboarding(): Promise<{ success: boolean; is_first_time_user: boolean; onboarding_completed: boolean }> {
  const res = await fetch(`${API_BASE_URL}/api/onboarding/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    throw new Error("Failed to reset onboarding");
  }
  return res.json();
}


