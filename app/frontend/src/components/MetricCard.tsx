import { motion } from "framer-motion";
import type { ReactNode } from "react";

type Props = {
  label: string;
  value: string | number;
  sub?: string;
  icon?: ReactNode;
  color?: string;
  trend?: "up" | "down" | "neutral";
};

export default function MetricCard({ label, value, sub, icon, color = "text-text-primary", trend }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card-glow p-4 flex flex-col gap-1 min-w-0"
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-text-secondary uppercase tracking-wider truncate">
          {label}
        </span>
        {icon && <span className="text-text-muted">{icon}</span>}
      </div>
      <div className={`text-2xl font-bold ${color} tabular-nums`}>{value}</div>
      {sub && (
        <div className="flex items-center gap-1 text-xs text-text-muted">
          {trend === "up" && <span className="text-db-red">&#9650;</span>}
          {trend === "down" && <span className="text-db-green">&#9660;</span>}
          {sub}
        </div>
      )}
    </motion.div>
  );
}
