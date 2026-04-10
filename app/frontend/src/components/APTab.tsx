import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText, AlertTriangle, Shield, CreditCard, Play, Square,
  CheckCircle2, XCircle, Clock, ArrowUpRight, ThumbsUp, ThumbsDown, Send
} from "lucide-react";
import { useSSE } from "../hooks/useSSE";
import { useMetrics } from "../hooks/useMetrics";
import MetricCard from "./MetricCard";
import GreetingBanner from "./GreetingBanner";
import ExceptionDrawer from "./ExceptionDrawer";
import InvoiceDrawer from "./InvoiceDrawer";
import SummaryCard from "./SummaryCard";
import { inr, matchStatusColor, matchStatusBg, matchStatusLabel, formatNum } from "../utils";

type P2PMetrics = {
  metrics: {
    total_invoices: number;
    matched: number;
    two_way: number;
    amount_mismatch: number;
    no_po: number;
    exceptions: number;
    overdue_count: number;
    total_amount: number;
    overdue_amount: number;
    avg_aging_days: number;
    touchless_rate: number;
  };
  payment_run: {
    total_payments: number;
    total_paid: number;
    avg_dpo: number;
    early_payments: number;
    on_time_payments: number;
    late_payments: number;
  };
};

type Props = {
  userName?: string;
  onNotify?: (msg: string) => void;
};

export default function APTab({ userName = "User", onNotify }: Props) {
  const stream = useSSE("/stream/p2p");
  const { data: metricsData } = useMetrics<P2PMetrics>("/api/metrics/p2p");
  const [selectedEx, setSelectedEx] = useState<(typeof stream.exceptions)[0] | null>(null);
  const [openInvoiceId, setOpenInvoiceId] = useState<string | null>(null);
  const [approvedIds, setApprovedIds] = useState<Set<string>>(new Set());
  const [escalating, setEscalating] = useState(false);
  const [showEscalateModal, setShowEscalateModal] = useState(false);
  const [escalateRecipient, setEscalateRecipient] = useState("akash.s@databricks.com");
  const [escalateTypes, setEscalateTypes] = useState<Set<string>>(
    new Set(["AMOUNT_MISMATCH", "NO_PO_REFERENCE", "CRITICAL_OVERDUE", "MISSING_GSTIN"])
  );
  const feedRef = useRef<HTMLDivElement>(null);

  const EXCEPTION_OPTIONS = [
    { key: "AMOUNT_MISMATCH",  label: "Amount Mismatch",          severity: "HIGH",     color: "text-db-amber" },
    { key: "NO_PO_REFERENCE",  label: "No PO Reference",          severity: "HIGH",     color: "text-db-amber" },
    { key: "CRITICAL_OVERDUE", label: "Critical Overdue (>60d)",  severity: "CRITICAL", color: "text-db-red"   },
    { key: "MISSING_GSTIN",    label: "Missing GSTIN",            severity: "MEDIUM",   color: "text-yellow-400" },
  ];

  function toggleEscalateType(key: string) {
    setEscalateTypes(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  async function submitEscalate() {
    if (!escalateRecipient || escalateTypes.size === 0) return;
    setEscalating(true);
    setShowEscalateModal(false);
    try {
      const res = await fetch("/api/escalate/p2p", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recipient: escalateRecipient,
          exception_types: Array.from(escalateTypes),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Unknown error");
      if (data.status === "no_exceptions") {
        onNotify?.("No matching exceptions — SQL Alert found zero rows.");
      } else {
        onNotify?.(`✓ SQL Alert fired — ${data.row_count} exception type(s) reported to ${escalateRecipient}`);
      }
    } catch (err) {
      onNotify?.(`Escalation failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setEscalating(false);
    }
  }

  const m = metricsData?.metrics;
  const pr = metricsData?.payment_run;

  // Auto-scroll feed
  useEffect(() => {
    if (feedRef.current && stream.isStreaming) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [stream.events.length, stream.isStreaming]);

  // Separate invoices from other events
  const invoices = stream.events.filter(
    (e) => e.type === "invoice" || e.type === "invoice_processing"
  );

  async function handleApproval(invoiceId: string, action: "APPROVED" | "REJECTED", e: React.MouseEvent) {
    e.stopPropagation();
    try {
      const resp = await fetch("/api/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ invoice_id: invoiceId, action, reason: "" }),
      });
      if (resp.ok) {
        setApprovedIds((prev) => new Set(prev).add(invoiceId));
        onNotify?.(`Invoice ${invoiceId} ${action.toLowerCase()}`);
      }
    } catch {
      // silently fail
    }
  }

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* KPI Strip */}
      {m && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <MetricCard label="Total Invoices" value={formatNum(m.total_invoices)} icon={<FileText className="w-4 h-4" />} />
          <MetricCard label="3-Way Matched" value={formatNum(m.matched)} color="text-db-green" icon={<CheckCircle2 className="w-4 h-4" />} />
          <MetricCard label="Exceptions" value={formatNum(m.exceptions)} color="text-db-red" icon={<AlertTriangle className="w-4 h-4" />} />
          <MetricCard label="Touchless Rate" value={`${m.touchless_rate}%`} color="text-db-blue" icon={<Shield className="w-4 h-4" />} />
          <MetricCard label="Overdue" value={formatNum(m.overdue_count)} color="text-db-amber" sub={inr(m.overdue_amount)} icon={<Clock className="w-4 h-4" />} />
          <MetricCard label="Avg Aging" value={`${m.avg_aging_days} days`} color="text-text-primary" icon={<ArrowUpRight className="w-4 h-4" />} />
        </div>
      )}

      {/* Control bar */}
      <div className="flex items-center gap-3">
        {!stream.isStreaming && !stream.isComplete && (
          <button
            onClick={stream.start}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-db-blue text-white font-medium text-sm hover:bg-db-blue/80 transition"
          >
            <Play className="w-4 h-4" /> Start Processing
          </button>
        )}
        {stream.isStreaming && (
          <button
            onClick={stream.stop}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-bg-card border border-border-subtle text-text-secondary text-sm hover:bg-bg-hover transition"
          >
            <Square className="w-4 h-4" /> Stop
          </button>
        )}
        {stream.isStreaming && (
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <span className="w-2 h-2 rounded-full bg-db-green live-pulse" />
            Processing... {stream.progress ? `${(stream.progress as Record<string, number>).processed}/${(stream.progress as Record<string, number>).total}` : ""}
          </div>
        )}
        {stream.exceptions.length > 0 && (
          <div className="ml-auto flex items-center gap-1 text-xs text-db-red">
            <AlertTriangle className="w-3 h-3" />
            {stream.exceptions.length} exception{stream.exceptions.length > 1 ? "s" : ""}
          </div>
        )}
      </div>

      {/* Error Alert */}
      {stream.error && (
        <div className="px-4 py-3 rounded-lg bg-db-red/10 border border-db-red/30 flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-db-red flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm text-db-red font-medium">Stream Error</p>
            <p className="text-xs text-text-secondary mt-0.5">{stream.error}</p>
          </div>
        </div>
      )}

      {/* Greeting */}
      <GreetingBanner greeting={stream.greeting} isStreaming={stream.isStreaming} userName={userName} />

      {/* Main content grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 flex-1 min-h-0">
        {/* Invoice Queue */}
        <div className="lg:col-span-2 glass-card flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
            <h3 className="text-sm font-semibold text-text-primary">Invoice Queue</h3>
            <span className="text-xs text-text-muted">{invoices.length} records</span>
          </div>
          <div ref={feedRef} className="flex-1 overflow-y-auto p-2 space-y-1.5">
            <AnimatePresence initial={false}>
              {invoices.map((evt, i) => {
                const d = evt.data as Record<string, string | number>;
                const status = (d.match_status || "") as string;
                const invId = d.invoice_id as string;
                const isActioned = approvedIds.has(invId);
                const needsAction = status === "AMOUNT_MISMATCH" || status === "NO_PO_REFERENCE";
                return (
                  <motion.div
                    key={`${d.invoice_id}-${i}`}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.3 }}
                    className={`px-3 py-2.5 rounded-lg border cursor-pointer hover:bg-bg-hover/50 transition ${
                      isActioned ? "border-db-green/30 bg-db-green/5" :
                      status === "THREE_WAY_MATCHED" ? "match-success" : ""
                    } ${isActioned ? "" : matchStatusBg(status)}`}
                    onClick={() => {
                      const exc = stream.exceptions.find(
                        (e) => (e.data as Record<string, unknown>).invoice_id === d.invoice_id
                      );
                      if (exc) setSelectedEx(exc);
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="font-mono text-xs text-text-muted">{d.invoice_id as string}</span>
                        <span className="text-sm text-text-primary truncate font-medium">
                          {d.vendor_name as string}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 flex-shrink-0">
                        <span className="text-sm font-semibold tabular-nums">{inr(d.invoice_total_inr)}</span>
                        {isActioned ? (
                          <span className="text-xs font-medium px-2 py-0.5 rounded text-db-green">
                            Actioned
                          </span>
                        ) : (
                          <span className={`text-xs font-medium px-2 py-0.5 rounded ${matchStatusColor(status)}`}>
                            {d._anim_status === "running" ? (
                              <span className="flex items-center gap-1">
                                <span className="w-1.5 h-1.5 rounded-full bg-db-blue live-pulse" />
                                Matching...
                              </span>
                            ) : (
                              matchStatusLabel(status)
                            )}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center justify-between mt-1">
                      <div className="flex items-center gap-3 text-xs text-text-muted">
                        <span>{d.vendor_category as string}</span>
                        <span>Due: {d.due_date as string}</span>
                        {d.aging_bucket && <span className="text-db-amber">{d.aging_bucket as string}</span>}
                        {String(d.is_overdue) === "true" && (
                          <span className="text-db-red flex items-center gap-0.5">
                            <XCircle className="w-3 h-3" /> Overdue
                          </span>
                        )}
                      </div>
                      {/* Approve / Reject buttons for exception invoices */}
                      {needsAction && !isActioned && (
                        <div className="flex items-center gap-1 ml-2">
                          <button
                            onClick={(e) => handleApproval(invId, "APPROVED", e)}
                            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-db-green/10 border border-db-green/30 text-db-green hover:bg-db-green/20 transition"
                            title="Approve"
                          >
                            <ThumbsUp className="w-3 h-3" /> Approve
                          </button>
                          <button
                            onClick={(e) => handleApproval(invId, "REJECTED", e)}
                            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-db-red/10 border border-db-red/30 text-db-red hover:bg-db-red/20 transition"
                            title="Reject"
                          >
                            <ThumbsDown className="w-3 h-3" /> Reject
                          </button>
                        </div>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
        </div>

        {/* Right side: Exceptions + Payment Run */}
        <div className="flex flex-col gap-4">
          {/* Exception ticker */}
          <div className="glass-card flex flex-col overflow-hidden" style={{ maxHeight: "300px" }}>
            <div className="px-4 py-3 border-b border-border-subtle flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-db-red" />
              <h3 className="text-sm font-semibold text-text-primary">Exceptions</h3>
              <span className="text-xs text-db-red font-mono">{stream.exceptions.length}</span>
              {stream.exceptions.length > 0 && (
                <button
                  onClick={() => setShowEscalateModal(true)}
                  disabled={escalating}
                  className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-db-red text-white hover:bg-db-red/80 disabled:opacity-50 transition"
                >
                  <Send className="w-3 h-3" />
                  {escalating ? "Sending…" : "Escalate"}
                </button>
              )}
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              <AnimatePresence initial={false}>
                {stream.exceptions.map((exc, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="p-2.5 rounded-lg border border-db-red/20 bg-db-red/5 cursor-pointer hover:bg-db-red/10 transition exception-flash"
                    onClick={() => setSelectedEx(exc)}
                  >
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${
                        exc.data.severity === "critical" ? "bg-db-red/20 text-db-red" : "bg-db-amber/20 text-db-amber"
                      }`}>
                        {exc.data.severity as string}
                      </span>
                      <span className="text-xs text-text-primary truncate">{exc.data.rule as string}</span>
                    </div>
                    <div className="text-xs text-text-muted mt-1 truncate">
                      {(exc.data.vendor_name || exc.data.customer_name || exc.data.invoice_id) as string}
                      {exc.data.amount && <span className="ml-1 text-text-secondary">{inr(exc.data.amount as number)}</span>}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
              {stream.exceptions.length === 0 && (
                <div className="text-xs text-text-muted text-center py-4">
                  No exceptions yet
                </div>
              )}
            </div>
          </div>

          {/* Payment Run Panel */}
          {pr && (
            <div className="glass-card p-4">
              <div className="flex items-center gap-2 mb-3">
                <CreditCard className="w-4 h-4 text-db-blue" />
                <h3 className="text-sm font-semibold text-text-primary">Payment Run</h3>
                <span className="ml-auto text-xs text-text-muted">Rajesh (Supervisor)</span>
              </div>
              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-text-muted">Total Paid</span>
                  <span className="font-semibold">{inr(pr.total_paid)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-text-muted">Avg DPO</span>
                  <span className={`font-semibold ${pr.avg_dpo > 45 ? "text-db-red" : "text-db-green"}`}>
                    {pr.avg_dpo} days
                  </span>
                </div>
                {/* DPO gauge */}
                <div>
                  <div className="flex justify-between text-xs text-text-muted mb-1">
                    <span>DPO Target: 45 days</span>
                    <span>{pr.avg_dpo} days</span>
                  </div>
                  <div className="h-2 rounded-full bg-bg-card overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${pr.avg_dpo <= 45 ? "bg-db-green" : "bg-db-red"}`}
                      style={{ width: `${Math.min((pr.avg_dpo / 60) * 100, 100)}%` }}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2 pt-2 border-t border-border-subtle">
                  <div className="text-center">
                    <div className="text-lg font-bold text-db-green">{pr.early_payments}</div>
                    <div className="text-[10px] text-text-muted">Early</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-db-blue">{pr.on_time_payments}</div>
                    <div className="text-[10px] text-text-muted">On Time</div>
                  </div>
                  <div className="text-center">
                    <div className="text-lg font-bold text-db-red">{pr.late_payments}</div>
                    <div className="text-[10px] text-text-muted">Late</div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Exception drawer */}
      <ExceptionDrawer
        exception={selectedEx}
        onClose={() => setSelectedEx(null)}
        onViewInvoice={(id) => {
          setSelectedEx(null);
          setOpenInvoiceId(id);
        }}
      />

      {/* Invoice source document drawer */}
      <InvoiceDrawer invoiceId={openInvoiceId} onClose={() => setOpenInvoiceId(null)} />

      {/* Escalate modal */}
      {showEscalateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-bg-panel border border-border-subtle rounded-xl shadow-2xl w-full max-w-sm mx-4 overflow-hidden"
          >
            {/* Header */}
            <div className="px-5 py-4 border-b border-border-subtle flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-db-red" />
              <h3 className="text-sm font-semibold text-text-primary">Escalate via SQL Alert</h3>
              <span className="ml-auto text-[10px] text-text-muted bg-bg-card px-2 py-0.5 rounded-full border border-border-subtle">
                Databricks native
              </span>
            </div>

            <div className="p-5 space-y-4">
              {/* Recipient */}
              <div>
                <label className="text-xs font-medium text-text-secondary block mb-1.5">
                  Send alert to
                </label>
                <input
                  type="email"
                  value={escalateRecipient}
                  onChange={e => setEscalateRecipient(e.target.value)}
                  className="w-full bg-bg-card border border-border-subtle rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-db-blue"
                  placeholder="email@example.com"
                />
              </div>

              {/* Exception type checkboxes */}
              <div>
                <label className="text-xs font-medium text-text-secondary block mb-2">
                  Include exception types
                </label>
                <div className="space-y-2">
                  {EXCEPTION_OPTIONS.map(opt => (
                    <label
                      key={opt.key}
                      className="flex items-center gap-3 p-2.5 rounded-lg border border-border-subtle bg-bg-card cursor-pointer hover:border-db-blue/40 transition"
                    >
                      <input
                        type="checkbox"
                        checked={escalateTypes.has(opt.key)}
                        onChange={() => toggleEscalateType(opt.key)}
                        className="accent-db-red w-3.5 h-3.5"
                      />
                      <span className="flex-1 text-xs text-text-primary">{opt.label}</span>
                      <span className={`text-[10px] font-bold uppercase ${opt.color}`}>
                        {opt.severity}
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              <p className="text-[11px] text-text-muted leading-relaxed">
                A Databricks SQL Alert will be created/updated for the selected exception types.
                The recipient will receive an email from Databricks if any rows are found.
              </p>
            </div>

            {/* Actions */}
            <div className="px-5 py-3 border-t border-border-subtle flex gap-2 justify-end">
              <button
                onClick={() => setShowEscalateModal(false)}
                className="px-3 py-1.5 rounded-lg text-xs text-text-muted hover:text-text-primary border border-border-subtle hover:border-border-default transition"
              >
                Cancel
              </button>
              <button
                onClick={submitEscalate}
                disabled={escalateTypes.size === 0 || !escalateRecipient}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-db-red text-white hover:bg-db-red/80 disabled:opacity-40 transition"
              >
                <Send className="w-3 h-3" />
                Send Alert
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}
