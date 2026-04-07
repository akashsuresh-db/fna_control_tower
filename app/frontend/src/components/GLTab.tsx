import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen, AlertTriangle, CheckCircle2, Play, Square,
  ClipboardCheck, Scale, UserCheck, XCircle
} from "lucide-react";
import { useSSE } from "../hooks/useSSE";
import { useMetrics } from "../hooks/useMetrics";
import MetricCard from "./MetricCard";
import GreetingBanner from "./GreetingBanner";
import ExceptionDrawer from "./ExceptionDrawer";
import SummaryCard from "./SummaryCard";
import { inr, formatNum } from "../utils";

type R2RMetrics = {
  metrics: {
    total_jes: number;
    total_lines: number;
    total_debits: number;
    total_credits: number;
    posted: number;
    pending: number;
    tb_total_debit: number;
    tb_total_credit: number;
    tb_imbalance: number;
    is_balanced: boolean;
    trial_balance: {
      account_code: string; account_name: string; account_type: string;
      debit: number; credit: number; balance: number; balance_type: string;
      transactions: number;
    }[];
  };
};

type ChecklistItem = { task: string; owner: string; status: string };

type Props = {
  userName?: string;
};

export default function GLTab({ userName = "User" }: Props) {
  const stream = useSSE("/stream/r2r");
  const { data: metricsData } = useMetrics<R2RMetrics>("/api/metrics/r2r");
  const [selectedEx, setSelectedEx] = useState<(typeof stream.exceptions)[0] | null>(null);
  const [showTB, setShowTB] = useState(false);
  const feedRef = useRef<HTMLDivElement>(null);

  const m = metricsData?.metrics;

  useEffect(() => {
    if (feedRef.current && stream.isStreaming) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [stream.events.length, stream.isStreaming]);

  const journalEntries = stream.events.filter((e) => e.type === "journal_entry");
  const checklistData = (stream.checklist ||
    (stream.greeting?.data as Record<string, unknown>)?.checklist || []) as ChecklistItem[];

  const tbLive = stream.tbUpdate as Record<string, unknown> | null;

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* KPI Strip */}
      {m && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <MetricCard label="Journal Entries" value={formatNum(m.total_jes)} icon={<BookOpen className="w-4 h-4" />} />
          <MetricCard label="Posted" value={formatNum(m.posted)} color="text-db-green" icon={<CheckCircle2 className="w-4 h-4" />} />
          <MetricCard label="Pending" value={formatNum(m.pending)} color="text-db-amber" icon={<ClipboardCheck className="w-4 h-4" />} />
          <MetricCard label="TB Debits" value={inr(m.tb_total_debit)} color="text-text-primary" />
          <MetricCard label="TB Credits" value={inr(m.tb_total_credit)} color="text-text-primary" />
          <MetricCard
            label="TB Status"
            value={m.is_balanced ? "BALANCED" : "IMBALANCED"}
            color={m.is_balanced ? "text-db-green" : "text-db-red"}
            icon={<Scale className="w-4 h-4" />}
          />
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center gap-3">
        {!stream.isStreaming && !stream.isComplete && (
          <button onClick={stream.start} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-db-blue text-white font-medium text-sm hover:bg-db-blue/80 transition">
            <Play className="w-4 h-4" /> Start JE Validation
          </button>
        )}
        {stream.isStreaming && (
          <button onClick={stream.stop} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-bg-card border border-border-subtle text-text-secondary text-sm hover:bg-bg-hover transition">
            <Square className="w-4 h-4" /> Stop
          </button>
        )}
        {stream.isStreaming && (
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <span className="w-2 h-2 rounded-full bg-db-green live-pulse" /> Validating entries...
          </div>
        )}
        <button
          onClick={() => setShowTB(!showTB)}
          className={`ml-auto px-3 py-1.5 rounded-lg text-xs font-medium transition ${
            showTB ? "bg-db-blue text-white" : "bg-bg-card border border-border-subtle text-text-secondary hover:bg-bg-hover"
          }`}
        >
          {showTB ? "Hide Trial Balance" : "Show Trial Balance"}
        </button>
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

      <GreetingBanner greeting={stream.greeting} isStreaming={stream.isStreaming} userName={userName} />

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 flex-1 min-h-0">
        {/* JE Feed or Trial Balance */}
        <div className="lg:col-span-2 glass-card flex flex-col overflow-hidden">
          {showTB ? (
            <>
              <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
                <h3 className="text-sm font-semibold text-text-primary">Live Trial Balance</h3>
                {tbLive && (
                  <span className={`text-xs font-semibold ${(tbLive.is_balanced as boolean) ? "text-db-green" : "text-db-red"}`}>
                    {(tbLive.is_balanced as boolean) ? "BALANCED" : "IMBALANCED"}
                  </span>
                )}
              </div>
              <div className="flex-1 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-bg-panel">
                    <tr className="text-xs text-text-muted">
                      <th className="text-left px-3 py-2">Account</th>
                      <th className="text-left px-3 py-2">Type</th>
                      <th className="text-right px-3 py-2">Debit</th>
                      <th className="text-right px-3 py-2">Credit</th>
                      <th className="text-right px-3 py-2">Balance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {m?.trial_balance.map((row, i) => (
                      <motion.tr
                        key={row.account_code}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: i * 0.02 }}
                        className="border-t border-border-subtle/50 hover:bg-bg-hover/30"
                      >
                        <td className="px-3 py-2">
                          <span className="font-mono text-xs text-text-muted mr-2">{row.account_code}</span>
                          <span className="text-text-primary">{row.account_name}</span>
                        </td>
                        <td className="px-3 py-2 text-xs text-text-muted">{row.account_type}</td>
                        <td className="px-3 py-2 text-right font-mono text-xs tabular-nums">
                          {row.debit > 0 ? inr(row.debit) : ""}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-xs tabular-nums">
                          {row.credit > 0 ? inr(row.credit) : ""}
                        </td>
                        <td className={`px-3 py-2 text-right font-mono text-xs font-semibold tabular-nums ${
                          row.balance_type === "DR" ? "text-db-green" : "text-db-blue"
                        }`}>
                          {inr(row.balance)} {row.balance_type}
                        </td>
                      </motion.tr>
                    ))}
                  </tbody>
                  {m && (
                    <tfoot className="sticky bottom-0 bg-bg-panel border-t-2 border-border-glow">
                      <tr className="font-semibold text-sm">
                        <td className="px-3 py-2" colSpan={2}>Total</td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums">{inr(m.tb_total_debit)}</td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums">{inr(m.tb_total_credit)}</td>
                        <td className={`px-3 py-2 text-right font-mono tabular-nums ${m.is_balanced ? "text-db-green" : "text-db-red"}`}>
                          {m.is_balanced ? "BALANCED" : `Diff: ${inr(m.tb_imbalance)}`}
                        </td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
            </>
          ) : (
            <>
              <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between">
                <h3 className="text-sm font-semibold text-text-primary">JE Validation Feed</h3>
                <span className="text-xs text-text-muted">{journalEntries.length} entries</span>
              </div>
              <div ref={feedRef} className="flex-1 overflow-y-auto p-2 space-y-1.5">
                <AnimatePresence initial={false}>
                  {journalEntries.map((evt, i) => {
                    const d = evt.data as Record<string, unknown>;
                    const balanced = d.is_balanced as boolean;
                    const lines = (d.lines || []) as Record<string, unknown>[];
                    return (
                      <motion.div
                        key={`${d.je_id}-${i}`}
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        className={`px-3 py-2.5 rounded-lg border cursor-pointer hover:bg-bg-hover/50 transition ${
                          balanced
                            ? "border-db-green/20 bg-db-green/5 match-success"
                            : "border-db-red/30 bg-db-red/5 exception-flash"
                        }`}
                        onClick={() => {
                          const exc = stream.exceptions.find(
                            (e) => (e.data as Record<string, unknown>).je_id === d.je_id
                          );
                          if (exc) setSelectedEx(exc);
                        }}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            {balanced ? (
                              <CheckCircle2 className="w-4 h-4 text-db-green flex-shrink-0" />
                            ) : (
                              <XCircle className="w-4 h-4 text-db-red flex-shrink-0" />
                            )}
                            <span className="font-mono text-xs text-text-muted">{d.je_number as string}</span>
                            <span className="text-xs px-1.5 py-0.5 rounded bg-bg-card text-text-muted">
                              {d.je_type as string}
                            </span>
                            <span className="text-sm text-text-primary truncate">{d.department as string}</span>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <span className="text-xs text-text-muted">{d.je_date as string}</span>
                            <span className={`text-xs font-semibold ${balanced ? "text-db-green" : "text-db-red"}`}>
                              {balanced ? "BALANCED" : "UNBALANCED"}
                            </span>
                          </div>
                        </div>
                        {/* Line items */}
                        <div className="mt-1.5 space-y-0.5">
                          {lines.slice(0, 3).map((l, li) => (
                            <div key={li} className="flex items-center text-xs text-text-muted gap-2">
                              <span className="font-mono w-10 text-right">{l.account_code as string}</span>
                              <span className="flex-1 truncate">{l.account_name as string}</span>
                              {(l.debit as number) > 0 && <span className="text-db-green tabular-nums">{inr(l.debit as number)} DR</span>}
                              {(l.credit as number) > 0 && <span className="text-db-blue tabular-nums">{inr(l.credit as number)} CR</span>}
                            </div>
                          ))}
                          {lines.length > 3 && (
                            <div className="text-[10px] text-text-muted pl-12">+{lines.length - 3} more lines</div>
                          )}
                        </div>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              </div>
            </>
          )}
        </div>

        {/* Right: Checklist + Running totals + Exceptions */}
        <div className="flex flex-col gap-4">
          {/* Close Checklist */}
          <div className="glass-card p-4">
            <div className="flex items-center gap-2 mb-3">
              <ClipboardCheck className="w-4 h-4 text-db-blue" />
              <h3 className="text-sm font-semibold text-text-primary">Close Checklist</h3>
            </div>
            {/* Progress bar */}
            {checklistData.length > 0 && (
              <div className="mb-3">
                <div className="flex justify-between text-xs text-text-muted mb-1">
                  <span>Progress</span>
                  <span>{checklistData.filter((c) => c.status === "completed").length}/{checklistData.length}</span>
                </div>
                <div className="h-2 rounded-full bg-bg-card overflow-hidden">
                  <motion.div
                    className="h-full rounded-full bg-db-green"
                    animate={{
                      width: `${(checklistData.filter((c) => c.status === "completed").length / checklistData.length) * 100}%`,
                    }}
                  />
                </div>
              </div>
            )}
            <div className="space-y-1.5">
              {checklistData.map((item, i) => (
                <div key={i} className="flex items-center gap-2 text-sm">
                  {item.status === "completed" ? (
                    <CheckCircle2 className="w-4 h-4 text-db-green flex-shrink-0" />
                  ) : item.status === "in_progress" ? (
                    <div className="w-4 h-4 rounded-full border-2 border-db-blue border-t-transparent animate-spin flex-shrink-0" />
                  ) : (
                    <div className="w-4 h-4 rounded border border-border-subtle flex-shrink-0" />
                  )}
                  <span className={item.status === "completed" ? "text-text-muted line-through" : "text-text-primary"}>
                    {item.task}
                  </span>
                  <span className="ml-auto text-[10px] text-text-muted">{item.owner}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Running TB Totals */}
          {tbLive && (
            <div className="glass-card p-4">
              <div className="flex items-center gap-2 mb-3">
                <Scale className="w-4 h-4 text-text-muted" />
                <h3 className="text-sm font-semibold text-text-primary">Running Balance</h3>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-text-muted">Debits</span>
                  <span className="font-mono tabular-nums text-db-green">{inr(tbLive.running_debit as number)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-text-muted">Credits</span>
                  <span className="font-mono tabular-nums text-db-blue">{inr(tbLive.running_credit as number)}</span>
                </div>
                <div className="border-t border-border-subtle pt-2 flex justify-between text-sm font-semibold">
                  <span>Status</span>
                  <span className={(tbLive.is_balanced as boolean) ? "text-db-green" : "text-db-red"}>
                    {(tbLive.is_balanced as boolean) ? "BALANCED" : "IMBALANCED"}
                  </span>
                </div>
                <div className="flex justify-between text-xs text-text-muted">
                  <span>JEs Posted: {tbLive.posted as number}</span>
                  <span className="text-db-red">Quarantined: {tbLive.quarantined as number}</span>
                </div>
              </div>
            </div>
          )}

          {/* Approval Queue */}
          <div className="glass-card p-4">
            <div className="flex items-center gap-2 mb-3">
              <UserCheck className="w-4 h-4 text-db-amber" />
              <h3 className="text-sm font-semibold text-text-primary">Controller Approval</h3>
              <span className="ml-auto text-xs text-text-muted">Vikram</span>
            </div>
            <div className="space-y-1">
              {stream.exceptions
                .filter((e) => (e.data as Record<string, unknown>).rule === "high_value_je")
                .slice(0, 5)
                .map((exc, i) => (
                  <div
                    key={i}
                    className="p-2 rounded-lg bg-db-amber/5 border border-db-amber/20 cursor-pointer hover:bg-db-amber/10 transition"
                    onClick={() => setSelectedEx(exc)}
                  >
                    <div className="flex justify-between text-xs">
                      <span className="text-text-primary font-mono">{(exc.data as Record<string, unknown>).je_number as string}</span>
                      <span className="text-db-amber font-semibold">{inr((exc.data as Record<string, unknown>).total_debit as number)}</span>
                    </div>
                  </div>
                ))}
              {stream.exceptions.filter((e) => (e.data as Record<string, unknown>).rule === "high_value_je").length === 0 && (
                <div className="text-xs text-text-muted text-center py-2">No pending approvals</div>
              )}
            </div>
          </div>

          {/* Quarantine alerts */}
          <div className="glass-card flex flex-col overflow-hidden" style={{ maxHeight: "180px" }}>
            <div className="px-4 py-3 border-b border-border-subtle flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-db-red" />
              <h3 className="text-sm font-semibold text-text-primary">Quarantine</h3>
              <span className="ml-auto text-xs text-db-red font-mono">
                {stream.exceptions.filter((e) => e.type === "quarantine").length}
              </span>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {stream.exceptions
                .filter((e) => e.type === "quarantine")
                .map((exc, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="p-2 rounded-lg border border-db-red/20 bg-db-red/5 cursor-pointer hover:bg-db-red/10 transition exception-flash text-xs"
                    onClick={() => setSelectedEx(exc)}
                  >
                    <span className="text-text-primary">{(exc.data as Record<string, unknown>).je_number as string}</span>
                    <span className="text-db-red ml-2">{(exc.data as Record<string, unknown>).rule as string}</span>
                  </motion.div>
                ))}
            </div>
          </div>
        </div>
      </div>

      <ExceptionDrawer exception={selectedEx} onClose={() => setSelectedEx(null)} />
    </div>
  );
}
