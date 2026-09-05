"use client";

import { useOnborda, type Step, type CardComponentProps } from "onborda";
import { completeOnboarding } from "@/lib/api";

export interface Tour {
  tour: string;
  steps: Step[];
}

export const ONBOARDING_TOUR_NAME = "flowaudit_executive_tour";

export const onboardingSteps: Tour[] = [
  {
    tour: ONBOARDING_TOUR_NAME,
    steps: [
      {
        icon: (
          <svg className="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        ),
        title: "Audit Stream & Real-time KPIs",
        content: (
          <p className="text-xs text-slate-300 leading-relaxed">
            Track real-time invoice throughput, straight-through auto-approval rates, pending triage depth, and high-risk anomalies detected by our multi-layered validation engine.
          </p>
        ),
        selector: "#onborda-kpis",
        side: "bottom",
        pointerPadding: 16,
        pointerRadius: 18,
      },
      {
        icon: (
          <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
        ),
        title: "Universal Invoice Ingestion",
        content: (
          <p className="text-xs text-slate-300 leading-relaxed">
            Drag &amp; drop or upload invoices in any format: <strong>PDF, JSON, XML, CSV, or TXT</strong>. Invoices are parsed, reconciled against product catalogs, and verified with sub-second deterministic checks.
          </p>
        ),
        selector: "#onborda-upload",
        side: "bottom",
        pointerPadding: 12,
        pointerRadius: 14,
      },
      {
        icon: (
          <svg className="w-5 h-5 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
          </svg>
        ),
        title: "Triage Focus & Scope Filters",
        content: (
          <p className="text-xs text-slate-300 leading-relaxed">
            Filter down to <strong>Pending Triage</strong> to review actionable invoices requiring executive intervention, or switch to <strong>All Portfolio</strong> to audit historical disbursements.
          </p>
        ),
        selector: "#onborda-scope-selector",
        side: "bottom",
        pointerPadding: 12,
        pointerRadius: 14,
      },
      {
        icon: (
          <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        ),
        title: "Executive AI Governance & Speed",
        content: (
          <p className="text-xs text-slate-300 leading-relaxed">
            Fine-tune system parameters, toggle the deep <strong>VP Cognitive Reflection loop</strong> on or off for instant sub-10ms approvals, and inspect offline/local AI fallbacks.
          </p>
        ),
        selector: "#onborda-settings",
        side: "bottom",
        pointerPadding: 12,
        pointerRadius: 14,
      },
      {
        icon: (
          <svg className="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        ),
        title: "Corporate Rules & Guardrails",
        content: (
          <p className="text-xs text-slate-300 leading-relaxed">
            Access enterprise policies governing blacklisted vendors, split billing structuring, catalog compliance, and custom deterministic SQL rules.
          </p>
        ),
        selector: "#onborda-rules-nav",
        side: "bottom",
        pointerPadding: 12,
        pointerRadius: 14,
      },
    ],
  },
];

export const TourCard: React.FC<CardComponentProps> = ({
  step,
  currentStep,
  totalSteps,
  nextStep,
  prevStep,
  arrow,
}) => {
  const { closeOnborda } = useOnborda();

  const handleFinish = async () => {
    closeOnborda();
    try {
      await completeOnboarding();
    } catch (err) {
      console.error("Failed to persist onboarding completion:", err);
    }
  };

  const handleSkip = async () => {
    closeOnborda();
    try {
      await completeOnboarding();
    } catch (err) {
      console.error("Failed to mark onboarding skipped:", err);
    }
  };

  const isLast = currentStep === totalSteps - 1;
  const progressPercent = Math.round(((currentStep + 1) / totalSteps) * 100);

  return (
    <div className="relative w-84 sm:w-96 rounded-2xl bg-slate-900/95 backdrop-blur-xl border border-slate-700/80 text-white shadow-2xl overflow-hidden p-5 transition-all text-left z-[1000]">
      {/* Visual arrow pointer from Onborda */}
      <div className="text-slate-800 pointer-events-none drop-shadow-md">
        {arrow}
      </div>

      {/* Card Header */}
      <div className="flex items-center justify-between gap-3 mb-2.5">
        <div className="flex items-center gap-2">
          {step.icon && (
            <div className="w-8 h-8 rounded-xl bg-slate-800/80 border border-slate-700/60 flex items-center justify-center shrink-0">
              {step.icon}
            </div>
          )}
          <span className="text-[10px] font-extrabold uppercase tracking-wider text-indigo-300 bg-indigo-950/80 border border-indigo-700/50 px-2 py-0.5 rounded-full">
            Step {currentStep + 1} of {totalSteps}
          </span>
        </div>

        <button
          type="button"
          onClick={handleSkip}
          className="text-slate-400 hover:text-white transition-colors px-2 py-1 rounded-lg hover:bg-slate-800/80 text-xs font-semibold cursor-pointer"
          title="Skip Tour"
        >
          Skip Tour
        </button>
      </div>

      {/* Progress Bar */}
      <div className="w-full h-1 bg-slate-800/90 rounded-full mb-3.5 overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-indigo-500 via-purple-500 to-emerald-400 transition-all duration-300 rounded-full"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* Step Title */}
      <h3 className="text-sm sm:text-base font-bold text-white mb-2 tracking-tight">
        {step.title}
      </h3>

      {/* Step Content */}
      <div className="mb-4">
        {step.content}
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between pt-3 border-t border-slate-800/90">
        <button
          type="button"
          onClick={prevStep}
          disabled={currentStep === 0}
          className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
            currentStep === 0
              ? "opacity-25 cursor-not-allowed text-slate-500"
              : "text-slate-300 hover:text-white hover:bg-slate-800 active:scale-95"
          }`}
        >
          Back
        </button>

        <div className="flex items-center gap-2">
          {isLast ? (
            <button
              type="button"
              onClick={handleFinish}
              className="px-4 py-1.5 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 shadow-md shadow-emerald-500/20 active:scale-95 transition-all cursor-pointer flex items-center gap-1.5"
            >
              <span>Finish Tour</span>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
              </svg>
            </button>
          ) : (
            <button
              type="button"
              onClick={nextStep}
              className="px-4 py-1.5 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 shadow-md shadow-indigo-600/30 active:scale-95 transition-all cursor-pointer flex items-center gap-1.5"
            >
              <span>Next</span>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
