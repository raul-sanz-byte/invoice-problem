import os

page_code = r'''"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  fetchStats,
  fetchInvoices,
  fetchInvoiceDetail,
  uploadInvoices,
  approveInvoice,
  rejectInvoice,
  rejectAndBlockInvoice,
  fetchVendors,
  updateVendorStatus,
  DashboardStats,
  InvoiceItem,
  VendorItem,
  UploadResponse,
} from "@/lib/api";
import {
  UploadCloud,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  DollarSign,
  FileText,
  ShieldCheck,
  ShieldAlert,
  ShieldBan,
  RefreshCw,
  Search,
  Check,
  X,
  Eye,
  Building,
  Calendar,
  Layers,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  UserCheck,
  HelpCircle,
  FileSpreadsheet,
  AlertCircle,
  BadgeAlert,
} from "lucide-react";

// Helper for rule color mapping and descriptive tooltip details
interface RuleStyle {
  bg: string;
  text: string;
  border: string;
  badgeBg: string;
  badgeText: string;
  label: string;
  detail: string;
}

function getRuleStyle(ruleStr: string): RuleStyle {
  const upper = ruleStr.toUpperCase();
  if (upper.includes("BLACKLISTED_VENDOR")) {
    return {
      bg: "bg-rose-50",
      text: "text-rose-900",
      border: "border-rose-400 ring-2 ring-rose-300/50",
      badgeBg: "bg-rose-600",
      badgeText: "text-white",
      label: "BLACKLISTED VENDOR",
      detail: "This vendor is on the executive fraud/violation blacklist. Disbursing funds to this entity is strictly prohibited.",
    };
  }
  if (upper.includes("AMOUNT_OVER_10K")) {
    return {
      bg: "bg-purple-50",
      text: "text-purple-900",
      border: "border-purple-300 ring-2 ring-purple-200/50",
      badgeBg: "bg-purple-100",
      badgeText: "text-purple-800",
      label: "AMOUNT OVER $10K",
      detail: "The invoice total exceeds $10,000.00, requiring explicit executive VP sign-off per corporate financial controls.",
    };
  }
  if (upper.includes("SUSPICIOUS_STRUCTURING")) {
    return {
      bg: "bg-indigo-50",
      text: "text-indigo-900",
      border: "border-indigo-300 ring-2 ring-indigo-200/50",
      badgeBg: "bg-indigo-100",
      badgeText: "text-indigo-800",
      label: "SUSPICIOUS STRUCTURING",
      detail: "Total amount falls between $9,000 and $9,999.99 (just below the $10,000 threshold), indicating potential evasion of executive review.",
    };
  }
  if (upper.includes("STOCK_MISMATCH")) {
    return {
      bg: "bg-amber-50",
      text: "text-amber-900",
      border: "border-amber-400 ring-2 ring-amber-300/50",
      badgeBg: "bg-amber-500",
      badgeText: "text-white",
      label: "STOCK MISMATCH",
      detail: "The quantity invoiced exceeds available warehouse inventory stock recorded in SQLite. Verify physical delivery before paying.",
    };
  }
  if (upper.includes("UNKNOWN_ITEMS")) {
    return {
      bg: "bg-orange-50",
      text: "text-orange-900",
      border: "border-orange-300 ring-2 ring-orange-200/50",
      badgeBg: "bg-orange-100",
      badgeText: "text-orange-800",
      label: "UNKNOWN ITEMS",
      detail: "Line items could not be matched with standard catalog products. Potential unapproved purchase or custom SKU.",
    };
  }
  if (upper.includes("ARITHMETIC_ERROR")) {
    return {
      bg: "bg-red-50",
      text: "text-red-900",
      border: "border-red-400 ring-2 ring-red-300/50",
      badgeBg: "bg-red-600",
      badgeText: "text-white",
      label: "ARITHMETIC ERROR",
      detail: "Calculations on this invoice (subtotal, tax computation, or line totals) do not match expected sums.",
    };
  }
  if (upper.includes("EXACT_DUPLICATE")) {
    return {
      bg: "bg-blue-50",
      text: "text-blue-900",
      border: "border-blue-400 ring-2 ring-blue-300/50",
      badgeBg: "bg-blue-600",
      badgeText: "text-white",
      label: "EXACT DUPLICATE",
      detail: "100% identical line items, vendor, and amount were previously submitted. Double-payment fraud protection triggered.",
    };
  }
  if (upper.includes("SUSPICIOUS_OR_FRAUD") || upper.includes("WIRE")) {
    return {
      bg: "bg-rose-50",
      text: "text-rose-900",
      border: "border-rose-400 ring-2 ring-rose-300/50",
      badgeBg: "bg-rose-500",
      badgeText: "text-white",
      label: "FRAUD ANOMALY",
      detail: "Urgent pressure language, wire transfer preference, or suspicious keywords detected in document body.",
    };
  }
  // Default rule style
  return {
    bg: "bg-amber-50",
    text: "text-amber-900",
    border: "border-amber-300",
    badgeBg: "bg-amber-100",
    badgeText: "text-amber-800",
    label: ruleStr.split(":")[0] || "RULE TRIGGERED",
    detail: ruleStr,
  };
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [invoices, setInvoices] = useState<InvoiceItem[]>([]);
  const [vendors, setVendors] = useState<VendorItem[]>([]);
  const [activeTab, setActiveTab] = useState<"pending" | "all" | "vendors">("pending");
  const [loading, setLoading] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>("");

  // Carousel state for pending invoices
  const [carouselIndex, setCarouselIndex] = useState<number>(0);

  // Upload state
  const [uploading, setUploading] = useState<boolean>(false);
  const [uploadFeedback, setUploadFeedback] = useState<UploadResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Modal / Detail state
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | null>(null);
  const [invoiceDetail, setInvoiceDetail] = useState<InvoiceItem | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);

  // Action status message banner
  const [actionNotice, setActionNotice] = useState<{
    type: "success" | "error" | "info" | "warning";
    title: string;
    message: string;
    paymentInfo?: any;
  } | null>(null);

  // Action in-progress tracking
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  // Load stats, invoices, and vendor registry
  const loadData = async (silent: boolean = false) => {
    if (!silent) setLoading(true);
    try {
      const [s, invs, vList] = await Promise.all([
        fetchStats(),
        fetchInvoices(activeTab === "pending" ? "pending" : "all"),
        fetchVendors().catch(() => []),
      ]);
      setStats(s);
      setInvoices(invs);
      setVendors(vList);
    } catch (err: any) {
      console.error("Failed loading data:", err);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    setCarouselIndex(0);
  }, [activeTab]);

  // Bulk / single file upload handler
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    setUploading(true);
    setUploadFeedback(null);
    setActionNotice(null);

    try {
      const res = await uploadInvoices(Array.from(files));
      setUploadFeedback(res);
      setActionNotice({
        type: "info",
        title: "Bulk Ingestion Processed",
        message: `Parsed ${res.summary.successful_ingestions} of ${res.summary.total_files} document(s). ${res.summary.auto_approved_paid} auto-approved & disbursed, ${res.summary.held_for_human_review} held for executive review.`,
      });
      await loadData(true);
    } catch (err: any) {
      setActionNotice({
        type: "error",
        title: "Upload Failed",
        message: err.message || "Failed to process files",
      });
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Human Approve & Pay
  const handleApprove = async (invoiceId: string) => {
    setActionLoadingId(invoiceId);
    setActionNotice(null);
    try {
      const result = await approveInvoice(
        invoiceId,
        "VP of Finance",
        "Executive approval granted after line-item & supplier verification"
      );

      setActionNotice({
        type: "success",
        title: `Payment Executed Successfully!`,
        message: `Invoice ${invoiceId} approved. Disbursed $${Number(
          result.amount_paid || 0
        ).toLocaleString("en-US", { minimumFractionDigits: 2 })} to ${result.vendor}. Database updated.`,
        paymentInfo: result.payment_details,
      });

      await loadData(true);
      if (selectedInvoiceId === invoiceId) {
        handleViewDetail(invoiceId);
      }
    } catch (err: any) {
      setActionNotice({
        type: "error",
        title: "Approval Failed",
        message: err.message || "Failed to approve and execute disbursement",
      });
    } finally {
      setActionLoadingId(null);
    }
  };

  // Standard Reject
  const handleReject = async (invoiceId: string) => {
    setActionLoadingId(invoiceId);
    setActionNotice(null);
    try {
      await rejectInvoice(
        invoiceId,
        "VP of Finance",
        "Rejected due to document discrepancy, arithmetic error, or policy violation"
      );

      setActionNotice({
        type: "info",
        title: `Invoice ${invoiceId} Rejected`,
        message: `Payment blocked. Invoice marked as REJECTED in database.`,
      });

      await loadData(true);
      if (selectedInvoiceId === invoiceId) {
        handleViewDetail(invoiceId);
      }
    } catch (err: any) {
      setActionNotice({
        type: "error",
        title: "Rejection Failed",
        message: err.message || "Failed to reject invoice",
      });
    } finally {
      setActionLoadingId(null);
    }
  };

  // Reject & Blacklist Company
  const handleRejectAndBlock = async (invoiceId: string) => {
    setActionLoadingId(invoiceId);
    setActionNotice(null);
    try {
      const res = await rejectAndBlockInvoice(
        invoiceId,
        "VP of Finance",
        "Rejected for fraudulent activity. Vendor has been added to the Executive Blacklist."
      );

      setActionNotice({
        type: "warning",
        title: `Invoice Rejected & Company Blacklisted!`,
        message: `Invoice ${invoiceId} was rejected, and vendor '${res.vendor}' has been permanently added to the company Blacklist. Future invoices from this vendor will be blocked.`,
      });

      await loadData(true);
      if (selectedInvoiceId === invoiceId) {
        handleViewDetail(invoiceId);
      }
    } catch (err: any) {
      setActionNotice({
        type: "error",
        title: "Reject & Block Failed",
        message: err.message || "Failed to block vendor",
      });
    } finally {
      setActionLoadingId(null);
    }
  };

  // Manage Vendor Status from Directory Tab
  const handleUpdateVendorStatus = async (
    vendorName: string,
    status: "whitelisted" | "blacklisted" | "standard"
  ) => {
    try {
      const reason =
        status === "blacklisted"
          ? "Blacklisted via Company Directory Governance"
          : status === "whitelisted"
          ? "Whitelisted as trusted supplier"
          : "Reset to standard review policy";

      await updateVendorStatus(vendorName, status, reason);
      setActionNotice({
        type: status === "blacklisted" ? "warning" : "success",
        title: `Vendor Updated`,
        message: `Vendor '${vendorName}' is now set to ${status.toUpperCase()}.`,
      });
      await loadData(true);
    } catch (err: any) {
      setActionNotice({
        type: "error",
        title: "Update Failed",
        message: err.message || "Failed to update vendor status",
      });
    }
  };

  // View Invoice Detail Modal
  const handleViewDetail = async (invoiceId: string) => {
    setSelectedInvoiceId(invoiceId);
    setLoadingDetail(true);
    try {
      const detail = await fetchInvoiceDetail(invoiceId);
      setInvoiceDetail(detail);
    } catch (err) {
      console.error("Failed fetching invoice detail:", err);
    } finally {
      setLoadingDetail(false);
    }
  };

  const closeModal = () => {
    setSelectedInvoiceId(null);
    setInvoiceDetail(null);
  };

  // Filtered invoices by search term
  const pendingInvoices = invoices.filter((inv) => inv.ui_status === "pending_approval");
  const filteredInvoices = invoices.filter((inv) => {
    const term = searchTerm.toLowerCase();
    return (
      inv.invoice_id.toLowerCase().includes(term) ||
      inv.vendor_name.toLowerCase().includes(term) ||
      (inv.rules_triggered && inv.rules_triggered.some((r) => r.toLowerCase().includes(term)))
    );
  });

  const filteredVendors = vendors.filter((v) =>
    v.vendor_name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      {/* Top Header */}
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
          <div className="flex items-center space-x-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-700 to-violet-600 text-white shadow-md shadow-indigo-100">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-slate-900">
                  InvoiceGuard AI
                </h1>
                <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-semibold text-indigo-600 border border-indigo-200">
                  FastAPI + Next.js
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Multi-Format Ingestion, Vendor Blacklisting/Whitelisting & Executive Disbursement
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              onClick={() => loadData()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition-colors cursor-pointer"
              title="Refresh data"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              Sync
            </button>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 transition-all disabled:opacity-50 cursor-pointer"
            >
              <UploadCloud className="h-4 w-4" />
              {uploading ? "Ingesting..." : "Bulk Upload"}
            </button>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              multiple
              accept=".json,.xml,.csv,.txt,.pdf"
              className="hidden"
            />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 space-y-6">
        {/* Notice Banner */}
        {actionNotice && (
          <div
            className={`rounded-xl border p-4 shadow-sm transition-all duration-300 ${
              actionNotice.type === "success"
                ? "border-emerald-200 bg-emerald-50/90 text-emerald-900"
                : actionNotice.type === "warning"
                ? "border-amber-300 bg-amber-50 text-amber-900"
                : actionNotice.type === "error"
                ? "border-rose-200 bg-rose-50 text-rose-900"
                : "border-sky-200 bg-sky-50 text-sky-900"
            }`}
          >
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                {actionNotice.type === "success" ? (
                  <CheckCircle2 className="h-6 w-6 text-emerald-600 mt-0.5 flex-shrink-0" />
                ) : actionNotice.type === "warning" ? (
                  <ShieldBan className="h-6 w-6 text-amber-600 mt-0.5 flex-shrink-0" />
                ) : actionNotice.type === "error" ? (
                  <XCircle className="h-6 w-6 text-rose-600 mt-0.5 flex-shrink-0" />
                ) : (
                  <Sparkles className="h-6 w-6 text-sky-600 mt-0.5 flex-shrink-0" />
                )}
                <div>
                  <h4 className="font-semibold text-sm">{actionNotice.title}</h4>
                  <p className="mt-1 text-sm leading-relaxed">{actionNotice.message}</p>
                  {actionNotice.paymentInfo && (
                    <div className="mt-2.5 rounded-lg bg-white/80 border border-emerald-200 p-2.5 text-xs text-slate-700 font-mono">
                      <div className="flex justify-between py-0.5">
                        <span className="text-slate-500">Payment ID:</span>
                        <span className="font-semibold text-slate-900">
                          {actionNotice.paymentInfo.payment_id}
                        </span>
                      </div>
                      <div className="flex justify-between py-0.5">
                        <span className="text-slate-500">Method:</span>
                        <span>MOCK_WIRE_TRANSFER</span>
                      </div>
                      <div className="flex justify-between py-0.5">
                        <span className="text-slate-500">Disbursed To:</span>
                        <span>{actionNotice.paymentInfo.vendor}</span>
                      </div>
                      <div className="flex justify-between py-0.5 border-t border-emerald-100 mt-1 pt-1">
                        <span className="text-slate-500 font-sans">Authorized By:</span>
                        <span className="font-sans font-medium text-emerald-800">
                          {actionNotice.paymentInfo.approved_by}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
              <button
                onClick={() => setActionNotice(null)}
                className="text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        {/* Executive KPI Stats Cards */}
        {stats && (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
                  Total Processed
                </span>
                <span className="rounded-md bg-slate-100 p-1.5 text-slate-600">
                  <FileText className="h-4 w-4" />
                </span>
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-bold tracking-tight text-slate-900">
                  {stats.total_invoices}
                </span>
                <span className="text-xs text-slate-500">documents</span>
              </div>
            </div>

            <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-amber-800">
                  Action Required
                </span>
                <span className="rounded-md bg-amber-100 p-1.5 text-amber-700">
                  <Clock className="h-4 w-4" />
                </span>
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-bold tracking-tight text-amber-900">
                  {stats.pending_approvals}
                </span>
                <span className="text-xs font-medium text-amber-700">held for human review</span>
              </div>
            </div>

            <div className="rounded-xl border border-emerald-200 bg-emerald-50/40 p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-emerald-800">
                  Total Disbursed
                </span>
                <span className="rounded-md bg-emerald-100 p-1.5 text-emerald-700">
                  <DollarSign className="h-4 w-4" />
                </span>
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-bold tracking-tight text-emerald-900">
                  ${stats.total_disbursed.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                </span>
                <span className="text-xs text-emerald-700">
                  ({stats.approved_count} approved)
                </span>
              </div>
            </div>

            <div className="rounded-xl border border-rose-200 bg-rose-50/40 p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-rose-800">
                  Flagged Suspicious
                </span>
                <span className="rounded-md bg-rose-100 p-1.5 text-rose-700">
                  <ShieldAlert className="h-4 w-4" />
                </span>
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-bold tracking-tight text-rose-900">
                  {stats.suspicious_count}
                </span>
                <span className="text-xs text-rose-700">
                  ({stats.rejected_count} rejected)
                </span>
              </div>
            </div>
          </div>
        )}

        {/* PENDING APPROVALS CAROUSEL */}
        {pendingInvoices.length > 0 && activeTab !== "vendors" && (
          <div className="rounded-2xl border border-amber-200 bg-gradient-to-r from-amber-500/10 via-amber-500/5 to-white p-5 shadow-sm">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500 text-white font-bold text-xs">
                  ★
                </span>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    Pending Invoices Carousel ({pendingInvoices.length} awaiting executive action)
                  </h3>
                  <p className="text-xs text-slate-500">
                    Cycle through invoices requiring human review with one-click decision controls
                  </p>
                </div>
              </div>

              {/* Carousel Controls */}
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-slate-600">
                  {carouselIndex + 1} of {pendingInvoices.length}
                </span>
                <button
                  onClick={() =>
                    setCarouselIndex((prev) => (prev > 0 ? prev - 1 : pendingInvoices.length - 1))
                  }
                  className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-600 hover:bg-slate-100 transition-colors cursor-pointer"
                  title="Previous"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <button
                  onClick={() =>
                    setCarouselIndex((prev) => (prev < pendingInvoices.length - 1 ? prev + 1 : 0))
                  }
                  className="rounded-lg border border-slate-200 bg-white p-1.5 text-slate-600 hover:bg-slate-100 transition-colors cursor-pointer"
                  title="Next"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Active Carousel Card */}
            {pendingInvoices[carouselIndex] && (
              <div className="rounded-xl border border-amber-200/90 bg-white p-5 shadow-md">
                <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                  {/* Left Column */}
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-lg font-bold text-slate-900">
                        {pendingInvoices[carouselIndex].invoice_id}
                      </span>
                      {pendingInvoices[carouselIndex].revision && (
                        <span className="rounded-md bg-indigo-50 border border-indigo-200 px-2 py-0.5 text-xs font-semibold text-indigo-700">
                          Rev: {pendingInvoices[carouselIndex].revision}
                        </span>
                      )}
                      <span className="rounded-md bg-amber-100 text-amber-900 px-2.5 py-0.5 text-xs font-bold">
                        ACTION REQUIRED
                      </span>
                      {pendingInvoices[carouselIndex].vendor_status === "blacklisted" && (
                        <span className="rounded-md bg-rose-600 text-white px-2 py-0.5 text-xs font-bold flex items-center gap-1">
                          <ShieldBan className="h-3 w-3" /> BLACKLISTED VENDOR
                        </span>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-slate-600">
                      <span className="font-semibold text-slate-900 text-sm">
                        {pendingInvoices[carouselIndex].vendor_name}
                      </span>
                      <span>Date: {pendingInvoices[carouselIndex].date}</span>
                      <span>Due: {pendingInvoices[carouselIndex].due_date}</span>
                      <span className="font-mono font-bold text-slate-900 text-base">
                        {pendingInvoices[carouselIndex].currency} $
                        {Number(pendingInvoices[carouselIndex].total).toLocaleString("en-US", {
                          minimumFractionDigits: 2,
                        })}
                      </span>
                    </div>

                    {/* Triggered Rule Badges with tooltips */}
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {pendingInvoices[carouselIndex].rules_triggered?.map((rule, idx) => {
                        const style = getRuleStyle(rule);
                        return (
                          <div
                            key={idx}
                            className="group relative inline-flex items-center cursor-help"
                          >
                            <span
                              className={`rounded px-2.5 py-1 text-xs font-bold shadow-sm ${style.badgeBg} ${style.badgeText}`}
                            >
                              {style.label}
                            </span>
                            {/* Hover Tooltip */}
                            <div className="pointer-events-none absolute bottom-full left-0 z-50 mb-2 hidden w-64 rounded-lg bg-slate-900 p-2.5 text-[11px] text-white shadow-xl group-hover:block transition-all">
                              <p className="font-semibold text-amber-300">{style.label}</p>
                              <p className="mt-1 text-slate-300">{style.detail}</p>
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {/* Critique quote */}
                    {pendingInvoices[carouselIndex].critique && (
                      <p className="text-xs text-slate-700 italic border-l-2 border-amber-500 pl-2 mt-1">
                        &ldquo;{pendingInvoices[carouselIndex].critique}&rdquo;
                      </p>
                    )}
                  </div>

                  {/* Right Column Action Buttons */}
                  <div className="flex flex-wrap items-center gap-2 self-start lg:self-center">
                    <button
                      onClick={() => handleViewDetail(pendingInvoices[carouselIndex].invoice_id)}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 transition-colors cursor-pointer"
                    >
                      <Eye className="h-3.5 w-3.5 text-slate-500" />
                      Inspect Invoice
                    </button>

                    <button
                      onClick={() => handleApprove(pendingInvoices[carouselIndex].invoice_id)}
                      disabled={actionLoadingId === pendingInvoices[carouselIndex].invoice_id}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow-sm hover:bg-emerald-700 focus:ring-2 focus:ring-emerald-500 transition-all disabled:opacity-50 cursor-pointer"
                    >
                      {actionLoadingId === pendingInvoices[carouselIndex].invoice_id ? (
                        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Check className="h-3.5 w-3.5 stroke-[3]" />
                      )}
                      Approve & Pay
                    </button>

                    <button
                      onClick={() => handleReject(pendingInvoices[carouselIndex].invoice_id)}
                      disabled={actionLoadingId === pendingInvoices[carouselIndex].invoice_id}
                      className="inline-flex items-center gap-1 rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100 transition-colors disabled:opacity-50 cursor-pointer"
                    >
                      <X className="h-3.5 w-3.5" />
                      Reject
                    </button>

                    {/* REJECT & BLOCK BUTTON */}
                    <button
                      onClick={() => handleRejectAndBlock(pendingInvoices[carouselIndex].invoice_id)}
                      disabled={actionLoadingId === pendingInvoices[carouselIndex].invoice_id}
                      className="inline-flex items-center gap-1 rounded-lg bg-rose-600 px-3 py-2 text-xs font-bold text-white shadow-sm hover:bg-rose-700 transition-colors disabled:opacity-50 cursor-pointer"
                      title="Rejects this invoice and adds the company to the blacklist"
                    >
                      <ShieldBan className="h-3.5 w-3.5" />
                      Reject & Block Vendor
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Drag-and-Drop Bulk Upload quick zone */}
        <div
          onClick={() => fileInputRef.current?.click()}
          className="group relative flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-300 bg-white p-5 text-center hover:border-indigo-400 hover:bg-indigo-50/20 transition-all shadow-sm"
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-50 text-indigo-600 group-hover:scale-110 transition-transform">
            <UploadCloud className="h-5 w-5" />
          </div>
          <h3 className="mt-2 text-sm font-semibold text-slate-800">
            {uploading ? "Ingesting Documents with AI & Business Guards..." : "Upload Invoices (Single or Bulk Batch)"}
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Accepts <span className="font-semibold text-slate-700">JSON, XML, CSV, TXT, and PDF</span>. Automatic stock check, VP critique & fraud detection.
          </p>
        </div>

        {/* Navigation Tabs and Search */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-slate-200 pb-3">
          <div className="flex flex-wrap items-center gap-1">
            <button
              onClick={() => setActiveTab("pending")}
              className={`rounded-lg px-3.5 py-2 text-xs font-semibold transition-all cursor-pointer ${
                activeTab === "pending"
                  ? "bg-amber-100 text-amber-900 shadow-sm"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              Action Required ({pendingInvoices.length})
            </button>
            <button
              onClick={() => setActiveTab("all")}
              className={`rounded-lg px-3.5 py-2 text-xs font-semibold transition-all cursor-pointer ${
                activeTab === "all"
                  ? "bg-slate-900 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              All Invoices & Ledger ({invoices.length})
            </button>
            {/* VENDOR GOVERNANCE TAB */}
            <button
              onClick={() => setActiveTab("vendors")}
              className={`rounded-lg px-3.5 py-2 text-xs font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                activeTab === "vendors"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              <ShieldCheck className="h-3.5 w-3.5" />
              Company Governance (Blacklist / Whitelist)
            </button>
          </div>

          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input
              type="text"
              placeholder={activeTab === "vendors" ? "Search company..." : "Search invoice, vendor, or rule..."}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full sm:w-64 rounded-lg border border-slate-200 bg-white py-1.5 pl-9 pr-3 text-xs text-slate-800 placeholder-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 shadow-sm"
            />
          </div>
        </div>

        {/* Tab 1 & 2: Invoices List View */}
        {activeTab !== "vendors" && (
          <div className="space-y-4">
            {loading ? (
              <div className="flex flex-col items-center justify-center py-16 text-slate-400">
                <RefreshCw className="h-8 w-8 animate-spin text-indigo-500" />
                <p className="mt-3 text-sm">Loading invoice portfolio...</p>
              </div>
            ) : filteredInvoices.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center">
                <FileText className="mx-auto h-10 w-10 text-slate-300" />
                <h3 className="mt-2 text-sm font-semibold text-slate-700">No invoices found</h3>
                <p className="mt-1 text-xs text-slate-500">
                  {activeTab === "pending"
                    ? "No pending approvals! All invoices have been reviewed."
                    : "No invoices matched your filter or search query."}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4">
                {filteredInvoices.map((inv) => {
                  const isPending = inv.ui_status === "pending_approval";
                  const isPaid = inv.ui_status === "paid";
                  const isRejected = inv.ui_status === "rejected";
                  const isBlacklisted = inv.vendor_status === "blacklisted";

                  return (
                    <div
                      key={`${inv.invoice_id}-${inv.id}`}
                      className={`group relative overflow-hidden rounded-xl border bg-white p-5 shadow-sm transition-all hover:shadow-md ${
                        isBlacklisted
                          ? "border-rose-400/80 bg-rose-50/10"
                          : isPending
                          ? "border-amber-200 hover:border-amber-300"
                          : isPaid
                          ? "border-slate-200 hover:border-emerald-300"
                          : "border-slate-200 hover:border-rose-300"
                      }`}
                    >
                      {/* Left Accent Bar */}
                      <div
                        className={`absolute inset-y-0 left-0 w-1.5 ${
                          isBlacklisted
                            ? "bg-rose-600"
                            : isPending
                            ? "bg-amber-500"
                            : isPaid
                            ? "bg-emerald-500"
                            : "bg-rose-500"
                        }`}
                      />

                      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                        {/* Details */}
                        <div className="space-y-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-base font-bold text-slate-900">
                              {inv.invoice_id}
                            </span>
                            {inv.revision && (
                              <span className="rounded-md bg-indigo-50 border border-indigo-200 px-2 py-0.5 text-xs font-semibold text-indigo-700">
                                Rev: {inv.revision}
                              </span>
                            )}

                            {/* Status Badge */}
                            {isPending && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
                                <Clock className="h-3 w-3" /> PENDING APPROVAL
                              </span>
                            )}
                            {isPaid && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-800">
                                <CheckCircle2 className="h-3 w-3" /> PAID (${Number(inv.total).toLocaleString()})
                              </span>
                            )}
                            {isRejected && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2.5 py-0.5 text-xs font-semibold text-rose-800">
                                <XCircle className="h-3 w-3" /> REJECTED
                              </span>
                            )}

                            {/* Vendor Status Tag */}
                            {isBlacklisted && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-rose-600 px-2.5 py-0.5 text-xs font-bold text-white shadow-sm">
                                <ShieldBan className="h-3 w-3" /> BLACKLISTED VENDOR
                              </span>
                            )}
                            {inv.vendor_status === "whitelisted" && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-bold text-emerald-800">
                                <UserCheck className="h-3 w-3" /> WHITELISTED
                              </span>
                            )}

                            <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 uppercase">
                              {inv.format_detected}
                            </span>
                          </div>

                          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600">
                            <div className="flex items-center gap-1 font-medium text-slate-800">
                              <Building className="h-3.5 w-3.5 text-slate-400" />
                              {inv.vendor_name}
                            </div>
                            <div className="flex items-center gap-1">
                              <Calendar className="h-3.5 w-3.5 text-slate-400" />
                              Date: {inv.date} | Due: {inv.due_date}
                            </div>
                            <div className="font-mono font-semibold text-slate-900 text-sm">
                              Total: {inv.currency} ${Number(inv.total).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                            </div>
                          </div>

                          {/* Rule Badges with Tooltips */}
                          {inv.rules_triggered && inv.rules_triggered.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 pt-1">
                              {inv.rules_triggered.map((rule, idx) => {
                                const style = getRuleStyle(rule);
                                return (
                                  <div
                                    key={idx}
                                    className="group relative inline-flex items-center cursor-help"
                                  >
                                    <span
                                      className={`rounded px-2 py-0.5 text-[11px] font-bold ${style.badgeBg} ${style.badgeText}`}
                                    >
                                      {style.label}
                                    </span>
                                    <div className="pointer-events-none absolute bottom-full left-0 z-50 mb-1.5 hidden w-64 rounded-lg bg-slate-900 p-2.5 text-[11px] text-white shadow-xl group-hover:block transition-all">
                                      <p className="font-semibold text-amber-300">{style.label}</p>
                                      <p className="mt-1 text-slate-300">{style.detail}</p>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}

                          {/* Disbursed Note */}
                          {isPaid && inv.payment_details && (
                            <div className="mt-1 text-xs text-emerald-800 flex items-center gap-2">
                              <span className="font-semibold">Disbursed:</span>
                              <span>
                                Paid ${Number(inv.payment_details.amount_paid || inv.total).toLocaleString()}{" "}
                                to {inv.vendor_name} via {inv.payment_details.payment_id || "Wire"}
                              </span>
                              {inv.human_reviewer && (
                                <span className="text-slate-500 font-medium">
                                  (Approved by {inv.human_reviewer})
                                </span>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Actions */}
                        <div className="flex flex-wrap items-center gap-2 self-end lg:self-center">
                          <button
                            onClick={() => handleViewDetail(inv.invoice_id)}
                            className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 transition-colors cursor-pointer"
                          >
                            <Eye className="h-3.5 w-3.5 text-slate-500" />
                            Inspect
                          </button>

                          {isPending && (
                            <>
                              <button
                                onClick={() => handleApprove(inv.invoice_id)}
                                disabled={actionLoadingId === inv.invoice_id}
                                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-bold text-white shadow-sm hover:bg-emerald-700 transition-all disabled:opacity-50 cursor-pointer"
                              >
                                {actionLoadingId === inv.invoice_id ? (
                                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                                ) : (
                                  <Check className="h-3.5 w-3.5 stroke-[3]" />
                                )}
                                Approve & Pay
                              </button>
                              <button
                                onClick={() => handleReject(inv.invoice_id)}
                                disabled={actionLoadingId === inv.invoice_id}
                                className="inline-flex items-center gap-1 rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100 transition-colors disabled:opacity-50 cursor-pointer"
                              >
                                <X className="h-3.5 w-3.5" />
                                Reject
                              </button>
                              <button
                                onClick={() => handleRejectAndBlock(inv.invoice_id)}
                                disabled={actionLoadingId === inv.invoice_id}
                                className="inline-flex items-center gap-1 rounded-lg bg-rose-600 px-3 py-2 text-xs font-bold text-white shadow-sm hover:bg-rose-700 transition-colors disabled:opacity-50 cursor-pointer"
                                title="Reject and blacklist vendor"
                              >
                                <ShieldBan className="h-3.5 w-3.5" />
                                Reject & Block
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* TAB 3: COMPANY GOVERNANCE (BLACKLIST / WHITELIST) */}
        {activeTab === "vendors" && (
          <div className="space-y-4">
            <div className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-4 text-xs text-indigo-900">
              <h4 className="font-bold text-sm text-indigo-950 flex items-center gap-2 mb-1">
                <ShieldCheck className="h-4 w-4 text-indigo-600" />
                Corporate Vendor Trust & Governance Registry
              </h4>
              <p className="text-slate-600">
                Manage vendor compliance statuses. Invoices from <strong>Blacklisted</strong> companies are automatically intercepted and prohibited from executive disbursement. Whitelisted companies represent pre-cleared, verified vendors.
              </p>
            </div>

            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-700 border-b border-slate-200 font-semibold">
                  <tr>
                    <th className="px-4 py-3">Vendor / Entity Name</th>
                    <th className="px-3 py-3">Trust Status</th>
                    <th className="px-3 py-3 text-right">Total Invoices</th>
                    <th className="px-3 py-3 text-right">Total Billed</th>
                    <th className="px-3 py-3 text-center">Suspicious Flags</th>
                    <th className="px-4 py-3">Audit Reason</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredVendors.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                        No vendors registered yet.
                      </td>
                    </tr>
                  ) : (
                    filteredVendors.map((v, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/70">
                        <td className="px-4 py-3 font-semibold text-slate-900">
                          {v.vendor_name}
                        </td>
                        <td className="px-3 py-3">
                          {v.status === "blacklisted" ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2.5 py-0.5 text-xs font-bold text-rose-800">
                              <ShieldBan className="h-3 w-3 text-rose-600" /> BLACKLISTED
                            </span>
                          ) : v.status === "whitelisted" ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-bold text-emerald-800">
                              <UserCheck className="h-3 w-3 text-emerald-600" /> WHITELISTED
                            </span>
                          ) : (
                            <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">
                              STANDARD
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-3 text-right font-mono font-medium">
                          {v.total_invoices}
                        </td>
                        <td className="px-3 py-3 text-right font-mono font-bold text-slate-900">
                          ${Number(v.total_amount).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="px-3 py-3 text-center">
                          {v.suspicious_count > 0 ? (
                            <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-800">
                              {v.suspicious_count} flagged
                            </span>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-slate-600 italic">
                          {v.reason || "Standard supplier record"}
                        </td>
                        <td className="px-4 py-3 text-right space-x-1.5">
                          {v.status !== "whitelisted" && (
                            <button
                              onClick={() => handleUpdateVendorStatus(v.vendor_name, "whitelisted")}
                              className="rounded-md border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-[11px] font-bold text-emerald-700 hover:bg-emerald-100 transition-colors cursor-pointer"
                            >
                              Whitelist
                            </button>
                          )}
                          {v.status !== "blacklisted" && (
                            <button
                              onClick={() => handleUpdateVendorStatus(v.vendor_name, "blacklisted")}
                              className="rounded-md border border-rose-300 bg-rose-50 px-2.5 py-1 text-[11px] font-bold text-rose-700 hover:bg-rose-100 transition-colors cursor-pointer"
                            >
                              Blacklist
                            </button>
                          )}
                          {v.status !== "standard" && (
                            <button
                              onClick={() => handleUpdateVendorStatus(v.vendor_name, "standard")}
                              className="rounded-md border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-600 hover:bg-slate-100 transition-colors cursor-pointer"
                            >
                              Reset
                            </button>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      {/* REALISTIC INVOICE-STYLE INSPECTION MODAL */}
      {selectedInvoiceId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/70 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="relative w-full max-w-4xl rounded-2xl bg-white shadow-2xl border border-slate-300 overflow-hidden my-6">
            {/* Modal Top Bar */}
            <div className="flex items-center justify-between border-b border-slate-200 bg-slate-100 px-6 py-3">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="h-5 w-5 text-indigo-600" />
                <span className="font-bold text-sm text-slate-800">
                  Document Inspector: {selectedInvoiceId}
                </span>
              </div>
              <button
                onClick={closeModal}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors cursor-pointer"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Modal Body: Realistic Invoice Layout */}
            <div className="p-8 space-y-6 max-h-[80vh] overflow-y-auto bg-slate-50/50">
              {loadingDetail || !invoiceDetail ? (
                <div className="flex flex-col items-center justify-center py-16 text-slate-400">
                  <RefreshCw className="h-7 w-7 animate-spin text-indigo-600" />
                  <p className="mt-2 text-xs">Rendering invoice document...</p>
                </div>
              ) : (
                <div className="rounded-xl border border-slate-300 bg-white p-8 shadow-sm space-y-6 font-sans">
                  {/* INVOICE HEADER */}
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between border-b border-slate-200 pb-6 gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-3xl font-extrabold tracking-tight text-slate-900">
                          INVOICE
                        </h2>
                        {invoiceDetail.revision && (
                          <span className="rounded bg-indigo-100 text-indigo-800 px-2 py-0.5 text-xs font-bold">
                            Rev: {invoiceDetail.revision}
                          </span>
                        )}
                      </div>
                      <p className="font-mono text-xs text-slate-500 mt-1">
                        Invoice Reference: <span className="font-bold text-slate-800">{invoiceDetail.invoice_id}</span>
                      </p>
                      <p className="text-xs text-slate-500">
                        Format Ingested: <span className="uppercase font-semibold text-slate-700">{invoiceDetail.format_detected}</span>
                      </p>
                    </div>

                    {/* Vendor Box */}
                    <div
                      className={`rounded-lg p-3 text-right max-w-sm border ${
                        invoiceDetail.vendor_status === "blacklisted"
                          ? "border-rose-400 bg-rose-50/60"
                          : "border-slate-200 bg-slate-50"
                      }`}
                    >
                      <div className="flex items-center justify-end gap-1.5 font-bold text-slate-900 text-base">
                        {invoiceDetail.vendor_status === "blacklisted" && (
                          <div className="group relative cursor-help">
                            <ShieldBan className="h-4 w-4 text-rose-600" />
                            <div className="pointer-events-none absolute right-0 bottom-full z-50 mb-1 hidden w-56 rounded bg-slate-900 p-2 text-[10px] text-white shadow-lg group-hover:block">
                              BLACKLISTED COMPANY: Past fraud or compliance violation.
                            </div>
                          </div>
                        )}
                        <span>{invoiceDetail.vendor_name}</span>
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {invoiceDetail.vendor_address || "Corporate Vendor Headquarters"}
                      </p>
                      {invoiceDetail.vendor_status === "blacklisted" && (
                        <p className="text-[11px] font-bold text-rose-600 mt-1">
                          ⚠️ EXECUTIVE BLACKLIST ENFORCED
                        </p>
                      )}
                    </div>
                  </div>

                  {/* METADATA BAR */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 rounded-lg bg-slate-50 p-4 border border-slate-200 text-xs">
                    <div>
                      <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold">
                        Invoice Date
                      </span>
                      <p className="font-bold text-slate-900 mt-0.5">{invoiceDetail.date}</p>
                    </div>
                    <div>
                      <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold">
                        Payment Due Date
                      </span>
                      <p className="font-bold text-slate-900 mt-0.5">{invoiceDetail.due_date}</p>
                    </div>
                    <div>
                      <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold">
                        Payment Terms
                      </span>
                      <p className="font-bold text-slate-900 mt-0.5">
                        {invoiceDetail.payment_terms || "Net 30"}
                        {invoiceDetail.payment_terms_days ? ` (${invoiceDetail.payment_terms_days} days)` : ""}
                      </p>
                    </div>
                    <div>
                      <span className="text-slate-500 uppercase tracking-wider text-[10px] font-semibold">
                        Approval Status
                      </span>
                      <p
                        className={`font-bold mt-0.5 uppercase ${
                          invoiceDetail.ui_status === "paid"
                            ? "text-emerald-600"
                            : invoiceDetail.ui_status === "rejected"
                            ? "text-rose-600"
                            : "text-amber-600"
                        }`}
                      >
                        {invoiceDetail.ui_status.replace("_", " ")}
                      </p>
                    </div>
                  </div>

                  {/* ANOMALIES & RULE TRIGGER CALLOUT */}
                  {invoiceDetail.rules_triggered && invoiceDetail.rules_triggered.length > 0 && (
                    <div className="rounded-xl border border-amber-200 bg-amber-50/40 p-4">
                      <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                        <AlertTriangle className="h-4 w-4 text-amber-600" />
                        Color-Coded Anomaly Flags (Hover badge for full explanation):
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {invoiceDetail.rules_triggered.map((r, idx) => {
                          const style = getRuleStyle(r);
                          return (
                            <div
                              key={idx}
                              className="group relative inline-flex items-center cursor-help"
                            >
                              <span
                                className={`rounded-lg px-3 py-1 text-xs font-bold shadow-sm ${style.badgeBg} ${style.badgeText}`}
                              >
                                {style.label}
                              </span>
                              {/* Hover Tooltip Box */}
                              <div className="pointer-events-none absolute bottom-full left-0 z-50 mb-2 hidden w-72 rounded-lg bg-slate-900 p-3 text-xs text-white shadow-2xl group-hover:block transition-all">
                                <div className="font-bold text-amber-300 mb-1">{style.label}</div>
                                <p className="text-slate-200 leading-relaxed">{style.detail}</p>
                                <div className="mt-1.5 border-t border-slate-700 pt-1 text-[10px] text-slate-400 font-mono">
                                  Raw: {r}
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      {/* AI Critique Text */}
                      {invoiceDetail.review?.critique && (
                        <p className="mt-3 text-xs text-slate-700 italic border-l-2 border-amber-500 pl-3">
                          &ldquo;{invoiceDetail.review.critique}&rdquo;
                        </p>
                      )}
                    </div>
                  )}

                  {/* LINE ITEMS TABLE (SHOWING NOTES, CATALOG STATUS & WAREHOUSE STOCK) */}
                  <div>
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2 flex items-center gap-1.5">
                      <Layers className="h-4 w-4 text-slate-400" />
                      Line Items & Stock Verification
                    </h4>
                    <div className="overflow-x-auto rounded-lg border border-slate-200">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-100 text-slate-700 font-semibold border-b border-slate-200">
                          <tr>
                            <th className="px-4 py-2.5">Item Description & Item Notes</th>
                            <th className="px-3 py-2.5 text-right">Quantity</th>
                            <th className="px-3 py-2.5 text-right">Unit Price</th>
                            <th className="px-3 py-2.5 text-right">Line Total</th>
                            <th className="px-4 py-2.5 text-center">Warehouse Stock Check</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200">
                          {invoiceDetail.line_items?.map((item, idx) => (
                            <tr key={idx} className="hover:bg-slate-50">
                              <td className="px-4 py-3">
                                <div className="font-bold text-slate-900 flex items-center gap-1.5">
                                  {item.item}
                                  {item.product_id && (
                                    <span className="text-[10px] font-mono font-normal text-slate-400">
                                      ({item.product_id})
                                    </span>
                                  )}
                                </div>
                                {/* Line Item Note Display */}
                                {item.note && (
                                  <div className="mt-0.5 text-[11px] font-medium text-indigo-600">
                                    Note: {item.note}
                                  </div>
                                )}
                              </td>
                              <td className="px-3 py-3 text-right font-mono font-medium">
                                {item.quantity}
                              </td>
                              <td className="px-3 py-3 text-right font-mono text-slate-700">
                                ${Number(item.unit_price).toFixed(2)}
                              </td>
                              <td className="px-3 py-3 text-right font-mono font-bold text-slate-900">
                                ${Number(item.quantity * item.unit_price).toFixed(2)}
                              </td>
                              <td className="px-4 py-3 text-center">
                                {item.stock_status === "sufficient" ? (
                                  <span className="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-[10px] font-bold text-emerald-800">
                                    ✓ Available ({item.quantity_in_stock})
                                  </span>
                                ) : item.stock_status === "out_of_stock" ? (
                                  <span className="inline-flex items-center rounded-full bg-rose-100 px-2.5 py-0.5 text-[10px] font-bold text-rose-800">
                                    ⚠ Out of Stock (0)
                                  </span>
                                ) : item.stock_status === "mismatch" ? (
                                  <span className="inline-flex items-center rounded-full bg-amber-100 px-2.5 py-0.5 text-[10px] font-bold text-amber-800">
                                    Deficit ({item.quantity_in_stock} on hand)
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-[10px] font-semibold text-slate-600">
                                    Unlisted SKU
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* FINANCIAL TOTALS BREAKDOWN & NOTES SECTION */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
                    {/* Left: General Notes & Terms */}
                    <div className="space-y-3">
                      <div className="rounded-lg bg-slate-50 p-4 border border-slate-200 text-xs">
                        <span className="font-bold text-slate-800 uppercase tracking-wider text-[10px] block mb-1">
                          Invoice Notes & Instructions:
                        </span>
                        <p className="text-slate-700 leading-relaxed italic">
                          {invoiceDetail.notes || "No special instructions attached by vendor."}
                        </p>
                      </div>

                      {invoiceDetail.revisions && invoiceDetail.revisions.length > 0 && (
                        <div className="rounded-lg bg-indigo-50/50 p-3 border border-indigo-100 text-xs">
                          <span className="font-bold text-indigo-950 block mb-1">
                            Revision History:
                          </span>
                          {invoiceDetail.revisions.map((rev, idx) => (
                            <div key={idx} className="text-slate-600 text-[11px]">
                              <strong>Rev {rev.revision}:</strong> {rev.change_summary} ({rev.changed_at})
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Right: Calculations (Subtotal, Tax, Shipping, Total) */}
                    <div className="rounded-xl bg-slate-50 p-4 border border-slate-200 text-xs space-y-2">
                      <div className="flex justify-between text-slate-600">
                        <span>Subtotal:</span>
                        <span className="font-mono font-medium">
                          ${Number(invoiceDetail.subtotal || invoiceDetail.total).toFixed(2)}
                        </span>
                      </div>

                      <div className="flex justify-between text-slate-600">
                        <span>
                          Tax {invoiceDetail.tax_rate ? `(${Number(invoiceDetail.tax_rate * 100).toFixed(1)}%)` : ""}:
                        </span>
                        <span className="font-mono font-medium">
                          ${Number(invoiceDetail.tax_amount || 0).toFixed(2)}
                        </span>
                      </div>

                      {invoiceDetail.shipping !== null && invoiceDetail.shipping !== undefined && (
                        <div className="flex justify-between text-slate-600">
                          <span>Shipping / Freight:</span>
                          <span className="font-mono font-medium">
                            ${Number(invoiceDetail.shipping).toFixed(2)}
                          </span>
                        </div>
                      )}

                      <div
                        className={`flex justify-between text-sm font-bold pt-2 border-t ${
                          invoiceDetail.total > 10000
                            ? "border-purple-300 text-purple-900 bg-purple-50/80 p-2 rounded"
                            : "border-slate-300 text-slate-900"
                        }`}
                      >
                        <div className="flex items-center gap-1.5">
                          <span>Total Amount:</span>
                          {invoiceDetail.total > 10000 && (
                            <span className="text-[10px] bg-purple-600 text-white px-1.5 py-0.5 rounded font-semibold">
                              &gt;$10K VP
                            </span>
                          )}
                        </div>
                        <span className="font-mono text-base">
                          {invoiceDetail.currency} ${Number(invoiceDetail.total).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer Controls */}
            {invoiceDetail && invoiceDetail.ui_status === "pending_approval" && (
              <div className="flex flex-wrap items-center justify-end gap-2.5 border-t border-slate-200 bg-slate-100 px-6 py-3">
                <button
                  onClick={() => handleReject(invoiceDetail.invoice_id)}
                  disabled={actionLoadingId === invoiceDetail.invoice_id}
                  className="rounded-lg border border-rose-300 bg-white px-3.5 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-50 transition-colors cursor-pointer"
                >
                  Reject Invoice
                </button>
                <button
                  onClick={() => handleRejectAndBlock(invoiceDetail.invoice_id)}
                  disabled={actionLoadingId === invoiceDetail.invoice_id}
                  className="inline-flex items-center gap-1 rounded-lg bg-rose-600 px-3.5 py-2 text-xs font-bold text-white shadow-sm hover:bg-rose-700 transition-colors cursor-pointer"
                  title="Blacklist this company from future disbursements"
                >
                  <ShieldBan className="h-3.5 w-3.5" />
                  Reject & Block Company
                </button>
                <button
                  onClick={() => handleApprove(invoiceDetail.invoice_id)}
                  disabled={actionLoadingId === invoiceDetail.invoice_id}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-5 py-2 text-xs font-bold text-white shadow-sm hover:bg-emerald-700 transition-colors cursor-pointer"
                >
                  <Check className="h-4 w-4 stroke-[3]" />
                  Approve & Disburse Wire Payment
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
'''

target = r"d:\invoice-problem\frontend\src\app\page.tsx"
with open(target, "w", encoding="utf-8") as f:
    f.write(page_code)

print(f"Successfully generated page.tsx ({len(page_code)} bytes)")

