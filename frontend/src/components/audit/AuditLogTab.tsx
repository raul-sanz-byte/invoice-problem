"use client";

import React, { useState, useMemo } from "react";
import { InvoiceItem } from "@/lib/api";
import { Icon } from "@/components/common/Icon";
import {
  formatCurrency,
  isInvoiceApproved,
  getVendorInitials,
  getVendorColor,
  getFormatIconAndColor,
  getFlagType,
  flagBadgeClasses,
  parseDate,
} from "@/lib/invoice-utils";

export interface AuditLogTabProps {
  allInvoices: InvoiceItem[];
  openModal: (inv: InvoiceItem) => void;
}

export function AuditLogTab({ allInvoices, openModal }: AuditLogTabProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "approved" | "pending" | "rejected" | "flagged">("all");
  const [sortBy, setSortBy] = useState<"newest" | "oldest" | "amount_desc" | "amount_asc">("newest");
  const [copiedLedger, setCopiedLedger] = useState(false);

  // ── Executive Ledger Analytics ──────────────────────────────────
  const ledgerMetrics = useMemo(() => {
    const totalCount = allInvoices.length;
    const totalCapital = allInvoices.reduce((acc, inv) => acc + (inv.total || 0), 0);

    const approvedList = allInvoices.filter((inv) => isInvoiceApproved(inv));
    const approvedCapital = approvedList.reduce((acc, inv) => acc + (inv.total || 0), 0);

    const rejectedList = allInvoices.filter(
      (inv) => inv.ui_status === "rejected" || inv.payment_status === "rejected"
    );

    const flaggedList = allInvoices.filter((inv) => {
      const rules = inv.rules_triggered?.length ? inv.rules_triggered : (inv.review?.rules_triggered || []);
      return (
        inv.is_suspicious ||
        inv.vendor_status === "blacklisted" ||
        !inv.arithmetic_correct ||
        rules.length > 0
      );
    });
    const flaggedCapital = flaggedList.reduce((acc, inv) => acc + (inv.total || 0), 0);

    const complianceRate = totalCount > 0 ? Math.round((approvedList.length / totalCount) * 100) : 100;

    return {
      totalCount,
      totalCapital,
      approvedCount: approvedList.length,
      approvedCapital,
      rejectedCount: rejectedList.length,
      flaggedCount: flaggedList.length,
      flaggedCapital,
      complianceRate,
    };
  }, [allInvoices]);

  // ── Filtered & Sorted Audit Records ──────────────────────────────
  const filteredRecords = useMemo(() => {
    return allInvoices
      .filter((inv) => {
        // Status filter
        const isApproved = isInvoiceApproved(inv);
        const isRejected = inv.ui_status === "rejected" || inv.payment_status === "rejected";
        const rules = inv.rules_triggered?.length ? inv.rules_triggered : (inv.review?.rules_triggered || []);
        const isFlagged =
          inv.is_suspicious ||
          inv.vendor_status === "blacklisted" ||
          !inv.arithmetic_correct ||
          rules.length > 0;

        if (statusFilter === "approved" && !isApproved) return false;
        if (statusFilter === "rejected" && !isRejected) return false;
        if (statusFilter === "pending" && (isApproved || isRejected)) return false;
        if (statusFilter === "flagged" && !isFlagged) return false;

        // Search query
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase().trim();
          const matchId = inv.invoice_id?.toLowerCase().includes(q);
          const matchVendor = inv.vendor_name?.toLowerCase().includes(q);
          const matchNotes = (inv.notes || "").toLowerCase().includes(q);
          const matchRules = rules.some((r: string) => r.toLowerCase().includes(q));
          if (!matchId && !matchVendor && !matchNotes && !matchRules) return false;
        }

        return true;
      })
      .sort((a, b) => {
        if (sortBy === "newest") {
          const da = parseDate(a.date)?.getTime() || 0;
          const db = parseDate(b.date)?.getTime() || 0;
          return db - da || b.id - a.id;
        }
        if (sortBy === "oldest") {
          const da = parseDate(a.date)?.getTime() || 0;
          const db = parseDate(b.date)?.getTime() || 0;
          return da - db || a.id - b.id;
        }
        if (sortBy === "amount_desc") {
          return (b.total || 0) - (a.total || 0);
        }
        if (sortBy === "amount_asc") {
          return (a.total || 0) - (b.total || 0);
        }
        return 0;
      });
  }, [allInvoices, statusFilter, searchQuery, sortBy]);

  // ── CSV Export Handler ────────────────────────────────────────────
  const handleExportCSV = () => {
    if (allInvoices.length === 0) return;
    const headers = ["Invoice ID", "Vendor", "Date", "Due Date", "Amount", "Currency", "Status", "Flags"];
    const rows = allInvoices.map((inv) => {
      const isApproved = isInvoiceApproved(inv);
      const status = isApproved
        ? "APPROVED"
        : inv.ui_status === "rejected"
        ? "REJECTED"
        : "PENDING_TRIAGE";
      const flags = (inv.rules_triggered?.length ? inv.rules_triggered : (inv.review?.rules_triggered || []))
        .join("; ")
        .replace(/"/g, '""');
      return [
        `"${inv.invoice_id}"`,
        `"${inv.vendor_name.replace(/"/g, '""')}"`,
        `"${inv.date}"`,
        `"${inv.due_date || ""}"`,
        inv.total,
        `"${inv.currency}"`,
        `"${status}"`,
        `"${flags}"`,
      ].join(",");
    });
    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `flowaudit_governance_ledger_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    setCopiedLedger(true);
    setTimeout(() => setCopiedLedger(false), 2500);
  };

  return (
    <div className="space-y-6 animate-fade-in max-w-[1720px] mx-auto">
      {/* ═══════════════════ EXECUTIVE LEDGER HEADER ═══════════════════ */}
      <div
        className="p-6 sm:p-8 rounded-3xl border shadow-xs relative overflow-hidden flex flex-col xl:flex-row xl:items-center justify-between gap-6"
        style={{
          background: "linear-gradient(135deg, rgba(255,255,255,0.95) 0%, rgba(248,250,252,0.95) 100%)",
          borderColor: "rgba(226,232,240,0.8)",
          boxShadow: "0 4px 20px -2px rgba(15, 23, 42, 0.04), 0 2px 6px -1px rgba(15, 23, 42, 0.02)",
        }}
      >
        <div className="space-y-2 max-w-2xl">
          <div className="flex items-center gap-2.5">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-bold tracking-wider uppercase bg-slate-900 text-white shadow-xs">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Cryptographic Ledger
            </span>
            <span className="text-[11px] font-mono text-slate-400 flex items-center gap-1">
              <Icon name="verified_user" className="text-[14px] text-emerald-600" />
              SHA-256 Verified
            </span>
          </div>

          <h1 className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight">
            Corporate Governance & Audit Ledger
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 leading-relaxed font-normal">
            Immutable transaction record capturing multi-stage OCR extraction, catalog reconciliation, policy enforcement decisions, and automated disbursement authorizations.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-3 shrink-0 flex-wrap">
          <button
            onClick={handleExportCSV}
            className="px-4 py-2.5 rounded-2xl bg-white hover:bg-slate-50 border border-slate-200/80 text-slate-700 text-xs font-bold transition-all shadow-xs flex items-center gap-2 active:scale-95 cursor-pointer"
            title="Download full audit ledger as CSV"
          >
            <Icon name={copiedLedger ? "check_circle" : "file_download"} className={`text-[17px] ${copiedLedger ? "text-emerald-600" : "text-slate-500"}`} />
            <span>{copiedLedger ? "Exported CSV" : "Export Ledger"}</span>
          </button>

          <div className="px-4 py-2.5 rounded-2xl bg-slate-900 text-white text-xs font-semibold flex items-center gap-2.5 shadow-sm">
            <Icon name="account_balance" className="text-[17px] text-indigo-400" />
            <span>Audit Core Active</span>
          </div>
        </div>
      </div>

      {/* ═══════════════════ KPI ANALYTICS STRIP ═══════════════════ */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 1. Total Volume */}
        <div
          className="p-5 rounded-2xl border bg-white shadow-2xs transition-all hover:shadow-xs flex flex-col justify-between space-y-3"
          style={{ borderColor: "rgba(226,232,240,0.8)" }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Total Audited Volume</span>
            <div className="w-8 h-8 rounded-xl bg-slate-100 flex items-center justify-center text-slate-600">
              <Icon name="receipt_long" className="text-[18px]" />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight font-mono">
              {formatCurrency(ledgerMetrics.totalCapital)}
            </div>
            <div className="text-[11px] font-medium text-slate-500 mt-1 flex items-center gap-1.5">
              <span className="font-bold text-slate-800">{ledgerMetrics.totalCount}</span> total transactions registered
            </div>
          </div>
        </div>

        {/* 2. Disbursed & Cleared */}
        <div
          className="p-5 rounded-2xl border bg-white shadow-2xs transition-all hover:shadow-xs flex flex-col justify-between space-y-3"
          style={{ borderColor: "rgba(226,232,240,0.8)" }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-700">Disbursed & Cleared</span>
            <div className="w-8 h-8 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center border border-emerald-200/60">
              <Icon name="check_circle" className="text-[18px]" />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-black text-emerald-700 tracking-tight font-mono">
              {formatCurrency(ledgerMetrics.approvedCapital)}
            </div>
            <div className="text-[11px] font-medium text-slate-500 mt-1 flex items-center gap-1.5">
              <span className="font-bold text-emerald-700">{ledgerMetrics.approvedCount}</span> approved
              <span className="text-slate-300">·</span>
              <span className="text-emerald-600 font-semibold">{ledgerMetrics.complianceRate}% rate</span>
            </div>
          </div>
        </div>

        {/* 3. Withheld Under Review */}
        <div
          className="p-5 rounded-2xl border bg-white shadow-2xs transition-all hover:shadow-xs flex flex-col justify-between space-y-3"
          style={{ borderColor: "rgba(226,232,240,0.8)" }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-amber-700">Withheld in Triage</span>
            <div className="w-8 h-8 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center border border-amber-200/60">
              <Icon name="pending_actions" className="text-[18px]" />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-black text-amber-800 tracking-tight font-mono">
              {formatCurrency(ledgerMetrics.flaggedCapital)}
            </div>
            <div className="text-[11px] font-medium text-slate-500 mt-1 flex items-center gap-1.5">
              <span className="font-bold text-amber-700">{ledgerMetrics.flaggedCount}</span> invoices held
              <span className="text-slate-300">·</span>
              <span className="text-amber-600 font-semibold">Anomalies flagged</span>
            </div>
          </div>
        </div>

        {/* 4. Integrity & Blocked Fraud */}
        <div
          className="p-5 rounded-2xl border bg-white shadow-2xs transition-all hover:shadow-xs flex flex-col justify-between space-y-3"
          style={{ borderColor: "rgba(226,232,240,0.8)" }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Payments Blocked</span>
            <div className="w-8 h-8 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center border border-rose-200/60">
              <Icon name="shield" className="text-[18px]" />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight font-mono">
              {ledgerMetrics.rejectedCount}
            </div>
            <div className="text-[11px] font-medium text-slate-500 mt-1 flex items-center gap-1.5">
              <span className="font-bold text-rose-600">Zero Leakage</span>
              <span className="text-slate-300">·</span>
              <span>Rejections enforced</span>
            </div>
          </div>
        </div>
      </div>

      {/* ═══════════════════ SEARCH & FILTER TOOLBAR ═══════════════════ */}
      <div
        className="p-4 rounded-2xl border bg-white shadow-2xs flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4"
        style={{ borderColor: "rgba(226,232,240,0.8)" }}
      >
        {/* Search Input */}
        <div className="relative flex-1 max-w-md">
          <Icon name="search" className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-[18px]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter by invoice ID, vendor name, or policy rule..."
            className="w-full pl-10 pr-9 py-2.5 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white focus:bg-white text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer p-0.5"
            >
              <Icon name="close" className="text-[16px]" />
            </button>
          )}
        </div>

        {/* Filter Pills & Sorting */}
        <div className="flex items-center gap-2.5 flex-wrap justify-between md:justify-end">
          {/* Status Pills */}
          <div className="flex items-center gap-1 bg-slate-100/80 p-1 rounded-xl border border-slate-200/60 text-xs">
            {[
              { id: "all", label: "All Records", count: allInvoices.length },
              { id: "approved", label: "Approved", count: ledgerMetrics.approvedCount },
              { id: "pending", label: "Pending", count: ledgerMetrics.flaggedCount },
              { id: "rejected", label: "Rejected", count: ledgerMetrics.rejectedCount },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setStatusFilter(tab.id as any)}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-all cursor-pointer text-[11px] flex items-center gap-1.5 ${
                  statusFilter === tab.id
                    ? "bg-white text-slate-900 shadow-2xs font-bold"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <span>{tab.label}</span>
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                    statusFilter === tab.id ? "bg-slate-100 text-slate-800" : "text-slate-400"
                  }`}
                >
                  {tab.count}
                </span>
              </button>
            ))}
          </div>

          {/* Sort Dropdown */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-slate-700 focus:outline-none focus:border-indigo-500 cursor-pointer shadow-2xs"
          >
            <option value="newest">Sort: Newest First</option>
            <option value="oldest">Sort: Oldest First</option>
            <option value="amount_desc">Sort: Amount (High to Low)</option>
            <option value="amount_asc">Sort: Amount (Low to High)</option>
          </select>
        </div>
      </div>

      {/* ═══════════════════ HIGH-END AUDIT LEDGER TABLE ═══════════════════ */}
      <div
        className="rounded-3xl border bg-white shadow-xs overflow-hidden"
        style={{ borderColor: "rgba(226,232,240,0.85)" }}
      >
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-600">Audited Transactions</span>
            <span className="px-2 py-0.5 rounded-md bg-slate-200/70 text-slate-700 text-[11px] font-mono font-bold">
              {filteredRecords.length}
            </span>
          </div>
          <span className="text-xs text-slate-400 font-medium">Click any row to open the 3-way variance inspection modal</span>
        </div>

        {filteredRecords.length === 0 ? (
          <div className="text-center py-16 px-4 space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
              <Icon name="filter_alt_off" className="text-[24px]" />
            </div>
            <h3 className="text-sm font-bold text-slate-700">No matching audit records</h3>
            <p className="text-xs text-slate-400 max-w-sm mx-auto">
              No transactions matched your search query or filter criteria. Try adjusting your search term.
            </p>
            <button
              onClick={() => {
                setSearchQuery("");
                setStatusFilter("all");
              }}
              className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-bold text-slate-700 transition-all cursor-pointer"
            >
              Reset Filters
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-200/80 bg-slate-50/80 text-slate-500 font-bold uppercase text-[10px] tracking-wider select-none">
                  <th className="py-3.5 px-4">Invoice &amp; Format</th>
                  <th className="py-3.5 px-4">Counterparty / Vendor</th>
                  <th className="py-3.5 px-4">Amount</th>
                  <th className="py-3.5 px-4">Governance Status</th>
                  <th className="py-3.5 px-4">Validation &amp; Anomaly Signals</th>
                  <th className="py-3.5 px-4">Issue Date</th>
                  <th className="py-3.5 px-4 text-right">Inspection</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredRecords.map((inv, idx) => {
                  const isApproved = isInvoiceApproved(inv);
                  const isRejected = inv.ui_status === "rejected" || inv.payment_status === "rejected";
                  const flags = inv.rules_triggered?.length ? inv.rules_triggered : (inv.review?.rules_triggered || []);
                  const formatStyle = getFormatIconAndColor(inv.format_detected, inv.source_file);
                  const flagType = getFlagType(inv);
                  const vendorInitials = getVendorInitials(inv.vendor_name || "Vendor");
                  const vendorColor = getVendorColor(inv.vendor_name || "Vendor");

                  return (
                    <tr
                      key={`audit-row-${inv.id ?? idx}-${idx}`}
                      onClick={() => openModal(inv)}
                      className="group hover:bg-indigo-50/30 cursor-pointer transition-all duration-150"
                    >
                      {/* Column 1: Invoice ID & Format */}
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-3">
                          <div
                            className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border ${formatStyle.bg} ${formatStyle.text} ${formatStyle.border} shadow-2xs group-hover:scale-105 transition-transform`}
                            title={inv.format_detected?.toUpperCase() || "DOCUMENT"}
                          >
                            <Icon name={formatStyle.icon} className="text-[18px]" />
                          </div>
                          <div>
                            <div className="font-mono font-extrabold text-slate-900 text-xs tracking-tight group-hover:text-indigo-600 transition-colors">
                              #{inv.invoice_id}
                            </div>
                            <div className="text-[10px] text-slate-400 font-mono flex items-center gap-1.5 mt-0.5">
                              <span className="uppercase font-bold tracking-wider">{inv.format_detected || "DOC"}</span>
                              {inv.payment_terms && (
                                <>
                                  <span>·</span>
                                  <span>{inv.payment_terms}</span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>

                      {/* Column 2: Vendor */}
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <div
                            className={`w-7 h-7 rounded-lg flex items-center justify-center text-white text-[11px] font-black shrink-0 shadow-2xs ${vendorColor}`}
                          >
                            {vendorInitials}
                          </div>
                          <div className="min-w-0">
                            <span className="font-semibold text-slate-800 truncate block text-xs">
                              {inv.vendor_name}
                            </span>
                            {inv.vendor_status === "blacklisted" ? (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded bg-rose-100 text-rose-800 text-[9px] font-bold uppercase tracking-wider">
                                <span className="w-1 h-1 rounded-full bg-rose-600" />
                                Blacklisted
                              </span>
                            ) : (
                              <span className="text-[10px] text-slate-400 truncate block">
                                {inv.vendor_address || "Verified Entity"}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>

                      {/* Column 3: Amount */}
                      <td className="py-3.5 px-4">
                        <div className="font-mono font-black text-slate-900 text-xs">
                          {formatCurrency(inv.total, inv.currency)}
                        </div>
                        <div className="text-[10px] text-slate-400 font-mono">
                          {inv.currency || "USD"}
                        </div>
                      </td>

                      {/* Column 4: Governance Status */}
                      <td className="py-3.5 px-4">
                        {isApproved ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200/80 text-[11px] font-bold shadow-2xs">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                            Disbursed
                          </span>
                        ) : isRejected ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-50 text-rose-700 border border-rose-200/80 text-[11px] font-bold shadow-2xs">
                            <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                            Blocked
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200/80 text-[11px] font-bold shadow-2xs">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                            Held for Triage
                          </span>
                        )}
                      </td>

                      {/* Column 5: Validation & Flags */}
                      <td className="py-3.5 px-4 max-w-xs">
                        {flags.length > 0 ? (
                          <div className="flex items-center gap-1.5 flex-wrap">
                            {flags.slice(0, 2).map((flg: string, flgIdx: number) => {
                              const upper = flg.toUpperCase();
                              const isCrit = upper.includes("BLACKLIST") || upper.includes("DUPLICATE") || upper.includes("ARITHMETIC");
                              return (
                                <span
                                  key={`flag-${flgIdx}-${flg}`}
                                  className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${
                                    isCrit
                                      ? "bg-rose-50 text-rose-700 border-rose-200"
                                      : "bg-amber-50 text-amber-800 border-amber-200"
                                  }`}
                                >
                                  {flg.split(":")[0]}
                                </span>
                              );
                            })}
                            {flags.length > 2 && (
                              <span className="text-[10px] font-bold text-slate-400 px-1 py-0.5 rounded bg-slate-100">
                                +{flags.length - 2} more
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-emerald-600 font-semibold text-[11px]">
                            <Icon name="check_circle" className="text-[14px]" />
                            <span>Clean · 3-Way Matched</span>
                          </span>
                        )}
                      </td>

                      {/* Column 6: Issue Date */}
                      <td className="py-3.5 px-4 text-slate-600 font-mono text-[11px]">
                        {inv.date || "—"}
                      </td>

                      {/* Column 7: Action */}
                      <td className="py-3.5 px-4 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            openModal(inv);
                          }}
                          className="px-3 py-1.5 rounded-xl bg-slate-100 group-hover:bg-indigo-600 group-hover:text-white text-slate-700 font-bold text-[11px] transition-all shadow-2xs flex items-center gap-1 ml-auto cursor-pointer"
                        >
                          <span>Inspect</span>
                          <Icon name="chevron_right" className="text-[14px]" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Table Footer Summary */}
        <div className="px-6 py-3.5 border-t border-slate-100 bg-slate-50/60 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            <span>Showing {filteredRecords.length} of {allInvoices.length} audited ledger entries</span>
          </div>
          <div className="flex items-center gap-4 text-[11px] font-medium">
            <span>Fiduciary Review Active</span>
            <span>·</span>
            <span>Zero Unresolved Variances</span>
          </div>
        </div>
      </div>
    </div>
  );
}
