"use client";

import React, { useState } from "react";
import { InvoiceItem, DashboardStats } from "@/lib/api";
import { Icon } from "@/components/common/Icon";
import { InvoiceCard } from "@/components/dashboard/InvoiceCard";
import {
  formatCurrency,
  AVAILABLE_FLAGS,
  FilterFlagOption,
  getVendorInitials,
  getVendorColor,
  isProcessedSuccessfullyWithoutFlags,
} from "@/lib/invoice-utils";

export interface InvoiceTriageTabProps {
  allInvoices: InvoiceItem[];
  carouselInvoices: InvoiceItem[];
  pendingInvoices: InvoiceItem[];
  kpiCounts: {
    ingested: number;
    approved: number;
    pending: number;
    flagged: number;
    rejected: number;
  };
  stats?: DashboardStats | null;
  total: number;
  currentIndex: number;
  goToIndex: (idx: number) => void;
  carouselRef: React.RefObject<HTMLDivElement | null>;
  filterToolbarRef: React.RefObject<HTMLDivElement | null>;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  portfolioScope: "actionable" | "all";
  setPortfolioScope: (scope: "actionable" | "all") => void;
  searchQuery: string;
  setSearchQuery: (q: string) => void;
  dueDateFilter: string;
  setDueDateFilter: (f: string) => void;
  dueCustomStart: string;
  setDueCustomStart: (d: string) => void;
  dueCustomEnd: string;
  setDueCustomEnd: (d: string) => void;
  invoiceDateFilter: string;
  setInvoiceDateFilter: (f: string) => void;
  invoiceCustomStart: string;
  setInvoiceCustomStart: (d: string) => void;
  invoiceCustomEnd: string;
  setInvoiceCustomEnd: (d: string) => void;
  selectedFlags: string[];
  setSelectedFlags: React.Dispatch<React.SetStateAction<string[]>>;
  selectedVendors: string[];
  setSelectedVendors: React.Dispatch<React.SetStateAction<string[]>>;
  withheldCompanies: { name: string; count: number }[];
  presentFlags: (FilterFlagOption & { count: number })[];
  sortBy: string;
  setSortBy: (s: any) => void;
  hasActiveFilters: boolean;
  resetAllFilters: () => void;
  loading: boolean;
  uploading: boolean;
  openModal: (inv: InvoiceItem) => void;
  handleViewOriginal: (id: string) => void;
  handleApprove: (id: string) => void;
  handleReject: (id: string) => void;
  handleBlacklist: (id: string) => void;
  actionLoadingId: string | null;
}

export function InvoiceTriageTab({
  allInvoices,
  carouselInvoices,
  pendingInvoices,
  kpiCounts,
  stats,
  total,
  currentIndex,
  goToIndex,
  carouselRef,
  filterToolbarRef,
  fileInputRef,
  portfolioScope,
  setPortfolioScope,
  searchQuery,
  setSearchQuery,
  dueDateFilter,
  setDueDateFilter,
  dueCustomStart,
  setDueCustomStart,
  dueCustomEnd,
  setDueCustomEnd,
  invoiceDateFilter,
  setInvoiceDateFilter,
  invoiceCustomStart,
  setInvoiceCustomStart,
  invoiceCustomEnd,
  setInvoiceCustomEnd,
  selectedFlags,
  setSelectedFlags,
  selectedVendors,
  setSelectedVendors,
  withheldCompanies,
  presentFlags,
  sortBy,
  setSortBy,
  hasActiveFilters,
  resetAllFilters,
  loading,
  uploading,
  openModal,
  handleViewOriginal,
  handleApprove,
  handleReject,
  handleBlacklist,
  actionLoadingId,
}: InvoiceTriageTabProps) {
  const [openDropdown, setOpenDropdown] = useState<"dueDate" | "invoiceDate" | "flags" | "company" | null>(null);
  const [vendorSearch, setVendorSearch] = useState("");

  const toggleFlag = (flagId: string) => {
    setSelectedFlags((prev) =>
      prev.includes(flagId) ? prev.filter((id) => id !== flagId) : [...prev, flagId]
    );
  };

  const toggleVendor = (vendor: string) => {
    setSelectedVendors((prev) =>
      prev.includes(vendor) ? prev.filter((v) => v !== vendor) : [...prev, vendor]
    );
  };

  const handleScopeChange = (scope: "actionable" | "all") => {
    if (scope === portfolioScope) return;
    setPortfolioScope(scope);
    goToIndex(0);
    if (carouselRef?.current) {
      carouselRef.current.scrollTo({ left: 0, behavior: "smooth" });
    }
  };

  // Financial analytics
  const pendingCapital = pendingInvoices.reduce((sum, inv) => sum + (inv.total || 0), 0);
  const straightThroughRate = kpiCounts.ingested > 0
    ? Math.min(100, Math.round((kpiCounts.approved / kpiCounts.ingested) * 100))
    : 100;

  return (
    <div className="space-y-5 animate-fade-in max-w-[1720px] mx-auto">
      {/* ═══════════════════ EXECUTIVE KPI STRIP ═══════════════════ */}
      <div
        id="onborda-kpis"
        className="grid grid-cols-2 lg:grid-cols-4 gap-3.5"
      >
        {/* 1. Pending Triage Queue */}
        <div
          className="p-4 sm:p-5 rounded-2xl border bg-white shadow-2xs transition-all hover:shadow-xs flex flex-col justify-between space-y-2.5"
          style={{ borderColor: "rgba(226,232,240,0.85)" }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-indigo-700 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-indigo-600 animate-pulse" />
              Pending Triage
            </span>
            <div className="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-100">
              <Icon name="pending_actions" className="text-[18px]" />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-black text-slate-900 font-mono tracking-tight">
              {kpiCounts.pending} <span className="text-xs text-slate-400 font-sans font-normal">invoices held</span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1.5">
              <span className="font-mono font-bold text-slate-700">{formatCurrency(pendingCapital)}</span>
              <span className="text-slate-300">·</span>
              <span>Awaiting decision</span>
            </div>
          </div>
        </div>

        {/* 2. Auto-Approved Straight-Through */}
        <div
          className="p-4 sm:p-5 rounded-2xl border bg-white shadow-2xs transition-all hover:shadow-xs flex flex-col justify-between space-y-2.5"
          style={{ borderColor: "rgba(226,232,240,0.85)" }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-700">Straight-Through Rate</span>
            <div className="w-8 h-8 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center border border-emerald-100">
              <Icon name="check_circle" className="text-[18px]" />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-black text-emerald-700 font-mono tracking-tight">
              {straightThroughRate}%
            </div>
            <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1.5">
              <span className="font-bold text-emerald-700">{kpiCounts.approved}</span> auto-approved
              <span className="text-slate-300">·</span>
              <span className="font-mono text-slate-600">{formatCurrency(stats?.total_disbursed ?? 0)}</span>
            </div>
          </div>
        </div>

        {/* 3. Flagged Risk & Anomalies */}
        <div
          className="p-4 sm:p-5 rounded-2xl border bg-white shadow-2xs transition-all hover:shadow-xs flex flex-col justify-between space-y-2.5"
          style={{ borderColor: "rgba(226,232,240,0.85)" }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-rose-700">Flagged Exceptions</span>
            <div className="w-8 h-8 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center border border-rose-100">
              <Icon name="shield_with_heart" className="text-[18px]" />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-black text-slate-900 font-mono tracking-tight">
              {kpiCounts.flagged} <span className="text-xs text-rose-600 font-sans font-bold">flagged</span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1.5">
              <span className="font-bold text-rose-700">{kpiCounts.rejected}</span> blocked
              <span className="text-slate-300">·</span>
              <span>Policy violations</span>
            </div>
          </div>
        </div>

        {/* 4. Live Audit Stream Status */}
        <div
          className="p-4 sm:p-5 rounded-2xl border bg-white shadow-2xs transition-all hover:shadow-xs flex flex-col justify-between space-y-2.5"
          style={{ borderColor: "rgba(226,232,240,0.85)" }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Ledger Stream</span>
            <div className="w-8 h-8 rounded-xl bg-slate-100 text-slate-600 flex items-center justify-center border border-slate-200/60">
              <Icon name="receipt" className="text-[18px]" />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-black text-slate-900 font-mono tracking-tight">
              {kpiCounts.ingested} <span className="text-xs text-slate-400 font-sans font-normal">total</span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1.5">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span className="text-emerald-700 font-semibold">Active & Synced</span>
              <span className="text-slate-300">·</span>
              <span>SQLite v4.8</span>
            </div>
          </div>
        </div>
      </div>

      {/* ═══════════════════ UNIFIED COMMAND & FILTER HUB ═══════════════════ */}
      <div
        ref={filterToolbarRef}
        className="p-4 sm:p-5 rounded-3xl border bg-white shadow-xs space-y-3.5 transition-all"
        style={{ borderColor: "rgba(226,232,240,0.85)" }}
      >
        {/* Row 1: Scope Switcher + Search Bar + Sort */}
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
          {/* Left: Scope Segmented Toggle & Search */}
          <div className="flex items-center gap-3 flex-1 min-w-0">
            {/* Scope Selector */}
            <div
              id="onborda-scope-selector"
              className="relative grid grid-cols-2 p-1 rounded-2xl bg-slate-100/90 border border-slate-200/70 text-xs shrink-0 select-none shadow-inner"
            >
              {/* Sliding Pill Indicator */}
              <div
                aria-hidden="true"
                className={`absolute top-1 bottom-1 left-1 w-[calc(50%-4px)] rounded-xl bg-white shadow-xs border border-slate-200/60 transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] pointer-events-none ${
                  portfolioScope === "all" ? "translate-x-full" : "translate-x-0"
                }`}
              />
              <button
                type="button"
                onClick={() => handleScopeChange("actionable")}
                className={`relative z-10 px-4 py-1.5 rounded-xl font-bold transition-colors duration-200 cursor-pointer text-xs flex items-center justify-center gap-1.5 ${
                  portfolioScope === "actionable"
                    ? "text-slate-900 font-extrabold"
                    : "text-slate-500 hover:text-slate-800"
                }`}
              >
                <span>Pending Triage</span>
                <span
                  className={`px-1.5 py-0.2 rounded-md text-[10px] font-mono transition-colors ${
                    portfolioScope === "actionable" ? "bg-indigo-50 text-indigo-700 font-bold" : "text-slate-400"
                  }`}
                >
                  {kpiCounts.pending}
                </span>
              </button>
              <button
                type="button"
                onClick={() => handleScopeChange("all")}
                className={`relative z-10 px-4 py-1.5 rounded-xl font-bold transition-colors duration-200 cursor-pointer text-xs flex items-center justify-center gap-1.5 ${
                  portfolioScope === "all"
                    ? "text-slate-900 font-extrabold"
                    : "text-slate-500 hover:text-slate-800"
                }`}
              >
                <span>All Portfolio</span>
                <span
                  className={`px-1.5 py-0.2 rounded-md text-[10px] font-mono transition-colors ${
                    portfolioScope === "all" ? "bg-slate-100 text-slate-800 font-bold" : "text-slate-400"
                  }`}
                >
                  {allInvoices.length}
                </span>
              </button>
            </div>

            {/* Search Input */}
            <div className="relative flex-1 max-w-md">
              <Icon name="search" className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-[18px]" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by invoice #, vendor, or item..."
                className="w-full pl-10 pr-9 py-2 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white focus:bg-white text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer p-0.5"
                >
                  <Icon name="close" className="text-[15px]" />
                </button>
              )}
            </div>
          </div>

          {/* Right: Sort Dropdown & Reset Action */}
          <div className="flex items-center gap-2.5 shrink-0 justify-between lg:justify-end">
            {/* Sort Selector */}
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 bg-white text-xs font-semibold text-slate-700 shadow-2xs">
              <Icon name="swap_vert" className="text-[16px] text-indigo-600" />
              <span className="text-slate-400 text-[11px] font-normal">Sort:</span>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                className="bg-transparent font-bold text-slate-800 outline-none cursor-pointer pr-1 text-xs"
              >
                <option value="urgent">Due Date: Most Urgent First</option>
                <option value="closest">Due Date: Closest to Today</option>
                <option value="due_desc">Due Date: Furthest First</option>
                <option value="date_desc">Invoice Date: Newest First</option>
                <option value="date_asc">Invoice Date: Oldest First</option>
                <option value="amount_desc">Amount: Highest First</option>
                <option value="amount_asc">Amount: Lowest First</option>
              </select>
            </div>

            {/* Clear Filters Button */}
            {hasActiveFilters && (
              <button
                onClick={resetAllFilters}
                className="px-3 py-1.5 rounded-xl text-xs font-bold text-rose-700 hover:bg-rose-50 border border-rose-200 transition-all flex items-center gap-1 cursor-pointer shadow-2xs"
                title="Clear all filters"
              >
                <Icon name="filter_alt_off" className="text-[15px]" />
                <span>Reset</span>
              </button>
            )}
          </div>
        </div>

        {/* Row 2: Clean Filter Popover Buttons */}
        <div className="flex items-center gap-2 flex-wrap pt-2 border-t border-slate-100">
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mr-1 flex items-center gap-1">
            <Icon name="tune" className="text-[14px]" />
            Filters:
          </span>

          {/* 1. Due Date Filter Popover */}
          <div className="relative">
            <button
              onClick={() => setOpenDropdown(openDropdown === "dueDate" ? null : "dueDate")}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all flex items-center gap-1.5 cursor-pointer shadow-2xs ${
                dueDateFilter !== "all" || dueCustomStart || dueCustomEnd
                  ? "bg-indigo-50 border-indigo-300 text-indigo-800 font-bold ring-2 ring-indigo-500/10"
                  : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"
              }`}
            >
              <Icon name="event" className="text-[15px] text-indigo-500" />
              <span>
                {dueDateFilter === "all"
                  ? "Due Date"
                  : dueDateFilter === "overdue"
                  ? "Overdue"
                  : dueDateFilter === "today"
                  ? "Due Today"
                  : dueDateFilter === "next7"
                  ? "Next 7 Days"
                  : dueDateFilter === "next30"
                  ? "Next 30 Days"
                  : "Custom Due"}
              </span>
              <Icon name="expand_more" className={`text-[15px] transition-transform ${openDropdown === "dueDate" ? "rotate-180" : ""}`} />
            </button>

            {openDropdown === "dueDate" && (
              <div className="absolute top-full left-0 mt-2 w-64 rounded-2xl bg-white border border-slate-200 shadow-2xl p-2.5 z-30 space-y-1.5 animate-scale-in text-xs">
                <div className="font-bold text-slate-900 px-2 py-1 border-b border-slate-100 flex items-center justify-between text-xs">
                  <span>Due Date Filter</span>
                  {dueDateFilter !== "all" && (
                    <button
                      onClick={() => {
                        setDueDateFilter("all");
                        setDueCustomStart("");
                        setDueCustomEnd("");
                      }}
                      className="text-[11px] text-indigo-600 hover:underline cursor-pointer font-semibold"
                    >
                      Clear
                    </button>
                  )}
                </div>
                <div className="space-y-0.5">
                  {[
                    { id: "all", label: "All Due Dates" },
                    { id: "overdue", label: "Overdue (Immediate Action)" },
                    { id: "today", label: "Due Today" },
                    { id: "next7", label: "Due within Next 7 Days" },
                    { id: "next30", label: "Due within Next 30 Days" },
                    { id: "custom", label: "Custom Date Range" },
                  ].map((opt) => (
                    <button
                      key={opt.id}
                      onClick={() => setDueDateFilter(opt.id)}
                      className={`w-full text-left px-2.5 py-1.5 rounded-lg transition-all flex items-center justify-between cursor-pointer ${
                        dueDateFilter === opt.id ? "bg-indigo-50 text-indigo-700 font-bold" : "hover:bg-slate-50 text-slate-700"
                      }`}
                    >
                      <span>{opt.label}</span>
                      {dueDateFilter === opt.id && <Icon name="check" className="text-[16px] text-indigo-600" />}
                    </button>
                  ))}
                </div>

                {dueDateFilter === "custom" && (
                  <div className="pt-2 border-t border-slate-100 space-y-2 px-1">
                    <div>
                      <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-1">From</span>
                      <input
                        type="date"
                        value={dueCustomStart}
                        onChange={(e) => setDueCustomStart(e.target.value)}
                        className="w-full px-2 py-1 rounded-lg border border-slate-200 text-xs bg-slate-50"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-1">To</span>
                      <input
                        type="date"
                        value={dueCustomEnd}
                        onChange={(e) => setDueCustomEnd(e.target.value)}
                        className="w-full px-2 py-1 rounded-lg border border-slate-200 text-xs bg-slate-50"
                      />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 2. Issue Date Filter Popover */}
          <div className="relative">
            <button
              onClick={() => setOpenDropdown(openDropdown === "invoiceDate" ? null : "invoiceDate")}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all flex items-center gap-1.5 cursor-pointer shadow-2xs ${
                invoiceDateFilter !== "all" || invoiceCustomStart || invoiceCustomEnd
                  ? "bg-indigo-50 border-indigo-300 text-indigo-800 font-bold ring-2 ring-indigo-500/10"
                  : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"
              }`}
            >
              <Icon name="calendar_month" className="text-[15px] text-sky-500" />
              <span>
                {invoiceDateFilter === "all"
                  ? "Issue Date"
                  : invoiceDateFilter === "last7"
                  ? "Last 7 Days"
                  : invoiceDateFilter === "last30"
                  ? "Last 30 Days"
                  : invoiceDateFilter === "last90"
                  ? "Last 90 Days"
                  : "Custom Issue"}
              </span>
              <Icon name="expand_more" className={`text-[15px] transition-transform ${openDropdown === "invoiceDate" ? "rotate-180" : ""}`} />
            </button>

            {openDropdown === "invoiceDate" && (
              <div className="absolute top-full left-0 mt-2 w-64 rounded-2xl bg-white border border-slate-200 shadow-2xl p-2.5 z-30 space-y-1.5 animate-scale-in text-xs">
                <div className="font-bold text-slate-900 px-2 py-1 border-b border-slate-100 flex items-center justify-between text-xs">
                  <span>Issue Date Filter</span>
                  {invoiceDateFilter !== "all" && (
                    <button
                      onClick={() => {
                        setInvoiceDateFilter("all");
                        setInvoiceCustomStart("");
                        setInvoiceCustomEnd("");
                      }}
                      className="text-[11px] text-indigo-600 hover:underline cursor-pointer font-semibold"
                    >
                      Clear
                    </button>
                  )}
                </div>
                <div className="space-y-0.5">
                  {[
                    { id: "all", label: "All Invoice Dates" },
                    { id: "last7", label: "Issued in Last 7 Days" },
                    { id: "last30", label: "Issued in Last 30 Days" },
                    { id: "last90", label: "Issued in Last 90 Days" },
                    { id: "custom", label: "Custom Date Range" },
                  ].map((opt) => (
                    <button
                      key={opt.id}
                      onClick={() => setInvoiceDateFilter(opt.id)}
                      className={`w-full text-left px-2.5 py-1.5 rounded-lg transition-all flex items-center justify-between cursor-pointer ${
                        invoiceDateFilter === opt.id ? "bg-indigo-50 text-indigo-700 font-bold" : "hover:bg-slate-50 text-slate-700"
                      }`}
                    >
                      <span>{opt.label}</span>
                      {invoiceDateFilter === opt.id && <Icon name="check" className="text-[16px] text-indigo-600" />}
                    </button>
                  ))}
                </div>

                {invoiceDateFilter === "custom" && (
                  <div className="pt-2 border-t border-slate-100 space-y-2 px-1">
                    <div>
                      <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-1">From</span>
                      <input
                        type="date"
                        value={invoiceCustomStart}
                        onChange={(e) => setInvoiceCustomStart(e.target.value)}
                        className="w-full px-2 py-1 rounded-lg border border-slate-200 text-xs bg-slate-50"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] uppercase font-semibold text-slate-400 block mb-1">To</span>
                      <input
                        type="date"
                        value={invoiceCustomEnd}
                        onChange={(e) => setInvoiceCustomEnd(e.target.value)}
                        className="w-full px-2 py-1 rounded-lg border border-slate-200 text-xs bg-slate-50"
                      />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 3. Anomaly Flags Multi-Select */}
          <div className="relative">
            <button
              onClick={() => setOpenDropdown(openDropdown === "flags" ? null : "flags")}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all flex items-center gap-1.5 cursor-pointer shadow-2xs ${
                selectedFlags.length > 0
                  ? "bg-rose-50 border-rose-300 text-rose-900 font-bold ring-2 ring-rose-500/10"
                  : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"
              }`}
            >
              <Icon name="flag" className="text-[15px] text-rose-500" />
              <span>Anomaly Flags</span>
              {selectedFlags.length > 0 && (
                <span className="px-1.5 py-0.2 rounded-full bg-rose-600 text-white text-[10px] font-bold">
                  {selectedFlags.length}
                </span>
              )}
              <Icon name="expand_more" className={`text-[15px] transition-transform ${openDropdown === "flags" ? "rotate-180" : ""}`} />
            </button>

            {openDropdown === "flags" && (
              <div className="absolute top-full left-0 mt-2 w-80 rounded-2xl bg-white border border-slate-200 shadow-2xl p-3 z-30 space-y-2 animate-scale-in text-xs">
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <span className="font-bold text-slate-900">Filter by Exception Flag</span>
                  <div className="flex items-center gap-2 text-[11px]">
                    <button
                      onClick={() => setSelectedFlags(presentFlags.map((f) => f.id))}
                      className="text-indigo-600 hover:underline cursor-pointer font-semibold"
                    >
                      Select All
                    </button>
                    <span className="text-slate-300">|</span>
                    <button
                      onClick={() => setSelectedFlags([])}
                      className="text-slate-400 hover:text-slate-600 cursor-pointer"
                    >
                      Clear
                    </button>
                  </div>
                </div>

                <div className="max-h-56 overflow-y-auto space-y-1 modal-scroll pr-1">
                  {presentFlags.map((flag) => {
                    const isChecked = selectedFlags.includes(flag.id);
                    return (
                      <div
                        key={flag.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleFlag(flag.id);
                        }}
                        className={`flex items-center justify-between p-2 rounded-xl transition-all cursor-pointer select-none ${
                          isChecked ? "bg-rose-50 text-rose-900 font-bold" : "hover:bg-slate-50 text-slate-700"
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => {}}
                            className="w-4 h-4 rounded text-rose-600 focus:ring-rose-500 border-slate-300 pointer-events-none"
                          />
                          <span className="truncate">{flag.label}</span>
                        </div>
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 font-bold">
                          {flag.count}
                        </span>
                      </div>
                    );
                  })}
                  {presentFlags.length === 0 && (
                    <div className="text-center py-4 text-slate-400">No anomaly flags present</div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* 4. Counterparty/Vendor Filter */}
          <div className="relative">
            <button
              onClick={() => setOpenDropdown(openDropdown === "company" ? null : "company")}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all flex items-center gap-1.5 cursor-pointer shadow-2xs ${
                selectedVendors.length > 0
                  ? "bg-amber-50 border-amber-300 text-amber-900 font-bold ring-2 ring-amber-500/10"
                  : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"
              }`}
            >
              <Icon name="business" className="text-[15px] text-amber-500" />
              <span>Vendors</span>
              {selectedVendors.length > 0 && (
                <span className="px-1.5 py-0.2 rounded-full bg-amber-600 text-white text-[10px] font-bold">
                  {selectedVendors.length}
                </span>
              )}
              <Icon name="expand_more" className={`text-[15px] transition-transform ${openDropdown === "company" ? "rotate-180" : ""}`} />
            </button>

            {openDropdown === "company" && (
              <div className="absolute top-full left-0 mt-2 w-80 rounded-2xl bg-white border border-slate-200 shadow-2xl p-3 z-30 space-y-2 animate-scale-in text-xs">
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <span className="font-bold text-slate-900">Filter by Counterparty</span>
                  <div className="flex items-center gap-2 text-[11px]">
                    <button
                      onClick={() => setSelectedVendors(withheldCompanies.map((c) => c.name))}
                      className="text-indigo-600 hover:underline cursor-pointer font-semibold"
                    >
                      Select All
                    </button>
                    <span className="text-slate-300">|</span>
                    <button
                      onClick={() => setSelectedVendors([])}
                      className="text-slate-400 hover:text-slate-600 cursor-pointer"
                    >
                      Clear
                    </button>
                  </div>
                </div>

                <input
                  type="text"
                  value={vendorSearch}
                  onChange={(e) => setVendorSearch(e.target.value)}
                  placeholder="Search vendors..."
                  className="w-full px-2.5 py-1.5 rounded-lg border border-slate-200 text-xs bg-slate-50 outline-none focus:bg-white focus:border-indigo-500"
                />

                <div className="max-h-56 overflow-y-auto space-y-1 modal-scroll pr-1">
                  {withheldCompanies
                    .filter((c) => c.name.toLowerCase().includes(vendorSearch.toLowerCase().trim()))
                    .map((company) => {
                      const isChecked = selectedVendors.includes(company.name);
                      const initials = getVendorInitials(company.name);
                      const color = getVendorColor(company.name);

                      return (
                        <div
                          key={company.name}
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleVendor(company.name);
                          }}
                          className={`flex items-center justify-between p-2 rounded-xl transition-all cursor-pointer select-none ${
                            isChecked ? "bg-amber-50 text-amber-900 font-bold" : "hover:bg-slate-50 text-slate-700"
                          }`}
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => {}}
                              className="w-4 h-4 rounded text-amber-600 focus:ring-amber-500 border-slate-300 pointer-events-none"
                            />
                            <div className={`w-5 h-5 rounded ${color} text-white text-[9px] font-bold flex items-center justify-center shrink-0`}>
                              {initials}
                            </div>
                            <span className="truncate">{company.name}</span>
                          </div>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 font-bold">
                            {company.count}
                          </span>
                        </div>
                      );
                    })}
                  {withheldCompanies.length === 0 && (
                    <div className="text-center py-4 text-slate-400">No counterparties found</div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Row 3: Active Filter Pills Bar */}
        {hasActiveFilters && (
          <div className="pt-2 border-t border-slate-100 flex items-center justify-between gap-2 flex-wrap text-xs">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">Active Filters:</span>

              {searchQuery.trim() && (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-lg bg-indigo-50 text-indigo-800 text-[11px] font-medium border border-indigo-200">
                  <span>Search: &quot;{searchQuery}&quot;</span>
                  <button onClick={() => setSearchQuery("")} className="hover:text-indigo-950 cursor-pointer">
                    <Icon name="close" className="text-[12px]" />
                  </button>
                </span>
              )}

              {dueDateFilter !== "all" && (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-lg bg-indigo-50 text-indigo-800 text-[11px] font-medium border border-indigo-200">
                  <span>Due: {dueDateFilter}</span>
                  <button
                    onClick={() => {
                      setDueDateFilter("all");
                      setDueCustomStart("");
                      setDueCustomEnd("");
                    }}
                    className="hover:text-indigo-950 cursor-pointer"
                  >
                    <Icon name="close" className="text-[12px]" />
                  </button>
                </span>
              )}

              {invoiceDateFilter !== "all" && (
                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-lg bg-sky-50 text-sky-800 text-[11px] font-medium border border-sky-200">
                  <span>Issued: {invoiceDateFilter}</span>
                  <button
                    onClick={() => {
                      setInvoiceDateFilter("all");
                      setInvoiceCustomStart("");
                      setInvoiceCustomEnd("");
                    }}
                    className="hover:text-sky-950 cursor-pointer"
                  >
                    <Icon name="close" className="text-[12px]" />
                  </button>
                </span>
              )}

              {selectedFlags.map((fId) => {
                const opt = AVAILABLE_FLAGS.find((f) => f.id === fId);
                return (
                  <span
                    key={fId}
                    className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-lg bg-rose-50 text-rose-800 text-[11px] font-medium border border-rose-200"
                  >
                    <span>{opt?.shortLabel || fId}</span>
                    <button
                      onClick={() => setSelectedFlags((prev) => prev.filter((id) => id !== fId))}
                      className="hover:text-rose-950 cursor-pointer"
                    >
                      <Icon name="close" className="text-[12px]" />
                    </button>
                  </span>
                );
              })}

              {selectedVendors.map((vendor) => (
                <span
                  key={vendor}
                  className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-lg bg-amber-50 text-amber-900 text-[11px] font-medium border border-amber-200"
                >
                  <span>{vendor}</span>
                  <button
                    onClick={() => setSelectedVendors((prev) => prev.filter((v) => v !== vendor))}
                    className="hover:text-amber-950 cursor-pointer"
                  >
                    <Icon name="close" className="text-[12px]" />
                  </button>
                </span>
              ))}
            </div>

            <div className="text-[11px] font-medium text-slate-500">
              Showing <span className="font-bold text-slate-800 font-mono">{total}</span> of {allInvoices.length} invoices
            </div>
          </div>
        )}
      </div>

      {/* ═══════════════════ CAROUSEL STAGE & DECK CONTROLS ═══════════════════ */}
      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-slate-400">
          <Icon name="sync" className="text-[36px] text-indigo-600 animate-spin" />
          <p className="text-sm font-semibold text-slate-600">Loading invoice portfolio...</p>
        </div>
      ) : total === 0 ? (
        <div
          className="p-12 sm:p-16 rounded-3xl border border-dashed bg-white text-center space-y-4 shadow-2xs"
          style={{ borderColor: "rgba(226,232,240,0.9)" }}
        >
          <div className="w-14 h-14 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center mx-auto border border-emerald-200/80 shadow-2xs">
            <Icon name="verified" className="text-[32px]" />
          </div>
          <div className="space-y-1 max-w-md mx-auto">
            <h3 className="text-lg font-black text-slate-900">Triage Queue Clear &amp; Reconciled</h3>
            <p className="text-xs text-slate-500 leading-relaxed">
              All invoices in the current scope have been processed cleanly with zero unresolved variances or pending human actions.
            </p>
          </div>
          <div className="flex items-center justify-center gap-3 pt-2 flex-wrap">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="px-4 py-2 rounded-xl text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-500 transition-all flex items-center gap-1.5 shadow-sm active:scale-95 cursor-pointer"
            >
              <Icon name="upload" className="text-[16px]" />
              <span>{uploading ? "Ingesting..." : "Upload New Invoice"}</span>
            </button>
            {allInvoices.some((inv) => isProcessedSuccessfullyWithoutFlags(inv)) && (
              <button
                onClick={() => {
                  const cleanInv = allInvoices.find((inv) => isProcessedSuccessfullyWithoutFlags(inv));
                  if (cleanInv) openModal(cleanInv);
                }}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-emerald-800 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 transition-all flex items-center gap-1.5 cursor-pointer active:scale-95"
              >
                <Icon name="receipt_long" className="text-[16px]" />
                <span>View Disbursed Invoices ({allInvoices.filter(isProcessedSuccessfullyWithoutFlags).length})</span>
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Deck Floating Stage Header Controls */}
          <div className="flex items-center justify-between px-2 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-bold text-slate-800">
                Invoice <span className="font-mono text-indigo-600 font-extrabold">{currentIndex + 1}</span> of {total}
              </span>
              <span className="text-slate-300">·</span>
              <span className="text-slate-400 hidden sm:inline text-[11px]">
                Navigate with <kbd className="px-1 py-0.5 rounded bg-slate-100 border text-[10px]">←</kbd> <kbd className="px-1 py-0.5 rounded bg-slate-100 border text-[10px]">→</kbd> or approve with <kbd className="px-1 py-0.5 rounded bg-slate-100 border text-[10px] font-bold text-emerald-700">A</kbd>
              </span>
            </div>

            {/* Previous / Next Deck Buttons */}
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => goToIndex(currentIndex - 1)}
                disabled={currentIndex === 0}
                className="p-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 disabled:opacity-30 cursor-pointer shadow-2xs transition-all active:scale-95"
                title="Previous invoice (Arrow Left)"
              >
                <Icon name="chevron_left" className="text-[18px]" />
              </button>

              {/* Progress Dots */}
              <div className="hidden sm:flex items-center gap-1 px-2 py-1 rounded-xl bg-slate-100 border border-slate-200/60">
                {carouselInvoices.slice(0, 10).map((_, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => goToIndex(idx)}
                    className={`rounded-full transition-all cursor-pointer ${
                      idx === currentIndex ? "bg-indigo-600 w-4 h-1.5" : "w-1.5 h-1.5 bg-slate-300 hover:bg-slate-400"
                    }`}
                  />
                ))}
                {total > 10 && <span className="text-[9px] font-mono text-slate-400 font-bold">+{total - 10}</span>}
              </div>

              <button
                type="button"
                onClick={() => goToIndex(currentIndex + 1)}
                disabled={currentIndex === total - 1}
                className="p-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 disabled:opacity-30 cursor-pointer shadow-2xs transition-all active:scale-95"
                title="Next invoice (Arrow Right)"
              >
                <Icon name="chevron_right" className="text-[18px]" />
              </button>
            </div>
          </div>

          {/* Carousel Track Stage */}
          <div className="relative w-full overflow-hidden py-2">
            <div
              key={portfolioScope}
              ref={carouselRef}
              className={`flex gap-6 transition-transform duration-500 ease-out py-4 px-2 overflow-x-auto hide-scrollbar scroll-smooth ${
                portfolioScope === "all" ? "animate-slide-in-right" : "animate-slide-in-left"
              }`}
              style={{ scrollSnapType: "x mandatory" }}
            >
              {carouselInvoices.map((inv, idx) => (
                <InvoiceCard
                  key={`invoice-card-${inv.id ?? idx}-${idx}`}
                  inv={inv}
                  idx={idx}
                  isActive={idx === currentIndex}
                  onCardClick={() => openModal(inv)}
                  onViewOriginal={handleViewOriginal}
                  onApprove={handleApprove}
                  onReject={handleReject}
                  onBlacklist={handleBlacklist}
                  actionLoadingId={actionLoadingId}
                />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
