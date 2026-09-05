import React from "react";
import { TestBusinessRuleResult } from "@/lib/api";
import { Icon } from "@/components/common/Icon";

export interface AddRuleModalProps {
  addRuleModalOpen: boolean;
  setAddRuleModalOpen: (open: boolean) => void;
  newRuleName: string;
  setNewRuleName: (name: string) => void;
  newRuleDesc: string;
  setNewRuleDesc: (desc: string) => void;
  newRuleAction: string;
  setNewRuleAction: (action: string) => void;
  newRuleCustomSql: string;
  setNewRuleCustomSql: (sql: string) => void;
  showCustomSqlInput: boolean;
  setShowCustomSqlInput: (show: boolean) => void;
  testingRule: boolean;
  testResult: TestBusinessRuleResult | null;
  submittingRule: boolean;
  handleSaveNewRule: (e: React.FormEvent) => Promise<void>;
  handleTestNewRule: () => Promise<void>;
  applyRuleTemplate: (name: string, desc: string) => void;
}

export function AddRuleModal({
  addRuleModalOpen,
  setAddRuleModalOpen,
  newRuleName,
  setNewRuleName,
  newRuleDesc,
  setNewRuleDesc,
  newRuleAction,
  setNewRuleAction,
  newRuleCustomSql,
  setNewRuleCustomSql,
  showCustomSqlInput,
  setShowCustomSqlInput,
  testingRule,
  testResult,
  submittingRule,
  handleSaveNewRule,
  handleTestNewRule,
  applyRuleTemplate,
}: AddRuleModalProps) {
  if (!addRuleModalOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 lg:p-10 transition-all animate-fade-in"
      style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(12px)" }}
      onClick={() => setAddRuleModalOpen(false)}
    >
      <div
        className="relative w-full max-w-2xl rounded-3xl shadow-2xl flex flex-col overflow-hidden border border-white/20 animate-scale-in"
        style={{ background: "var(--surface)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div
          className="px-6 py-4 border-b flex items-center justify-between gap-4"
          style={{
            background: "var(--surface-container-lowest)",
            borderColor: "var(--surface-container)",
          }}
        >
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-600">
              <Icon name="add_moderator" className="text-[24px]" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900">Add Corporate Policy Rule</h2>
              <p className="text-xs text-slate-500">
                Translate natural language conditions into deterministic SQLite queries or AI LLM evaluators.
              </p>
            </div>
          </div>
          <button
            onClick={() => setAddRuleModalOpen(false)}
            className="p-1.5 rounded-xl hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-all cursor-pointer"
          >
            <Icon name="close" className="text-[20px]" />
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleSaveNewRule} className="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
          {/* Rule Name */}
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center justify-between">
              <span>Rule Code Name</span>
              <span className="text-[10px] text-slate-400 font-normal">
                Uppercase identifier (e.g. ACME_PRICE_CAP)
              </span>
            </label>
            <input
              type="text"
              required
              placeholder="e.g. RESTRICT_ACME_EXPENSES"
              value={newRuleName}
              onChange={(e) => setNewRuleName(e.target.value.toUpperCase().replace(/\s+/g, "_"))}
              className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-slate-300 text-xs font-mono font-bold text-slate-800 placeholder-slate-400 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition-all"
            />
          </div>

          {/* Natural Language Condition */}
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center justify-between">
              <span>Condition / Description</span>
              <span className="text-[10px] text-slate-400 font-normal">
                Natural language policy specification
              </span>
            </label>
            <textarea
              required
              rows={3}
              placeholder={
                "e.g. Vendor is Acme Corp and total > 3000\nor: Payment terms Net 90\nor: Total > 15000\nor: Item GadgetX unit price over 250"
              }
              value={newRuleDesc}
              onChange={(e) => setNewRuleDesc(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-slate-300 text-xs text-slate-800 placeholder-slate-400 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 transition-all"
            />
          </div>

          {/* Quick Template Chips */}
          <div className="space-y-1.5">
            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              Quick Archetype Templates (Click to fill):
            </span>
            <div className="flex items-center gap-1.5 flex-wrap">
              {[
                { label: "Vendor + Amount", name: "RESTRICT_ACME_EXPENSES", desc: "Vendor is Acme Corp and total > 3000" },
                { label: "Payment Terms", name: "DISALLOW_NET_90", desc: "Payment terms Net 90" },
                { label: "Amount Ceiling", name: "HIGH_VALUE_THRESHOLD", desc: "Total over $15,000" },
                { label: "Line Item Price", name: "WIDGET_PRICE_CAP", desc: "Item GadgetX unit price over 250" },
                { label: "Shipping Fee", name: "EXCESSIVE_SHIPPING", desc: "Shipping over 150" },
                { label: "Foreign Currency", name: "NON_USD_SETTLEMENT", desc: "Non-USD currency transaction" },
                {
                  label: "AI Subjective",
                  name: "VAGUE_CONSULTING",
                  desc: "Flag invoices where work description is vague, duplicate consulting, or lacks clear milestone deliverables",
                },
              ].map((tmpl) => (
                <button
                  key={tmpl.label}
                  type="button"
                  onClick={() => applyRuleTemplate(tmpl.name, tmpl.desc)}
                  className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-indigo-50 hover:text-indigo-700 text-[11px] font-medium text-slate-700 border border-slate-200 transition-all cursor-pointer"
                >
                  {tmpl.label}
                </button>
              ))}
            </div>
          </div>

          {/* Enforcement Action */}
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">
              Enforcement Action
            </label>
            <div className="grid grid-cols-3 gap-2">
              {[
                {
                  id: "REQUIRE_HUMAN_APPROVAL",
                  label: "VP Human Approval",
                  desc: "Hold in Pending Triage",
                  icon: "pending_actions",
                  color: "text-amber-700 border-amber-300 bg-amber-50/50",
                },
                {
                  id: "REJECT",
                  label: "Auto-Reject",
                  desc: "Block disbursement",
                  icon: "cancel",
                  color: "text-rose-700 border-rose-300 bg-rose-50/50",
                },
                {
                  id: "WARN",
                  label: "Policy Warning",
                  desc: "Flag without holding",
                  icon: "warning",
                  color: "text-blue-700 border-blue-300 bg-blue-50/50",
                },
              ].map((act) => (
                <button
                  key={act.id}
                  type="button"
                  onClick={() => setNewRuleAction(act.id)}
                  className={`p-3 rounded-xl border text-left cursor-pointer transition-all ${
                    newRuleAction === act.id
                      ? `${act.color} ring-2 ring-indigo-500 font-semibold shadow-xs`
                      : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <Icon name={act.icon} className="text-[16px]" />
                    <span className="text-xs font-bold">{act.label}</span>
                  </div>
                  <p className="text-[10px] opacity-75">{act.desc}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Advanced SQL Accordion Toggle */}
          <div className="pt-1">
            <button
              type="button"
              onClick={() => setShowCustomSqlInput(!showCustomSqlInput)}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 flex items-center gap-1 cursor-pointer"
            >
              <Icon name={showCustomSqlInput ? "expand_less" : "expand_more"} className="text-[18px]" />
              <span>
                {showCustomSqlInput
                  ? "Hide Advanced SQLite Expression"
                  : "Advanced: Custom SQLite WHERE Clause"}
              </span>
            </button>

            {showCustomSqlInput && (
              <div className="mt-2 space-y-1">
                <input
                  type="text"
                  placeholder="e.g. total > 5000 AND LOWER(payment_terms) LIKE '%net 90%'"
                  value={newRuleCustomSql}
                  onChange={(e) => setNewRuleCustomSql(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-900 border border-slate-700 text-xs font-mono text-emerald-400 placeholder-slate-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
                />
                <p className="text-[10px] text-slate-400">
                  Direct SQLite boolean WHERE clause evaluated against the invoices table.
                </p>
              </div>
            )}
          </div>

          {/* Live Test & Preview Button */}
          <div className="pt-2 flex items-center justify-between gap-3 border-t border-slate-100">
            <button
              type="button"
              onClick={handleTestNewRule}
              disabled={testingRule || !newRuleDesc.trim()}
              className="px-3.5 py-2 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold flex items-center gap-1.5 cursor-pointer shadow-xs disabled:opacity-50 transition-all"
            >
              <Icon
                name={testingRule ? "sync" : "science"}
                className={`text-[16px] ${testingRule ? "animate-spin text-indigo-600" : "text-indigo-600"}`}
              />
              <span>{testingRule ? "Testing..." : "Test & Compile Rule"}</span>
            </button>
          </div>

          {/* Test Result Display */}
          {testResult && (
            <div className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200 text-xs space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-900 flex items-center gap-1.5">
                  <Icon name="verified" className="text-[16px] text-emerald-600" />
                  Rule Compiler Output
                </span>
                <span
                  className={`px-2 py-0.5 rounded-md text-[10px] font-bold ${
                    testResult.compiled.rule_type === "deterministic_query"
                      ? "bg-emerald-100 text-emerald-800"
                      : "bg-purple-100 text-purple-800"
                  }`}
                >
                  {testResult.compiled.rule_type === "deterministic_query"
                    ? "Deterministic SQLite Query"
                    : "AI LLM Evaluator"}
                </span>
              </div>

              {testResult.compiled.sql_query && (
                <div className="p-2.5 rounded-xl bg-slate-900 text-emerald-300 font-mono text-[11px] overflow-x-auto">
                  {testResult.compiled.sql_query}
                </div>
              )}

              <div className="text-[11px] text-slate-600">
                {testResult.compiled.rule_type === "deterministic_query" ? (
                  <span>
                    Current Database Test:{" "}
                    <span className="font-bold text-slate-900">
                      {testResult.matches_count} invoices
                    </span>{" "}
                    match this condition in SQLite.
                  </span>
                ) : (
                  <span>{testResult.message}</span>
                )}
              </div>
            </div>
          )}

          {/* Modal Actions */}
          <div
            className="pt-4 border-t flex items-center justify-end gap-3"
            style={{ borderColor: "var(--surface-container)" }}
          >
            <button
              type="button"
              onClick={() => setAddRuleModalOpen(false)}
              className="px-4 py-2.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submittingRule}
              className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white text-xs font-bold flex items-center gap-2 cursor-pointer shadow-sm disabled:opacity-50"
            >
              <Icon
                name={submittingRule ? "sync" : "check"}
                className={`text-[16px] ${submittingRule ? "animate-spin" : ""}`}
              />
              <span>{submittingRule ? "Deploying..." : "Save & Deploy Policy Rule"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
