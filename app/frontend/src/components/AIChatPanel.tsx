import { useState, useRef, useEffect, useCallback } from "react";
import { flushSync } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send, Bot, User, ChevronDown, ChevronRight,
  Database, Sparkles, Table2, GitBranch,
  History, Plus, Clock, MessageSquare, X,
  FileText,
} from "lucide-react";
import { inr } from "../utils";
import InvoiceDrawer from "./InvoiceDrawer";

// ─── Types ───────────────────────────────────────────────────

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  routing?: { domain: string; explanation: string; tool?: string; fallback?: boolean };
  sql?: string;
  data?: { columns: string[]; rows: Record<string, string>[] };
  error?: string;
  loading?: boolean;
  streaming?: boolean;
  agent?: string;
  asked_at?: string;
};

type SessionCard = {
  session_id: string;
  first_question: string;
  tab: string;
  started_at: string;
  last_active: string;
  message_count: number;
};

type Props = {
  activeTab: string;
  userName?: string;
};

// ─── Constants ───────────────────────────────────────────────

const DOMAIN_LABELS: Record<string, string> = {
  P2P: "Procure-to-Pay",
  O2C: "Order-to-Cash",
  R2R: "Record-to-Report",
  GENERAL: "Cross-Process",
  FULL: "Cross-Process",
};

const DOMAIN_COLORS: Record<string, string> = {
  P2P: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  O2C: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  R2R: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  GENERAL: "bg-purple-500/15 text-purple-400 border-purple-500/30",
  FULL: "bg-purple-500/15 text-purple-400 border-purple-500/30",
};

const TAB_COLORS: Record<string, string> = {
  "AP Operations": "bg-blue-500/15 text-blue-400",
  "AR Operations": "bg-emerald-500/15 text-emerald-400",
  "GL Operations": "bg-amber-500/15 text-amber-400",
};

const AGENT_LABELS: Record<string, string> = {
  call_p2p_agent: "P2P Agent",
  call_o2c_agent: "O2C Agent",
  call_r2r_agent: "R2R Agent",
  call_full_agent: "Finance Agent",
  "mas-6f799597-endpoint": "Finance Agent",
};

function agentLabel(agent?: string, tool?: string): string {
  if (agent && AGENT_LABELS[agent]) return AGENT_LABELS[agent];
  if (tool && AGENT_LABELS[tool]) return AGENT_LABELS[tool];
  if (agent?.startsWith("mas-")) return "Finance Agent";
  return "Finance Agent";
}

const SUGGESTIONS: Record<string, string[]> = {
  P2P: [
    "Which invoices are at risk of late payment this week?",
    "Show vendors with lowest match compliance",
    "What is the total amount in 3-way matched invoices?",
  ],
  O2C: [
    "Which customers have the highest overdue amounts?",
    "What is our current DSO?",
    "Show customers with overdue amounts above 1 crore",
  ],
  R2R: [
    "Are there any unreconciled accounts in the trial balance?",
    "Show journal entries above 50 lakhs",
    "What is the expense breakdown by department?",
  ],
};

// ─── Markdown renderer ───────────────────────────────────────
// Line-by-line state machine — handles mixed content in a single pass:
//   ## / ### headings, numbered items with sub-bullets, bullet lists,
//   markdown tables, bold/italic/code inline, plain paragraphs.

function parseMdTable(lines: string[]): { headers: string[]; rows: string[][] } | null {
  const isRow = (l: string) => l.trim().startsWith("|") && l.trim().endsWith("|");
  const isSep = (l: string) => /^\|[\s\-|:]+\|$/.test(l.trim());
  if (!isRow(lines[0])) return null;
  const cells = (l: string) => l.trim().slice(1, -1).split("|").map((c) => c.trim());
  const headers = cells(lines[0]);
  const start = lines.length > 1 && isSep(lines[1]) ? 2 : 1;
  const rows = lines.slice(start).filter(isRow).map(cells);
  return rows.length ? { headers, rows } : null;
}

function MdTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border-subtle my-2">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-bg-hover">
            {headers.map((h, i) => (
              <th key={i} className="px-3 py-2 text-left font-semibold text-text-muted uppercase tracking-wide whitespace-nowrap border-b border-border-subtle">
                {renderInline(h)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} className={`border-b border-border-subtle/40 ${ri % 2 === 0 ? "" : "bg-bg-card/30"}`}>
              {headers.map((_, ci) => (
                <td key={ci} className="px-3 py-2 text-text-secondary">
                  {renderInline(row[ci] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MarkdownText({ text }: { text: string }) {
  if (!text) return null;

  const lines = text.split("\n");
  const els: React.ReactNode[] = [];
  let i = 0;
  let k = 0;

  const isTable  = (l: string) => l.trim().startsWith("|") && l.trim().endsWith("|");
  const isHead   = (l: string) => /^#{1,4}\s/.test(l.trim());
  const isBullet = (l: string) => /^[-*•]\s/.test(l.trim());
  const isNum    = (l: string) => /^\d+[.)]\s/.test(l.trim());
  const isBreak  = (l: string) => !l.trim() || isTable(l) || isHead(l.trim().replace(/^\*+/, "").replace(/\*+$/, "")) || isBullet(l) || isNum(l);

  while (i < lines.length) {
    const raw  = lines[i];
    const trim = raw.trim();

    // blank line
    if (!trim) { i++; continue; }

    // ── Table block ──────────────────────────────────────────────
    if (isTable(raw)) {
      const tLines: string[] = [];
      while (i < lines.length && (isTable(lines[i]) || /^\|[\s\-|:]+\|$/.test(lines[i].trim()))) {
        if (lines[i].trim()) tLines.push(lines[i]);
        i++;
      }
      const parsed = parseMdTable(tLines);
      if (parsed) els.push(<MdTable key={k++} headers={parsed.headers} rows={parsed.rows} />);
      continue;
    }

    // ── Heading ──────────────────────────────────────────────────
    // Also handles bold-wrapped headings like **## Foo:** that agents sometimes emit
    const normForHead = trim.replace(/^\*+/, "").replace(/\*+$/, "");
    if (isHead(normForHead)) {
      const level = normForHead.match(/^(#+)/)?.[1].length ?? 2;
      const txt   = normForHead.replace(/^#+\s+/, "");
      els.push(
        <p key={k++} className={
          level === 1 ? "font-bold text-text-primary text-sm mt-3 mb-0.5"
          : level === 2 ? "font-semibold text-text-primary text-sm mt-2 mb-0.5 border-b border-border-subtle/40 pb-0.5"
          : "font-medium text-text-muted text-xs uppercase tracking-wide mt-1.5"
        }>
          {renderInline(txt)}
        </p>
      );
      i++;
      continue;
    }

    // ── Numbered item (+ optional sub-bullets) ───────────────────
    if (isNum(trim)) {
      const num  = trim.match(/^(\d+)/)?.[1] ?? String(els.length + 1);
      const body = trim.replace(/^\d+[.)]\s+/, "");
      i++;
      const subs: string[] = [];
      while (i < lines.length && isBullet(lines[i]) && lines[i].trim()) {
        subs.push(lines[i].trim().replace(/^[-*•]\s+/, ""));
        i++;
      }
      els.push(
        <div key={k++} className="flex gap-2.5 items-start">
          <span className="flex-shrink-0 w-5 h-5 rounded-full bg-bg-hover text-text-muted text-[10px] flex items-center justify-center font-semibold mt-0.5">
            {num}
          </span>
          <div className="flex-1 min-w-0">
            <span className="text-text-primary leading-snug">{renderInline(body)}</span>
            {subs.length > 0 && (
              <div className="mt-1 space-y-0.5 pl-0.5">
                {subs.map((s, si) => (
                  <div key={si} className="flex gap-1.5 items-start text-text-secondary">
                    <span className="mt-1.5 w-1 h-1 rounded-full bg-text-muted flex-shrink-0 opacity-50" />
                    <span className="text-xs leading-snug">{renderInline(s)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      );
      continue;
    }

    // ── Bullet item ──────────────────────────────────────────────
    if (isBullet(trim)) {
      const body = trim.replace(/^[-*•]\s+/, "");
      els.push(
        <div key={k++} className="flex gap-2 items-start">
          <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-db-blue flex-shrink-0" />
          <span className="text-text-primary leading-snug">{renderInline(body)}</span>
        </div>
      );
      i++;
      continue;
    }

    // ── Plain paragraph ──────────────────────────────────────────
    const plain: string[] = [];
    while (i < lines.length && !isBreak(lines[i])) {
      plain.push(lines[i]);
      i++;
    }
    if (plain.join("").trim()) {
      els.push(
        <p key={k++} className="text-text-primary leading-relaxed">
          {plain.map((l, li) => (
            <span key={li}>
              {li > 0 && l.trim() && <br />}
              {renderInline(l)}
            </span>
          ))}
        </p>
      );
    }
  }

  return <div className="space-y-1 text-sm">{els}</div>;
}

// Global invoice click callback — set by AIChatPanel, used by renderInline
let _onInvoiceClick: ((id: string) => void) | null = null;

/** Render inline markdown: **bold**, *italic*, `code`, and invoice number links */
function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  // Regex: **bold**, *italic*, `code`, INVxxxxxx or VINV-YYYY-NNNNN invoice numbers
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\b(VINV-\d{4}-\d+|INV\d{4,})\b)/g;
  let last = 0;
  let match;
  let key = 0;

  const isInvoiceId = (s: string) =>
    /^INV\d{4,}$/.test(s.trim()) || /^VINV-\d{4}-\d+$/.test(s.trim());

  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }
    if (match[2]) {
      // Bold: if the entire bold content is an invoice ID, render as clickable button
      if (isInvoiceId(match[2])) {
        const id = match[2].trim();
        parts.push(
          <button key={key++} onClick={() => _onInvoiceClick?.(id)}
            className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-db-blue/10 text-db-blue border border-db-blue/25 hover:bg-db-blue/20 hover:border-db-blue/50 transition-colors cursor-pointer"
            title={`View source file for ${id}`}>
            <FileText size={9} className="flex-shrink-0" />{id}
          </button>
        );
      } else {
        parts.push(<strong key={key++} className="font-semibold text-text-primary">{match[2]}</strong>);
      }
    } else if (match[3]) {
      parts.push(<em key={key++} className="italic">{match[3]}</em>);
    } else if (match[4]) {
      parts.push(
        <code key={key++} className="px-1 py-0.5 rounded bg-bg-hover text-db-blue font-mono text-[11px]">
          {match[4]}
        </code>
      );
    } else if (match[5]) {
      const id = match[5];
      parts.push(
        <button
          key={key++}
          onClick={() => _onInvoiceClick?.(id)}
          className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[11px] font-mono font-semibold bg-db-blue/10 text-db-blue border border-db-blue/25 hover:bg-db-blue/20 hover:border-db-blue/50 transition-colors cursor-pointer"
          title={`View source file for ${id}`}
        >
          <FileText size={9} className="flex-shrink-0" />
          {id}
        </button>
      );
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts.length === 1 && typeof parts[0] === "string" ? parts[0] : <>{parts}</>;
}

// ─── Helpers ─────────────────────────────────────────────────

function relativeTime(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  } catch {
    return "";
  }
}

// ─── Main Component ──────────────────────────────────────────

export default function AIChatPanel({ activeTab, userName }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [sessions, setSessions] = useState<SessionCard[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [openInvoiceId, setOpenInvoiceId] = useState<string | null>(null);

  // Wire invoice click handler into renderInline
  _onInvoiceClick = setOpenInvoiceId;

  const sessionId = useRef<string>(crypto.randomUUID());
  const previousResponseId = useRef<string>("");  // Mosaic AI Agent stateful continuity
  const feedRef = useRef<HTMLDivElement>(null);

  const tabKey = activeTab === "AP Operations" ? "P2P"
    : activeTab === "AR Operations" ? "O2C"
    : "R2R";

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [messages]);

  // Auto-restore the most recent session on mount
  useEffect(() => {
    async function init() {
      try {
        const r = await fetch("/api/my-sessions");
        const d = await r.json();
        const list: SessionCard[] = d.sessions || [];
        if (list.length > 0) {
          setSessions(list);
          await resumeSession(list[0]);
        }
      } catch {
        // start fresh on error
      }
    }
    init();
  }, []); // resumeSession is stable (useCallback with [] deps) — safe to omit

  const openHistory = useCallback(async () => {
    setShowHistory(true);
    setLoadingSessions(true);
    try {
      const r = await fetch("/api/my-sessions");
      const d = await r.json();
      setSessions(d.sessions || []);
    } catch {
      setSessions([]);
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  const resumeSession = useCallback(async (card: SessionCard) => {
    setShowHistory(false);
    setIsLoading(true);
    try {
      const r = await fetch(`/api/session/${card.session_id}`);
      const d = await r.json();
      if (d.messages && d.messages.length > 0) {
        const restored: ChatMessage[] = d.messages.map((m: {
          role: string; content: string; sql?: string;
          genie_space?: string; routing_info?: { domain: string; explanation: string; tool?: string };
          asked_at?: string;
        }) => ({
          role: m.role as "user" | "assistant",
          content: m.content || "",
          sql: m.sql || undefined,
          routing: m.routing_info ? {
            domain: m.routing_info.domain || "",
            explanation: m.routing_info.explanation || "Loaded from history",
            tool: m.routing_info.tool,
          } : undefined,
          agent: m.routing_info ? "mas-6f799597-endpoint" : undefined,
          asked_at: m.asked_at,
        }));
        setMessages(restored);
        sessionId.current = card.session_id;
        // Restore agent thread: use stored previous_response_id if available,
        // otherwise fall back to "" so the backend replays Lakebase history on next question
        previousResponseId.current = d.previous_response_id || "";
      }
    } catch {
      sessionId.current = card.session_id;
      previousResponseId.current = "";
    } finally {
      setIsLoading(false);
    }
  }, []);

  const newSession = useCallback(() => {
    sessionId.current = crypto.randomUUID();
    previousResponseId.current = "";
    setMessages([]);
    setShowHistory(false);
  }, []);

  async function sendMessage(text: string) {
    if (!text.trim() || isLoading) return;
    setMessages((prev) => [
      ...prev,
      { role: "user", content: text },
      { role: "assistant", content: "", loading: true },
    ]);
    setInput("");
    setIsLoading(true);

    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: text,
          active_tab: tabKey,
          session_id: sessionId.current,
          previous_response_id: previousResponseId.current,
        }),
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let sseBuffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        sseBuffer += decoder.decode(value, { stream: true });

        // SSE messages are separated by double newlines
        const parts = sseBuffer.split("\n\n");
        sseBuffer = parts.pop() ?? "";

        for (const part of parts) {
          for (const line of part.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            let data: Record<string, unknown>;
            try {
              data = JSON.parse(line.slice(6));
            } catch {
              continue;
            }

            if (data.type === "chunk") {
              // flushSync bypasses React 18 batching so each token renders immediately
              flushSync(() => {
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  if (last?.role !== "assistant") return prev;
                  return [
                    ...prev.slice(0, -1),
                    { ...last, loading: false, streaming: true, content: last.content + (data.text as string) },
                  ];
                });
              });
            } else if (data.type === "done") {
              if (data.session_id) sessionId.current = data.session_id as string;
              if (data.previous_response_id) previousResponseId.current = data.previous_response_id as string;
              flushSync(() => {
                setMessages((prev) => {
                  const last = prev[prev.length - 1];
                  if (last?.role !== "assistant") return prev;
                  return [
                    ...prev.slice(0, -1),
                    {
                      ...last,
                      loading: false,
                      streaming: false,
                      routing: data.routing as ChatMessage["routing"],
                      agent: data.agent as string,
                    },
                  ];
                });
              });
            } else if (data.type === "error") {
              throw new Error(data.message as string);
            }
          }
        }
      }
    } catch (e) {
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last?.role === "assistant") {
          return [
            ...prev.slice(0, -1),
            { ...last, loading: false, streaming: false, content: `Error: ${(e as Error).message}`, error: (e as Error).message },
          ];
        }
        return [...prev, { role: "assistant", content: `Error: ${(e as Error).message}`, error: (e as Error).message }];
      });
    } finally {
      setIsLoading(false);
    }
  }

  const msgCount = messages.filter((m) => !m.loading).length;
  const userCount = messages.filter((m) => m.role === "user" && !m.loading).length;

  return (
    <div className="flex h-full bg-bg-panel border-l border-border-subtle relative">

      {/* Main chat column — always full width; drawer overlays as fixed panel */}
      <div className="flex flex-col w-full">

      {/* Header */}
      <div className="px-4 py-3 border-b border-border-subtle flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-[#003159]">
              <Sparkles className="w-4 h-4 text-blue-400" />
            </div>
            <div>
              <div className="text-sm font-semibold text-text-primary">Finance AI</div>
              <div className="flex items-center gap-1.5 text-[10px] text-text-muted mt-0.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span>Multi-Agent Supervisor</span>
                <span className="opacity-40">·</span>
                <span>{DOMAIN_LABELS[tabKey]}</span>
                {userCount > 0 && (
                  <>
                    <span className="opacity-40">·</span>
                    <span>{userCount} Q</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-0.5">
            <button
              onClick={newSession}
              title="New session"
              className="p-1.5 rounded-lg hover:bg-bg-hover transition text-text-muted hover:text-text-primary"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={openHistory}
              title="Session history"
              className={`p-1.5 rounded-lg transition ${showHistory ? "bg-bg-hover text-text-primary" : "hover:bg-bg-hover text-text-muted hover:text-text-primary"}`}
            >
              <History className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Messages feed */}
      <div ref={feedRef} className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="space-y-4">
            <div className="text-center py-6">
              <div className="w-10 h-10 rounded-xl bg-[#003159] flex items-center justify-center mx-auto mb-3">
                <Sparkles className="w-5 h-5 text-blue-400" />
              </div>
              <p className="text-xs font-medium text-text-primary mb-1">Finance AI Assistant</p>
              <p className="text-[11px] text-text-muted">
                Ask questions in plain English. Routes to the right agent automatically.
              </p>
            </div>
            <div className="space-y-1.5">
              {SUGGESTIONS[tabKey]?.map((s, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(s)}
                  className="w-full text-left text-xs p-3 rounded-xl bg-bg-card border border-border-subtle hover:bg-bg-hover hover:border-border-glow transition text-text-secondary group"
                >
                  <span className="group-hover:text-text-primary transition">{s}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <AnimatePresence initial={false}>
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.15 }}
              className={`flex gap-2.5 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {/* Avatar — assistant only, left side */}
              {msg.role === "assistant" && (
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-[#003159] border border-blue-500/20 flex items-center justify-center mt-0.5">
                  <Bot className="w-3.5 h-3.5 text-blue-400" />
                </div>
              )}

              <div className={`flex flex-col gap-1.5 ${msg.role === "user" ? "items-end max-w-[82%]" : "items-start max-w-[90%]"}`}>

                {/* User message bubble */}
                {msg.role === "user" && (
                  <div className="px-3.5 py-2.5 rounded-2xl rounded-tr-sm bg-blue-600/90 text-white text-sm leading-relaxed">
                    {msg.content}
                  </div>
                )}

                {/* Assistant: loading */}
                {msg.role === "assistant" && msg.loading && (
                  <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-bg-card border border-border-subtle">
                    <div className="flex gap-1.5 items-center h-4">
                      {[0, 1, 2].map((n) => (
                        <span
                          key={n}
                          className="w-1.5 h-1.5 rounded-full bg-text-muted opacity-60"
                          style={{ animation: `bounce 1.2s ${n * 0.2}s infinite` }}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Assistant: response */}
                {msg.role === "assistant" && !msg.loading && (
                  <div className="space-y-2 w-full">

                    {/* Routing chain pill — only shown after streaming completes */}
                    {msg.routing && !msg.streaming && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-bg-card border border-border-subtle text-[10px] text-text-muted">
                          <GitBranch className="w-2.5 h-2.5" />
                          <span>Supervisor</span>
                        </div>
                        <span className="text-text-muted text-[10px]">→</span>
                        <div className={`flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-medium ${DOMAIN_COLORS[msg.routing.domain] || DOMAIN_COLORS.FULL}`}>
                          {agentLabel(msg.agent, msg.routing.tool)}
                        </div>
                        <span className="text-text-muted text-[10px]">→</span>
                        <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-bg-card border border-border-subtle text-[10px] text-text-muted">
                          <Database className="w-2.5 h-2.5" />
                          <span>Genie</span>
                        </div>
                        {msg.routing.fallback && (
                          <span className="text-[10px] text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded-full">fallback</span>
                        )}
                      </div>
                    )}

                    {/* Answer bubble */}
                    <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-bg-card border border-border-subtle">
                      {msg.error && !msg.content ? (
                        <p className="text-xs text-red-400">{msg.error}</p>
                      ) : msg.streaming ? (
                        // While streaming: plain text + blinking cursor (no markdown parsing on partial content)
                        <span className="text-sm text-text-primary leading-relaxed whitespace-pre-wrap">
                          {msg.content}<span className="inline-block w-0.5 h-[1em] bg-text-primary ml-0.5 align-middle animate-pulse" />
                        </span>
                      ) : (
                        <MarkdownText text={msg.content} />
                      )}
                    </div>

                    {/* Routing details (collapsible) — only shown after streaming completes */}
                    {msg.routing && !msg.streaming && <RoutingBlock routing={msg.routing} agent={msg.agent} />}

                    {/* SQL — only shown after streaming completes */}
                    {msg.sql && !msg.streaming && <SQLBlock sql={msg.sql} />}

                    {/* Data table — only shown after streaming completes */}
                    {msg.data && msg.data.columns && msg.data.rows?.length > 0 && !msg.streaming && (
                      <DataTable columns={msg.data.columns} rows={msg.data.rows} />
                    )}
                  </div>
                )}
              </div>

              {/* User avatar — right side */}
              {msg.role === "user" && (
                <div className="flex-shrink-0 w-7 h-7 rounded-full bg-bg-card border border-border-subtle flex items-center justify-center mt-0.5">
                  {userName ? (
                    <span className="text-[10px] font-semibold text-text-primary">
                      {userName.charAt(0).toUpperCase()}
                    </span>
                  ) : (
                    <User className="w-3.5 h-3.5 text-text-muted" />
                  )}
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Input bar */}
      <div className="p-3 border-t border-border-subtle flex-shrink-0">
        <form
          onSubmit={(e) => { e.preventDefault(); sendMessage(input); }}
          className="flex gap-2 items-end"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your finance data…"
            disabled={isLoading}
            className="flex-1 px-3.5 py-2.5 rounded-xl bg-bg-card border border-border-subtle text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-blue-500/60 transition disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="p-2.5 rounded-xl bg-blue-600 text-white disabled:opacity-40 hover:bg-blue-500 active:scale-95 transition"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>

      {/* Session History Drawer */}
      <AnimatePresence>
        {showHistory && (
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.2 }}
            className="absolute inset-0 bg-bg-panel flex flex-col z-10"
          >
            <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between flex-shrink-0">
              <div className="flex items-center gap-2">
                <History className="w-4 h-4 text-text-muted" />
                <span className="text-sm font-semibold text-text-primary">Chat History</span>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={newSession}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-blue-600/10 text-blue-400 text-xs font-medium hover:bg-blue-600/20 transition"
                >
                  <Plus className="w-3 h-3" />
                  New session
                </button>
                <button
                  onClick={() => setShowHistory(false)}
                  className="p-1.5 rounded-lg hover:bg-bg-hover transition text-text-muted"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {loadingSessions ? (
                <div className="flex items-center justify-center py-12 text-text-muted text-xs gap-2">
                  <div className="w-3 h-3 rounded-full border-2 border-text-muted border-t-transparent animate-spin" />
                  Loading sessions…
                </div>
              ) : sessions.length === 0 ? (
                <div className="text-center py-12">
                  <MessageSquare className="w-8 h-8 text-text-muted mx-auto mb-3 opacity-40" />
                  <p className="text-sm text-text-muted">No past sessions yet</p>
                  <p className="text-xs text-text-muted opacity-60 mt-1">Start a conversation to build history</p>
                </div>
              ) : (
                sessions.map((s) => {
                  const isCurrent = s.session_id === sessionId.current;
                  return (
                    <button
                      key={s.session_id}
                      onClick={() => resumeSession(s)}
                      className={`w-full text-left p-3.5 rounded-xl border transition ${
                        isCurrent
                          ? "border-blue-500/40 bg-blue-500/5"
                          : "border-border-subtle bg-bg-card hover:bg-bg-hover hover:border-border-glow"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                          TAB_COLORS[s.tab] || "bg-bg-hover text-text-muted"
                        }`}>
                          {s.tab === "AP Operations" ? "P2P"
                            : s.tab === "AR Operations" ? "O2C"
                            : s.tab === "GL Operations" ? "R2R"
                            : s.tab}
                        </span>
                        <div className="flex items-center gap-1 text-[10px] text-text-muted">
                          <Clock className="w-2.5 h-2.5" />
                          {relativeTime(s.last_active)}
                          {isCurrent && <span className="ml-1 text-blue-400 font-medium">· current</span>}
                        </div>
                      </div>
                      <p className="text-xs text-text-primary line-clamp-2 leading-relaxed mb-2">
                        {s.first_question}
                      </p>
                      <div className="flex items-center gap-1 text-[10px] text-text-muted">
                        <MessageSquare className="w-2.5 h-2.5" />
                        {s.message_count} message{s.message_count !== 1 ? "s" : ""}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <style>{`
        @keyframes bounce {
          0%, 60%, 100% { transform: translateY(0); }
          30% { transform: translateY(-4px); }
        }
      `}</style>
      </div>{/* end main chat column */}

      {/* Invoice Drawer — fixed overlay */}
      <InvoiceDrawer invoiceId={openInvoiceId} onClose={() => setOpenInvoiceId(null)} />
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────

function RoutingBlock({
  routing,
  agent,
}: {
  routing: { domain: string; explanation: string; tool?: string; fallback?: boolean };
  agent?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-border-subtle overflow-hidden text-xs">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-1.5 px-3 py-2 bg-bg-card hover:bg-bg-hover transition text-text-muted"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <GitBranch className="w-3 h-3" />
        <span>Routing details</span>
      </button>
      {open && (
        <div className="px-3 py-2.5 bg-bg-primary text-text-secondary space-y-1.5 border-t border-border-subtle">
          <div className="flex gap-2">
            <span className="text-text-muted w-16 flex-shrink-0">Tool</span>
            <code className="text-blue-400 font-mono text-[11px]">{agent || routing.tool || "—"}</code>
          </div>
          <div className="flex gap-2">
            <span className="text-text-muted w-16 flex-shrink-0">Domain</span>
            <span>{DOMAIN_LABELS[routing.domain] || routing.domain}</span>
          </div>
          <div className="flex gap-2">
            <span className="text-text-muted w-16 flex-shrink-0">Reason</span>
            <span className="text-text-secondary">{routing.explanation}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function SQLBlock({ sql }: { sql: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-border-subtle overflow-hidden text-xs">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-1.5 px-3 py-2 bg-bg-card hover:bg-bg-hover transition text-text-muted"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <Database className="w-3 h-3" />
        <span>Generated SQL</span>
      </button>
      {open && (
        <pre className="px-3 py-3 bg-bg-primary text-[11px] text-blue-300 overflow-x-auto font-mono leading-relaxed border-t border-border-subtle">
          {sql}
        </pre>
      )}
    </div>
  );
}

function DataTable({ columns, rows }: { columns: string[]; rows: Record<string, string>[] }) {
  return (
    <div className="rounded-xl border border-border-subtle overflow-hidden text-xs">
      <div className="flex items-center gap-1.5 px-3 py-2 bg-bg-card text-text-muted border-b border-border-subtle">
        <Table2 className="w-3 h-3" />
        <span>{rows.length} row{rows.length !== 1 ? "s" : ""}</span>
      </div>
      <div className="overflow-x-auto max-h-[220px] overflow-y-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-bg-panel">
            <tr>
              {columns.map((col) => (
                <th key={col} className="text-left px-3 py-2 text-[10px] font-semibold text-text-muted uppercase tracking-wide whitespace-nowrap border-b border-border-subtle">
                  {col.replace(/_/g, " ")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={ri} className={`border-b border-border-subtle/40 ${ri % 2 === 0 ? "" : "bg-bg-card/30"}`}>
                {columns.map((col) => (
                  <td key={col} className="px-3 py-2 text-text-secondary whitespace-nowrap">
                    {formatCell(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatCell(val: string | null | undefined): string {
  if (val == null) return "—";
  const num = parseFloat(val);
  if (!isNaN(num) && num > 10000) return inr(num);
  return val;
}
