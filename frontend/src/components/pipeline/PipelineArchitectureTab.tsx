import React from "react";
import { DashboardStats } from "@/lib/api";
import { Icon } from "@/components/common/Icon";
import { formatCurrency } from "@/lib/invoice-utils";

export interface PipelineArchitectureTabProps {
  stats?: DashboardStats | null;
}

export function PipelineArchitectureTab({ stats }: PipelineArchitectureTabProps) {
  return (
    <div className="space-y-5 animate-fade-in">
      {/* Pipeline Header */}
      <div
        className="p-6 sm:p-7 rounded-3xl border shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-5"
        style={{
          background: "var(--surface-container-lowest)",
          borderColor: "var(--surface-container)",
        }}
      >
        <div className="space-y-1.5 max-w-3xl">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-2xl bg-gradient-to-tr from-emerald-600 to-teal-600 flex items-center justify-center text-white shadow-sm shrink-0">
              <Icon name="account_tree" className="text-[24px]" />
            </div>
            <div>
              <h1 className="text-xl sm:text-2xl font-black text-slate-900 tracking-tight">
                Automated Pipeline & Autonomous Execution Engine
              </h1>
              <p className="text-xs font-medium text-slate-500">
                End-to-end multi-format ingestion, OCR extraction, deterministic SQLite policy verification, VP cognitive review, and disbursement.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <div className="px-3.5 py-1.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>Pipeline Online & Healthy</span>
          </div>
        </div>
      </div>

      {/* 5-Stage Ingestion Flowchart */}
      <div className="p-6 rounded-3xl border bg-white border-slate-200/80 shadow-xs space-y-4">
        <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
          Execution Architecture (5 Continuous Stages)
        </div>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-3.5 relative">
          {[
            {
              step: "01",
              title: "Multi-Format Ingestion",
              desc: "Ingests raw PDF, JSON, XML, CSV, and unstructured TXT documents.",
              icon: "upload_file",
              color: "from-blue-600 to-indigo-600",
              badge: "Multi-Format",
            },
            {
              step: "02",
              title: "AI & Deterministic Parse",
              desc: "Extracts vendor, totals, due dates, and line item catalog matches.",
              icon: "document_scanner",
              color: "from-indigo-600 to-violet-600",
              badge: "Gemini / Claude",
            },
            {
              step: "03",
              title: "Business Rules Engine",
              desc: "Applies deterministic SQLite queries (0ms) & AI subjective evaluators.",
              icon: "gavel",
              color: "from-violet-600 to-purple-600",
              badge: "SQL + AI Hybrid",
            },
            {
              step: "04",
              title: "VP Cognitive Triage",
              desc: "Performs fraud analysis, unbundled billing detection, and risk scoring.",
              icon: "psychology",
              color: "from-purple-600 to-pink-600",
              badge: "Self-Reflection",
            },
            {
              step: "05",
              title: "Autonomous Settlement",
              desc: "Auto-disburses clean zero-flag invoices; holds high-risk for VP sign-off.",
              icon: "payments",
              color: "from-emerald-600 to-teal-600",
              badge: "Instant Payout",
            },
          ].map((stage) => (
            <div
              key={stage.step}
              className="p-4 rounded-2xl border border-slate-200/90 bg-slate-50/50 flex flex-col justify-between space-y-3 relative group hover:bg-white hover:shadow-sm hover:border-indigo-300 transition-all"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs font-black text-slate-400">STAGE {stage.step}</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-white text-slate-700 border border-slate-200 shadow-2xs">
                  {stage.badge}
                </span>
              </div>

              <div className="space-y-1.5">
                <div className={`w-9 h-9 rounded-xl bg-gradient-to-tr ${stage.color} flex items-center justify-center text-white shadow-2xs`}>
                  <Icon name={stage.icon} className="text-[20px]" />
                </div>
                <h3 className="text-xs font-extrabold text-slate-900">{stage.title}</h3>
                <p className="text-[11px] text-slate-600 leading-relaxed">{stage.desc}</p>
              </div>

              <div className="pt-2 border-t border-slate-200/60 flex items-center justify-between text-[10px] font-medium text-slate-500">
                <span>Active</span>
                <Icon name="check_circle" className="text-[14px] text-emerald-600" />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Engine Performance & Telemetry */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
        <div className="p-5 rounded-2xl border bg-white border-slate-200/80 shadow-xs space-y-2">
          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Autonomous Clearance</span>
          <div className="text-2xl font-black text-emerald-600">
            {stats && stats.total_invoices > 0 ? Math.round((stats.approved_count / stats.total_invoices) * 100) : 100}%
          </div>
          <p className="text-xs text-slate-500">Clean zero-flag invoices approved and scheduled for instant disbursement.</p>
        </div>

        <div className="p-5 rounded-2xl border bg-white border-slate-200/80 shadow-xs space-y-2">
          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Deterministic Rule Latency</span>
          <div className="text-2xl font-black text-indigo-600">&lt; 2 ms</div>
          <p className="text-xs text-slate-500">Fast indexed SQLite WHERE queries on extracted database columns.</p>
        </div>

        <div className="p-5 rounded-2xl border bg-white border-slate-200/80 shadow-xs space-y-2">
          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Disbursement Volume</span>
          <div className="text-2xl font-black text-slate-900">{formatCurrency(stats?.total_disbursed ?? 0)}</div>
          <p className="text-xs text-slate-500">Total verified funds cleared through corporate mock payment service.</p>
        </div>
      </div>
    </div>
  );
}
