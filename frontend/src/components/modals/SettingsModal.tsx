"use client";

import React from "react";
import Icon from "@/components/common/Icon";
import { SystemSettings, OnboardingStatus, resetOnboarding } from "@/lib/api";
import { ONBOARDING_TOUR_NAME } from "@/components/onboarding/OnboardingTour";

interface SettingsModalProps {
  settingsOpen: boolean;
  setSettingsOpen: (open: boolean) => void;
  settings: SystemSettings | null;
  savingSettings: boolean;
  handleToggleVPReview: (val: boolean) => Promise<void>;
  onboardingStatus: OnboardingStatus | null;
  setOnboardingStatus: React.Dispatch<React.SetStateAction<OnboardingStatus | null>>;
  startOnborda: (name: string) => void;
}

export default function SettingsModal({
  settingsOpen,
  setSettingsOpen,
  settings,
  savingSettings,
  handleToggleVPReview,
  onboardingStatus,
  setOnboardingStatus,
  startOnborda,
}: SettingsModalProps) {
  if (!settingsOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-xl rounded-2xl bg-white border border-slate-200 shadow-2xl overflow-hidden animate-scale-in flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-slate-50 to-indigo-50/30">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-100 text-indigo-600 flex items-center justify-center shadow-xs">
              <Icon name="tune" className="text-[22px]" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">System &amp; AI Governance Settings</h2>
              <p className="text-xs text-slate-500">Configure delegated authority, review engines, and reflection loops</p>
            </div>
          </div>
          <button
            onClick={() => setSettingsOpen(false)}
            className="p-1.5 rounded-xl hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
          >
            <Icon name="close" className="text-[20px]" />
          </button>
        </div>

        {/* Modal Content */}
        <div className="p-6 overflow-y-auto space-y-6 text-xs text-slate-600">
          {/* Feature Toggle Card: VP Cognitive Review */}
          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-sm text-slate-900">VP Executive Cognitive Review</span>
                  {settings?.enable_vp_review ? (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-indigo-100 text-indigo-700 border border-indigo-200">
                      AI REFLECTION ACTIVE
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-100 text-emerald-700 border border-emerald-200">
                      DISABLED (FAST &lt;10MS)
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">
                  Controls whether an LLM self-reflection &amp; critique loop runs on invoices during ingestion and triage.
                </p>
              </div>

              {/* Toggle Switch */}
              <button
                type="button"
                disabled={savingSettings}
                onClick={() => handleToggleVPReview(!settings?.enable_vp_review)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  settings?.enable_vp_review ? "bg-indigo-600" : "bg-slate-300"
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                    settings?.enable_vp_review ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>

            {/* Sub-explanations */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-slate-200/70">
              <div
                className={`p-3 rounded-lg border text-[11px] space-y-1 ${
                  !settings?.enable_vp_review ? "bg-emerald-50/60 border-emerald-200 text-emerald-900" : "bg-white border-slate-200 text-slate-500"
                }`}
              >
                <div className="font-bold flex items-center gap-1.5">
                  <Icon name="bolt" className="text-[14px]" />
                  Fast Deterministic (Default)
                </div>
                <p className="leading-normal">
                  Full automated validation: catalog stock checks, $10K limit, math reconciliation, and policy rules. Invoices auto-approved in &lt;10ms with zero LLM overhead.
                </p>
              </div>

              <div
                className={`p-3 rounded-lg border text-[11px] space-y-1 ${
                  settings?.enable_vp_review ? "bg-indigo-50/60 border-indigo-200 text-indigo-900" : "bg-white border-slate-200 text-slate-500"
                }`}
              >
                <div className="font-bold flex items-center gap-1.5">
                  <Icon name="psychology" className="text-[14px]" />
                  Deep AI Reflection Loop
                </div>
                <p className="leading-normal">
                  Invokes OpenRouter / LLM after validations pass to conduct a critical fiduciary reflection challenging split billing, unbundling, and rush orders (~2s round-trip).
                </p>
              </div>
            </div>
          </div>

          {/* Engine & Pipeline Specs */}
          <div className="p-4 rounded-xl border border-slate-200 bg-white space-y-3">
            <div className="font-bold text-xs text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
              <Icon name="memory" className="text-[16px] text-indigo-500" />
              Active Infrastructure Telemetry
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">LLM Engine</span>
                <span className="font-bold text-slate-800">
                  {settings?.llm_provider || "OpenRouter"} ({settings?.model || "openai/gpt-4o-mini"})
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Vector Retrieval</span>
                <span className="font-bold text-slate-800">{settings?.qdrant_mode || "Qdrant Vector Engine"}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Extraction Router</span>
                <span className="font-bold text-slate-800">Hybrid Deterministic + LLM Fallback</span>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">Database Engine</span>
                <span className="font-bold text-slate-800">SQLite with Strict Foreign Keys</span>
              </div>
            </div>
          </div>

          {/* Onboarding Tour Control & SQLite First-Time User State */}
          <div className="p-4 rounded-xl border border-slate-200 bg-white space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-xs text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                    <Icon name="explore" className="text-[16px] text-indigo-500" />
                    Guided Onboarding Tour (Onborda)
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold border ${
                      onboardingStatus?.onboarding_completed
                        ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                        : "bg-amber-50 text-amber-700 border-amber-200"
                    }`}
                  >
                    {onboardingStatus?.onboarding_completed ? "COMPLETED (SQLITE)" : "FIRST-TIME USER"}
                  </span>
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">
                  First-time user walkthrough status is stored directly in SQLite. You can replay the tour at any time.
                </p>
              </div>

              <button
                type="button"
                onClick={async () => {
                  setSettingsOpen(false);
                  try {
                    await resetOnboarding();
                    setOnboardingStatus({ is_first_time_user: true, onboarding_completed: false });
                    setTimeout(() => {
                      startOnborda(ONBOARDING_TOUR_NAME);
                    }, 300);
                  } catch (err) {
                    console.error("Failed to replay tour:", err);
                  }
                }}
                className="px-3 py-1.5 rounded-xl bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 text-xs font-bold transition-all cursor-pointer flex items-center gap-1.5 shadow-xs active:scale-95 shrink-0"
              >
                <Icon name="restart_alt" className="text-[15px]" />
                Replay Tour
              </button>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-slate-100 bg-slate-50 flex items-center justify-between">
          <span className="text-[11px] text-slate-400">
            Changes persist automatically and apply to all future invoice uploads.
          </span>
          <button
            onClick={() => setSettingsOpen(false)}
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs cursor-pointer shadow-xs active:scale-95 transition-all"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
