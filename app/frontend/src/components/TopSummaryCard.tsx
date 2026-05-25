import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Sparkles, RefreshCw } from "lucide-react";

type Summary = {
  tab: string;
  bullets: string[];
  as_of: string | null;
};

type Props = {
  tab: "P2P" | "O2C" | "R2R";
};

const TAB_TITLE: Record<string, string> = {
  P2P: "Today's AP priorities",
  O2C: "Today's AR priorities",
  R2R: "Today's GL priorities",
};

/**
 * Compact, glance-card summary at the top of each tab.
 * Calls /api/summary/{tab}; renders ≤4 bullets with mild markdown (bold).
 * Refreshes on mount and via the small refresh button.
 */
export default function TopSummaryCard({ tab }: Props) {
  const [data, setData] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch(`/api/summary/${tab}`);
      if (!r.ok) {
        setErr(`HTTP ${r.status}`);
        return;
      }
      const j = (await r.json()) as Summary;
      setData(j);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  // Tiny bold parser: **text** → <strong>text</strong>. Defensive: if the LLM
  // emits an orphan `**` (e.g. "Name**" with no opener), convert it to a bold pair.
  function renderBullet(b: string) {
    let text = b.replace(/^[-•*]\s*/, "");

    // Backend normaliser handles most cases; this is a last-mile safety net.
    const starCount = (text.match(/\*\*/g) || []).length;
    if (starCount % 2 === 1) {
      // Promote `Name**` (capitalised word run followed by closing-only **) to `**Name**`.
      text = text.replace(/([A-Z][\w'.,&-]*(?:\s+[A-Z][\w'.,&-]*)*)\*\*/, "**$1**");
      // If still odd, strip a stray `**` so we don't render literal asterisks.
      if ((text.match(/\*\*/g) || []).length % 2 === 1) {
        text = text.replace("**", "");
      }
    }

    const parts = text.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((p, i) =>
      /^\*\*[^*]+\*\*$/.test(p) ? (
        <strong key={i} className="text-text-primary font-semibold">
          {p.slice(2, -2)}
        </strong>
      ) : (
        <span key={i}>{p}</span>
      )
    );
  }

  const title = TAB_TITLE[tab] || "Today's priorities";

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="relative rounded-xl border border-db-amber/25 bg-gradient-to-br from-bg-card/95 to-bg-card/70 backdrop-blur-sm shadow-sm p-4 overflow-hidden"
    >
      {/* Subtle decorative gradient */}
      <div className="absolute -top-10 -right-10 w-32 h-32 rounded-full bg-db-amber/8 blur-2xl pointer-events-none" />

      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-md bg-db-amber/15">
            <Sparkles className="w-4 h-4 text-db-amber" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-text-primary leading-tight">{title}</h3>
            <p className="text-[10px] text-text-muted leading-tight">
              {loading
                ? "Generating with Claude…"
                : err
                ? `error: ${err}`
                : data?.as_of
                ? "AI summary of live data"
                : ""}
            </p>
          </div>
        </div>
        <button
          onClick={load}
          className="opacity-60 hover:opacity-100 transition p-1 rounded hover:bg-bg-hover"
          aria-label="Refresh summary"
          disabled={loading}
        >
          <RefreshCw className={`w-3.5 h-3.5 text-text-muted ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {data && data.bullets && data.bullets.length > 0 ? (
        <ul className="space-y-1 text-[13px] text-text-secondary leading-snug">
          {data.bullets.slice(0, 4).map((b, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-db-amber/70 select-none">•</span>
              <span className="flex-1">{renderBullet(b)}</span>
            </li>
          ))}
        </ul>
      ) : loading ? (
        <div className="space-y-1.5">
          <div className="h-3 bg-bg-hover/50 rounded animate-pulse" />
          <div className="h-3 bg-bg-hover/50 rounded animate-pulse w-5/6" />
          <div className="h-3 bg-bg-hover/50 rounded animate-pulse w-2/3" />
        </div>
      ) : (
        <p className="text-[13px] text-text-muted italic">
          Summary unavailable — check the warehouse and DLT pipeline.
        </p>
      )}
    </motion.div>
  );
}
