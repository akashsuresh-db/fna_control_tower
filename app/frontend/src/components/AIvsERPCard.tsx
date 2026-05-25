import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { CheckCircle2, XCircle, AlertTriangle, ShieldCheck, FileText, RefreshCw } from "lucide-react";

type Check = {
  id: number;
  name: string;
  status: "PASS" | "WARN" | "FAIL";
  detail: string;
};
type Recommendation = { label: "APPROVE" | "HOLD" | "REJECT"; tone: "success" | "warning" | "danger"; reason: string };
type Verify = {
  invoice_id: string;
  invoice_number: string;
  vendor_name: string;
  checks: Check[];
  recommendation: Recommendation;
};

type Props = {
  invoiceId: string;
  onClose?: () => void;
};

/**
 * "Verify before approve" card. Hits /api/verify-invoice/{id} and renders the
 * eight credibility checks plus the recommended action. Designed to be opened
 * from the exception drawer or the invoice queue.
 */
export default function AIvsERPCard({ invoiceId, onClose }: Props) {
  const [v, setV] = useState<Verify | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch(`/api/verify-invoice/${encodeURIComponent(invoiceId)}`);
      if (!r.ok) {
        setErr(`HTTP ${r.status}`);
        return;
      }
      setV((await r.json()) as Verify);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [invoiceId]);

  const recColors: Record<string, string> = {
    success: "bg-db-green/15 text-db-green border-db-green/30",
    warning: "bg-db-amber/15 text-db-amber border-db-amber/30",
    danger:  "bg-db-red/15 text-db-red border-db-red/30",
  };
  const statusIcon = (s: Check["status"]) =>
    s === "PASS" ? <CheckCircle2 className="w-3.5 h-3.5 text-db-green" />
    : s === "WARN" ? <AlertTriangle className="w-3.5 h-3.5 text-db-amber" />
    : <XCircle className="w-3.5 h-3.5 text-db-red" />;

  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-border-subtle bg-bg-card/95 shadow-lg p-4"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-md bg-db-blue/15">
            <ShieldCheck className="w-4 h-4 text-db-blue" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-text-primary leading-tight">
              Pre-approval credibility check
            </h3>
            <p className="text-[10px] text-text-muted leading-tight">
              {v ? `${v.invoice_number} · ${v.vendor_name}` : (loading ? "Running 8 checks…" : err)}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={load} className="opacity-60 hover:opacity-100 transition p-1 rounded hover:bg-bg-hover" disabled={loading} aria-label="Re-run checks">
            <RefreshCw className={`w-3.5 h-3.5 text-text-muted ${loading ? "animate-spin" : ""}`} />
          </button>
          {onClose && (
            <button onClick={onClose} className="opacity-60 hover:opacity-100 transition p-1 rounded hover:bg-bg-hover" aria-label="Close">
              <XCircle className="w-4 h-4 text-text-muted" />
            </button>
          )}
        </div>
      </div>

      {v ? (
        <>
          <ul className="space-y-1 text-xs">
            {v.checks.map((c) => (
              <li
                key={c.id}
                className={`flex items-start gap-2 px-2 py-1.5 rounded ${
                  c.status === "FAIL" ? "bg-db-red/5" : c.status === "WARN" ? "bg-db-amber/5" : ""
                }`}
              >
                <span className="mt-0.5">{statusIcon(c.status)}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-text-primary font-medium">{c.name}</div>
                  <div className="text-text-muted text-[11px]">{c.detail}</div>
                </div>
              </li>
            ))}
          </ul>
          <div className={`mt-3 p-2.5 rounded-lg border text-xs font-semibold ${recColors[v.recommendation.tone]}`}>
            <span className="text-[10px] uppercase tracking-wide opacity-80">Recommendation</span>
            <div className="text-base mt-0.5">{v.recommendation.label}</div>
            <div className="text-[11px] font-normal opacity-90 mt-1">{v.recommendation.reason}</div>
          </div>
        </>
      ) : loading ? (
        <div className="space-y-1.5">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <div key={i} className="h-5 bg-bg-hover/50 rounded animate-pulse" />
          ))}
        </div>
      ) : (
        <p className="text-xs text-text-muted italic">{err ?? "No verification data."}</p>
      )}
    </motion.div>
  );
}
