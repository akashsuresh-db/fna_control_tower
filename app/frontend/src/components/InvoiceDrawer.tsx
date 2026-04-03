/**
 * InvoiceDrawer — fetches & renders a finance invoice as a PDF.
 *
 * Uses the backend /api/invoice/{id}/pdf endpoint which generates
 * a properly formatted PDF via reportlab. Displays it inline via <iframe>
 * and provides a download button.
 *
 * Used by AIChatPanel (invoice ID clicks in chat) and APTab (exception panel).
 */
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, X, AlertTriangle, CheckCircle, XCircle, Download, Loader2 } from "lucide-react";

// ─── Types ────────────────────────────────────────────────────

export type InvoiceDetail = {
  invoice_id: string;
  invoice_number: string | null;
  quarantine_reason: string | null;
  vendor_id: string;
  vendor_name: string | null;
  po_id: string | null;
  invoice_date: string;
  due_date: string;
  invoice_amount: number;
  po_amount: number;
  status: string | null;
  gstin: string | null;
  payment_terms: string | null;
  raw_text: string;
  file_path: string;
};

// ─── Quarantine Badge ─────────────────────────────────────────

function QuarantineBadge({ reason }: { reason: string | null }) {
  if (!reason)
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
        <CheckCircle size={10} /> MATCHED
      </span>
    );
  const colors: Record<string, string> = {
    AMOUNT_MISMATCH: "bg-amber-500/15 text-amber-400 border-amber-500/20",
    NO_PO_REFERENCE: "bg-red-500/15 text-red-400 border-red-500/20",
    DUPLICATE: "bg-purple-500/15 text-purple-400 border-purple-500/20",
    MISSING_FIELDS: "bg-orange-500/15 text-orange-400 border-orange-500/20",
  };
  const cls = colors[reason] ?? "bg-red-500/15 text-red-400 border-red-500/20";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${cls}`}>
      <AlertTriangle size={10} /> {reason.replace(/_/g, " ")}
    </span>
  );
}

// ─── InvoicePanel (inner content) ─────────────────────────────

function InvoicePanel({
  invoiceId,
  onClose,
}: {
  invoiceId: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<InvoiceDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(true);
  const [pdfError, setPdfError] = useState(false);

  const pdfUrl = `/api/invoice/${encodeURIComponent(invoiceId)}/pdf`;
  const downloadUrl = `${pdfUrl}?download=true`;

  useEffect(() => {
    setLoading(true);
    setError(null);
    setDetail(null);
    setPdfLoading(true);
    setPdfError(false);
    fetch(`/api/invoice/${encodeURIComponent(invoiceId)}`)
      .then((r) => r.json())
      .then((d) => {
        if (d.error) setError(d.error);
        else setDetail(d);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [invoiceId]);

  const fmt = (n: number) =>
    n ? `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—";

  return (
    <div className="flex flex-col h-full bg-bg-card">
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle flex-shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <FileText size={15} className="text-db-blue flex-shrink-0" />
          <span className="text-sm font-semibold text-text-primary truncate">{invoiceId}</span>
          {detail && <QuarantineBadge reason={detail.quarantine_reason} />}
        </div>
        <div className="flex items-center gap-1 flex-shrink-0 ml-2">
          {/* Download button */}
          <a
            href={downloadUrl}
            download={`invoice-${invoiceId}.pdf`}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-db-blue/10 border border-db-blue/25 text-db-blue text-xs font-medium hover:bg-db-blue/20 transition"
            title="Download PDF"
          >
            <Download size={12} />
            <span className="hidden sm:inline">Download</span>
          </a>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-bg-hover text-text-muted hover:text-text-primary transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* ── Body ── */}
      <div className="flex flex-col flex-1 min-h-0">
        {/* Loading / error for metadata fetch */}
        {loading && (
          <div className="flex items-center justify-center py-6 text-text-muted text-sm gap-2">
            <Loader2 size={14} className="animate-spin" />
            Loading invoice…
          </div>
        )}
        {error && (
          <div className="m-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex items-start gap-2">
            <XCircle size={13} className="flex-shrink-0 mt-0.5" />
            {error}
          </div>
        )}

        {detail && (
          <>
            {/* ── Compact ERP metadata strip ── */}
            <div className="px-4 py-2.5 border-b border-border-subtle/50 flex-shrink-0">
              <div className="grid grid-cols-3 gap-x-4 gap-y-1 text-[11px]">
                {[
                  ["Vendor", detail.vendor_name ?? detail.vendor_id],
                  ["Invoice #", detail.invoice_number ?? detail.invoice_id],
                  ["Status", detail.status ?? "—"],
                  ["Invoice Amt", fmt(detail.invoice_amount)],
                  ["PO Amt", fmt(detail.po_amount)],
                  ["Due Date", detail.due_date || "—"],
                ].map(([label, val]) => (
                  <div key={label}>
                    <div className="text-text-muted text-[9px] uppercase tracking-wide">{label}</div>
                    <div className="text-text-primary font-medium truncate">{val}</div>
                  </div>
                ))}
              </div>

              {/* Amount mismatch callout */}
              {detail.quarantine_reason === "AMOUNT_MISMATCH" && detail.po_amount > 0 && (
                <div className="mt-2 px-2 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-[10px]">
                  <strong>Mismatch:</strong> Invoice {fmt(detail.invoice_amount)} vs PO {fmt(detail.po_amount)} —
                  diff {fmt(Math.abs(detail.invoice_amount - detail.po_amount))}{" "}
                  ({((Math.abs(detail.invoice_amount - detail.po_amount) / detail.po_amount) * 100).toFixed(1)}%)
                </div>
              )}
            </div>

            {/* ── PDF viewer ── */}
            <div className="flex-1 relative min-h-0">
              {/* PDF loading spinner overlay */}
              {pdfLoading && !pdfError && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-bg-card z-10">
                  <Loader2 size={20} className="animate-spin text-db-blue" />
                  <span className="text-xs text-text-muted">Generating PDF…</span>
                </div>
              )}

              {/* PDF error fallback */}
              {pdfError && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-bg-card z-10">
                  <XCircle size={20} className="text-red-400" />
                  <span className="text-xs text-text-muted text-center px-4">
                    Could not render PDF.{" "}
                    <a href={downloadUrl} className="text-db-blue underline" download>
                      Download instead
                    </a>
                  </span>
                </div>
              )}

              <iframe
                key={invoiceId}
                src={pdfUrl}
                title={`Invoice ${invoiceId}`}
                className="w-full h-full border-0"
                style={{ minHeight: "100%", background: "#f3f4f6" }}
                onLoad={() => setPdfLoading(false)}
                onError={() => { setPdfLoading(false); setPdfError(true); }}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Exported Overlay Drawer ──────────────────────────────────

/**
 * Full-viewport fixed overlay drawer.
 * Renders as: dark backdrop + slide-in panel from right edge.
 */
export default function InvoiceDrawer({
  invoiceId,
  onClose,
}: {
  invoiceId: string | null;
  onClose: () => void;
}) {
  return (
    <AnimatePresence>
      {invoiceId && (
        <>
          <motion.div
            key="invoice-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 bg-black/40 z-40"
            onClick={onClose}
          />
          <motion.div
            key="invoice-drawer"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.25, ease: "easeInOut" }}
            className="fixed top-0 right-0 bottom-0 w-[580px] max-w-full z-50 shadow-2xl"
          >
            <InvoicePanel invoiceId={invoiceId} onClose={onClose} />
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
