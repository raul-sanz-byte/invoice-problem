"use client";

import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  fetchStats,
  fetchInvoices,
  fetchInvoiceDetail,
  uploadInvoices,
  approveInvoice,
  rejectInvoice,
  rejectAndBlockInvoice,
  fetchOriginalInvoiceContent,
  fetchBusinessRules,
  createBusinessRule,
  toggleBusinessRule,
  deleteBusinessRule,
  testBusinessRule,
  BusinessRule,
  TestBusinessRuleResult,
  DashboardStats,
  InvoiceItem,
  UploadResultItem,
  OriginalInvoiceResponse,
  SystemSettings,
  fetchSettings,
  updateSettings,
  fetchOnboardingStatus,
  OnboardingStatus,
} from "@/lib/api";
import { useOnborda } from "onborda";
import { ONBOARDING_TOUR_NAME } from "@/components/onboarding/OnboardingTour";
import {
  parseDate,
  isInvoiceWithheld,
  isInvoiceApproved,
  isProcessedSuccessfullyWithoutFlags,
  hasRaisedFlags,
  AVAILABLE_FLAGS,
  invoiceMatchesFlag,
} from "@/lib/invoice-utils";
import { UploadFailureInfo } from "@/components/modals/UploadFailureModal";

export function useDashboardData() {
  const { startOnborda } = useOnborda();
  const [onboardingStatus, setOnboardingStatus] = useState<OnboardingStatus | null>(null);

  // ── State ──────────────────────────────────────────────────────────
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [allInvoices, setAllInvoices] = useState<InvoiceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [activeNav, setActiveNav] = useState("invoice-triage");

  // Modal
  const [modalOpen, setModalOpen] = useState(false);
  const [modalInvoice, setModalInvoice] = useState<InvoiceItem | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Original Invoice Viewer Modal
  const [originalViewerOpen, setOriginalViewerOpen] = useState(false);
  const [originalDoc, setOriginalDoc] = useState<OriginalInvoiceResponse | null>(null);
  const [loadingOriginal, setLoadingOriginal] = useState(false);
  const [originalError, setOriginalError] = useState<string | null>(null);
  const [copiedRaw, setCopiedRaw] = useState(false);

  // Toast
  const [toast, setToast] = useState<{
    visible: boolean;
    action: "approve" | "reject" | "blacklist" | "rule_created" | "rule_toggled" | "rule_deleted" | "custom" | "upload_success";
    invoiceId?: string;
    message?: string;
  } | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Settings State ──
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);

  // ── Vendor Rules & Policy Management State ──
  const [businessRules, setBusinessRules] = useState<BusinessRule[]>([]);
  const [loadingRules, setLoadingRules] = useState(false);
  const [addRuleModalOpen, setAddRuleModalOpen] = useState(false);
  const [newRuleName, setNewRuleName] = useState("");
  const [newRuleDesc, setNewRuleDesc] = useState("");
  const [newRuleAction, setNewRuleAction] = useState<string>("REQUIRE_HUMAN_APPROVAL");
  const [newRuleCustomSql, setNewRuleCustomSql] = useState("");
  const [showCustomSqlInput, setShowCustomSqlInput] = useState(false);
  const [testResult, setTestResult] = useState<TestBusinessRuleResult | null>(null);
  const [testingRule, setTestingRule] = useState(false);
  const [submittingRule, setSubmittingRule] = useState(false);
  const [activeRuleTestId, setActiveRuleTestId] = useState<number | null>(null);
  const [ruleTestResults, setRuleTestResults] = useState<Record<number, TestBusinessRuleResult>>({});

  // Upload
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  // Clean Upload Success Modal (Zero Flags)
  const [cleanSuccessModal, setCleanSuccessModal] = useState<{
    open: boolean;
    invoices: UploadResultItem[];
    selectedIndex: number;
  } | null>(null);
  const [copiedCleanLogs, setCopiedCleanLogs] = useState(false);

  // Upload Failure / AI Quota Modal
  const [uploadFailureModal, setUploadFailureModal] = useState<UploadFailureInfo | null>(null);
  const [failureRawExpanded, setFailureRawExpanded] = useState(false);

  // Action loading
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  // Carousel ref
  const carouselRef = useRef<HTMLDivElement>(null);
  const filterToolbarRef = useRef<HTMLDivElement>(null);

  // ── Filter & Sort State ──────────────────────────────────────────
  const [searchQuery, setSearchQuery] = useState("");
  const [portfolioScope, setPortfolioScope] = useState<"actionable" | "all">("actionable");
  const [sortBy, setSortBy] = useState<
    "urgent" | "closest" | "due_desc" | "date_desc" | "date_asc" | "amount_desc" | "amount_asc"
  >("urgent");

  // Due Date Filter: "all" | "overdue" | "today" | "next7" | "next30" | "custom"
  const [dueDateFilter, setDueDateFilter] = useState<string>("all");
  const [dueCustomStart, setDueCustomStart] = useState<string>("");
  const [dueCustomEnd, setDueCustomEnd] = useState<string>("");

  // Invoice Date Filter: "all" | "last7" | "last30" | "last90" | "custom"
  const [invoiceDateFilter, setInvoiceDateFilter] = useState<string>("all");
  const [invoiceCustomStart, setInvoiceCustomStart] = useState<string>("");
  const [invoiceCustomEnd, setInvoiceCustomEnd] = useState<string>("");

  // Multi-select Flags
  const [selectedFlags, setSelectedFlags] = useState<string[]>([]);

  // Multi-select Companies
  const [selectedVendors, setSelectedVendors] = useState<string[]>([]);

  // ── Derived Flags Present in Invoices ────────────────────────────
  const presentFlags = useMemo(() => {
    return AVAILABLE_FLAGS.map((flag) => {
      const count = allInvoices.filter((inv) => invoiceMatchesFlag(inv, flag.id)).length;
      return { ...flag, count };
    }).filter((flag) => flag.count > 0);
  }, [allInvoices]);

  // ── Derived Companies (Only Invoices Currently Withheld) ───────────
  const withheldCompanies = useMemo(() => {
    const map = new Map<string, number>();
    allInvoices.forEach((inv) => {
      if (inv.vendor_name && isInvoiceWithheld(inv)) {
        map.set(inv.vendor_name, (map.get(inv.vendor_name) || 0) + 1);
      }
    });
    return Array.from(map.entries())
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [allInvoices]);

  // ── Filtered & Sorted Invoices ────────────────────────────────────
  const filteredInvoices = useMemo(() => {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const oneDay = 1000 * 60 * 60 * 24;

    return allInvoices
      .filter((inv) => {
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase().trim();
          const matchesId = inv.invoice_id.toLowerCase().includes(q);
          const matchesVendor = inv.vendor_name.toLowerCase().includes(q);
          const matchesNotes = (inv.notes || "").toLowerCase().includes(q);
          const matchesItem = (inv.line_items || []).some((li) => li.item.toLowerCase().includes(q));
          if (!matchesId && !matchesVendor && !matchesNotes && !matchesItem) return false;
        }

        if (portfolioScope === "actionable" && !selectedFlags.includes("ZERO_FLAGS")) {
          if (isProcessedSuccessfullyWithoutFlags(inv)) return false;
        }

        if (dueDateFilter !== "all") {
          const d = parseDate(inv.due_date);
          if (!d) return false;
          const dTime = d.getTime();

          if (dueDateFilter === "overdue") {
            if (dTime >= todayStart) return false;
          } else if (dueDateFilter === "today") {
            if (dTime < todayStart || dTime >= todayStart + oneDay) return false;
          } else if (dueDateFilter === "next7") {
            if (dTime < todayStart || dTime > todayStart + 7 * oneDay) return false;
          } else if (dueDateFilter === "next30") {
            if (dTime < todayStart || dTime > todayStart + 30 * oneDay) return false;
          } else if (dueDateFilter === "custom") {
            if (dueCustomStart && inv.due_date && inv.due_date < dueCustomStart) return false;
            if (dueCustomEnd && inv.due_date && inv.due_date > dueCustomEnd) return false;
          }
        }

        if (invoiceDateFilter !== "all") {
          const d = parseDate(inv.date);
          if (!d) return false;
          const dTime = d.getTime();

          if (invoiceDateFilter === "last7") {
            if (dTime < todayStart - 7 * oneDay || dTime > todayStart + oneDay) return false;
          } else if (invoiceDateFilter === "last30") {
            if (dTime < todayStart - 30 * oneDay || dTime > todayStart + oneDay) return false;
          } else if (invoiceDateFilter === "last90") {
            if (dTime < todayStart - 90 * oneDay || dTime > todayStart + oneDay) return false;
          } else if (invoiceDateFilter === "custom") {
            if (invoiceCustomStart && inv.date && inv.date < invoiceCustomStart) return false;
            if (invoiceCustomEnd && inv.date && inv.date > invoiceCustomEnd) return false;
          }
        }

        if (selectedFlags.length > 0) {
          const matchesFlag = selectedFlags.some((fId) => invoiceMatchesFlag(inv, fId));
          if (!matchesFlag) return false;
        }

        if (selectedVendors.length > 0) {
          if (!selectedVendors.includes(inv.vendor_name)) return false;
        }

        return true;
      })
      .sort((a, b) => {
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();

        const getDueDiff = (inv: InvoiceItem) => {
          const d = parseDate(inv.due_date || inv.date);
          if (!d) return 999999;
          return Math.round((d.getTime() - today) / (1000 * 60 * 60 * 24));
        };

        if (sortBy === "urgent") {
          const diffA = getDueDiff(a);
          const diffB = getDueDiff(b);
          if (diffA !== diffB) return diffA - diffB;
          if (a.ui_status === "pending_approval" && b.ui_status !== "pending_approval") return -1;
          if (b.ui_status === "pending_approval" && a.ui_status !== "pending_approval") return 1;
          return a.id - b.id;
        }

        if (sortBy === "closest") {
          const diffA = Math.abs(getDueDiff(a));
          const diffB = Math.abs(getDueDiff(b));
          if (diffA !== diffB) return diffA - diffB;
          return a.id - b.id;
        }

        if (sortBy === "due_desc") {
          const diffA = getDueDiff(a);
          const diffB = getDueDiff(b);
          return diffB - diffA;
        }

        if (sortBy === "date_desc") {
          const da = new Date(a.date).getTime() || 0;
          const db = new Date(b.date).getTime() || 0;
          return db - da;
        }

        if (sortBy === "date_asc") {
          const da = new Date(a.date).getTime() || 0;
          const db = new Date(b.date).getTime() || 0;
          return da - db;
        }

        if (sortBy === "amount_desc") {
          return (b.total || 0) - (a.total || 0);
        }

        if (sortBy === "amount_asc") {
          return (a.total || 0) - (b.total || 0);
        }

        return 0;
      });
  }, [
    allInvoices,
    searchQuery,
    portfolioScope,
    dueDateFilter,
    dueCustomStart,
    dueCustomEnd,
    invoiceDateFilter,
    invoiceCustomStart,
    invoiceCustomEnd,
    selectedFlags,
    selectedVendors,
    sortBy,
  ]);

  const carouselInvoices = filteredInvoices;
  const pendingInvoices = carouselInvoices.filter((inv) => inv.ui_status === "pending_approval");
  const total = carouselInvoices.length;

  // ── Executive KPI Counts & Triage Metrics ──────────────────────────
  const isInvoiceInPendingTriage = useCallback((inv: InvoiceItem) => {
    if (inv.ui_status === "rejected" || inv.payment_status === "rejected" || inv.human_approval_status === "rejected") {
      return false;
    }
    if (isProcessedSuccessfullyWithoutFlags(inv) || isInvoiceApproved(inv)) {
      return false;
    }
    return (
      inv.ui_status === "pending_approval" ||
      inv.payment_status === "pending_approval" ||
      inv.human_approval_status === "pending" ||
      inv.decision === "requires_human_approval" ||
      inv.requires_human === 1 ||
      hasRaisedFlags(inv)
    );
  }, []);

  const kpiCounts = useMemo(() => {
    if (!allInvoices || allInvoices.length === 0) {
      return {
        ingested: stats?.total_invoices ?? 0,
        approved: stats?.approved_count ?? 0,
        pending: stats?.pending_approvals ?? 0,
        flagged: stats?.suspicious_count ?? 0,
        rejected: stats?.rejected_count ?? 0,
      };
    }

    const pendingList = allInvoices.filter(isInvoiceInPendingTriage);
    const approvedList = allInvoices.filter(inv => isProcessedSuccessfullyWithoutFlags(inv) || isInvoiceApproved(inv));
    const rejectedList = allInvoices.filter(inv => inv.ui_status === "rejected" || inv.payment_status === "rejected" || inv.human_approval_status === "rejected");
    const flaggedInPending = pendingList.filter(inv => hasRaisedFlags(inv));

    return {
      ingested: stats?.total_invoices ?? allInvoices.length,
      approved: approvedList.length,
      pending: pendingList.length,
      flagged: flaggedInPending.length,
      rejected: rejectedList.length,
    };
  }, [allInvoices, stats, isInvoiceInPendingTriage]);

  // Clamp carousel index when filtered items change
  useEffect(() => {
    if (currentIndex >= total && total > 0) {
      setCurrentIndex(total - 1);
    } else if (total === 0) {
      setCurrentIndex(0);
    }
  }, [total, currentIndex]);

  const resetAllFilters = () => {
    setSearchQuery("");
    setPortfolioScope("actionable");
    setSortBy("urgent");
    setDueDateFilter("all");
    setDueCustomStart("");
    setDueCustomEnd("");
    setInvoiceDateFilter("all");
    setInvoiceCustomStart("");
    setInvoiceCustomEnd("");
    setSelectedFlags([]);
    setSelectedVendors([]);
  };

  const hasActiveFilters =
    searchQuery.trim() !== "" ||
    dueDateFilter !== "all" ||
    dueCustomStart !== "" ||
    dueCustomEnd !== "" ||
    invoiceDateFilter !== "all" ||
    invoiceCustomStart !== "" ||
    invoiceCustomEnd !== "" ||
    selectedFlags.length > 0 ||
    selectedVendors.length > 0 ||
    sortBy !== "urgent";

  // ── Data loading ──────────────────────────────────────────────────
  const loadData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [s, invs] = await Promise.all([
        fetchStats().catch(() => null),
        fetchInvoices("all").catch(() => []),
      ]);
      if (s) setStats(s);

      const list = invs || [];
      if (list.some((inv) => !inv.line_items || inv.line_items.length === 0)) {
        const enriched = await Promise.all(
          list.map(async (inv) => {
            if (inv.line_items && inv.line_items.length > 0) return inv;
            try {
              const detail = await fetchInvoiceDetail(inv.invoice_id);
              return { ...inv, line_items: detail.line_items || [] };
            } catch {
              return inv;
            }
          })
        );
        setAllInvoices(enriched);
      } else {
        setAllInvoices(list);
      }
    } catch (err) {
      console.error("Failed loading data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSettings = useCallback(async () => {
    try {
      const data = await fetchSettings();
      setSettings(data);
      const onb = await fetchOnboardingStatus();
      setOnboardingStatus(onb);
    } catch (err) {
      console.error("Failed loading settings:", err);
    }
  }, []);

  useEffect(() => {
    loadData();
    loadSettings();
  }, [loadData, loadSettings]);

  // ── Onboarding Tour Auto-Starter for First Time Users ───────────────
  useEffect(() => {
    let active = true;
    async function checkFirstTimeUser() {
      try {
        const onb = await fetchOnboardingStatus();
        if (active) {
          setOnboardingStatus(onb);
          if (onb.is_first_time_user) {
            setTimeout(() => {
              if (active) {
                startOnborda(ONBOARDING_TOUR_NAME);
              }
            }, 800);
          }
        }
      } catch (err) {
        console.error("Failed checking first time user onboarding:", err);
      }
    }
    checkFirstTimeUser();
    return () => {
      active = false;
    };
  }, [startOnborda]);

  const handleToggleVPReview = async (enabled: boolean) => {
    setSavingSettings(true);
    try {
      const res = await updateSettings({ enable_vp_review: enabled });
      setSettings((prev) => (prev ? { ...prev, enable_vp_review: res.enable_vp_review } : null));
      showToast(
        "custom",
        "",
        enabled
          ? "VP Executive AI Reflection Review is now ENABLED."
          : "VP Executive AI Review DISABLED (Fast Deterministic Mode active)."
      );
    } catch (err) {
      console.error("Failed to update settings:", err);
    } finally {
      setSavingSettings(false);
    }
  };

  // ── Business rules loader ─────────────────────────────────────────
  const loadBusinessRules = useCallback(async () => {
    setLoadingRules(true);
    try {
      const rules = await fetchBusinessRules();
      setBusinessRules(rules);
    } catch (err) {
      console.error("Failed loading business rules:", err);
    } finally {
      setLoadingRules(false);
    }
  }, []);

  useEffect(() => {
    if (activeNav === "vendor-rules") {
      loadBusinessRules();
    }
  }, [activeNav, loadBusinessRules]);

  // ── Carousel navigation ──────────────────────────────────────────
  const goToIndex = useCallback((idx: number) => {
    const clamped = Math.max(0, Math.min(idx, total - 1));
    setCurrentIndex(clamped);
    const track = carouselRef.current;
    if (track) {
      const cards = track.querySelectorAll<HTMLElement>(".carousel-card");
      const card = cards[clamped];
      if (card) {
        // Horizontally scroll the carousel track ONLY; never scroll or jump the parent window/page
        const cardRect = card.getBoundingClientRect();
        const trackRect = track.getBoundingClientRect();
        const cardOffset = cardRect.left - trackRect.left + track.scrollLeft;
        const targetScrollLeft = cardOffset - (track.clientWidth - card.clientWidth) / 2;
        track.scrollTo({
          left: Math.max(0, targetScrollLeft),
          behavior: "smooth",
        });
      }
    }
  }, [total]);

  // ── Sync index on manual scroll ───────────────────────────────────
  useEffect(() => {
    const track = carouselRef.current;
    if (!track) return;
    let scrollTimeout: ReturnType<typeof setTimeout>;
    const onScroll = () => {
      clearTimeout(scrollTimeout);
      scrollTimeout = setTimeout(() => {
        const rect = track.getBoundingClientRect();
        const center = rect.left + rect.width / 2;
        const cards = track.querySelectorAll<HTMLElement>(".carousel-card");
        let closest = 0;
        let minDist = Infinity;
        cards.forEach((card, i) => {
          const cr = card.getBoundingClientRect();
          const dist = Math.abs(cr.left + cr.width / 2 - center);
          if (dist < minDist) { minDist = dist; closest = i; }
        });
        if (closest !== currentIndex) setCurrentIndex(closest);
      }, 80);
    };
    track.addEventListener("scroll", onScroll);
    return () => track.removeEventListener("scroll", onScroll);
  }, [currentIndex]);

  // ── Modal ─────────────────────────────────────────────────────────
  const openModal = async (inv: InvoiceItem) => {
    setModalOpen(true);
    setLoadingDetail(true);
    try {
      const detail = await fetchInvoiceDetail(inv.invoice_id);
      setModalInvoice({
        ...inv,
        ...detail,
        rules_triggered: (detail.rules_triggered && detail.rules_triggered.length > 0)
          ? detail.rules_triggered
          : (detail.review?.rules_triggered && detail.review.rules_triggered.length > 0)
            ? detail.review.rules_triggered
            : (inv.rules_triggered || []),
        ui_status: detail.ui_status || inv.ui_status,
      });
    } catch {
      setModalInvoice(inv);
    } finally {
      setLoadingDetail(false);
    }
  };

  const closeModal = () => {
    setModalOpen(false);
    setTimeout(() => setModalInvoice(null), 200);
  };

  const closeOriginalViewer = () => {
    setOriginalViewerOpen(false);
  };

  const handleViewOriginal = async (invoiceId: string) => {
    setOriginalViewerOpen(true);
    setLoadingOriginal(true);
    setOriginalError(null);
    setCopiedRaw(false);
    try {
      const data = await fetchOriginalInvoiceContent(invoiceId);
      setOriginalDoc(data);
    } catch (err: any) {
      console.error("Failed to load original invoice:", err);
      setOriginalError(err?.message || "Failed to load original invoice document from backend server");
    } finally {
      setLoadingOriginal(false);
    }
  };

  const handleCopyRaw = () => {
    if (originalDoc?.content) {
      navigator.clipboard.writeText(originalDoc.content);
      setCopiedRaw(true);
      setTimeout(() => setCopiedRaw(false), 2000);
    }
  };

  // ── Toast ─────────────────────────────────────────────────────────
  const showToast = (
    action: "approve" | "reject" | "blacklist" | "rule_created" | "rule_toggled" | "rule_deleted" | "custom" | "upload_success",
    invoiceId: string = "",
    message?: string
  ) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast({ visible: true, action, invoiceId, message });
    toastTimerRef.current = setTimeout(() => {
      setToast(prev => prev ? { ...prev, visible: false } : null);
      setTimeout(() => setToast(null), 300);
    }, 3200);
  };

  // ── Actions ───────────────────────────────────────────────────────
  const handleApprove = async (invoiceId: string) => {
    setActionLoadingId(invoiceId);
    try {
      await approveInvoice(invoiceId);
      showToast("approve", invoiceId);
      await loadData(true);
      if (currentIndex >= pendingInvoices.length - 1 && currentIndex > 0)
        setCurrentIndex(prev => prev - 1);
    } catch (err) {
      console.error("Approval failed:", err);
      await loadData(true);
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleReject = async (invoiceId: string) => {
    setActionLoadingId(invoiceId);
    try {
      await rejectInvoice(invoiceId);
      showToast("reject", invoiceId);
      await loadData(true);
      if (currentIndex >= pendingInvoices.length - 1 && currentIndex > 0)
        setCurrentIndex(prev => prev - 1);
    } catch (err) {
      console.error("Rejection failed:", err);
      await loadData(true);
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleBlacklist = async (invoiceId: string) => {
    setActionLoadingId(invoiceId);
    try {
      await rejectAndBlockInvoice(invoiceId);
      showToast("blacklist", invoiceId);
      await loadData(true);
      if (currentIndex >= pendingInvoices.length - 1 && currentIndex > 0)
        setCurrentIndex(prev => prev - 1);
    } catch (err) {
      console.error("Blacklist failed:", err);
      await loadData(true);
    } finally {
      setActionLoadingId(null);
    }
  };

  // ── Vendor Rule Handlers ──────────────────────────────────────────
  const handleToggleRule = async (rule: BusinessRule) => {
    try {
      const res = await toggleBusinessRule(rule.id);
      setBusinessRules(prev => prev.map(r => r.id === rule.id ? { ...r, is_active: res.is_active } : r));
      showToast("rule_toggled", "", `Rule "${rule.name}" is now ${res.is_active ? "ACTIVE" : "INACTIVE"}.`);
    } catch (err: any) {
      alert(err.message || "Failed to toggle rule");
    }
  };

  const handleDeleteRule = async (rule: BusinessRule) => {
    if (rule.is_system) {
      alert("Default system rules cannot be deleted, but you can toggle them inactive.");
      return;
    }
    if (!confirm(`Permanently delete custom policy rule "${rule.name}"?`)) return;
    try {
      await deleteBusinessRule(rule.id);
      setBusinessRules(prev => prev.filter(r => r.id !== rule.id));
      showToast("rule_deleted", "", `Rule "${rule.name}" successfully deleted.`);
    } catch (err: any) {
      alert(err.message || "Failed to delete rule");
    }
  };

  const handleTestExistingRule = async (rule: BusinessRule) => {
    setActiveRuleTestId(rule.id);
    try {
      const result = await testBusinessRule({
        name: rule.name,
        description: rule.description,
        raw_query: rule.sql_query || undefined,
      });
      setRuleTestResults(prev => ({ ...prev, [rule.id]: result }));
    } catch (err: any) {
      alert(err.message || "Failed to test rule against invoices");
    } finally {
      setActiveRuleTestId(null);
    }
  };

  const handleTestNewRule = async () => {
    if (!newRuleDesc.trim()) {
      alert("Please enter a rule description or natural language condition.");
      return;
    }
    setTestingRule(true);
    setTestResult(null);
    try {
      const result = await testBusinessRule({
        name: newRuleName.trim() || "CUSTOM_RULE",
        description: newRuleDesc.trim(),
        raw_query: showCustomSqlInput && newRuleCustomSql.trim() ? newRuleCustomSql.trim() : undefined,
      });
      setTestResult(result);
    } catch (err: any) {
      alert(err.message || "Rule test and compilation failed");
    } finally {
      setTestingRule(false);
    }
  };

  const handleSaveNewRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRuleName.trim()) {
      alert("Please enter a rule name.");
      return;
    }
    if (!newRuleDesc.trim()) {
      alert("Please enter a rule description.");
      return;
    }
    setSubmittingRule(true);
    try {
      await createBusinessRule({
        name: newRuleName.trim(),
        description: newRuleDesc.trim(),
        action: newRuleAction,
        raw_query: showCustomSqlInput && newRuleCustomSql.trim() ? newRuleCustomSql.trim() : undefined,
      });
      showToast("rule_created", "", `Policy rule "${newRuleName.trim().toUpperCase()}" created and active!`);
      setAddRuleModalOpen(false);
      setNewRuleName("");
      setNewRuleDesc("");
      setNewRuleCustomSql("");
      setShowCustomSqlInput(false);
      setTestResult(null);
      await loadBusinessRules();
    } catch (err: any) {
      alert(err.message || "Failed to create rule");
    } finally {
      setSubmittingRule(false);
    }
  };

  const applyRuleTemplate = (name: string, desc: string) => {
    setNewRuleName(name);
    setNewRuleDesc(desc);
    setTestResult(null);
  };

  // ── Upload ────────────────────────────────────────────────────────
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    setUploading(true);
    setFailureRawExpanded(false);
    try {
      const res = await uploadInvoices(Array.from(files));
      await loadData(true);

      const allResults = res.results || [];
      const actualInvoices = allResults.filter(
        (r) => r.is_invoice !== false && !r.skipped
      );

      if (actualInvoices.length === 0) {
        return;
      }

      const ingestedInvoices = actualInvoices.filter(
        (r) => r.success || Boolean(r.invoice_id)
      );
      const failedInvoices = actualInvoices.filter(
        (r) => !r.success && !r.invoice_id
      );

      const isFlagged = (r: UploadResultItem) =>
        Boolean(
          (r.rules_triggered && r.rules_triggered.length > 0) ||
          r.requires_human ||
          (r.decision && r.decision !== "auto_approved") ||
          (r.warnings && r.warnings.length > 0) ||
          (r.errors && r.errors.length > 0)
        );

      const flaggedInvoices = ingestedInvoices.filter(isFlagged);
      const cleanInvoices = ingestedInvoices.filter((r) => !isFlagged(r));

      if (flaggedInvoices.length > 0) {
        const primaryFlagged = flaggedInvoices[0];
        const invId = primaryFlagged.invoice_id;

        showToast(
          "upload_success",
          invId || "",
          flaggedInvoices.length === 1 && invId
            ? `Invoice ${invId} uploaded successfully.`
            : "Invoice uploaded successfully."
        );

        if (invId) {
          try {
            const detail = await fetchInvoiceDetail(invId);
            if (detail) {
              await openModal(detail as InvoiceItem);
            } else {
              await openModal({
                id: 0,
                invoice_id: invId,
                vendor_name: primaryFlagged.vendor || "Vendor",
                total: primaryFlagged.total || 0,
                currency: primaryFlagged.currency || "USD",
                rules_triggered: primaryFlagged.rules_triggered || [],
                ui_status: "pending_approval",
                format_detected: primaryFlagged.format_detected || "json",
                date: primaryFlagged.date || "",
                due_date: primaryFlagged.due_date || "",
                subtotal: primaryFlagged.subtotal ?? null,
                tax_rate: primaryFlagged.tax_rate ?? null,
                tax_amount: primaryFlagged.tax_amount ?? null,
                payment_terms: primaryFlagged.payment_terms ?? null,
                source_file: primaryFlagged.filename,
                is_suspicious: primaryFlagged.requires_human ? 1 : 0,
                suspicion_reasons: primaryFlagged.rules_triggered || [],
                arithmetic_correct: 1,
              } as InvoiceItem);
            }
          } catch {
            await openModal({
              id: 0,
              invoice_id: invId,
              vendor_name: primaryFlagged.vendor || "Vendor",
              total: primaryFlagged.total || 0,
              currency: primaryFlagged.currency || "USD",
              rules_triggered: primaryFlagged.rules_triggered || [],
              ui_status: "pending_approval",
              format_detected: primaryFlagged.format_detected || "json",
              date: primaryFlagged.date || "",
              due_date: primaryFlagged.due_date || "",
              subtotal: primaryFlagged.subtotal ?? null,
              tax_rate: primaryFlagged.tax_rate ?? null,
              tax_amount: primaryFlagged.tax_amount ?? null,
              payment_terms: primaryFlagged.payment_terms ?? null,
              source_file: primaryFlagged.filename,
              is_suspicious: primaryFlagged.requires_human ? 1 : 0,
              suspicion_reasons: primaryFlagged.rules_triggered || [],
              arithmetic_correct: 1,
            } as InvoiceItem);
          }
        }
      } else if (cleanInvoices.length > 0) {
        setCleanSuccessModal({
          open: true,
          invoices: cleanInvoices,
          selectedIndex: 0,
        });
      }

      if (failedInvoices.length > 0) {
        const quotaItem = failedInvoices.find((r) => r.is_quota_error);
        const isQuota = !!quotaItem;
        const rawError =
          quotaItem?.quota_details?.raw_error ||
          quotaItem?.errors?.[0] ||
          failedInvoices[0]?.errors?.[0] ||
          "Unknown upload failure";
        setUploadFailureModal({
          open: true,
          failures: failedInvoices,
          isQuota,
          rawError,
        });
      }
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : String(err);
      console.error("Upload failed:", errMsg);
      const isQuota = /429|quota|resource_exhausted|rate.?limit|generativelanguage/i.test(errMsg);
      setUploadFailureModal({
        open: true,
        failures: [],
        isQuota,
        rawError: errMsg,
      });
      await loadData(true);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return {
    startOnborda,
    onboardingStatus,
    setOnboardingStatus,
    stats,
    allInvoices,
    loading,
    currentIndex,
    setCurrentIndex,
    goToIndex,
    carouselRef,
    activeNav,
    setActiveNav,
    modalOpen,
    modalInvoice,
    loadingDetail,
    openModal,
    closeModal,
    originalViewerOpen,
    originalDoc,
    loadingOriginal,
    originalError,
    copiedRaw,
    handleViewOriginal,
    closeOriginalViewer,
    handleCopyRaw,
    toast,
    settingsOpen,
    setSettingsOpen,
    settings,
    savingSettings,
    handleToggleVPReview,
    businessRules,
    loadingRules,
    loadBusinessRules,
    handleToggleRule,
    handleDeleteRule,
    handleTestExistingRule,
    ruleTestResults,
    setRuleTestResults,
    activeRuleTestId,
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
    testResult,
    testingRule,
    submittingRule,
    handleSaveNewRule,
    handleTestNewRule,
    applyRuleTemplate,
    fileInputRef,
    uploading,
    handleFileUpload,
    cleanSuccessModal,
    setCleanSuccessModal,
    copiedCleanLogs,
    setCopiedCleanLogs,
    uploadFailureModal,
    setUploadFailureModal,
    failureRawExpanded,
    setFailureRawExpanded,
    actionLoadingId,
    handleApprove,
    handleReject,
    handleBlacklist,
    filterToolbarRef,
    searchQuery,
    setSearchQuery,
    portfolioScope,
    setPortfolioScope,
    sortBy,
    setSortBy,
    dueDateFilter,
    setDueDateFilter,
    dueCustomStart,
    setDueCustomStart,
    dueCustomEnd,
    setDueCustomEnd,
    invoiceDateFilter,
    setInvoiceDateFilter,
    invoiceCustomStart,
    setInvoiceCustomStart,
    invoiceCustomEnd,
    setInvoiceCustomEnd,
    selectedFlags,
    setSelectedFlags,
    selectedVendors,
    setSelectedVendors,
    presentFlags,
    withheldCompanies,
    filteredInvoices,
    carouselInvoices,
    pendingInvoices,
    total,
    kpiCounts,
    resetAllFilters,
    hasActiveFilters,
  };
}
