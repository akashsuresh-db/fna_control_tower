import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Users, AlertTriangle, DollarSign, Phone, Play, Square,
  CheckCircle2, Clock, TrendingUp, ShieldAlert, X
} from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ResponsiveContainer } from "recharts";
import { useSSE } from "../hooks/useSSE";
import { useMetrics } from "../hooks/useMetrics";
import MetricCard from "./MetricCard";
import GreetingBanner from "./GreetingBanner";
import ExceptionDrawer from "./ExceptionDrawer";
import SummaryCard from "./SummaryCard";
import { inr, formatNum, agingColor } from "../utils";

type O2CMetrics = {
  metrics: {
    total_outstanding: number;
    avg_dso: number;
    total_invoices: number;
    collected: number;
    total_collected: number;
    overdue_count: number;
    cei: number;
    aging_buckets: { bucket: string; count: number; amount: number }[];
    customers_at_risk: {
      name: string; credit_limit: number; outstanding: number;
      utilization: number; overdue: number; dso: number;
    }[];
  };
};

type Props = {
  userName?: string;
  onNotify?: (msg: string) => void;
};

type CallLogModal = {
  customerId: string;
  customerName: string;
} | null;

export default function ARTab({ userName = "User", onNotify }: Props) {
  const stream = useSSE("/stream/o2c");
  const { data: metricsData } = useMetrics<O2CMetrics>("/api/metrics/o2c");
  const [selectedEx, setSelectedEx] = useState<(typeof stream.exceptions)[0] | null>(null);
  const [callModal, setCallModal] = useState<CallLogModal>(null);
  const [callOutcome, setCallOutcome] = useState("REACHED_PTP");
  const [callPtpDate, setCallPtpDate] = useState("");
  const [callNotes, setCallNotes] = useState("");
  const [callSubmitting, setCallSubmitting] = useState(false);
  const feedRef = useRef<HTMLDivElement>(null);

  const m = metricsData?.metrics;

  useEffect(() => {
    if (feedRef.current && stream.isStreaming) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [stream.events.length, stream.isStreaming]);

  const collections = stream.events.filter(
    (e) => e.type === "collection" || e.type === "payment_received"
  );

  // Running collected ticker
  const collectedToday = collections
    .filter((e) => e.type === "payment_received")
    .reduce((sum, e) => sum + parseFloat(String((e.data as Record<string, unknown>).amount_collected_inr || 0)), 0);

  async function handleCallLog() {
    if (!callModal) return;
    setCallSubmitting(true);
    try {
      const resp = await fetch("/api/call-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: callModal.customerId,
          customer_name: callModal.customerName,
          outcome: callOutcome,
          ptp_date: callOutcome === "REACHED_PTP" ? callPtpDate : null,
          notes: callNotes,
        }),
      });
      if (resp.ok) {
        onNotify?.(`Call logged for ${callModal.customerName}: ${callOutcome}`);
        setCallModal(null);
        setCallOutcome("REACHED_PTP");
        setCallPtpDate("");
        setCallNotes("");
      }
    } catch {
      // silently fail
    } finally {
      setCallSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* KPI Strip */}
      {m && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <MetricCard label="AR Outstanding" value={inr(m.total_outstanding)} icon={<DollarSign className="w-4 h-4" />} />
          <MetricCard label="DSO" value={`${m.avg_dso} days`} color={m.avg_dso > 42 ? "text-db-amber" : "text-db-green"} sub="Target: 42 days" icon={<TrendingUp className="w-4 h-4" />} />
          <MetricCard label="CEI" value={`${m.cei}%`} color="text-db-blue" icon={<CheckCircle2 className="w-4 h-4" />} />
          <MetricCard label="Overdue" value={formatNum(m.overdue_count)} color="text-db-red" icon={<Clock className="w-4 h-4" />} />
          <MetricCard label="Collected" value={formatNum(m.collected)} color="text-db-green" icon={<DollarSign className="w-4 h-4" />} />
          <MetricCard label="At Risk" value={formatNum(m.customers_at_risk.length)} color="text-db-amber" icon={<ShieldAlert className="w-4 h-4" />} />
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center gap-3">
        {!stream.isStreaming && !stream.isComplete && (
          <button onClick={stream.start} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-db-blue text-white font-medium text-sm hover:bg-db-blue/80 transition">
            <Play className="w-4 h-4" /> Start Collection Run
          </button>
        )}
        {stream.isStreaming && (
          <button onClick={stream.stop} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-bg-card border border-border-subtle text-text-secondary text-sm hover:bg-bg-hover transition">
            <Square className="w-4 h-4" /> Stop
          </button>
        )}
        {stream.isStreaming && (
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <span className="w-2 h-2 rounded-full bg-db-green live-pulse" /> Processing...
          </div>
        )}
        {collectedToday > 0 && (
          <div className="ml-auto glass-card px-3 py-1.5 flex items-center gap-2">
            <DollarSign className="w-3 h-3 text-db-green" />
            <span className="text-xs text-text-muted">Collected today:</span>
            <span className="text-sm font-bold text-db-green tabular-nums">{inr(collectedToday)}</span>
          </div>
        )}
      </div>

      <GreetingBanner greeting={stream.greeting} isStreaming={stream.isStreaming} userName={userName} />

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 flex-1 min-h-0">
        {/* Left: Collections feed */}
        <div className="lg:col-span-2 glass-card flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Phone className="w-4 h-4 text-text-muted" />
              <h3 className="text-sm font-semibold text-text-primary">Collections Queue</h3>
            </div>
            <span className="text-xs text-text-muted">{collections.length} records</span>
          </div>
          <div ref={feedRef} className="flex-1 overflow-y-auto p-2 space-y-1.5">
            <AnimatePresence initial={false}>
              {collections.map((evt, i) => {
                const d = evt.data as Record<string, string | number | boolean>;
                const isPayment = evt.type === "payment_received";
                const daysOverdue = Number(d.days_overdue || 0);
                return (
                  <motion.div
                    key={`${d.o2c_invoice_id}-${i}`}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    className={`px-3 py-2.5 rounded-lg border cursor-pointer hover:bg-bg-hover/50 transition ${
                      isPayment
                        ? "border-db-green/30 bg-db-green/5 match-success"
                        : daysOverdue > 90
                        ? "border-db-red/30 bg-db-red/5"
                        : daysOverdue > 60
                        ? "border-db-amber/30 bg-db-amber/5"
                        : "border-border-subtle bg-bg-card/50"
                    }`}
                    onClick={() => {
                      const exc = stream.exceptions.find(
                        (e) => (e.data as Record<string, unknown>).invoice_id === d.o2c_invoice_id
                      );
                      if (exc) setSelectedEx(exc);
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        {isPayment ? (
                          <CheckCircle2 className="w-4 h-4 text-db-green flex-shrink-0" />
                        ) : daysOverdue > 60 ? (
                          <AlertTriangle className="w-4 h-4 text-db-red flex-shrink-0" />
                        ) : (
                          <Clock className="w-4 h-4 text-text-muted flex-shrink-0" />
                        )}
                        <span className="text-sm text-text-primary truncate font-medium">
                          {d.customer_name as string}
                        </span>
                        <span className="text-xs text-text-muted">{d.segment as string}</span>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className="text-sm font-semibold tabular-nums">
                          {isPayment ? (
                            <span className="text-db-green">{inr(d.amount_collected_inr)}</span>
                          ) : (
                            inr(d.balance_outstanding)
                          )}
                        </span>
                        <span className={`text-xs font-medium px-2 py-0.5 rounded ${
                          isPayment
                            ? "text-db-green"
                            : daysOverdue > 90
                            ? "text-db-red"
                            : daysOverdue > 60
                            ? "text-db-amber"
                            : "text-text-secondary"
                        }`}>
                          {isPayment
                            ? (d.auto_matched ? "Auto-Applied" : "Manual Review")
                            : `${d.days_outstanding} days`
                          }
                        </span>
                        {/* Log Call button for overdue items */}
                        {!isPayment && daysOverdue > 0 && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setCallModal({
                                customerId: d.o2c_invoice_id as string,
                                customerName: d.customer_name as string,
                              });
                            }}
                            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-db-blue/10 border border-db-blue/30 text-db-blue hover:bg-db-blue/20 transition"
                            title="Log Call"
                          >
                            <Phone className="w-3 h-3" /> Log
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-text-muted">
                      <span>{d.invoice_number as string}</span>
                      <span>Due: {d.due_date as string}</span>
                      <span>{d.aging_bucket as string}</span>
                      <span className={isPayment ? "text-db-green" : ""}>{d.invoice_status as string}</span>
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>
        </div>

        {/* Right side */}
        <div className="flex flex-col gap-4">
          {/* Aging Chart */}
          {m && m.aging_buckets.length > 0 && (
            <div className="glass-card p-4">
              <h3 className="text-sm font-semibold text-text-primary mb-3">AR Aging</h3>
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={m.aging_buckets} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                  <XAxis
                    dataKey="bucket"
                    tick={{ fontSize: 10, fill: "#8B949E" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis hide />
                  <Tooltip
                    contentStyle={{ background: "#111d2e", border: "1px solid #1e3050", borderRadius: 8, fontSize: 12 }}
                    formatter={(val: number) => [inr(val), "Amount"]}
                    labelStyle={{ color: "#8B949E" }}
                  />
                  <Bar dataKey="amount" radius={[4, 4, 0, 0]}>
                    {m.aging_buckets.map((entry, idx) => (
                      <Cell key={idx} fill={agingColor(entry.bucket)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Credit Risk Customers */}
          {m && m.customers_at_risk.length > 0 && (
            <div className="glass-card flex flex-col overflow-hidden" style={{ maxHeight: "280px" }}>
              <div className="px-4 py-3 border-b border-border-subtle flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-db-amber" />
                <h3 className="text-sm font-semibold text-text-primary">Credit Risk</h3>
                <span className="ml-auto text-xs text-text-muted">Amit (Credit Mgr)</span>
              </div>
              <div className="flex-1 overflow-y-auto p-2 space-y-1">
                {m.customers_at_risk.map((c, i) => (
                  <div key={i} className="p-2.5 rounded-lg bg-bg-card/50 border border-border-subtle">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-text-primary truncate">{c.name}</span>
                      <span className={`text-xs font-mono font-bold ${c.utilization > 100 ? "text-db-red" : "text-db-amber"}`}>
                        {c.utilization.toFixed(0)}%
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-bg-card mt-1.5 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${c.utilization > 100 ? "bg-db-red" : "bg-db-amber"}`}
                        style={{ width: `${Math.min(c.utilization, 100)}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-[10px] text-text-muted mt-1">
                      <span>Outstanding: {inr(c.outstanding)}</span>
                      <span>Limit: {inr(c.credit_limit)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Exceptions */}
          <div className="glass-card flex flex-col overflow-hidden" style={{ maxHeight: "200px" }}>
            <div className="px-4 py-3 border-b border-border-subtle flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-db-red" />
              <h3 className="text-sm font-semibold text-text-primary">Exceptions</h3>
              <span className="ml-auto text-xs text-db-red font-mono">{stream.exceptions.length}</span>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {stream.exceptions.map((exc, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="p-2 rounded-lg border border-db-red/20 bg-db-red/5 cursor-pointer hover:bg-db-red/10 transition exception-flash"
                  onClick={() => setSelectedEx(exc)}
                >
                  <div className="text-xs text-text-primary truncate">{exc.data.rule as string}</div>
                  <div className="text-[10px] text-text-muted truncate mt-0.5">
                    {(exc.data.customer_name || exc.data.invoice_id) as string}
                  </div>
                </motion.div>
              ))}
              {stream.exceptions.length === 0 && (
                <div className="text-xs text-text-muted text-center py-4">No exceptions yet</div>
              )}
            </div>
          </div>
        </div>
      </div>

      <ExceptionDrawer exception={selectedEx} onClose={() => setSelectedEx(null)} />

      {/* Call Log Modal */}
      <AnimatePresence>
        {callModal && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/50 z-40"
              onClick={() => setCallModal(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[420px] max-w-[90vw] bg-bg-panel border border-border-subtle rounded-xl shadow-2xl p-6"
            >
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-text-primary">Log Collection Call</h3>
                  <p className="text-xs text-text-muted mt-0.5">{callModal.customerName}</p>
                </div>
                <button onClick={() => setCallModal(null)} className="p-1 rounded hover:bg-bg-hover text-text-muted">
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-4">
                {/* Outcome */}
                <div>
                  <label className="text-xs font-medium text-text-secondary block mb-2">Outcome</label>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { value: "REACHED_PTP", label: "Reached - PTP" },
                      { value: "REACHED_DISPUTE", label: "Reached - Dispute" },
                      { value: "VOICEMAIL", label: "Voicemail" },
                      { value: "ESCALATE", label: "Escalate" },
                    ].map((opt) => (
                      <button
                        key={opt.value}
                        onClick={() => setCallOutcome(opt.value)}
                        className={`px-3 py-2 rounded-lg text-xs font-medium border transition ${
                          callOutcome === opt.value
                            ? "bg-db-blue/15 border-db-blue/40 text-db-blue"
                            : "bg-bg-card border-border-subtle text-text-secondary hover:bg-bg-hover"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* PTP Date (conditional) */}
                {callOutcome === "REACHED_PTP" && (
                  <div>
                    <label className="text-xs font-medium text-text-secondary block mb-1">Promise-to-Pay Date</label>
                    <input
                      type="date"
                      value={callPtpDate}
                      onChange={(e) => setCallPtpDate(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg bg-bg-card border border-border-subtle text-sm text-text-primary focus:outline-none focus:border-db-blue"
                    />
                  </div>
                )}

                {/* Notes */}
                <div>
                  <label className="text-xs font-medium text-text-secondary block mb-1">Notes</label>
                  <textarea
                    value={callNotes}
                    onChange={(e) => setCallNotes(e.target.value)}
                    rows={3}
                    placeholder="Call details..."
                    className="w-full px-3 py-2 rounded-lg bg-bg-card border border-border-subtle text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-db-blue resize-none"
                  />
                </div>

                {/* Submit */}
                <button
                  onClick={handleCallLog}
                  disabled={callSubmitting}
                  className="w-full py-2 rounded-lg bg-db-blue text-white text-sm font-medium hover:bg-db-blue/80 disabled:opacity-40 transition"
                >
                  {callSubmitting ? "Logging..." : "Log Call"}
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
