import { motion } from "framer-motion";
import { CheckCircle2, Sparkles } from "lucide-react";
import type { SSEEvent } from "../hooks/useSSE";

type Props = {
  summary: SSEEvent | null;
};

export default function SummaryCard({ summary }: Props) {
  if (!summary) return null;
  const d = summary.data;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.5 }}
      className="glass-card-glow p-6 border border-db-green/30"
    >
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-full bg-db-green/15">
          <CheckCircle2 className="w-6 h-6 text-db-green" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <h3 className="font-bold text-text-primary">End of Day Summary</h3>
            <Sparkles className="w-4 h-4 text-db-amber" />
          </div>
          <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">
            {d.message as string}
          </p>
        </div>
      </div>
    </motion.div>
  );
}
