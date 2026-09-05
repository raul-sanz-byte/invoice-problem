import React from "react";
import { UploadResultItem } from "@/lib/api";
import { Icon } from "@/components/common/Icon";
import { formatCurrency } from "@/lib/invoice-utils";

export interface CleanSuccessModalState {
  open: boolean;
  invoices: UploadResultItem[];
  selectedIndex: number;
}

export interface CleanUploadSuccessModalProps {
  cleanSuccessModal: CleanSuccessModalState | null;
  setCleanSuccessModal: React.Dispatch<React.SetStateAction<CleanSuccessModalState | null>>;
  copiedCleanLogs: boolean;
  setCopiedCleanLogs: React.Dispatch<React.SetStateAction<boolean>>;
}

export function CleanUploadSuccessModal({
  cleanSuccessModal,
  setCleanSuccessModal,
  copiedCleanLogs,
  setCopiedCleanLogs,
}: CleanUploadSuccessModalProps) {
  if (!cleanSuccessModal?.open || cleanSuccessModal.invoices.length === 0) return null;

  const curIdx = cleanSuccessModal.selectedIndex;
  const inv = cleanSuccessModal.invoices[curIdx];
  if (!inv) return null;

  const allLogsText = (inv.logs || []).join("\n");
  const handleCopyCleanLogs = () => {
    navigator.clipboard.writeText(allLogsText);
    setCopiedCleanLogs(true);
    setTimeout(() => setCopiedCleanLogs(false), 2000);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 lg:p-10 transition-all animate-fade-in"
      style={{ background: "rgba(0,0,0,0.72)", backdropFilter: "blur(14px)" }}
      onClick={() => setCleanSuccessModal(null)}
    >
      <div
        className="relative w-full max-w-5xl max-h-[92vh] rounded-3xl shadow-2xl flex flex-col overflow-hidden border border-emerald-500/30 animate-scale-in"
        style={{ background: "var(--surface)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Top Header */}
        <div
          className="px-6 py-4 border-b flex items-center justify-between gap-4"
          style={{
            background:
              "linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(99, 102, 241, 0.08) 100%)",
            borderColor: "rgba(16, 185, 129, 0.2)",
          }}
        >
          <div className="flex items-center gap-3.5 min-w-0">
            <div className="w-11 h-11 rounded-2xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-600 shadow-sm shrink-0">
              <Icon name="verified" className="text-[26px]" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-base sm:text-lg font-bold truncate">
                  Invoice Processed Successfully
                </h2>
                <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold uppercase bg-emerald-100 text-emerald-800 border border-emerald-300/80 flex items-center gap-1 shadow-xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  0 Flags · Auto-Approved
                </span>
              </div>
              <p className="text-xs" style={{ color: "var(--secondary)" }}>
                Passed arithmetic validation, catalog cross-match, and VP anti-fraud policies.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => setCleanSuccessModal(null)}
              className="p-2 rounded-xl bg-slate-200/70 hover:bg-slate-300 text-slate-700 transition-all cursor-pointer"
              title="Close"
            >
              <Icon name="close" className="text-[18px]" />
            </button>
          </div>
        </div>

        {/* Multi-invoice Selector Tabs if batch upload */}
        {cleanSuccessModal.invoices.length > 1 && (
          <div className="px-6 py-2.5 bg-slate-100/70 border-b border-slate-200/60 flex items-center gap-2 overflow-x-auto">
            <span className="text-xs font-semibold text-slate-500 shrink-0">Uploaded batch:</span>
            {cleanSuccessModal.invoices.map((item, idx) => (
              <button
                key={idx}
                onClick={() => setCleanSuccessModal({ ...cleanSuccessModal, selectedIndex: idx })}
                className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-all shrink-0 cursor-pointer ${
                  idx === curIdx
                    ? "bg-emerald-600 text-white font-semibold shadow-sm"
                    : "bg-white text-slate-700 hover:bg-slate-50 border border-slate-200"
                }`}
              >
                {item.invoice_id || item.filename} · {item.currency || "USD"}{" "}
                {item.total?.toFixed(2) || "0.00"}
              </button>
            ))}
          </div>
        )}

        {/* Scrollable Content Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 modal-scroll">
          {/* ── METRICS TELEMETRY STRIP ── */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
            {/* Processing Time */}
            <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/25 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-emerald-800 font-semibold mb-1">
                <span className="flex items-center gap-1">
                  <Icon name="bolt" className="text-[16px] text-amber-500" />
                  Turnaround Time
                </span>
                <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-emerald-200/60 text-emerald-900">
                  Fast
                </span>
              </div>
              <div className="text-2xl font-black font-mono tracking-tight text-emerald-950">
                {inv.processing_time_ms ? `${inv.processing_time_ms.toFixed(1)} ms` : "< 50 ms"}
              </div>
              <div className="text-[11px] text-emerald-700/90 mt-1 font-mono truncate">
                {inv.stage_timings
                  ? `parse ${inv.stage_timings.parsing_ms ?? 0}ms · val ${
                      inv.stage_timings.validation_ms ?? 0
                    }ms · review ${inv.stage_timings.vp_review_ms ?? 0}ms`
                  : "End-to-end ingestion latency"}
              </div>
            </div>

            {/* Decision */}
            <div className="p-4 rounded-2xl bg-indigo-500/10 border border-indigo-500/25 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-indigo-800 font-semibold mb-1">
                <span className="flex items-center gap-1">
                  <Icon name="verified_user" className="text-[16px] text-indigo-600" />
                  VP Decision
                </span>
                <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-indigo-200/60 text-indigo-900">
                  Zero Flags
                </span>
              </div>
              <div className="text-xl font-bold tracking-tight text-indigo-950">
                {inv.decision === "auto_approved" ? "Auto-Approved" : "Approved"}
              </div>
              <div className="text-[11px] text-indigo-700/90 mt-1">
                Delegated VP limit ($10,000 threshold)
              </div>
            </div>

            {/* Payment Status */}
            <div className="p-4 rounded-2xl bg-teal-500/10 border border-teal-500/25 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-teal-800 font-semibold mb-1">
                <span className="flex items-center gap-1">
                  <Icon name="payments" className="text-[16px] text-teal-600" />
                  Disbursement
                </span>
                <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-teal-200/60 text-teal-900 font-bold">
                  Paid
                </span>
              </div>
              <div className="text-xl font-bold tracking-tight text-teal-950">
                {formatCurrency(inv.total || 0, inv.currency || "USD")}
              </div>
              <div className="text-[11px] text-teal-700/90 mt-1 truncate">
                Cleared via automated payment rails
              </div>
            </div>

            {/* Format & Extractor */}
            <div className="p-4 rounded-2xl bg-slate-100 border border-slate-200 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-slate-700 font-semibold mb-1">
                <span className="flex items-center gap-1">
                  <Icon name="schema" className="text-[16px] text-slate-600" />
                  Format Extracted
                </span>
                <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-200 text-slate-800 font-bold">
                  .{inv.format_detected || "TXT"}
                </span>
              </div>
              <div className="text-base font-bold tracking-tight text-slate-900 truncate">
                {inv.filename}
              </div>
              <div className="text-[11px] text-slate-600 mt-1 font-mono truncate">
                Engine: {inv.extraction_method || "parser"}
              </div>
            </div>
          </div>

          {/* ── TWO COLUMN: INVOICE DETAILS & EXECUTION LOGS ── */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left Column: Invoice Details & Line Items (6 cols) */}
            <div className="lg:col-span-6 space-y-4">
              <div className="p-5 rounded-2xl border border-slate-200/80 bg-white/70 shadow-xs space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div>
                    <span className="text-[11px] font-mono text-slate-400 block uppercase">
                      Invoice Identifier
                    </span>
                    <span className="text-lg font-bold text-slate-900">{inv.invoice_id || "INV-N/A"}</span>
                  </div>
                  <div className="text-right">
                    <span className="text-[11px] font-mono text-slate-400 block uppercase">
                      Total Invoiced
                    </span>
                    <span className="text-lg font-black text-emerald-600">
                      {formatCurrency(inv.total || 0, inv.currency || "USD")}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <span className="text-slate-400 block text-[11px]">Vendor Name</span>
                    <span className="font-semibold text-slate-800">{inv.vendor || "Unknown Vendor"}</span>
                    {inv.vendor_address && (
                      <span className="text-[11px] text-slate-500 block truncate">{inv.vendor_address}</span>
                    )}
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[11px]">Invoice Date / Due</span>
                    <span className="font-semibold text-slate-800">{inv.date || "N/A"}</span>
                    {inv.due_date && (
                      <span className="text-[11px] text-slate-500 block">Due: {inv.due_date}</span>
                    )}
                  </div>
                </div>

                {/* Line Items Table */}
                <div className="pt-2">
                  <div className="flex items-center justify-between text-xs font-semibold text-slate-700 mb-2">
                    <span>Reconciled Line Items ({inv.line_items?.length ?? inv.line_items_count ?? 0})</span>
                    <span className="text-[11px] text-emerald-600 font-mono">Catalog 100% Matched</span>
                  </div>
                  <div className="border border-slate-200/70 rounded-xl overflow-hidden text-xs">
                    <table className="w-full text-left">
                      <thead className="bg-slate-50 text-[11px] text-slate-500 font-semibold border-b border-slate-200/70">
                        <tr>
                          <th className="py-2 px-3">Item</th>
                          <th className="py-2 px-2 text-right">Qty</th>
                          <th className="py-2 px-2 text-right">Price</th>
                          <th className="py-2 px-3 text-right">Total</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {inv.line_items && inv.line_items.length > 0 ? (
                          inv.line_items.map((li, i) => (
                            <tr key={i} className="hover:bg-slate-50/60">
                              <td className="py-2 px-3 font-medium text-slate-800">{li.item}</td>
                              <td className="py-2 px-2 text-right font-mono text-slate-600">{li.quantity}</td>
                              <td className="py-2 px-2 text-right font-mono text-slate-600">
                                ${li.unit_price.toFixed(2)}
                              </td>
                              <td className="py-2 px-3 text-right font-mono font-bold text-slate-900">
                                ${(li.amount ?? li.quantity * li.unit_price).toFixed(2)}
                              </td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan={4} className="py-3 px-3 text-center text-slate-400">
                              All items verified & matched against catalog
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* AI Reflection / Critique Box */}
                {inv.critique && (
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/70 text-xs space-y-1">
                    <span className="font-semibold text-slate-700 flex items-center gap-1.5">
                      <Icon name="psychology" className="text-[16px] text-indigo-600" />
                      VP Risk Reflection
                    </span>
                    <p className="text-[11px] text-slate-600 italic leading-relaxed">
                      "{inv.critique}"
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Right Column: Execution Logs Terminal (6 cols) */}
            <div className="lg:col-span-6 flex flex-col h-full space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold px-1">
                <span className="flex items-center gap-1.5 text-slate-700">
                  <Icon name="terminal" className="text-[16px] text-indigo-600" />
                  Pipeline Processing & Audit Logs
                </span>
                <button
                  onClick={handleCopyCleanLogs}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-[11px] font-medium transition-all cursor-pointer"
                  title="Copy logs to clipboard"
                >
                  <Icon
                    name={copiedCleanLogs ? "check" : "content_copy"}
                    className={`text-[14px] ${copiedCleanLogs ? "text-emerald-600" : ""}`}
                  />
                  <span>{copiedCleanLogs ? "Copied" : "Copy Logs"}</span>
                </button>
              </div>

              <div className="rounded-2xl overflow-hidden border border-slate-800 bg-[#0d1117] shadow-xl flex flex-col flex-1">
                {/* Terminal header */}
                <div className="px-4 py-2.5 bg-[#161b22] border-b border-slate-800 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <div className="flex gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80 inline-block" />
                      <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80 inline-block" />
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80 inline-block" />
                    </div>
                    <span className="font-mono text-[11px] text-slate-400 ml-1.5">
                      pipeline-ingestion.log
                    </span>
                  </div>
                  <span className="font-mono text-[10px] text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/60">
                    SUCCESS: 0 FLAGS
                  </span>
                </div>

                {/* Log lines */}
                <div className="p-4 max-h-[380px] overflow-y-auto select-all modal-scroll font-mono text-xs leading-relaxed text-slate-300 space-y-1.5">
                  {inv.logs && inv.logs.length > 0 ? (
                    inv.logs.map((line, lIdx) => {
                      const isSuccess =
                        line.includes("SUCCESS") ||
                        line.includes("AUTO-APPROVED") ||
                        line.includes("100% MATCH");
                      const isNotice = line.includes("Extracted") || line.includes("Validated");
                      return (
                        <div key={lIdx} className="flex items-start gap-2">
                          <span className="text-slate-600 select-none text-[10px] w-5 text-right shrink-0 pt-0.5">
                            {lIdx + 1}
                          </span>
                          <span
                            className={
                              isSuccess ? "text-emerald-400" : isNotice ? "text-cyan-300" : "text-slate-300"
                            }
                          >
                            {line}
                          </span>
                        </div>
                      );
                    })
                  ) : (
                    <div className="text-slate-500 italic py-4 text-center">
                      No logs recorded for this ingestion lifecycle.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div
          className="px-6 py-3.5 border-t flex flex-col sm:flex-row items-center justify-between gap-3 text-xs"
          style={{
            background: "var(--surface-container-lowest)",
            borderColor: "var(--surface-container)",
            color: "var(--secondary)",
          }}
        >
          <div className="flex items-center gap-2">
            <Icon name="verified" className="text-[16px] text-emerald-500" />
            <span>Verified clean operating expenditure. Stored in SQLite & disbursed.</span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleCopyCleanLogs}
              className="px-3.5 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold text-xs transition-all flex items-center gap-1.5 cursor-pointer"
            >
              <Icon name={copiedCleanLogs ? "check" : "content_copy"} className="text-[15px]" />
              <span>{copiedCleanLogs ? "Copied!" : "Copy Processing Logs"}</span>
            </button>
            <button
              onClick={() => setCleanSuccessModal(null)}
              className="px-5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs transition-all flex items-center gap-1.5 cursor-pointer shadow-sm"
            >
              <Icon name="done" className="text-[16px]" />
              <span>Done</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
