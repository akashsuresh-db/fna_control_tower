import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { CheckCircle2, AlertTriangle, ArrowLeftRight, RefreshCw } from "lucide-react";
import { inr } from "../utils";

type ReconRow = {
  account_code: string;
  account_name: string;
  balance_type: "DR" | "CR";
  subledger_amount: number;
  gl_amount: number;
  delta: number;
  tied: boolean;
  subledger_source_table: string;
  subledger_metric: string;
};

/**
 * Single-glance proof that the AP/AR sub-ledger reconciles to the GL trial balance.
 * Hits /api/recon. Green row = tied (Δ < ₹1). Red row = broken loop, render the delta.
 */
export default function GLReconCard() {
  const [rows, setRows] = useState<ReconRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch("/api/recon");
      if (!r.ok) {
        setErr(`HTTP ${r.status}`);
        return;
      }
      const j = await r.json();
      setRows(j.rows as ReconRow[]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const allTied = rows && rows.length > 0 && rows.every((r) => r.tied);

  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-border-subtle bg-bg-card/80 backdrop-blur-sm shadow-sm p-4"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div
            className={`p-1.5 rounded-md ${
              allTied ? "bg-db-green/15" : "bg-db-red/15"
            }`}
          >
            {allTied ? (
              <CheckCircle2 className="w-4 h-4 text-db-green" />
            ) : (
              <ArrowLeftRight className="w-4 h-4 text-db-red" />
            )}
          </div>
          <div>
            <h3 className="text-sm font-bold text-text-primary leading-tight">
              Sub-ledger ↔ GL reconciliation
            </h3>
            <p className="text-[10px] text-text-muted leading-tight">
              {loading
                ? "Loading…"
                : err
                ? `error: ${err}`
                : allTied
                ? "All accounts tie out — loop closed ✓"
                : "Imbalance detected — investigate red rows"}
            </p>
          </div>
        </div>
        <button
          onClick={load}
          className="opacity-60 hover:opacity-100 transition p-1 rounded hover:bg-bg-hover"
          aria-label="Refresh reconciliation"
          disabled={loading}
        >
          <RefreshCw
            className={`w-3.5 h-3.5 text-text-muted ${loading ? "animate-spin" : ""}`}
          />
        </button>
      </div>

      {rows && rows.length > 0 ? (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text-muted border-b border-border-subtle">
              <th className="text-left font-normal py-1.5">Acct</th>
              <th className="text-left font-normal">Account</th>
              <th className="text-right font-normal">Sub-ledger</th>
              <th className="text-right font-normal">GL TB</th>
              <th className="text-right font-normal">Δ</th>
              <th className="text-center font-normal w-8">Tied</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.account_code}
                className={
                  r.tied ? "" : "bg-db-red/5 ring-1 ring-db-red/30"
                }
              >
                <td className="font-mono text-text-secondary py-2">
                  {r.account_code}
                </td>
                <td className="text-text-primary">
                  {r.account_name}
                  <span className="ml-2 text-[9px] font-mono opacity-50">
                    [{r.balance_type}]
                  </span>
                </td>
                <td className="text-right tabular-nums">{inr(r.subledger_amount)}</td>
                <td className="text-right tabular-nums">{inr(r.gl_amount)}</td>
                <td
                  className={`text-right tabular-nums ${
                    Math.abs(r.delta) < 1 ? "text-db-green" : "text-db-red font-semibold"
                  }`}
                >
                  {Math.abs(r.delta) < 1 ? "₹0.00" : inr(r.delta)}
                </td>
                <td className="text-center">
                  {r.tied ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-db-green inline" />
                  ) : (
                    <AlertTriangle className="w-3.5 h-3.5 text-db-red inline" />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : loading ? (
        <div className="space-y-1.5">
          <div className="h-3 bg-bg-hover/50 rounded animate-pulse" />
          <div className="h-3 bg-bg-hover/50 rounded animate-pulse" />
        </div>
      ) : (
        <p className="text-[12px] text-text-muted italic">
          Reconciliation view unavailable.
        </p>
      )}

      {rows && rows.length > 0 && (
        <p className="mt-2 text-[10px] text-text-muted">
          Sources: <code className="text-text-secondary">gold_fact_collections</code> and
          {" "}
          <code className="text-text-secondary">gold_fact_invoices</code> ↔
          {" "}<code className="text-text-secondary">gold_fact_trial_balance</code>
        </p>
      )}
    </motion.div>
  );
}
