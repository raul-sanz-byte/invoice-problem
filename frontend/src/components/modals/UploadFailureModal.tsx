"use client";

import React from "react";
import Icon from "@/components/common/Icon";

export interface UploadFailureInfo {
  open: boolean;
  isQuota: boolean;
  failures: Array<{ filename: string; errors?: string[] }>;
  rawError?: string;
}

interface UploadFailureModalProps {
  uploadFailureModal: UploadFailureInfo | null;
  setUploadFailureModal: (modal: UploadFailureInfo | null) => void;
  failureRawExpanded: boolean;
  setFailureRawExpanded: React.Dispatch<React.SetStateAction<boolean>>;
}

export default function UploadFailureModal({
  uploadFailureModal,
  setUploadFailureModal,
  failureRawExpanded,
  setFailureRawExpanded,
}: UploadFailureModalProps) {
  if (!uploadFailureModal?.open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-8 animate-fade-in"
      style={{ background: "rgba(0,0,0,0.80)", backdropFilter: "blur(16px)" }}
      onClick={() => setUploadFailureModal(null)}
    >
      <div
        className="relative w-full max-w-2xl max-h-[90vh] rounded-3xl shadow-2xl flex flex-col overflow-hidden border animate-scale-in"
        style={{
          background: "var(--surface)",
          borderColor: uploadFailureModal.isQuota ? "rgba(245,158,11,0.35)" : "rgba(239,68,68,0.35)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="px-6 py-5 border-b flex items-start justify-between gap-4"
          style={{
            background: uploadFailureModal.isQuota
              ? "linear-gradient(135deg,rgba(245,158,11,0.13) 0%,rgba(239,68,68,0.08) 100%)"
              : "linear-gradient(135deg,rgba(239,68,68,0.13) 0%,rgba(245,158,11,0.06) 100%)",
            borderColor: uploadFailureModal.isQuota ? "rgba(245,158,11,0.2)" : "rgba(239,68,68,0.2)",
          }}
        >
          <div className="flex items-center gap-3.5 min-w-0">
            <div
              className="w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 shadow-sm"
              style={{
                background: uploadFailureModal.isQuota ? "rgba(245,158,11,0.15)" : "rgba(239,68,68,0.15)",
                border: uploadFailureModal.isQuota ? "1px solid rgba(245,158,11,0.4)" : "1px solid rgba(239,68,68,0.4)",
              }}
            >
              <Icon
                name={uploadFailureModal.isQuota ? "data_usage" : "error"}
                className={`text-[28px] ${uploadFailureModal.isQuota ? "text-amber-500" : "text-rose-500"}`}
              />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap mb-0.5">
                <h2 className="text-base font-bold">
                  {uploadFailureModal.isQuota ? "AI Quota Exceeded — Invoice Not Ingested" : "Upload Failed — Invoice Not Ingested"}
                </h2>
                <span
                  className="px-2.5 py-0.5 rounded-full text-[11px] font-bold uppercase flex items-center gap-1"
                  style={{
                    background: uploadFailureModal.isQuota ? "rgba(245,158,11,0.15)" : "rgba(239,68,68,0.15)",
                    color: uploadFailureModal.isQuota ? "#d97706" : "#dc2626",
                    border: uploadFailureModal.isQuota ? "1px solid rgba(245,158,11,0.4)" : "1px solid rgba(239,68,68,0.4)",
                  }}
                >
                  <span className={`w-1.5 h-1.5 rounded-full inline-block animate-pulse ${uploadFailureModal.isQuota ? "bg-amber-500" : "bg-rose-500"}`} />
                  {uploadFailureModal.isQuota ? "429 RESOURCE_EXHAUSTED" : "INGESTION FAILED"}
                </span>
              </div>
              <p className="text-xs" style={{ color: "var(--secondary)" }}>
                {uploadFailureModal.failures.length > 0
                  ? `${uploadFailureModal.failures.length} file(s) failed to ingest.`
                  : "The upload request failed before reaching the server."}
              </p>
            </div>
          </div>
          <button
            onClick={() => setUploadFailureModal(null)}
            className="p-2 rounded-xl bg-slate-200/70 hover:bg-slate-300 text-slate-700 transition-all cursor-pointer shrink-0"
            title="Close"
          >
            <Icon name="close" className="text-[18px]" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto flex-1 modal-scroll space-y-5">
          {/* What Happened */}
          <div className="p-4 rounded-2xl border bg-amber-50/60 border-amber-200/70">
            <h3 className="text-xs font-bold text-amber-900 flex items-center gap-1.5 mb-2">
              <Icon name="info" className="text-[16px] text-amber-600" />
              What Happened
            </h3>
            {uploadFailureModal.isQuota ? (
              <p className="text-xs text-amber-800 leading-relaxed">
                Your <strong>Google Gemini Free Tier API quota</strong> was exceeded while the AI was trying to extract invoice fields from the uploaded document.
                The Gemini Free Tier allows up to <strong>20 requests per day</strong> for <code className="bg-amber-100 px-1 rounded text-[11px]">gemini-2.5-flash</code>.
                Because field extraction failed, the invoice could not be parsed and was <strong>NOT saved</strong> to the SQLite database.
              </p>
            ) : (
              <p className="text-xs text-amber-800 leading-relaxed">
                An error occurred during the ingestion pipeline. The AI extraction layer encountered a problem and the invoice could not be parsed or saved to the database.
              </p>
            )}
          </div>

          {/* Why Invoice Was Not Ingested */}
          <div className="p-4 rounded-2xl border bg-rose-50/50 border-rose-200/60">
            <h3 className="text-xs font-bold text-rose-900 flex items-center gap-1.5 mb-2">
              <Icon name="storage" className="text-[16px] text-rose-600" />
              Why the Invoice Was Not Saved
            </h3>
            <p className="text-xs text-rose-800 leading-relaxed">
              FlowAudit AI requires AI-extracted structured fields (invoice ID, vendor, totals, line items) before saving to the database.
              If AI extraction fails, the pipeline aborts early to prevent <strong>incomplete or corrupt invoice records</strong> from entering the audit system.
              The invoice file is preserved in <code className="bg-rose-100 px-1 rounded text-[11px]">uploads/</code> but was not ingested.
            </p>
          </div>

          {/* Next Steps */}
          <div className="p-4 rounded-2xl border border-indigo-200/60 bg-indigo-50/40">
            <h3 className="text-xs font-bold text-indigo-900 flex items-center gap-1.5 mb-3">
              <Icon name="lightbulb" className="text-[16px] text-indigo-600" />
              How to Resolve
            </h3>
            <ul className="space-y-2.5">
              {uploadFailureModal.isQuota ? (
                <>
                  <li className="flex items-start gap-2 text-xs text-indigo-800">
                    <span className="w-5 h-5 rounded-full bg-indigo-200 text-indigo-700 text-[11px] font-bold flex items-center justify-center shrink-0 mt-0.5">1</span>
                    <span><strong>Wait ~60 seconds</strong> for the Gemini burst window to reset, then re-upload the PDF.</span>
                  </li>
                  <li className="flex items-start gap-2 text-xs text-indigo-800">
                    <span className="w-5 h-5 rounded-full bg-indigo-200 text-indigo-700 text-[11px] font-bold flex items-center justify-center shrink-0 mt-0.5">2</span>
                    <span><strong>Upgrade to a paid tier</strong> at <code className="bg-indigo-100 px-1 rounded">ai.google.dev</code> — the free tier limit is 20 req/day for gemini-2.5-flash.</span>
                  </li>
                  <li className="flex items-start gap-2 text-xs text-indigo-800">
                    <span className="w-5 h-5 rounded-full bg-indigo-200 text-indigo-700 text-[11px] font-bold flex items-center justify-center shrink-0 mt-0.5">3</span>
                    <span>Set <code className="bg-indigo-100 px-1 rounded">OPENAI_API_KEY</code> in your <code className="bg-indigo-100 px-1 rounded">.env</code> as a fallback LLM provider.</span>
                  </li>
                  <li className="flex items-start gap-2 text-xs text-indigo-800">
                    <span className="w-5 h-5 rounded-full bg-indigo-200 text-indigo-700 text-[11px] font-bold flex items-center justify-center shrink-0 mt-0.5">4</span>
                    <span>For <strong>JSON/CSV/XML</strong> formats, the AI is not needed — those use deterministic parsers and will always succeed.</span>
                  </li>
                </>
              ) : (
                <>
                  <li className="flex items-start gap-2 text-xs text-indigo-800">
                    <span className="w-5 h-5 rounded-full bg-indigo-200 text-indigo-700 text-[11px] font-bold flex items-center justify-center shrink-0 mt-0.5">1</span>
                    <span>Check that the <strong>backend server</strong> is running at <code className="bg-indigo-100 px-1 rounded">http://localhost:8000</code>.</span>
                  </li>
                  <li className="flex items-start gap-2 text-xs text-indigo-800">
                    <span className="w-5 h-5 rounded-full bg-indigo-200 text-indigo-700 text-[11px] font-bold flex items-center justify-center shrink-0 mt-0.5">2</span>
                    <span>Ensure a valid <code className="bg-indigo-100 px-1 rounded">GEMINI_API_KEY</code> or <code className="bg-indigo-100 px-1 rounded">OPENAI_API_KEY</code> is set in your <code className="bg-indigo-100 px-1 rounded">.env</code> file.</span>
                  </li>
                  <li className="flex items-start gap-2 text-xs text-indigo-800">
                    <span className="w-5 h-5 rounded-full bg-indigo-200 text-indigo-700 text-[11px] font-bold flex items-center justify-center shrink-0 mt-0.5">3</span>
                    <span>Verify the file is a supported format: <strong>PDF, JSON, CSV, XML, or TXT</strong>.</span>
                  </li>
                </>
              )}
            </ul>
          </div>

          {/* Affected files list */}
          {uploadFailureModal.failures.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold" style={{ color: "var(--on-surface-variant)" }}>
                Affected File(s)
              </h3>
              {uploadFailureModal.failures.map((f, idx) => (
                <div key={idx} className="flex items-center gap-2.5 p-3 rounded-xl bg-slate-100/70 border border-slate-200/70">
                  <Icon name="description" className="text-[18px] text-slate-500 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-slate-800 truncate">{f.filename}</p>
                    {f.errors && f.errors.length > 0 && (
                      <p className="text-[11px] text-rose-600 truncate mt-0.5">{f.errors[0].replace("[AI_QUOTA_EXCEEDED] ", "")}</p>
                    )}
                  </div>
                  <span className="shrink-0 px-2 py-0.5 rounded-md text-[10px] font-bold bg-rose-100 text-rose-700 border border-rose-200">FAILED</span>
                </div>
              ))}
            </div>
          )}

          {/* Raw error expander */}
          {uploadFailureModal.rawError && (
            <div className="space-y-1.5">
              <button
                onClick={() => setFailureRawExpanded((v) => !v)}
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 transition-colors cursor-pointer"
              >
                <Icon name={failureRawExpanded ? "expand_less" : "expand_more"} className="text-[16px]" />
                {failureRawExpanded ? "Hide" : "Show"} Raw Error Details
              </button>
              {failureRawExpanded && (
                <div className="p-3 rounded-xl bg-slate-900 border border-slate-700 font-mono text-[11px] text-rose-300 overflow-x-auto whitespace-pre-wrap break-all max-h-52 modal-scroll">
                  {uploadFailureModal.rawError}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t flex items-center justify-between gap-3" style={{ borderColor: "var(--surface-container)" }}>
          <p className="text-[11px] text-slate-400 flex items-center gap-1">
            <Icon name="shield" className="text-[14px]" />
            Invoice was NOT saved to the database. No data was corrupted.
          </p>
          <button
            onClick={() => setUploadFailureModal(null)}
            className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-slate-700 to-slate-800 hover:from-slate-600 hover:to-slate-700 text-white text-xs font-bold cursor-pointer shadow-sm flex items-center gap-1.5"
          >
            <Icon name="close" className="text-[16px]" />
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
