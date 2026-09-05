import React from "react";
import { Icon } from "@/components/common/Icon";
import { SystemSettings } from "@/lib/api";

export interface DashboardHeaderProps {
  activeNav: string;
  setActiveNav: (tab: string) => void;
  uploading: boolean;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  handleFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  setSettingsOpen: (open: boolean) => void;
  settings?: SystemSettings | null;
}

export function DashboardHeader({
  activeNav,
  setActiveNav,
  uploading,
  fileInputRef,
  handleFileUpload,
  setSettingsOpen,
  settings,
}: DashboardHeaderProps) {
  return (
    <header
      className="fixed top-0 left-0 w-full z-40 backdrop-blur-xl"
      style={{
        background: "rgba(232,234,240,0.9)",
        boxShadow: "0 1px 8px rgba(0,0,0,0.04)",
      }}
    >
      <div className="h-20 max-w-[1720px] mx-auto px-6 lg:px-12 flex items-center justify-between gap-6">
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-600 to-violet-600 flex items-center justify-center">
              <Icon name="verified_user" className="text-white text-[18px]" />
            </div>
            <span
              className="font-semibold text-lg tracking-tight"
              style={{ fontFamily: "'Plus Jakarta Sans', sans-serif" }}
            >
              FlowAudit AI
            </span>
          </div>
        </div>

        <nav className="hidden md:flex items-center gap-2">
          {[
            { key: "invoice-triage", label: "Invoice Triage" },
            { key: "automated-pipeline", label: "Automated Pipeline" },
            { key: "vendor-rules", label: "Vendor Rules" },
            { key: "audit-log-analytics", label: "Audit Log & Analytics" },
          ].map((tab) => (
            <button
              key={tab.key}
              id={tab.key === "vendor-rules" ? "onborda-rules-nav" : undefined}
              onClick={() => setActiveNav(tab.key)}
              className={`px-4 py-2 rounded-xl transition-all text-sm font-medium cursor-pointer ${
                activeNav === tab.key ? "neo-raised font-semibold" : "hover:opacity-80"
              }`}
              style={{
                background:
                  activeNav === tab.key ? "var(--primary-container)" : "transparent",
                color:
                  activeNav === tab.key
                    ? "var(--on-primary-container)"
                    : "var(--on-surface-variant)",
              }}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <button
            id="onborda-upload"
            onClick={() => fileInputRef.current?.click()}
            className="hidden sm:flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 transition-all cursor-pointer shadow-sm active:scale-95"
          >
            <Icon name="upload" className="text-[16px]" />
            {uploading ? "Ingesting..." : "Upload Invoice"}
          </button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            multiple
            accept=".json,.xml,.csv,.txt,.pdf"
            className="hidden"
          />

          <div className="flex items-center gap-2">
            {/* Settings Button */}
            <button
              id="onborda-settings"
              onClick={() => setSettingsOpen(true)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-200/80 transition-all cursor-pointer shadow-xs active:scale-95"
              title="System Settings & AI Governance"
            >
              <Icon name="settings" className="text-[16px] text-slate-500" />
              <span className="hidden sm:inline">Settings</span>
              {settings?.enable_vp_review && (
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
              )}
            </button>

            {/* VP Avatar Button (opens settings) */}
            <button
              onClick={() => setSettingsOpen(true)}
              className="flex items-center pl-1 cursor-pointer"
              title="VP Profile & System Settings"
            >
              <div
                className="p-0.5 rounded-full neo-raised"
                style={{ background: "var(--surface)" }}
              >
                <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center text-white text-xs font-bold shadow-xs">
                  VP
                </div>
              </div>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
