"use client";

import React, { useState, useMemo } from "react";
import { BusinessRule, TestBusinessRuleResult, InvoiceItem } from "@/lib/api";
import { Icon } from "@/components/common/Icon";
import { formatCurrency } from "@/lib/invoice-utils";

export interface RulesTabProps {
  businessRules: BusinessRule[];
  loadingRules: boolean;
  loadBusinessRules: () => Promise<void>;
  openAddRuleModal: () => void;
  handleToggleRule: (rule: BusinessRule) => Promise<void>;
  handleDeleteRule: (rule: BusinessRule) => Promise<void>;
  handleTestExistingRule: (rule: BusinessRule) => Promise<void>;
  ruleTestResults: Record<number, TestBusinessRuleResult>;
  setRuleTestResults: React.Dispatch<React.SetStateAction<Record<number, TestBusinessRuleResult>>>;
  activeRuleTestId: number | null;
  allInvoices: InvoiceItem[];
  openModal: (inv: InvoiceItem) => void;
}

export function RulesTab({
  businessRules,
  loadingRules,
  loadBusinessRules,
  openAddRuleModal,
  handleToggleRule,
  handleDeleteRule,
  handleTestExistingRule,
  ruleTestResults,
  setRuleTestResults,
  activeRuleTestId,
  allInvoices,
  openModal,
}: RulesTabProps) {
  const [ruleSearch, setRuleSearch] = useState("");
  const [ruleTypeFilter, setRuleTypeFilter] = useState<"all" | "deterministic" | "llm" | "system" | "custom">("all");
  const [expandedSqlIds, setExpandedSqlIds] = useState<Record<number, boolean>>({});

  const toggleSqlExpand = (id: number) => {
    setExpandedSqlIds((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // ── Executive Rule Telemetry ─────────────────────────────────────
  const ruleMetrics = useMemo(() => {
    const total = businessRules.length;
    const active = businessRules.filter((r) => r.is_active).length;
    const deterministic = businessRules.filter((r) => r.rule_type === "deterministic_query").length;
    const llmEval = businessRules.filter((r) => r.rule_type === "llm_eval").length;
    const system = businessRules.filter((r) => r.is_system).length;
    const custom = businessRules.filter((r) => !r.is_system).length;
    const enforcementRate = total > 0 ? Math.round((active / total) * 100) : 100;

    return { total, active, deterministic, llmEval, system, custom, enforcementRate };
  }, [businessRules]);

  // ── Filtered Rules ──────────────────────────────────────────────
  const filteredRules = useMemo(() => {
    return businessRules.filter((r) => {
      if (ruleTypeFilter === "deterministic" && r.rule_type !== "deterministic_query") return false;
      if (ruleTypeFilter === "llm" && r.rule_type !== "llm_eval") return false;
      if (ruleTypeFilter === "system" && !r.is_system) return false;
      if (ruleTypeFilter === "custom" && r.is_system) return false;

      if (ruleSearch.trim()) {
        const q = ruleSearch.toLowerCase().trim();
        const matchName = r.name.toLowerCase().includes(q);
        const matchDesc = (r.description || "").toLowerCase().includes(q);
        const matchSql = (r.sql_query || "").toLowerCase().includes(q);
        return matchName || matchDesc || matchSql;
      }
      return true;
    });
  }, [businessRules, ruleTypeFilter, ruleSearch]);

  return (
    <div className="space-y-6 animate-fade-in max-w-[1720px] mx-auto">
      {/* ═══════════════════ EXECUTIVE RULES HEADER ═══════════════════ */}
      <div
        className="p-6 sm:p-8 rounded-3xl border shadow-xs relative overflow-hidden flex flex-col xl:flex-row xl:items-center justify-between gap-6"
        style={{
          background: "linear-gradient(135deg, rgba(255,255,255,0.95) 0%, rgba(248,250,252,0.95) 100%)",
          borderColor: "rgba(226,232,240,0.85)",
          boxShadow: "0 4px 20px -2px rgba(15, 23, 42, 0.04), 0 2px 6px -1px rgba(15, 23, 42, 0.02)",
        }}
      >
        <div className="space-y-2 max-w-2xl">
          <div className="flex items-center gap-2.5">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-bold tracking-wider uppercase bg-slate-900 text-white shadow-xs">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
              Policy Engine Core
            </span>
            <span className="text-[11px] font-mono text-slate-400 flex items-center gap-1">
              <Icon name="verified" className="text-[14px] text-indigo-600" />
              Continuous Automated Enforcement
            </span>
          </div>

          <h1 className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight">
            Vendor Rules &amp; Governance Policies
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 leading-relaxed font-normal">
            Deterministic SQLite queries evaluate instantly with 0ms LLM overhead; cognitive reflection models audit subtle structuring and unbundling risks. Violations automatically become invoice triage flags.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-3 shrink-0 flex-wrap">
          <button
            onClick={() => loadBusinessRules()}
            disabled={loadingRules}
            className="px-4 py-2.5 rounded-2xl bg-white hover:bg-slate-50 border border-slate-200/80 text-slate-700 text-xs font-bold transition-all shadow-xs flex items-center gap-2 active:scale-95 cursor-pointer disabled:opacity-50"
            title="Reload policy rules from SQLite database"
          >
            <Icon name="refresh" className={`text-[17px] ${loadingRules ? "animate-spin text-indigo-600" : "text-slate-500"}`} />
            <span>{loadingRules ? "Syncing..." : "Sync Rules"}</span>
          </button>

          <button
            onClick={openAddRuleModal}
            className="px-5 py-2.5 rounded-2xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white text-xs font-bold flex items-center gap-2 cursor-pointer shadow-sm hover:shadow-indigo-500/25 active:scale-95 transition-all"
          >
            <Icon name="add" className="text-[18px]" />
            <span>Add Policy Rule</span>
          </button>
        </div>
      </div>

      {/* ═══════════════════ KPI ANALYTICS STRIP ═══════════════════ */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 1. Active Guardrails */}
        <div
          className="p-5 rounded-2xl border bg-white shadow-2xs transition-all hover:shadow-xs flex flex-col justify-between space-y-3"
          style={{ borderColor: "rgba(226,232,240,0.85)" }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-indigo-700">Active Enforcement</span>
            <div className="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-100">
              <Icon name="verified_user" className="text-[18px]" />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-black text-slate-900 font-mono tracking-tight">
              {ruleMetrics.active} <span className="text-xs text-slate-400 font-sans font-normal">/ {ruleMetrics.total}</span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span className="font-bold text-emerald-700">{ruleMetrics.enforcementRate}% coverage</span>
              <span className="text-slate-300">·</span>
              <span>Guardrails online</span>
            </div>
          </div>
        </div>

        {/* 2. Deterministic SQL */}
        <div
          className="p-5 rounded-2xl border bg-white shadow-2xs transition-all hover:shadow-xs flex flex-col justify-between space-y-3"
          style={{ borderColor: "rgba(226,232,240,0.85)" }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-700">Deterministic SQL</span>
            <div className="w-8 h-8 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center border border-emerald-100">
              <Icon name="database" className="text-[18px]" />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-black text-emerald-700 font-mono tracking-tight">
              {ruleMetrics.deterministic}
            </div>
            <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1.5">
              <span className="font-bold text-emerald-700">0ms LLM Cost</span>
              <span className="text-slate-300">·</span>
              <span>Direct SQLite clauses</span>
            </div>
          </div>
        </div>

        {/* 3. Cognitive AI Evaluators */}
        <div
          className="p-5 rounded-2xl border bg-white shadow-2xs transition-all hover:shadow-xs flex flex-col justify-between space-y-3"
          style={{ borderColor: "rgba(226,232,240,0.85)" }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-purple-700">Cognitive AI Rules</span>
            <div className="w-8 h-8 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center border border-purple-100">
              <Icon name="psychology" className="text-[18px]" />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-black text-purple-700 font-mono tracking-tight">
              {ruleMetrics.llmEval}
            </div>
            <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1.5">
              <span className="font-bold text-purple-700">Semantic reasoning</span>
              <span className="text-slate-300">·</span>
              <span>Fraud heuristics</span>
            </div>
          </div>
        </div>

        {/* 4. Baseline Safeguards */}
        <div
          className="p-5 rounded-2xl border bg-white shadow-2xs transition-all hover:shadow-xs flex flex-col justify-between space-y-3"
          style={{ borderColor: "rgba(226,232,240,0.85)" }}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Baseline Safeguards</span>
            <div className="w-8 h-8 rounded-xl bg-slate-100 text-slate-600 flex items-center justify-center border border-slate-200/60">
              <Icon name="shield" className="text-[18px]" />
            </div>
          </div>
          <div>
            <div className="text-2xl sm:text-3xl font-black text-slate-900 font-mono tracking-tight">
              {ruleMetrics.system} <span className="text-xs text-slate-400 font-sans font-normal">system flags</span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1 flex items-center gap-1.5">
              <span className="font-bold text-indigo-600">{ruleMetrics.custom} custom</span>
              <span className="text-slate-300">·</span>
              <span>Always verified</span>
            </div>
          </div>
        </div>
      </div>

      {/* ═══════════════════ SEARCH & FILTER TOOLBAR ═══════════════════ */}
      <div
        className="p-4 rounded-2xl border bg-white shadow-2xs flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4"
        style={{ borderColor: "rgba(226,232,240,0.85)" }}
      >
        {/* Search Input */}
        <div className="relative flex-1 max-w-md">
          <Icon name="search" className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-[18px]" />
          <input
            type="text"
            placeholder="Search policies by rule name, description, or SQL clause..."
            value={ruleSearch}
            onChange={(e) => setRuleSearch(e.target.value)}
            className="w-full pl-10 pr-9 py-2.5 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white focus:bg-white text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all"
          />
          {ruleSearch && (
            <button
              onClick={() => setRuleSearch("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer p-0.5"
            >
              <Icon name="close" className="text-[16px]" />
            </button>
          )}
        </div>

        {/* Type Filter Pills */}
        <div className="flex items-center gap-1 bg-slate-100/80 p-1 rounded-xl border border-slate-200/60 text-xs flex-wrap">
          {[
            { key: "all", label: "All Rules", count: ruleMetrics.total },
            { key: "deterministic", label: "Deterministic SQL", count: ruleMetrics.deterministic },
            { key: "llm", label: "AI Reasoning", count: ruleMetrics.llmEval },
            { key: "system", label: "System Core", count: ruleMetrics.system },
            { key: "custom", label: "Custom Rules", count: ruleMetrics.custom },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setRuleTypeFilter(tab.key as any)}
              className={`px-3 py-1.5 rounded-lg font-semibold transition-all cursor-pointer text-[11px] flex items-center gap-1.5 ${
                ruleTypeFilter === tab.key
                  ? "bg-white text-slate-900 shadow-2xs font-bold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <span>{tab.label}</span>
              <span
                className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                  ruleTypeFilter === tab.key ? "bg-slate-100 text-slate-800" : "text-slate-400"
                }`}
              >
                {tab.count}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* ═══════════════════ RULES LIST ═══════════════════ */}
      {loadingRules ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-slate-400">
          <Icon name="sync" className="text-[36px] text-indigo-600 animate-spin" />
          <p className="text-xs font-semibold text-slate-600">Loading policy rules from SQLite engine...</p>
        </div>
      ) : filteredRules.length === 0 ? (
        <div
          className="p-12 sm:p-16 rounded-3xl border border-dashed bg-white text-center space-y-3 shadow-2xs"
          style={{ borderColor: "rgba(226,232,240,0.9)" }}
        >
          <div className="w-12 h-12 rounded-2xl bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
            <Icon name="filter_alt_off" className="text-[24px]" />
          </div>
          <h3 className="text-sm font-bold text-slate-800">No matching policy rules</h3>
          <p className="text-xs text-slate-400 max-w-sm mx-auto">
            {ruleSearch ? `No rules matched query "${ruleSearch}".` : "No rules found under the selected category."}
          </p>
          <button
            onClick={() => {
              setRuleSearch("");
              setRuleTypeFilter("all");
            }}
            className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-xs font-bold text-slate-700 transition-all cursor-pointer"
          >
            Reset Filters
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          {filteredRules.map((rule) => {
            const testRes = ruleTestResults[rule.id];
            const isTestingThis = activeRuleTestId === rule.id;
            const isSqlExpanded = Boolean(expandedSqlIds[rule.id]);

            return (
              <div
                key={rule.id}
                className={`p-5 sm:p-6 rounded-3xl border transition-all duration-200 bg-white shadow-2xs hover:shadow-xs ${
                  !rule.is_active ? "opacity-60 bg-slate-50/50" : ""
                }`}
                style={{ borderColor: "rgba(226,232,240,0.85)" }}
              >
                <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-5">
                  {/* Left: Engine Icon & Policy Specs */}
                  <div className="flex items-start gap-4 flex-1 min-w-0">
                    <div
                      className={`w-11 h-11 rounded-2xl flex items-center justify-center shrink-0 shadow-2xs border ${
                        rule.rule_type === "deterministic_query"
                          ? "bg-emerald-50 border-emerald-200/80 text-emerald-700"
                          : "bg-purple-50 border-purple-200/80 text-purple-700"
                      }`}
                    >
                      <Icon
                        name={rule.rule_type === "deterministic_query" ? "database" : "psychology"}
                        className="text-[22px]"
                      />
                    </div>

                    <div className="space-y-2 flex-1 min-w-0">
                      {/* Name & Badges */}
                      <div className="flex items-center gap-2.5 flex-wrap">
                        <span className="font-mono font-extrabold text-slate-900 text-sm tracking-tight">
                          {rule.name}
                        </span>

                        {/* Enforcement Action Pill */}
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border shadow-2xs ${
                            rule.action === "REJECT"
                              ? "bg-rose-50 text-rose-700 border-rose-200"
                              : rule.action === "WARN"
                              ? "bg-blue-50 text-blue-700 border-blue-200"
                              : "bg-amber-50 text-amber-800 border-amber-200"
                          }`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              rule.action === "REJECT"
                                ? "bg-rose-500"
                                : rule.action === "WARN"
                                ? "bg-blue-500"
                                : "bg-amber-500"
                            }`}
                          />
                          {rule.action === "REQUIRE_HUMAN_APPROVAL"
                            ? "Hold for Approval"
                            : rule.action === "REJECT"
                            ? "Auto-Block"
                            : "Warning Only"}
                        </span>

                        {/* System vs Custom */}
                        {rule.is_system ? (
                          <span className="text-[10px] font-medium text-slate-400 bg-slate-100 px-2 py-0.5 rounded-md">
                            System Core
                          </span>
                        ) : (
                          <span className="text-[10px] font-bold text-violet-700 bg-violet-50 border border-violet-200/80 px-2 py-0.5 rounded-md">
                            Custom Policy
                          </span>
                        )}
                      </div>

                      {/* Description */}
                      <p className="text-xs text-slate-600 leading-relaxed font-normal">
                        {rule.description}
                      </p>

                      {/* SQL Clause Expander or LLM Spec */}
                      {rule.sql_query && (
                        <div className="pt-1">
                          <button
                            onClick={() => toggleSqlExpand(rule.id)}
                            className="inline-flex items-center gap-1 text-[11px] font-mono font-semibold text-indigo-600 hover:text-indigo-800 transition-colors cursor-pointer"
                          >
                            <Icon name={isSqlExpanded ? "expand_less" : "expand_more"} className="text-[15px]" />
                            <span>{isSqlExpanded ? "Hide SQL Expression" : "Inspect Evaluator Query"}</span>
                          </button>

                          {isSqlExpanded && (
                            <div className="mt-2 p-3.5 rounded-2xl bg-slate-900 text-slate-100 font-mono text-[11px] overflow-x-auto border border-slate-800 shadow-2xs space-y-1">
                              <div className="flex items-center justify-between text-slate-400 text-[10px] uppercase font-sans font-bold select-none border-b border-slate-800 pb-1.5">
                                <span>WHERE Clause Filter:</span>
                                <span className="text-emerald-400 font-mono">0ms overhead</span>
                              </div>
                              <div className="text-emerald-300 font-mono select-all pt-1 leading-normal">
                                {rule.sql_query}
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {rule.rule_type === "llm_eval" && (
                        <div className="mt-1 inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-purple-50/70 border border-purple-100 text-purple-900 text-xs">
                          <Icon name="auto_awesome" className="text-[15px] text-purple-600 shrink-0" />
                          <span className="text-[11px] text-purple-800">
                            Evaluated dynamically during invoice ingestion via cognitive critique loop.
                          </span>
                        </div>
                      )}

                      {/* Test Result Inspection Box */}
                      {testRes && (
                        <div className="mt-3 p-3.5 rounded-2xl bg-indigo-50/80 border border-indigo-200/80 text-indigo-950 text-xs space-y-2 shadow-2xs">
                          <div className="flex items-center justify-between">
                            <span className="font-bold flex items-center gap-1.5 text-indigo-900">
                              <Icon name="check_circle" className="text-[16px] text-indigo-600" />
                              Simulation Result: <span className="font-extrabold">{testRes.matches_count} Invoices Triggered</span>
                            </span>
                            <button
                              onClick={() =>
                                setRuleTestResults((prev) => {
                                  const copy = { ...prev };
                                  delete copy[rule.id];
                                  return copy;
                                })
                              }
                              className="text-indigo-500 hover:text-indigo-800 text-[11px] font-semibold cursor-pointer"
                            >
                              Dismiss
                            </button>
                          </div>

                          {testRes.sample_matches.length > 0 ? (
                            <div className="flex items-center gap-2 flex-wrap pt-1">
                              <span className="text-[11px] text-indigo-700 font-medium">Matching Invoices:</span>
                              {testRes.sample_matches.map((m, mIdx) => (
                                <button
                                  key={`rule-match-${mIdx}`}
                                  onClick={() => {
                                    const matchedInv = allInvoices.find((i) => i.invoice_id === m.invoice_id);
                                    if (matchedInv) openModal(matchedInv);
                                  }}
                                  className="px-2.5 py-1 rounded-lg bg-white border border-indigo-200 text-indigo-700 font-mono text-[11px] font-bold hover:bg-indigo-600 hover:text-white transition-all cursor-pointer shadow-2xs"
                                >
                                  #{m.invoice_id} ({formatCurrency(m.total, m.currency)})
                                </button>
                              ))}
                            </div>
                          ) : (
                            <div className="text-[11px] text-indigo-700 italic">
                              {testRes.message || "No invoices in current database match this condition."}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Right: Enforcement Controls */}
                  <div className="flex items-center lg:flex-col lg:items-end gap-3.5 shrink-0 pt-1">
                    {/* Toggle Switch */}
                    <div className="flex items-center gap-2.5">
                      <span className={`text-[10px] font-bold uppercase tracking-wider ${rule.is_active ? "text-emerald-700" : "text-slate-400"}`}>
                        {rule.is_active ? "Enforcing" : "Paused"}
                      </span>
                      <button
                        onClick={() => handleToggleRule(rule)}
                        className={`w-11 h-6 rounded-full transition-colors relative cursor-pointer ${
                          rule.is_active ? "bg-indigo-600" : "bg-slate-300"
                        }`}
                        title={rule.is_active ? "Pause policy enforcement" : "Activate policy enforcement"}
                      >
                        <span
                          className={`absolute top-1 left-1 bg-white w-4 h-4 rounded-full transition-transform shadow-xs ${
                            rule.is_active ? "transform translate-x-5" : ""
                          }`}
                        />
                      </button>
                    </div>

                    {/* Simulation & Action Buttons */}
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleTestExistingRule(rule)}
                        disabled={isTestingThis}
                        className="px-3 py-1.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold flex items-center gap-1.5 cursor-pointer transition-all shadow-2xs active:scale-95 disabled:opacity-50"
                        title="Simulate rule evaluation against all SQLite invoices"
                      >
                        <Icon
                          name={isTestingThis ? "sync" : "play_arrow"}
                          className={`text-[16px] ${isTestingThis ? "animate-spin text-indigo-600" : "text-indigo-600"}`}
                        />
                        <span>{isTestingThis ? "Simulating..." : "Dry Run"}</span>
                      </button>

                      {!rule.is_system ? (
                        <button
                          onClick={() => handleDeleteRule(rule)}
                          className="p-2 rounded-xl border border-rose-200/80 bg-rose-50/60 hover:bg-rose-100 text-rose-600 text-xs font-semibold transition-all cursor-pointer shadow-2xs active:scale-95"
                          title="Delete custom policy"
                        >
                          <Icon name="delete" className="text-[16px]" />
                        </button>
                      ) : (
                        <div
                          className="p-2 rounded-xl text-slate-300 bg-slate-50"
                          title="Core baseline policy (immutable)"
                        >
                          <Icon name="lock" className="text-[16px]" />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
