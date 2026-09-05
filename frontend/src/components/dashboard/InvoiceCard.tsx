import React from "react";
import { InvoiceItem } from "@/lib/api";
import { Icon } from "@/components/common/Icon";
import {
  getFlagType,
  getFlagLabel,
  getAIConfidence,
  getVendorInitials,
  getVendorColor,
  getDueUrgencyInfo,
  isInvoiceApproved,
  flagBadgeClasses,
  formatCurrency,
} from "@/lib/invoice-utils";

export interface InvoiceCardProps {
  inv: InvoiceItem;
  idx: number;
  isActive: boolean;
  onCardClick: () => void;
  onViewOriginal: (id: string) => void;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onBlacklist: (id: string) => void;
  actionLoadingId: string | null;
}

export function InvoiceCard({
  inv,
  idx,
  isActive,
  onCardClick,
  onViewOriginal,
  onApprove,
  onReject,
  onBlacklist,
  actionLoadingId,
}: InvoiceCardProps) {
  const flagType = getFlagType(inv);
  const flagLabel = getFlagLabel(inv);
  const aiConf = getAIConfidence(inv);
  const initials = getVendorInitials(inv.vendor_name);
  const vendorColor = getVendorColor(inv.vendor_name);
  const urgency = getDueUrgencyInfo(inv.due_date);
  const isApproved = isInvoiceApproved(inv);

  return (
    <div
      className={`carousel-card group relative rounded-3xl bg-white transition-all duration-300 transform hover:-translate-y-1.5 cursor-pointer paper-shadow overflow-hidden ${
        isActive ? "ring-2 ring-indigo-500/60 active-slide-glow" : ""
      }`}
      style={{
        scrollSnapAlign: "center",
        flexShrink: 0,
        width: "min(90vw, 640px)",
        minWidth: "min(90vw, 560px)",
        color: "var(--on-surface)",
      }}
      data-index={idx}
      onClick={onCardClick}
    >
      {/* Top Status Accent Bar */}
      <div
        className={`h-1.5 w-full ${
          isApproved
            ? "bg-gradient-to-r from-emerald-400 via-teal-500 to-emerald-600"
            : flagType === "error" || inv.is_suspicious
            ? "bg-gradient-to-r from-rose-500 via-red-600 to-rose-700"
            : flagType === "warning"
            ? "bg-gradient-to-r from-amber-400 via-amber-500 to-orange-500"
            : "bg-gradient-to-r from-indigo-500 via-violet-500 to-indigo-600"
        }`}
      />

      {/* ── Visual APPROVED Stamp for Approved / Zero-Flag / Cleared Invoices ── */}
      {isApproved && (
        <div className="absolute top-7 right-7 pointer-events-none z-20 transform rotate-[-12deg] select-none opacity-90 transition-transform duration-300 group-hover:scale-105">
          <div className="border-[3.5px] border-dashed border-emerald-600/90 rounded-2xl px-3.5 py-1.5 bg-emerald-50/80 backdrop-blur-xs shadow-sm flex flex-col items-center justify-center">
            <div className="flex items-center gap-1 text-emerald-700 font-black text-[13px] tracking-widest uppercase">
              <Icon name="verified" className="text-[17px] text-emerald-600" />
              <span>APPROVED</span>
            </div>
            <span className="text-[9px] font-mono font-bold text-emerald-800/80 tracking-wider">
              {inv.ui_status === "paid" || inv.payment_status === "paid" ? "CLEARED & PAID" : "APPROVED"}
            </span>
          </div>
        </div>
      )}

      {/* Paper Invoice Interior */}
      <div className="p-7 sm:p-9 space-y-6">
        {/* Header / Letterhead */}
        <div className="flex items-start justify-between border-b pb-5" style={{ borderColor: "var(--surface-container-high)" }}>
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <div className={`w-8 h-8 rounded-lg ${vendorColor} text-white font-bold flex items-center justify-center text-sm shadow-sm`}>
                {initials}
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900 tracking-tight">{inv.vendor_name}</h3>
                <p className="text-[11px] text-slate-500">
                  {inv.vendor_address || "Address on file"}
                </p>
              </div>
            </div>
            <p className="text-[11px] text-slate-400 font-mono pt-1 flex items-center gap-2">
              <span>{inv.payment_terms ? `Terms: ${inv.payment_terms}` : ""} · {inv.format_detected?.toUpperCase()}</span>
              <span>·</span>
              <button
                onClick={(e) => { e.stopPropagation(); onViewOriginal(inv.invoice_id); }}
                className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 font-sans font-semibold text-[11px] hover:underline cursor-pointer"
                title="View original raw file"
              >
                <Icon name="visibility" className="text-[13px]" /> View Original
              </button>
            </p>
          </div>
          <div className="text-right">
            <span className={`inline-block px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider mb-2 ${flagBadgeClasses(flagType)}`}>
              {flagType === "error" && <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-600 mr-1 animate-pulse" />}
              {flagLabel}
            </span>
            <div className="text-xl font-mono font-extrabold text-slate-900">#{inv.invoice_id}</div>
            <div className="text-[11px] text-slate-500">
              Issue Date: <span className="font-medium text-slate-700">{inv.date}</span>
            </div>
          </div>
        </div>

        {/* Meta Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 py-2 px-3 bg-slate-50 rounded-xl border border-slate-100 text-xs">
          <div>
            <div className="text-[10px] uppercase font-semibold text-slate-400 flex items-center justify-between">
              <span>Due Date</span>
              {urgency && (
                <span className={`text-[9px] px-1.5 py-0.5 rounded-md border shrink-0 ${urgency.color}`}>
                  {urgency.label}
                </span>
              )}
            </div>
            <div className="font-mono font-medium text-slate-800 text-xs mt-0.5">{inv.due_date}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase font-semibold text-slate-400">Payment Terms</div>
            <div className="font-medium text-slate-800 text-xs">{inv.payment_terms || "Standard"}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase font-semibold text-slate-400">AI Confidence</div>
            <div className={`font-semibold text-xs ${aiConf.color}`}>{aiConf.value}% ({aiConf.label})</div>
          </div>
          <div>
            <div className="text-[10px] uppercase font-semibold text-slate-400">Status</div>
            <div className={`font-mono font-medium text-[11px] ${
              inv.ui_status === "paid" ? "text-emerald-600" :
              inv.ui_status === "rejected" ? "text-red-600" :
              inv.ui_status === "pending_approval" ? "text-amber-600" : "text-slate-600"
            }`}>
              {inv.ui_status === "paid" ? "Paid & Cleared" :
               inv.ui_status === "rejected" ? "Rejected" :
               inv.ui_status === "pending_approval" ? "Pending Triage" : "Unreviewed"}
            </div>
          </div>
        </div>

        {/* Line Items Detail Section */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-[11px] font-semibold text-slate-400 uppercase tracking-wider px-1">
            <span className="flex items-center gap-1.5">
              <Icon name="receipt_long" className="text-[14px]" />
              Line Items ({inv.line_items?.length || 0})
            </span>
            <span className="text-right">Total ({inv.currency})</span>
          </div>
          <div className="divide-y divide-slate-100 text-xs font-mono">
            {inv.line_items && inv.line_items.length > 0 ? (
              inv.line_items.slice(0, 3).map((li, liIdx) => {
                const isFlagged = li.stock_status === "out_of_stock" || li.stock_status === "mismatch";
                return (
                  <div
                    key={liIdx}
                    className={`py-2.5 flex items-center justify-between transition-colors ${
                      isFlagged ? "bg-amber-50/70 -mx-2 px-2 rounded-lg" : "hover:bg-slate-50/80 -mx-2 px-2 rounded-lg"
                    }`}
                  >
                    <div className="font-sans pr-4 space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className={`font-semibold ${isFlagged ? "text-amber-900" : "text-slate-900"}`}>
                          {li.item}
                        </span>
                        {li.stock_status === "out_of_stock" && (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider bg-red-100 text-red-700">
                            Out of Stock
                          </span>
                        )}
                        {li.stock_status === "mismatch" && (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider bg-amber-100 text-amber-800">
                            Stock Low ({li.quantity_in_stock ?? 0})
                          </span>
                        )}
                        {li.stock_status === "sufficient" && (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-emerald-100 text-emerald-800">
                            In Stock
                          </span>
                        )}
                        {li.catalog_matched && !li.stock_status && (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-indigo-50 text-indigo-700">
                            Catalog
                          </span>
                        )}
                      </div>
                      <div className={`text-[11px] font-sans flex items-center gap-1.5 ${isFlagged ? "text-amber-700" : "text-slate-500"}`}>
                        <span>
                          Qty {li.quantity} × {formatCurrency(li.unit_price, inv.currency)}
                        </span>
                        {li.note && (
                          <>
                            <span>·</span>
                            <span className="italic text-slate-400">{li.note}</span>
                          </>
                        )}
                        {li.product_id && (
                          <>
                            <span>·</span>
                            <span className="font-mono text-[10px] text-slate-400">{li.product_id}</span>
                          </>
                        )}
                      </div>
                    </div>
                    <span className={`font-bold font-mono shrink-0 text-sm ${isFlagged ? "text-amber-900" : "text-slate-900"}`}>
                      {formatCurrency(li.amount ?? li.quantity * li.unit_price, inv.currency)}
                    </span>
                  </div>
                );
              })
            ) : (
              <div className="py-3 px-2 text-xs text-slate-400 font-sans flex items-center justify-between">
                <span className="italic">No itemized breakdown — billing as lump-sum invoice</span>
                <span className="font-mono font-semibold text-slate-700">
                  {formatCurrency(inv.total, inv.currency)}
                </span>
              </div>
            )}
            {(inv.line_items?.length ?? 0) > 3 && (
              <div className="py-2 text-center text-[11px] text-indigo-600 font-sans font-medium flex items-center justify-center gap-1">
                <span>+{(inv.line_items?.length ?? 0) - 3} more line items</span>
                <span className="text-[10px] text-slate-400">· Click card for full matrix</span>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="pt-3 border-t border-slate-200 flex flex-col sm:flex-row items-end sm:items-center justify-between gap-2">
          {/* Warning message */}
          {inv.rules_triggered?.length ? (
            <div className={`text-[11px] px-3 py-1.5 rounded-lg border flex items-center gap-1.5 w-full sm:w-auto ${
              flagType === "error" ? "text-red-700 bg-red-50 border-red-200" :
              flagType === "warning" ? "text-amber-700 bg-amber-50 border-amber-200/60" :
              "text-emerald-700 bg-emerald-50 border-emerald-200"
            }`}>
              <Icon name={flagType === "error" ? "warning" : flagType === "success" ? "verified" : "info"} className="text-[16px]" />
              <span>{inv.rules_triggered[0].split(":").slice(-1)[0]?.trim() || inv.rules_triggered[0]}</span>
            </div>
          ) : inv.is_suspicious ? (
            <div className="text-[11px] text-red-700 bg-red-50 px-3 py-1.5 rounded-lg border border-red-200 flex items-center gap-1.5">
              <Icon name="dangerous" className="text-[16px]" />
              <span>{inv.suspicion_reasons?.[0] || "Suspicious activity detected"}</span>
            </div>
          ) : (
            <div className="text-[11px] text-emerald-700 bg-emerald-50 px-3 py-1.5 rounded-lg border border-emerald-200 flex items-center gap-1.5">
              <Icon name="verified" className="text-[16px]" />
              <span>Ready for 1-click execution or automated clearing.</span>
            </div>
          )}
          <div className="text-right shrink-0">
            {inv.shipping !== null && inv.shipping !== undefined && Number(inv.shipping) > 0 && (
              <div className="text-[11px] font-mono text-slate-600 mb-0.5 flex items-center justify-end gap-1.5">
                <span className="text-slate-400 font-sans font-medium text-[10px] uppercase tracking-wide">Shipping:</span>
                <span className="font-semibold text-slate-700 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200/60">
                  {formatCurrency(inv.shipping, inv.currency)}
                </span>
              </div>
            )}
            <div className="text-[11px] text-slate-400 uppercase font-semibold">Total Payable</div>
            <div className="text-2xl font-black text-slate-900 tracking-tight font-mono">
              {formatCurrency(inv.total, inv.currency)}
            </div>
          </div>
        </div>

        {/* ── Bottom Action Buttons ── */}
        <div
          className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2"
          onClick={(e) => e.stopPropagation()}
        >
          {isApproved ? (
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold tracking-wide">
                <Icon name="verified" className="text-[15px] text-emerald-600" />
                <span>CLEARED & APPROVED</span>
              </span>
              <span className="text-[11px] text-slate-400">Zero flags / Executive clearance granted</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 font-sans">
              <span className="font-medium text-slate-500">Actions:</span>
              <span className="hidden sm:inline text-slate-400">Press</span>
              <kbd className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 font-mono text-[10px] text-slate-600 font-bold">A</kbd>
              <span className="hidden sm:inline text-slate-400">or</span>
              <kbd className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 font-mono text-[10px] text-slate-600 font-bold">R</kbd>
            </div>
          )}

          <div className="flex items-center gap-2">
            <button
              onClick={(e) => { e.stopPropagation(); onViewOriginal(inv.invoice_id); }}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-semibold text-xs border border-indigo-200/80 transition-all active:scale-95 shadow-xs cursor-pointer"
              title="View original raw invoice document"
            >
              <Icon name="description" className="text-[14px]" />
              Original
            </button>

            {/* Only show decision actions if the invoice is NOT approved */}
            {!isApproved && (
              <>
                <button
                  onClick={(e) => { e.stopPropagation(); onApprove(inv.invoice_id); }}
                  disabled={actionLoadingId === inv.invoice_id}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-all active:scale-95 shadow-sm hover:shadow-emerald-500/30 disabled:opacity-50 cursor-pointer"
                >
                  <Icon name="check_circle" className="text-[15px]" />
                  Approve
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); onReject(inv.invoice_id); }}
                  disabled={actionLoadingId === inv.invoice_id}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs border border-rose-400/40 transition-all active:scale-95 shadow-sm hover:shadow-rose-500/30 disabled:opacity-50 cursor-pointer"
                >
                  <Icon name="cancel" className="text-[15px]" />
                  Reject
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); onBlacklist(inv.invoice_id); }}
                  disabled={actionLoadingId === inv.invoice_id}
                  className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-black text-rose-400 hover:text-rose-300 font-semibold text-xs border border-rose-900/60 transition-all active:scale-95 shadow-sm disabled:opacity-50 cursor-pointer"
                >
                  <Icon name="block" className="text-[15px]" />
                  Blacklist
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
