/** Format INR currency. */
export function formatINR(value: number | string | null | undefined): string {
  if (value == null) return "---";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "---";
  if (Math.abs(num) >= 1_00_00_000) {
    return `${(num / 1_00_00_000).toFixed(2)} Cr`;
  }
  if (Math.abs(num) >= 1_00_000) {
    return `${(num / 1_00_000).toFixed(2)} L`;
  }
  return num.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

/** Format INR with rupee sign. */
export function inr(value: number | string | null | undefined): string {
  const formatted = formatINR(value);
  if (formatted === "---") return formatted;
  return `\u20B9${formatted}`;
}

/** Format number with commas. */
export function formatNum(value: number | string | null | undefined): string {
  if (value == null) return "0";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "0";
  return num.toLocaleString("en-IN");
}

/** Status color mapping. */
export function matchStatusColor(status: string): string {
  switch (status) {
    case "THREE_WAY_MATCHED": return "text-db-green";
    case "TWO_WAY_MATCHED": return "text-db-blue";
    case "AMOUNT_MISMATCH": return "text-db-red";
    case "NO_PO_REFERENCE": return "text-db-amber";
    default: return "text-text-secondary";
  }
}

export function matchStatusBg(status: string): string {
  switch (status) {
    case "THREE_WAY_MATCHED": return "bg-db-green/15 border-db-green/30";
    case "TWO_WAY_MATCHED": return "bg-db-blue/15 border-db-blue/30";
    case "AMOUNT_MISMATCH": return "bg-db-red/15 border-db-red/30";
    case "NO_PO_REFERENCE": return "bg-db-amber/15 border-db-amber/30";
    default: return "bg-bg-card border-border-subtle";
  }
}

export function matchStatusLabel(status: string): string {
  switch (status) {
    case "THREE_WAY_MATCHED": return "3-Way Matched";
    case "TWO_WAY_MATCHED": return "2-Way Matched";
    case "AMOUNT_MISMATCH": return "Amount Mismatch";
    case "NO_PO_REFERENCE": return "No PO Reference";
    default: return status;
  }
}

export function severityColor(severity: string): string {
  switch (severity) {
    case "critical": return "border-db-red bg-db-red/10";
    case "high": return "border-db-amber bg-db-amber/10";
    case "medium": return "border-db-blue bg-db-blue/10";
    default: return "border-border-subtle bg-bg-card";
  }
}

export function severityBadge(severity: string): string {
  switch (severity) {
    case "critical": return "bg-db-red/20 text-db-red";
    case "high": return "bg-db-amber/20 text-db-amber";
    case "medium": return "bg-db-blue/20 text-db-blue";
    default: return "bg-bg-card text-text-secondary";
  }
}

export function agingColor(bucket: string): string {
  if (bucket.includes("0-30")) return "#22C55E";
  if (bucket.includes("31-60")) return "#FF7033";
  if (bucket.includes("61-90")) return "#FF3621";
  if (bucket.includes("90+")) return "#DC2626";
  return "#6B7280";
}
