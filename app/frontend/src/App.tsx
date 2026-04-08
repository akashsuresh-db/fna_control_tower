import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  FileText, Users, BookOpen, PanelRightOpen, PanelRightClose,
  Database, Zap
} from "lucide-react";
import APTab from "./components/APTab";
import ARTab from "./components/ARTab";
import GLTab from "./components/GLTab";
import AIChatPanel from "./components/AIChatPanel";

const TABS = [
  { id: "AP Operations", icon: FileText, label: "AP Operations", sub: "Procure to Pay" },
  { id: "AR Operations", icon: Users, label: "AR Operations", sub: "Order to Cash" },
  { id: "GL Operations", icon: BookOpen, label: "GL Operations", sub: "Record to Report" },
];

type UserInfo = { name: string; email: string; username: string };

export default function App() {
  const [activeTab, setActiveTab] = useState("AP Operations");
  const [chatOpen, setChatOpen] = useState(true);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [notification, setNotification] = useState<string | null>(null);

  // Fetch user identity on mount
  useEffect(() => {
    fetch("/api/me")
      .then((r) => r.json())
      .then((data) => setUser(data))
      .catch(() => setUser({ name: "User", email: "", username: "" }));
  }, []);

  // Auto-dismiss notification after 4 seconds
  useEffect(() => {
    if (notification) {
      const timer = setTimeout(() => setNotification(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [notification]);

  const userName = user?.name || "User";

  return (
    <div className="flex flex-col h-screen bg-bg-primary">
      {/* Top Bar */}
      <header className="flex items-center justify-between px-4 py-2 border-b border-border-subtle bg-bg-panel/80 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          {/* Databricks logo area */}
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-db-red flex items-center justify-center">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="text-sm font-bold text-text-primary tracking-tight">Finance Operations</div>
              <div className="text-[10px] text-text-muted flex items-center gap-1">
                <Database className="w-2.5 h-2.5" />
                Powered by Databricks Lakehouse
              </div>
            </div>
          </div>
        </div>

        {/* Tab buttons */}
        <nav className="flex gap-1">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition ${
                  active
                    ? "text-text-primary bg-bg-card"
                    : "text-text-muted hover:text-text-secondary hover:bg-bg-hover"
                }`}
              >
                <Icon className="w-4 h-4" />
                <span className="hidden md:inline">{tab.label}</span>
                <span className="hidden lg:inline text-[10px] text-text-muted font-normal">
                  {tab.sub}
                </span>
                {active && (
                  <motion.div
                    layoutId="activeTab"
                    className="absolute bottom-0 left-2 right-2 h-0.5 bg-db-blue rounded-full"
                  />
                )}
              </button>
            );
          })}
        </nav>

        {/* Right section: user avatar + chat toggle */}
        <div className="flex items-center gap-3">
          {/* User identity */}
          {user && (
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-db-blue/20 border border-db-blue/30 flex items-center justify-center text-xs font-bold text-db-blue">
                {userName[0]?.toUpperCase()}
              </div>
              <span className="text-xs text-text-secondary hidden sm:inline">{userName}</span>
            </div>
          )}

          {/* Chat toggle */}
          <button
            onClick={() => setChatOpen(!chatOpen)}
            className="p-2 rounded-lg bg-bg-card border border-border-subtle text-text-muted hover:text-text-primary transition"
            title={chatOpen ? "Close AI Panel" : "Open AI Panel"}
          >
            {chatOpen ? <PanelRightClose className="w-4 h-4" /> : <PanelRightOpen className="w-4 h-4" />}
          </button>
        </div>
      </header>

      {/* Notification toast (auto-dismisses after 4s) */}
      {notification && (
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -20 }}
          className="absolute top-14 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-lg bg-db-green/15 border border-db-green/30 text-sm text-db-green shadow-lg"
        >
          {notification}
        </motion.div>
      )}

      {/* Content */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Main panel — all tabs stay mounted so pipeline state is preserved when switching */}
        <main className="flex-1 overflow-y-auto p-4">
          <div style={{ display: activeTab === "AP Operations" ? "contents" : "none" }}>
            <APTab userName={userName} onNotify={setNotification} />
          </div>
          <div style={{ display: activeTab === "AR Operations" ? "contents" : "none" }}>
            <ARTab userName={userName} onNotify={setNotification} />
          </div>
          <div style={{ display: activeTab === "GL Operations" ? "contents" : "none" }}>
            <GLTab userName={userName} />
          </div>
        </main>

        {/* AI Chat sidebar */}
        {chatOpen && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 380, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            className="flex-shrink-0 overflow-hidden"
            style={{ width: 380 }}
          >
            <AIChatPanel activeTab={activeTab} userName={userName} />
          </motion.aside>
        )}
      </div>
    </div>
  );
}
