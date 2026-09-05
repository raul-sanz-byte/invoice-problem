"use client";

import React, { useEffect } from "react";
import { Onborda, OnbordaProvider } from "onborda";
import {
  onboardingSteps,
  TourCard,
} from "@/components/onboarding/OnboardingTour";
import { Icon } from "@/components/common/Icon";
import { useDashboardData } from "@/hooks/useDashboardData";

import { DashboardHeader } from "@/components/dashboard/DashboardHeader";
import { InvoiceTriageTab } from "@/components/dashboard/InvoiceTriageTab";
import { RulesTab } from "@/components/rules/RulesTab";
import { PipelineArchitectureTab } from "@/components/pipeline/PipelineArchitectureTab";
import { AuditLogTab } from "@/components/audit/AuditLogTab";
import { InvoiceInspectionModal } from "@/components/modals/InvoiceInspectionModal";
import { OriginalInvoiceModal } from "@/components/modals/OriginalInvoiceModal";
import { CleanUploadSuccessModal } from "@/components/modals/CleanUploadSuccessModal";
import { AddRuleModal } from "@/components/modals/AddRuleModal";
import UploadFailureModal from "@/components/modals/UploadFailureModal";
import SettingsModal from "@/components/modals/SettingsModal";

// =====================================================================
//  MAIN DASHBOARD COMPONENT
// =====================================================================
function FlowAuditDashboardContent() {
  const data = useDashboardData();

  // ── Keyboard shortcuts ────────────────────────────────────────────
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      if (e.key === "Escape") {
        if (data.cleanSuccessModal?.open) {
          data.setCleanSuccessModal(null);
          return;
        }
        if (data.uploadFailureModal?.open) {
          data.setUploadFailureModal(null);
          return;
        }
        if (data.originalViewerOpen) {
          data.closeOriginalViewer();
          return;
        }
        if (data.modalOpen) {
          data.closeModal();
          return;
        }
      }
      if (data.modalOpen || data.originalViewerOpen || data.cleanSuccessModal?.open || data.uploadFailureModal?.open) return;

      if (e.key === "ArrowRight") {
        data.goToIndex(data.currentIndex + 1);
      } else if (e.key === "ArrowLeft") {
        data.goToIndex(data.currentIndex - 1);
      } else if (e.key.toLowerCase() === "a" && data.carouselInvoices[data.currentIndex]) {
        data.handleApprove(data.carouselInvoices[data.currentIndex].invoice_id);
      } else if (e.key.toLowerCase() === "r" && data.carouselInvoices[data.currentIndex]) {
        data.handleReject(data.carouselInvoices[data.currentIndex].invoice_id);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    data.currentIndex,
    data.modalOpen,
    data.originalViewerOpen,
    data.cleanSuccessModal,
    data.uploadFailureModal,
    data.carouselInvoices,
    data.goToIndex,
    data.handleApprove,
    data.handleReject,
    data.setCleanSuccessModal,
    data.setUploadFailureModal,
    data.closeOriginalViewer,
    data.closeModal,
  ]);

  // ── Render ────────────────────────────────────────────────────────
  return (
    <>
      {/* ═══════════════════ HEADER ═══════════════════ */}
      <DashboardHeader
        activeNav={data.activeNav}
        setActiveNav={data.setActiveNav}
        uploading={data.uploading}
        fileInputRef={data.fileInputRef}
        handleFileUpload={data.handleFileUpload}
        setSettingsOpen={data.setSettingsOpen}
        settings={data.settings}
      />

      {/* Hidden file input for header upload */}
      <input
        type="file"
        ref={data.fileInputRef}
        onChange={data.handleFileUpload}
        multiple
        accept=".json,.xml,.csv,.txt,.pdf"
        className="hidden"
      />

      {/* ═══════════════════ MAIN CONTENT ═══════════════════ */}
      <main className="w-full pt-20 min-h-[calc(100vh-80px)] overflow-x-hidden" style={{ background: "var(--surface)" }}>
        <div className="flex flex-col w-full pb-10">
          <div className="w-full max-w-[1720px] mx-auto px-4 sm:px-6 lg:px-8 py-5 space-y-4">
            {/* Tab 1: Invoice Triage */}
            {data.activeNav === "invoice-triage" && (
              <InvoiceTriageTab
                allInvoices={data.allInvoices}
                carouselInvoices={data.carouselInvoices}
                pendingInvoices={data.pendingInvoices}
                kpiCounts={data.kpiCounts}
                stats={data.stats}
                total={data.total}
                currentIndex={data.currentIndex}
                goToIndex={data.goToIndex}
                carouselRef={data.carouselRef}
                filterToolbarRef={data.filterToolbarRef}
                fileInputRef={data.fileInputRef}
                portfolioScope={data.portfolioScope}
                setPortfolioScope={data.setPortfolioScope}
                searchQuery={data.searchQuery}
                setSearchQuery={data.setSearchQuery}
                dueDateFilter={data.dueDateFilter}
                setDueDateFilter={data.setDueDateFilter}
                dueCustomStart={data.dueCustomStart}
                setDueCustomStart={data.setDueCustomStart}
                dueCustomEnd={data.dueCustomEnd}
                setDueCustomEnd={data.setDueCustomEnd}
                invoiceDateFilter={data.invoiceDateFilter}
                setInvoiceDateFilter={data.setInvoiceDateFilter}
                invoiceCustomStart={data.invoiceCustomStart}
                setInvoiceCustomStart={data.setInvoiceCustomStart}
                invoiceCustomEnd={data.invoiceCustomEnd}
                setInvoiceCustomEnd={data.setInvoiceCustomEnd}
                selectedFlags={data.selectedFlags}
                setSelectedFlags={data.setSelectedFlags}
                selectedVendors={data.selectedVendors}
                setSelectedVendors={data.setSelectedVendors}
                withheldCompanies={data.withheldCompanies}
                presentFlags={data.presentFlags}
                sortBy={data.sortBy}
                setSortBy={data.setSortBy}
                hasActiveFilters={data.hasActiveFilters}
                resetAllFilters={data.resetAllFilters}
                loading={data.loading}
                uploading={data.uploading}
                openModal={data.openModal}
                handleViewOriginal={data.handleViewOriginal}
                handleApprove={data.handleApprove}
                handleReject={data.handleReject}
                handleBlacklist={data.handleBlacklist}
                actionLoadingId={data.actionLoadingId}
              />
            )}

            {/* Tab 2: Automated Pipeline */}
            {data.activeNav === "automated-pipeline" && (
              <PipelineArchitectureTab stats={data.stats} />
            )}

            {/* Tab 3: Vendor Rules & Policy Management */}
            {data.activeNav === "vendor-rules" && (
              <RulesTab
                businessRules={data.businessRules}
                loadingRules={data.loadingRules}
                loadBusinessRules={data.loadBusinessRules}
                openAddRuleModal={() => data.setAddRuleModalOpen(true)}
                handleToggleRule={data.handleToggleRule}
                handleDeleteRule={data.handleDeleteRule}
                handleTestExistingRule={data.handleTestExistingRule}
                ruleTestResults={data.ruleTestResults}
                setRuleTestResults={data.setRuleTestResults}
                activeRuleTestId={data.activeRuleTestId}
                allInvoices={data.allInvoices}
                openModal={data.openModal}
              />
            )}

            {/* Tab 4: Audit Log & Ledger Stream */}
            {data.activeNav === "audit-log-analytics" && (
              <AuditLogTab
                allInvoices={data.allInvoices}
                openModal={data.openModal}
              />
            )}
          </div>
        </div>
      </main>

      {/* ═══════════════════ MODALS ═══════════════════ */}
      <InvoiceInspectionModal
        modalOpen={data.modalOpen}
        closeModal={data.closeModal}
        modalInvoice={data.modalInvoice}
        loadingDetail={data.loadingDetail}
        handleViewOriginal={data.handleViewOriginal}
        handleApprove={data.handleApprove}
        handleReject={data.handleReject}
        handleBlacklist={data.handleBlacklist}
      />

      <OriginalInvoiceModal
        originalViewerOpen={data.originalViewerOpen}
        closeOriginalViewer={data.closeOriginalViewer}
        originalDoc={data.originalDoc}
        loadingOriginal={data.loadingOriginal}
        originalError={data.originalError}
        copiedRaw={data.copiedRaw}
        handleCopyRaw={data.handleCopyRaw}
        modalInvoice={data.modalInvoice}
      />

      <CleanUploadSuccessModal
        cleanSuccessModal={data.cleanSuccessModal}
        setCleanSuccessModal={data.setCleanSuccessModal}
        copiedCleanLogs={data.copiedCleanLogs}
        setCopiedCleanLogs={data.setCopiedCleanLogs}
      />

      <AddRuleModal
        addRuleModalOpen={data.addRuleModalOpen}
        setAddRuleModalOpen={data.setAddRuleModalOpen}
        newRuleName={data.newRuleName}
        setNewRuleName={data.setNewRuleName}
        newRuleDesc={data.newRuleDesc}
        setNewRuleDesc={data.setNewRuleDesc}
        newRuleAction={data.newRuleAction}
        setNewRuleAction={data.setNewRuleAction}
        newRuleCustomSql={data.newRuleCustomSql}
        setNewRuleCustomSql={data.setNewRuleCustomSql}
        showCustomSqlInput={data.showCustomSqlInput}
        setShowCustomSqlInput={data.setShowCustomSqlInput}
        testingRule={data.testingRule}
        testResult={data.testResult}
        submittingRule={data.submittingRule}
        handleSaveNewRule={data.handleSaveNewRule}
        handleTestNewRule={data.handleTestNewRule}
        applyRuleTemplate={data.applyRuleTemplate}
      />

      <UploadFailureModal
        uploadFailureModal={data.uploadFailureModal}
        setUploadFailureModal={data.setUploadFailureModal}
        failureRawExpanded={data.failureRawExpanded}
        setFailureRawExpanded={data.setFailureRawExpanded}
      />

      <SettingsModal
        settingsOpen={data.settingsOpen}
        setSettingsOpen={data.setSettingsOpen}
        settings={data.settings}
        savingSettings={data.savingSettings}
        handleToggleVPReview={data.handleToggleVPReview}
        onboardingStatus={data.onboardingStatus}
        setOnboardingStatus={data.setOnboardingStatus}
        startOnborda={data.startOnborda}
      />

      {/* ═══════════════════ TOAST ═══════════════════ */}
      {data.toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 transition-all duration-300 px-5 py-3 rounded-2xl shadow-2xl flex items-center gap-3 text-xs font-semibold text-white border border-white/20 ${
            data.toast.visible ? "animate-slide-up" : "animate-slide-down"
          }`}
          style={{ background: "rgb(15,23,42)" }}
        >
          <Icon
            name={
              data.toast.action === "upload_success" ? "cloud_done" :
              data.toast.action === "approve" ? "check_circle" :
              data.toast.action === "reject" ? "cancel" :
              data.toast.action === "blacklist" ? "block" :
              data.toast.action === "rule_created" ? "add_task" :
              data.toast.action === "rule_toggled" ? "tune" :
              data.toast.action === "rule_deleted" ? "delete" : "notifications"
            }
            className={`text-[20px] ${
              data.toast.action === "approve" || data.toast.action === "upload_success" || data.toast.action === "rule_created" || data.toast.action === "rule_toggled"
                ? "text-emerald-400"
                : data.toast.action === "reject" || data.toast.action === "rule_deleted"
                  ? "text-rose-400"
                  : "text-amber-400"
            }`}
          />
          <span>
            {data.toast.message
              ? data.toast.message
              : data.toast.action === "upload_success"
                ? "Invoice uploaded successfully."
                : data.toast.action === "approve"
                  ? `${data.toast.invoiceId} Approved for Payment`
                  : data.toast.action === "reject"
                    ? `${data.toast.invoiceId} Rejected & Sent Back to Vendor`
                    : `${data.toast.invoiceId} Rejected & Vendor Blacklisted`}
          </span>
        </div>
      )}

      {/* ═══════════════════ FOOTER ═══════════════════ */}
      <footer className="w-full py-8" style={{ background: "var(--surface)" }}>
        <div className="max-w-[1720px] mx-auto px-6 lg:px-12 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs" style={{ color: "var(--on-surface-variant)" }}>
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
            <span>FlowAudit AI Enterprise Core v4.8</span>
          </div>
          <div className="flex items-center gap-6">
            <a className="hover:opacity-80 transition-opacity cursor-pointer">Security & Compliance</a>
            <a className="hover:opacity-80 transition-opacity cursor-pointer">System Logs</a>
            <a className="hover:opacity-80 transition-opacity cursor-pointer">Support Desk</a>
          </div>
        </div>
      </footer>
    </>
  );
}

export default function FlowAuditDashboard() {
  return (
    <OnbordaProvider>
      <Onborda
        steps={onboardingSteps}
        cardComponent={TourCard}
        shadowRgb="15, 23, 42"
        shadowOpacity="0.75"
        interact={true}
      >
        <FlowAuditDashboardContent />
      </Onborda>
    </OnbordaProvider>
  );
}
