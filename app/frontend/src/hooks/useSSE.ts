import { useState, useEffect, useCallback, useRef } from "react";

export type SSEEvent = {
  type: string;
  data: Record<string, unknown>;
};

export function useSSE(url: string | null) {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [greeting, setGreeting] = useState<SSEEvent | null>(null);
  const [summary, setSummary] = useState<SSEEvent | null>(null);
  const [exceptions, setExceptions] = useState<SSEEvent[]>([]);
  const [progress, setProgress] = useState<Record<string, unknown> | null>(null);
  const [checklist, setChecklist] = useState<unknown[] | null>(null);
  const [tbUpdate, setTbUpdate] = useState<Record<string, unknown> | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const start = useCallback(() => {
    if (!url) return;
    // Reset state
    setEvents([]);
    setGreeting(null);
    setSummary(null);
    setExceptions([]);
    setProgress(null);
    setChecklist(null);
    setTbUpdate(null);
    setIsStreaming(true);
    setIsComplete(false);

    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const parsed: SSEEvent = JSON.parse(e.data);
        switch (parsed.type) {
          case "greeting":
            setGreeting(parsed);
            break;
          case "summary":
            setSummary(parsed);
            setIsStreaming(false);
            setIsComplete(true);
            es.close();
            break;
          case "quarantine":
          case "exception":
            setExceptions((prev) => [...prev, parsed]);
            setEvents((prev) => [...prev, parsed]);
            break;
          case "progress":
            setProgress(parsed.data);
            break;
          case "checklist_update":
            setChecklist((parsed.data as Record<string, unknown>).checklist as unknown[]);
            break;
          case "tb_update":
            setTbUpdate(parsed.data);
            break;
          default:
            setEvents((prev) => [...prev, parsed]);
            break;
        }
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      setIsStreaming(false);
      es.close();
    };
  }, [url]);

  const stop = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  useEffect(() => {
    return () => {
      if (esRef.current) esRef.current.close();
    };
  }, []);

  return {
    events,
    greeting,
    summary,
    exceptions,
    progress,
    checklist,
    tbUpdate,
    isStreaming,
    isComplete,
    start,
    stop,
  };
}
