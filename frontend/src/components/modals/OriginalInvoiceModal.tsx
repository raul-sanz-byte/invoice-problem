import React from "react";
import { OriginalInvoiceResponse, InvoiceItem } from "@/lib/api";
import { Icon } from "@/components/common/Icon";
import { getFormatIconAndColor, formatFileSize } from "@/lib/invoice-utils";

export interface OriginalInvoiceModalProps {
  originalViewerOpen: boolean;
  closeOriginalViewer: () => void;
  originalDoc: OriginalInvoiceResponse | null;
  loadingOriginal: boolean;
  originalError: string | null;
  copiedRaw: boolean;
  handleCopyRaw: () => void;
  modalInvoice?: InvoiceItem | null;
}

export function OriginalInvoiceModal({
  originalViewerOpen,
  closeOriginalViewer,
  originalDoc,
  loadingOriginal,
  originalError,
  copiedRaw,
  handleCopyRaw,
  modalInvoice,
}: OriginalInvoiceModalProps) {
  if (!originalViewerOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 lg:p-10 transition-all animate-fade-in"
      style={{ background: "rgba(0,0,0,0.65)", backdropFilter: "blur(14px)" }}
      onClick={closeOriginalViewer}
    >
      <div
        className="relative w-full max-w-5xl max-h-[92vh] rounded-3xl shadow-2xl flex flex-col overflow-hidden border border-white/20 animate-scale-in"
        style={{ background: "var(--surface)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="px-6 py-4 border-b flex items-center justify-between gap-4"
          style={{
            background: "var(--surface-container-lowest)",
            borderColor: "var(--surface-container)",
          }}
        >
          <div className="flex items-center gap-3 min-w-0">
            {(() => {
              const styling = getFormatIconAndColor(originalDoc?.format, originalDoc?.filename);
              return (
                <div
                  className={`p-2.5 rounded-xl ${styling.bg} ${styling.text} border ${styling.border} flex items-center justify-center shrink-0`}
                >
                  <Icon name={styling.icon} className="text-[24px]" />
                </div>
              );
            })()}
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-base sm:text-lg font-bold truncate">
                  {originalDoc?.filename || "Original Invoice Document"}
                </h2>
                {originalDoc && (
                  <span className="px-2 py-0.5 rounded-md text-[10px] font-mono font-bold uppercase bg-slate-100 text-slate-700 border border-slate-200 shrink-0">
                    .{originalDoc.format}
                  </span>
                )}
              </div>
              <div className="text-xs flex items-center gap-2 truncate" style={{ color: "var(--secondary)" }}>
                <span>Invoice #{originalDoc?.invoice_id || modalInvoice?.invoice_id || "..."}</span>
                {originalDoc?.size_bytes ? (
                  <>
                    <span>·</span>
                    <span>Size: {formatFileSize(originalDoc.size_bytes)}</span>
                  </>
                ) : null}
                {originalDoc?.content_type && (
                  <>
                    <span>·</span>
                    <span className="font-mono text-[11px] hidden sm:inline">{originalDoc.content_type}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {originalDoc && !originalDoc.is_binary && originalDoc.content && (
              <button
                onClick={handleCopyRaw}
                className="hidden sm:flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-all cursor-pointer"
                title="Copy raw document content to clipboard"
              >
                <Icon
                  name={copiedRaw ? "check" : "content_copy"}
                  className={`text-[16px] ${copiedRaw ? "text-emerald-600" : ""}`}
                />
                <span>{copiedRaw ? "Copied!" : "Copy Raw"}</span>
              </button>
            )}
            {originalDoc && (
              <>
                <button
                  onClick={() => window.open(originalDoc.view_url, "_blank")}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold border border-indigo-200/80 transition-all cursor-pointer"
                  title="Open document in new browser tab"
                >
                  <Icon name="open_in_new" className="text-[16px]" />
                  <span className="hidden sm:inline">New Tab</span>
                </button>
                <a
                  href={originalDoc.download_url}
                  download={originalDoc.filename}
                  className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-sm transition-all cursor-pointer"
                  title="Download original file"
                >
                  <Icon name="download" className="text-[16px]" />
                  <span className="hidden sm:inline">Download</span>
                </a>
              </>
            )}
            <button
              onClick={closeOriginalViewer}
              className="p-2 rounded-xl hover:opacity-80 transition-all flex items-center justify-center cursor-pointer ml-1"
              style={{ background: "var(--surface-container-low)", color: "var(--secondary)" }}
              title="Close (ESC)"
            >
              <Icon name="close" className="text-[20px]" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div
          className="p-6 overflow-y-auto flex-1 modal-scroll flex flex-col"
          style={{ background: "var(--surface)" }}
        >
          {loadingOriginal ? (
            <div className="flex flex-col items-center justify-center py-24 gap-3">
              <Icon name="sync" className="text-[36px] text-indigo-500 animate-spin" />
              <p className="text-sm font-medium" style={{ color: "var(--secondary)" }}>
                Fetching original document from server...
              </p>
            </div>
          ) : originalError ? (
            <div className="p-6 rounded-2xl bg-red-50 border border-red-200 text-red-700 flex flex-col items-center text-center gap-3 my-auto">
              <Icon name="error" className="text-[40px] text-red-500" />
              <div className="font-semibold text-base">Unable to load document</div>
              <p className="text-xs text-red-600 max-w-md">{originalError}</p>
              {originalDoc && (
                <a
                  href={originalDoc.view_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 px-4 py-2 rounded-xl bg-red-600 text-white font-semibold text-xs shadow-sm hover:bg-red-500 transition-all"
                >
                  Try Direct Server Link
                </a>
              )}
            </div>
          ) : originalDoc?.is_binary || originalDoc?.format.toLowerCase() === "pdf" ? (
            <div className="w-full h-[68vh] rounded-2xl overflow-hidden border border-slate-200 bg-slate-100 flex flex-col shadow-inner">
              <iframe
                src={originalDoc.view_url}
                className="w-full h-full"
                title={`Original PDF ${originalDoc.filename}`}
              />
            </div>
          ) : originalDoc?.content ? (
            <div className="rounded-2xl overflow-hidden border border-slate-800 bg-slate-950 shadow-2xl flex flex-col flex-1">
              <div className="px-4 py-2.5 bg-slate-900 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400">
                <div className="flex items-center gap-2">
                  <div className="flex gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80 inline-block" />
                    <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80 inline-block" />
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80 inline-block" />
                  </div>
                  <span className="font-mono text-[11px] text-slate-300 ml-2 font-medium">
                    {originalDoc.filename}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-[11px] text-slate-500 font-mono">
                  <span>{originalDoc.format.toUpperCase()}</span>
                  <span>·</span>
                  <span>UTF-8</span>
                </div>
              </div>
              <div className="p-5 max-h-[62vh] overflow-auto select-all modal-scroll flex-1">
                <pre className="font-mono text-xs leading-relaxed text-slate-200 whitespace-pre">
                  <code>{originalDoc.content}</code>
                </pre>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-20 gap-3 text-slate-400">
              <Icon name="description" className="text-[48px]" />
              <p className="text-sm">No raw preview content available for this document format.</p>
              {originalDoc && (
                <a
                  href={originalDoc.download_url}
                  download={originalDoc.filename}
                  className="px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold shadow-sm hover:bg-indigo-500 transition-all flex items-center gap-1.5"
                >
                  <Icon name="download" className="text-[16px]" /> Download Original File
                </a>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
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
            <span>Retrieved verbatim from backend AP repository.</span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={closeOriginalViewer}
              className="px-4 py-2 rounded-xl bg-slate-200 hover:bg-slate-300 text-slate-800 font-semibold text-xs transition-all cursor-pointer"
            >
              Close Viewer
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
