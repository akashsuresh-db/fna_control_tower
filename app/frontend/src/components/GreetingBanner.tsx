import { useState } from "react";
import { motion } from "framer-motion";
import { X } from "lucide-react";

type Props = {
  greeting: {
    type: string;
    data: {
      persona?: string;
      role?: string;
      message?: string;
      buckets?: Record<string, number>;
      checklist?: unknown[];
    };
  } | null;
  isStreaming: boolean;
  userName?: string;
};

export default function GreetingBanner({ greeting, isStreaming, userName = "User" }: Props) {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  if (!greeting) {
    return (
      <div className="glass-card p-6 flex items-center gap-4">
        <div className="w-3 h-3 rounded-full bg-db-amber live-pulse" />
        <span className="text-text-secondary">
          {isStreaming ? "Connecting to data pipeline..." : "Click Start to begin processing"}
        </span>
      </div>
    );
  }

  const { role, message } = greeting.data;

  // Build greeting with actual user name
  const displayMessage = `Good morning, ${userName}.\n${message || ""}`;

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card-glow p-6 relative"
    >
      {/* Dismiss button */}
      <button
        onClick={() => setDismissed(true)}
        className="absolute top-3 right-3 p-1 rounded hover:bg-bg-hover text-text-muted hover:text-text-primary transition"
        title="Dismiss"
      >
        <X className="w-4 h-4" />
      </button>

      <div className="flex items-start gap-4">
        <div className="flex-shrink-0 w-10 h-10 rounded-full bg-db-navy flex items-center justify-center text-lg font-bold text-db-blue">
          {userName[0]?.toUpperCase() || "?"}
        </div>
        <div className="flex-1 min-w-0 pr-6">
          <div className="flex items-center gap-2 mb-2">
            <span className="font-semibold text-text-primary">{userName}</span>
            <span className="text-xs text-text-muted px-2 py-0.5 rounded-full bg-bg-card border border-border-subtle">
              {role}
            </span>
            {isStreaming && (
              <span className="flex items-center gap-1 text-xs text-db-green">
                <span className="w-2 h-2 rounded-full bg-db-green live-pulse" />
                LIVE
              </span>
            )}
          </div>
          <pre className="text-sm text-text-secondary whitespace-pre-wrap font-sans leading-relaxed">
            {displayMessage}
          </pre>
        </div>
      </div>
    </motion.div>
  );
}
