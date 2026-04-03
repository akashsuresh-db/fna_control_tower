import { motion, AnimatePresence } from "framer-motion";
import { X, AlertTriangle, ShieldAlert, Info, FileText } from "lucide-react";
import { severityBadge, inr } from "../utils";
import type { SSEEvent } from "../hooks/useSSE";

type Props = {
  exception: SSEEvent | null;
  onClose: () => void;
  onViewInvoice?: (id: string) => void;
};

export default function ExceptionDrawer({ exception, onClose, onViewInvoice }: Props) {
  return (
    <AnimatePresence>
      {exception && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 z-40"
            onClick={onClose}
          />
          {/* Drawer */}
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="fixed right-0 top-0 bottom-0 w-[440px] max-w-[90vw] bg-bg-panel border-l border-db-red/30 z-50 shadow-2xl overflow-y-auto"
          >
            <div className="p-6">
              {/* Header */}
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                  {exception.data.severity === "critical" ? (
                    <ShieldAlert className="w-5 h-5 text-db-red" />
                  ) : (
                    <AlertTriangle className="w-5 h-5 text-db-amber" />
                  )}
                  <span className="font-bold text-text-primary">
                    {exception.type === "quarantine" ? "Quarantine Alert" : "Exception Detected"}
                  </span>
                </div>
                <button
                  onClick={onClose}
                  className="p-1 rounded hover:bg-bg-hover text-text-muted hover:text-text-primary transition"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Severity badge */}
              <div className="mb-4">
                <span className={`inline-flex px-3 py-1 rounded-full text-xs font-semibold uppercase ${severityBadge(exception.data.severity as string)}`}>
                  {exception.data.severity as string}
                </span>
              </div>

              {/* Details */}
              <div className="space-y-4">
                {exception.data.invoice_id && (
                  <div className="glass-card p-4">
                    <div className="text-xs text-text-muted mb-1">Document</div>
                    <div className="font-mono text-sm text-text-primary">
                      {exception.data.invoice_id as string}
                      {exception.data.invoice_number && (
                        <span className="text-text-muted ml-2">({exception.data.invoice_number as string})</span>
                      )}
                    </div>
                    {(exception.data.vendor_name || exception.data.customer_name) && (
                      <div className="text-sm text-text-secondary mt-1">
                        {(exception.data.vendor_name || exception.data.customer_name) as string}
                      </div>
                    )}
                    {exception.data.amount && (
                      <div className="text-lg font-bold text-text-primary mt-2">
                        {inr(exception.data.amount as number)}
                      </div>
                    )}
                    {onViewInvoice && (
                      <button
                        onClick={() => {
                          const id = (exception.data.invoice_number || exception.data.invoice_id) as string;
                          onViewInvoice(id);
                        }}
                        className="mt-3 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-db-blue/10 border border-db-blue/25 text-db-blue text-xs font-medium hover:bg-db-blue/20 transition w-full justify-center"
                      >
                        <FileText size={12} />
                        View Source Invoice
                      </button>
                    )}
                  </div>
                )}

                {/* Rule that fired */}
                <div className="glass-card p-4 border-l-2 border-db-red">
                  <div className="text-xs text-text-muted mb-1">DLT Expectation / Rule</div>
                  <div className="font-mono text-sm text-db-red">
                    {exception.data.rule as string}
                  </div>
                </div>

                {/* Reason */}
                <div className="glass-card p-4">
                  <div className="text-xs text-text-muted mb-1">What Failed</div>
                  <div className="text-sm text-text-primary leading-relaxed">
                    {exception.data.reason as string}
                  </div>
                </div>

                {/* Resolution */}
                <div className="glass-card p-4 border-l-2 border-db-blue">
                  <div className="flex items-center gap-1 text-xs text-text-muted mb-1">
                    <Info className="w-3 h-3" />
                    Recommended Action
                  </div>
                  <div className="text-sm text-text-primary leading-relaxed">
                    {exception.data.resolution as string}
                  </div>
                </div>

                {/* JE specific details */}
                {exception.data.je_number && (
                  <div className="glass-card p-4">
                    <div className="text-xs text-text-muted mb-2">Journal Entry Details</div>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <span className="text-text-muted">JE#:</span>{" "}
                        <span className="font-mono">{exception.data.je_number as string}</span>
                      </div>
                      <div>
                        <span className="text-text-muted">Posted by:</span>{" "}
                        {exception.data.posted_by as string}
                      </div>
                      <div>
                        <span className="text-text-muted">Debit:</span>{" "}
                        <span className="text-db-green">{inr(exception.data.total_debit as number)}</span>
                      </div>
                      <div>
                        <span className="text-text-muted">Credit:</span>{" "}
                        <span className="text-db-red">{inr(exception.data.total_credit as number)}</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* SLA Clock placeholder */}
                <div className="glass-card p-4 flex items-center justify-between">
                  <div className="text-xs text-text-muted">SLA Resolution Target</div>
                  <div className="text-sm font-mono text-db-amber">
                    {exception.data.severity === "critical" ? "4 hours" : "24 hours"}
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
